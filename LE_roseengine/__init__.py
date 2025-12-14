# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import octoprint.filemanager
import octoprint.filemanager.util
import octoprint.util
from octoprint.events import Events
import re
import sys
import os
import time
import subprocess
import threading
import logging
import numpy as np
import math
import shutil
from svgpathtools import *
from itertools import zip_longest
from . import geometric
from . import profiles
import json
import plotly.graph_objects as go
class RoseenginePlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.TemplatePlugin,
):

    def __init__(self):
        self.axis = 'X'
        self.datafolder = None
        self.a_inc = 0.5
        self.running = False
        self.inject = None
        self.recording = False
        #contains all the raw values that can be transformed into working values
        self.rock_main = {}
        self.pump_main = {}
        self.rock_work = []
        self.pump_work = []
        self.working_x = []
        self.working_z = []
        self.working_angles = []
        self.working_mod = []
        self.recorded = []
        self.last_position = None
        self.chunk = 10
        self.buffer = 0
        self.buffer_received = True
        #self.modifiers = {"amp": 1, "phase": 0, "forward": True}
        np.set_printoptions(suppress=True,precision=3)
        self.b_adjust = False
        self.bref = 0.0

        self.jobThread = None
        self.buffer = None
        self.feedcontrol =  {"current": 0, "next": 0}
        self.start_coords = {"x": None, "z": None, "a": None}
        self.ms_threshold = 100
        self.bf_target = 60

        self.rpm = 0.0
        self.updated_rpm = 0.0
        self.rpm_lock = threading.Lock()
        self.phase = 0
        self.r_amp = 1.0
        self.p_amp = 1.0
        self.pump_invert = False
        self.forward = True

        self.auto_reset = False
        self.relative_return = False
        self.rr = False
        self.reset_cmds = False
        self.state = None
        self.stopping = False

        self.rock_para = False
        self.pump_para = False

        self.ellipse = None
        self.ecc_offset = 0.0

        self.use_scan = None
        self.scan_file = None
        self.spline = None
        self.a_spline = None
        self.pump_profile = None

        #geometric chuck
        self.geo = geometric.GeometricChuck()
        self.geo_radii = []
        self.geo_angles = []
        self.geo_depth = None
        self.geo_points = 6000
        self.geo_thresh = 500
        self.geo_interp = 6000
        self.radial_depth = 0
        self.gcode_geo = False
        self.geo_cutdepth = 0.0
        self.geo_stepdown = 0.0
        self.geo_feedrate = 0.0
        self.geo_plunge = 0.0

        #laser
        self.laser_mode = False
        self.laser = False
        self.laser_feed = 0
        self.laser_base = 0
        #laser settings
        self.power_correct = False
        self.max_correct = 3
        self.min_correct = 0.5
        self.use_m3 = False
        self.laser_start = False
        self.laser_stop = False

        #coordinate tracking
        self.current_a = None
        self.current_b = None
        self.current_x = None
        self.current_z = None

        #plotly
        self.go = go

    def initialize(self):
        self.datafolder = self.get_plugin_data_folder()
        self._event_bus.subscribe("LATHEENGRAVER_SEND_POSITION", self.get_position)
        #self._event_bus.unsubscribe...

        self.a_inc = float(self._settings.get(["a_inc"]))
        self.chunk  = int(self._settings.get(["chunk"]))
        self.bf_target = int(self._settings.get(["bf_threshold"]))
        self.ms_threshold = int(self._settings.get(["ms_threshold"]))
        self.auto_reset = bool(self._settings.get(["auto_reset"]))
        self.geo_points = int(self._settings.get(["geo_points"]))
        self.geo_thresh = int(self._settings.get(["geo_thresh"]))
        self.geo_interp = int(self._settings.get(["geo_interp"]))
        self.relative_return = bool(self._settings.get(["relative_return"]))
        self.power_correct = bool(self._settings.get(["power_correct"]))
        self.max_correct = float(self._settings.get(["max_correct"]))
        self.min_correct = float(self._settings.get(["min_correct"]))
        self.use_m3 = bool(self._settings.get(["use_m3"]))
        self.laser_start = bool(self._settings.get(["laser_start"]))
        self.laser_stop = bool(self._settings.get(["laser_stop"]))
        self.exp = bool(self._settings.get(["exp"]))
        self.geo_cutdepth = float(self._settings.get(["geo_cutdepth"]))
        self.geo_stepdown = float(self._settings.get(["geo_stepdown"]))
        self.geo_feedrate = float(self._settings.get(["geo_feedrate"]))
        self.geo_plunge = float(self._settings.get(["geo_plunge"]))
        self.reset_priority = self._settings.get(["reset_priority"])

        storage = self._file_manager._storage("local")
        
        if storage.folder_exists("rosette"):
            self._logger.info("rosette folder exists")
        else:
            storage.add_folder("rosette")
            templates_folder = os.path.join(self._settings.getBaseFolder("uploads"), "rosette")
            source_folder = os.path.join(self._basefolder, "static", "rosette")
            if os.path.exists(source_folder):
                for file_name in os.listdir(source_folder):
                    if file_name.endswith(".svg"):
                        source_file = os.path.join(source_folder, file_name)
                        destination_file = os.path.join(templates_folder, file_name)
                        shutil.copy(source_file, destination_file)
                        self._logger.info(f"Copied {file_name} to rosette folder")

    def get_settings_defaults(self):
        return dict(
            a_inc=0.5,
            chunk=5,
            bf_threshold=80,
            ms_threshold=10,
            auto_reset=True,
            geo_stages=3,
            geo_points=6000,
            geo_thresh=500,
            geo_interp=6000,
            relative_return=False,
            power_correct=False,
            laser_start=False,
            laser_stop=False,
            max_correct=10,
            min_correct=0.0001,
            r_radius=50,
            r_stage=10,
            r_phase=False,
            r_phase_v=45,
            exp=False,
            geo_cutdepth=1.0,
            geo_stepdown=1.0,
            geo_feedrate=800,
            geo_plunge=200,
            reset_priority="none"
            )
    
    def get_template_configs(self):
        return [
            dict(type="settings", name="Rose Engine", custom_bindings=False)
        ]
    
    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.initialize()

    def get_extension_tree(self, *args, **kwargs):
        return {'model': {'png': ["png", "jpg", "jpeg", "gif", "txt", "stl", "svg", "json", "clr"]}}

    def get_assets(self):
        return {
            "js": ["js/roseengine.js", "js/plotly-latest.min.js"],
            "css": ["css/roseengine.css"],
        }
    
    def on_event(self, event, payload):
        if event == "plugin_latheengraver_send_position":
            self.get_position(event, payload)

        if event == "UpdateFiles":
            #get all file lists
            data = dict(
                func="refresh"
            )
            self._plugin_manager.send_plugin_message("roseengine", data)

    def get_position(self, event, payload):
        #self._logger.info(payload)
        self.current_x = payload["x"]
        self.current_z = payload["z"]
        self.current_a = payload["a"]
        self.current_b = payload["b"]
        self.buffer = payload["bf"]
        self.state = payload["state"]
        laser_mode = bool(payload["laser"])
        if laser_mode != self.laser_mode:
            self._logger.info(f"laser_mode is {laser_mode} and self.laser_mode is {self.laser_mode}")
            self._logger.info("Laser mode changed")
            self._plugin_manager.send_plugin_message("roseengine", dict(laser=laser_mode))
            self.laser_mode = laser_mode
        #self._logger.info(payload["state"])
        self.buffer_received = True
        
        if self.state == "Idle" and self.stopping:
            self.stopping =  False
        
        if self.reset_cmds and self.state == "Idle":
            #self._printer.commands(self.reset_cmds)
            self._reset_gcode()

    def angle_from_center(self, x, y, cx, cy):
        angle_rad = math.atan2(y - cy, x - cx)
        return (math.degrees(angle_rad) + 360) % 360

    def distance_from_center(self, x, y, cx, cy):
        return math.hypot(x - cx, y - cy)      
    
    def create_working_path(self, rosette, amp):
        rl = rosette["radii"]
        an = rosette["angles"]
        radii = np.array(rl)
        radii = np.append(radii,radii[0])
        angles = np.array(an)
        angles = np.append(angles, 0.0)
        angles = np.deg2rad(angles)
        angles = np.unwrap(angles)
        angles = np.degrees(angles)
        radii = np.array(radii) * amp
        # Calculate differences
        radius_diffs = np.diff(radii)
        angle_diffs = np.diff(angles)
        working = {"radii": radius_diffs, "angles": angle_diffs}
        wl = len(working["radii"])
        al = len(working["angles"])
        self._logger.debug(f"Created working set with lengths: r={wl}, a={al}")
        self._logger.debug(f"Radii sum: {np.sum(radius_diffs)}")
        return working
    
    def _geometric(self, data):
        radii = []
        angles = []
        #reset geo
        self.geo = geometric.GeometricChuck()
        for stage in data:
            if stage["radius"] > 0:
                self.geo.add_stage(radius=stage["radius"],
                                p=stage["p"],
                                q=stage["q"],
                                phase=np.radians(stage["phase"])
                                )
                self._logger.debug("Added stage")

        periods = self.geo.required_periods()
        #if periods > 30:
        #    periods  = 30
        self._logger.debug(f"Periods: {periods}")
        t, angles, radii = self.geo.generate_polar_path(num_points=self.geo_points, t_range=(0, 2*np.pi * periods))
        avg_a_inc = np.mean(np.abs(angles))
        if avg_a_inc < 0.05:
            msg=dict(title="Angle Error",
                      text="The average angular displacement is too low. Decrease the sample number and try again.",
                      type="warning")
            self.send_le_error(msg)
            return
        angles = np.unwrap(angles)
        angles = np.degrees(angles)
        self._logger.debug("Unrolled angles:")
        self._logger.debug(angles)
        #calculate min, max
        max_radius = np.max(radii)
        min_radius = np.min(radii)
        max_idx = np.argmax(radii)

        #self._logger.debug(radii)
        #self._logger.debug("Rolled angles")
        #self._logger.debug(angles)
            
        rosette = {
            "radii": radii,
            "angles": angles,
            "max_radius": max_radius,
            "min_radius": min_radius,
            "type": "geometric"
        }

        return rosette

    def _parametric_sine(self, data):
        wave = data["wave_type"]
        amplitude = float(data["amp"])
        num_peaks = int(data["peak"])
        phase_shift = float(data["phase"])
        radii = []
        angles = []
        phase_shift_rad = math.radians(phase_shift)
        for deg in np.arange(0, 360, self.a_inc):
            radians = math.radians(deg)
            if wave == "sin":
                displacement = amplitude * math.sin(num_peaks * radians + phase_shift_rad)
            elif wave == "tri":
                # Triangle wave, centered at zero
                displacement = amplitude * (2 / math.pi) * np.arcsin(np.sin(num_peaks * radians + phase_shift_rad))
            elif wave == "square":
                # Square wave: sign of sine
                displacement = amplitude * np.sign(np.sin(num_peaks * radians + phase_shift_rad))
            elif wave == "saw":
                # Sawtooth wave: ramp from -amplitude to +amplitude
                # Normalize angle to [0, 2pi) for each period
                period = 2 * math.pi / num_peaks
                value = ((radians + phase_shift_rad) % period) / period
                displacement = amplitude * (2 * value - 1)
            else:
                displacement = 0
            angles.append(deg)
            radii.append(displacement)

        if len(radii) > 0:
            max_idx = int(np.argmax(radii))
            radii = np.roll(radii, -max_idx)
            angles = np.roll(angles, -max_idx)
            angle_offset = angles[0]
            angles = (angles - angle_offset) % 360
        
        rosette = {
            "radii": radii,
            "angles": angles,
            "max_radius": None,
            "min_radius": None,
            "type": "parametric"
        }

        return rosette
    
    def _ellipse_rad(self, angle):
        angle_rad = np.deg2rad(angle)
        a = self.ellipse["a"]
        ratio = self.ellipse["ratio"]
        b = a / ratio
        
        r = (a * b) / np.sqrt((b * np.cos(angle_rad))**2 + (a * np.sin(angle_rad))**2)
        return r

    def _update_injection(self, cmd: str, axis_val: tuple) -> str:
        axis, delta = axis_val
        # Regex pattern to find axis (e.g., A, Z, etc.)
        pattern = re.compile(rf'({axis})([-+]?[0-9]*\.?[0-9]+)')
        orig_cmd = cmd
        match = pattern.search(cmd)
        if match:
            # Axis already exists, add delta to existing value
            old_val = float(match.group(2))
            new_val = old_val + delta
            # Replace old value with new value (formatted to 4 decimal places)
            cmd = pattern.sub(f"{axis}{new_val:.4f}", cmd, count=1)
        else:
            # Axis doesn't exist, insert before F command
            insert_pattern = re.compile(r'(F[-+]?[0-9]*\.?[0-9]+)')
            insert_match = insert_pattern.search(cmd)
            insert_str = f"{axis}{delta:.4f} "
            if insert_match:
                # Insert before F
                idx = insert_match.start()
                cmd = cmd[:idx] + insert_str + cmd[idx:]
            else:
                # Append at end if F not found
                cmd += ' ' + insert_str.strip()
        self._logger.info(f"injected, orig: {orig_cmd}, new: {cmd}")
        return cmd
    
    def resample_offset(self, radii, angles, offset=0.0):

        ang_rad = np.deg2rad(angles)
        # to Cartesian coordinates
        x = radii * np.cos(ang_rad)
        y = radii * np.sin(ang_rad)
        x2 = x + offset
        y2 = y 

        # convert back to polar
        offset_radii  = np.hypot(x2, y2)
        offset_radians = np.arctan2(y2, x2)
        offset_radians = np.unwrap(offset_radians)
        offset_angles = np.rad2deg(offset_radians)

        return offset_radii, offset_angles

    def resample_path_to_polar(self, path, center=None, radial_offset=0.0):
        if not center:
            xmin, xmax, ymin, ymax = path.bbox()
            cx = (xmin + xmax) / 2
            cy = (ymin + ymax) / 2
        else:
            cx = center[0]
            cy = center[1]

        radii = []
        angles = []
        N_STEPS = 10000
        ANGLE_STEP = self.a_inc
        t_values = np.linspace(0, 1, N_STEPS+1)
        last_angle = None
        first_angle = None

        for idx, t in enumerate(t_values):
            pt = path.point(t)
            x, y = pt.real, pt.imag
            angle = self.angle_from_center(x, y, cx, cy)
            radius = self.distance_from_center(x, y, cx, cy)

            if last_angle is None:
                # First point
                radii.append(radius)
                angles.append(0.0)
                last_angle = angle
                first_angle = angle
                continue

            # Compute relative angle from first point
            rel_angle = (angle - first_angle + 360) % 360

            # Check if we've crossed the next ANGLE_STEP
            prev_rel_angle = (last_angle - first_angle + 360) % 360
            angle_diff = rel_angle - prev_rel_angle

            # Handle wrap-around
            if angle_diff < -180:
                angle_diff += 360
            elif angle_diff > 180:
                angle_diff -= 360

            if abs(angle_diff) >= ANGLE_STEP:
                radii.append(radius)
                angles.append(rel_angle)
                last_angle = angle
        return angles, radii

    def load_rosette(self, filepath, type):
        folder = self._settings.getBaseFolder("uploads")
        #filename = f"{folder}/{filepath}"
        filename = os.path.join(folder, filepath)
        ext = os.path.splitext(filename)[1].lower()
        radii = []
        angles = []
        special_case = False

        if ext == ".clr":
            try:
                angles = []
                radii = []
                with open(filename, "r") as f:
                    lines = f.readlines()
                # ignore first line (header) and parse subsequent lines
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = re.split(r'\s+', line)
                    if len(parts) < 2:
                        continue
                    try:
                        ang = float(parts[0])
                        rad = 25.4 * float(parts[1])
                    except ValueError:
                        continue
                    angles.append(ang)
                    radii.append(rad)
                if not angles:
                    raise ValueError("No numeric data found in CLR file")
                
            except Exception as e:
                self._logger.error(f"Failed to read/parse CLR file {filename}: {e}", exc_info=True)
                raise

        if ext == ".svg":
            paths, attributes = svg2paths(filename)
            path = paths[0]  # assume single path
            center = None
            for a in attributes:
                if a["id"] == "center":
                    center = (float(a["cx"]), float(a["cy"]))
                    break

            angles, radii = self.resample_path_to_polar(path, center)
        
        radii = np.array(radii)
        angles = np.array(angles)

        # Roll so largest radius is first
        max_idx = np.argmax(radii)
        radii = np.roll(radii, -max_idx)
        angles = np.roll(angles, -max_idx)

        # Offset angles so first is 0
        angle_offset = angles[0]
        self._logger.debug(f"First angle is: {angles[0]}")
        angles = (angles - angle_offset) % 360

        # Detect if the path is going in reverse (large jump between first and second angle)
        if len(angles) > 1:
            angle_jump = (angles[1] - angles[0]) % 360
            if angle_jump > 180:
                radii = radii[::-1]
                angles = angles[::-1]
                angle_offset = angles[0]
                angles = (angles - angle_offset) % 360
        
        if (
            len(radii) > 1 and
            np.isclose(radii[0], radii[-1]) and
            np.isclose(angles[0], angles[-1])
        ):
            radii = radii[:-1]
            angles = angles[:-1]
         
        expected_points = int(360 / self.a_inc)
        uniform_angles = np.arange(0, 360, self.a_inc)
        
        if len(angles) < expected_points:
            self._logger.debug("Running interpolation...")
            # Interpolate radii to uniform angles
            # Ensure angles are sorted for interpolation
            sort_idx = np.argsort(angles)
            sorted_angles = angles[sort_idx]
            sorted_radii = radii[sort_idx]
            # Use np.interp, which wraps at 360
            uniform_radii = np.interp(uniform_angles, sorted_angles, sorted_radii)
            angles = uniform_angles
            radii = uniform_radii

            # Roll so the largest radius is at index 0, then normalize angles so index 0 == 0°
            max_idx = int(np.argmax(radii))
            self._logger.debug(f"Interpolation: max_idx={max_idx}, max_radius={radii[max_idx]:.3f}, angle_at_max={angles[max_idx]:.6f}")
            radii = np.roll(radii, -max_idx)
            angles = np.roll(angles, -max_idx)
            # Normalize relative to first angle and keep values in [0,360)
            angles = (angles - angles[0]) % 360
            angles[0] = 0.0
            # Reduce floating noise
            angles = np.round(angles, 6)
            self._logger.debug(f"Post-interp first_angle={angles[0]}, first_radius={radii[0]:.3f}")
        
        elif len(angles) > expected_points and ext == ".svg":
            special_case = True

        if self.ecc_offset and type == "rock":
            radii, angles = self.resample_offset(radii, angles, self.ecc_offset)

        max_radius = np.max(radii)
        min_radius = np.min(radii)
        self._logger.debug(f"First/last radii/angle: {radii[0]} {angles[0]} {radii[-1]} {angles[-1]}")

        rosette = {
            "radii": radii,
            "angles": angles,
            "max_radius": max_radius,
            "min_radius": min_radius,
            "type": "svg"
        }

        if special_case:
            rosette["special"] = True
        else:
            rosette["special"] = False

        self._logger.debug(f"radii length:{len(radii)}")
        self._logger.debug(f"angle length:{len(angles)}")
        self._logger.debug(rosette)
        return rosette
    
    def _geometric_thread(self):
        self._logger.info("Starting geometric thread")
        #get avg. angular change for feed calc
        avg_a_inc = np.mean(np.abs(self.geo_angles))
        self._logger.debug(f"Average angular displacement: {avg_a_inc}")
        try:
            bf_target = self.bf_target
            dir = "" if self.forward else "-"
            #this reverses direction, but would also have to reverse list to truly be in reverse
            degrees_sec = (self.rpm * 360) / 60
            degrees_chunk = self.chunk * self.a_inc
            loop_start = None
            loop_end = None
            cmdlist = []
            #cmdlist.append("G92 A0")
            if self.laser_mode and self.laser_start:
                lc = "M4"
                if self.use_m3:
                    lc="M3"
                cmdlist.append(f"{lc} S{self.laser_base}")
                self.laser = True
            #cmdlist.append("M3 S1000")
            #used for laser radius tracking
            track_z = self.start_coords["z"]

            while self.running:
                self.buffer = 0
                degrees_sec = (self.rpm * 360) / 60
                degrees_chunk = self.chunk * avg_a_inc
                time_unit = avg_a_inc/degrees_sec * 1000 #ms
                tms = round(time.time() * 1000)
                self.feedcontrol["current"] = tms
                self._logger.debug("AT THE START")
                #first chunk will be full size
                #next_interval = time_unit*self.chunk
                next_interval = int(degrees_chunk / degrees_sec * 1000)  # in milliseconds
                self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                #self._logger.info(f"Next interval at {self.rpm} RPM, {next_interval}, bf_target {bf_target}")
                current_angle = 0
                for i in range(0, len(self.geo_radii), self.chunk):
              
                    with self.rpm_lock:
                        if self.updated_rpm > 0:
                            #self._logger.info("Updating RPM")
                            self.rpm = self.updated_rpm
                            self.updated_rpm = 0.0
                            degrees_sec = (self.rpm * 360) / 60
                            next_interval = int(degrees_chunk / degrees_sec * 1000)  

                    feed = (360/avg_a_inc) * self.rpm
                    rchunk = self.geo_radii[i:i+self.chunk]
                    achunk = self.geo_angles[i:i+self.chunk]
                    xchunk = self.geo_depth[i:i+self.chunk]
                    chunk_distance = 0
                                        
                    for c in range(0, len(rchunk)):
                        a = achunk[c]
                        z = rchunk[c]
                        x = xchunk[c]
                        if self.b_adjust:
                            bangle = math.radians(self.current_b - self.bref) *-1
                            x = x*math.cos(bangle) + z*math.sin(bangle)
                            z = -z*math.sin(bangle) + z*math.cos(bangle)
                        track_z = track_z + z
                        cmdlist.append(f"G93 G91 G1 X{x:0.3f} A{a:0.3f} Z{z:0.3f} F{feed:0.1f}")
                        if self.laser_mode and self.laser:
                            #calculate the chunk distance
                            arc = track_z * math.radians(a)
                            chunk_distance = chunk_distance + math.sqrt(arc**2 + x**2 + z**2)
                    if self.laser and chunk_distance and self.power_correct:
                        #figure out scaling of power here
                        calc_time = len(rchunk) / (feed) #time in minutes to complete chunk
                        nf = chunk_distance/calc_time #calculated feed
                        sf = nf/self.laser_feed 
                        if sf < self.min_correct:
                            sf = self.min_correct
                        if sf > self.max_correct:
                            sf = self.max_correct
                        scaled = int(self.laser_base * sf)
                        cmdlist[0] = cmdlist[0] + f" S{scaled}"

                    #All modifications should be PRE injection
                    if self.inject:
                        if not isinstance(self.inject, tuple) and self.inject.startswith("S"):
                            m = re.search(r"S\s*=?\s*([0-9]+)", self.inject, re.IGNORECASE)
                            if m:
                                val = int(m.group(1))
                                # set laser state and base power
                                if val == 0:
                                    self.laser = False
                                    cmdlist.append("S0")
                                else:
                                    self.laser = True
                                    self.laser_base = val
                                    lc = "M4"
                                    if self.use_m3:
                                        lc="M3"
                                    cmdlist.append(f"{lc} S{val}")
                                    self._logger.info(f"Injected laser power command M4 S{val}, laser={'on' if self.laser else 'off'}")
                            else:
                                self._logger.warning(f"Unrecognized S-inject format: {self.inject}")
                            self.inject = None
                        else:
                            cmdlist[-1] = self._update_injection(cmdlist[-1], self.inject)
                            self.inject = None
                    # Loop until we are ready to send the next chunk
                    tms = round(time.time() * 1000)
                    while self.feedcontrol["next"] - tms > self.ms_threshold or self.buffer < bf_target:
                            time.sleep(self.ms_threshold/2000)
                            tms = round(time.time() * 1000)
                            if not self.running:
                                break

                    #self._logger.info(f"buffer is now at {self.buffer}")
                    self._printer.commands(cmdlist)
                    self.buffer_received = False
                    #in case RPM has changed
                    degrees_sec = (self.rpm * 360) / 60
                    next_interval = int(degrees_chunk / degrees_sec * 1000)
                    self.feedcontrol["current"] = round(time.time() * 1000)
                    self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                    cmdlist = []
                    if not self.running:
                        break
                if self.laser and self.laser_stop:
                    self.running = False
                    self._logger.debug("Stopping from laser_stop")
                    self._printer.commands(["S0"])
    
        except Exception as e:
            self._logger.error(f"Exception in job thread: {e}", exc_info=True)
        self._logger.info("Geometric Thread ended")
        if self.laser: #just a safety, will also send M5
            self._printer.commands(["S0"])


#TODO: rework this. Yuck. if using radial offset have to figure out how to handle angles with rock+pump. May need to move to using python plotly for everything
    def _job_thread(self):  
        self._logger.info("Starting job thread")
        #phase offsets applied here to the working array
        phasecmds = []
        pump_rad_start = 0
        if self.pump_offset and self.pump_main:
            #base the roll on self.a_inc
            roll = int(self.pump_offset/self.a_inc)
            #determine absolute value at this position from main
            zero_pump = self.pump_main["radii"][0]
            pump_rad_start = zero_pump - self.pump_main["radii"][roll]
            self._logger.debug(f"pump phase offset X value: {pump_rad_start}")
            self.working_x[:, 1] = np.roll(self.working_x[:, 1], roll)
            phasecmds.append(f"G0 G91 X{pump_rad_start:0.3f}")

        try:
            bf_target = self.bf_target
            degrees_sec = (self.rpm * 360) / 60
            degrees_chunk = self.chunk * self.a_inc
            loop_start = None
            loop_end = None
            cmdlist = []
            #cmdlist.append("G92 A0")
            ovality_z = 0 #this is how far we have already moved Z at any point
            if self.laser_mode and self.laser_start:
                lc = "M4"
                if self.use_m3:
                    lc="M3"
                cmdlist.append(f"{lc} S{self.laser_base}")
                self.laser = True
            #cmdlist.append("M3 S1000")
            if len(phasecmds):
                cmdlist.extend(phasecmds)
            track = {"x": self.start_coords["x"], "z": self.start_coords["z"], "a": self.start_coords["a"]}
            
            if not self.forward:
                self.working_angles = self.working_angles*-1
                #self.working_x = np.flip(self.working_x)
                #self.working_z = np.flip(self.working_z)
                #self.working_mod = np.flip(self.working_mod)

            while self.running:
                self.buffer = 0
                degrees_sec = (self.rpm * 360) / 60
                degrees_chunk = self.chunk * self.a_inc
                time_unit = self.a_inc/degrees_sec * 1000 #ms
                tms = round(time.time() * 1000)
                if loop_start:
                    self._logger.debug(f"loop time ms: {tms - loop_start}")
                    self._logger.debug(f"Z-positiong at loop: {track["z"]}")
                loop_start = tms
                self.feedcontrol["current"] = tms
                
                #first chunk will be full size
                next_interval = int(degrees_chunk / degrees_sec * 1000)  # in milliseconds
                self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                current_angle = 0
                #right now self.working is just rock, pump, mod 
                for i in range(0, len(self.working_angles), self.chunk):
                    with self.rpm_lock:
                        if self.updated_rpm > 0:
                            #self._logger.info("Updating RPM")
                            self.rpm = self.updated_rpm
                            self.updated_rpm = 0.0
                            degrees_sec = (self.rpm * 360) / 60
                            next_interval = int(degrees_chunk / degrees_sec * 1000)  
                    feed = (360/self.a_inc) * self.rpm
                    zchunk = self.working_z[i:i+self.chunk]
                    achunk = self.working_angles[i:i+self.chunk]
                    xchunk = self.working_x[i:i+self.chunk]
                    modchunk = self.working_mod[i:i+self.chunk]
                    chunk_distance = 0
                    #tofix
                    current_angle = track["a"]
                    
                    for c in range(0, len(achunk)):
                        a = achunk[c]
                        z = zchunk[c]
                        x = xchunk[c]
                        m = modchunk[c]
                        track["z"] = track["z"] + z
                        track["x"] = track["x"] + x
                        track["a"] = track["a"] + a

                        if self.b_adjust:
                            bangle = math.radians(self.current_b - self.bref) *-1
                            x = x*math.cos(bangle) + z*math.sin(bangle)
                            z = -x*math.sin(bangle) + z*math.cos(bangle)
                        if self.ellipse:
                            z = z + m
                        if self.use_scan:
                            #just assume we are doing pumping
                            zdiff = profiles.ovality_mod(self,track["x"],track["a"])
                            tx = track["x"]
                            ta = track["a"]
                            delta_ov = zdiff - ovality_z
                            z = z + delta_ov
                            ovality_z = zdiff
                            #self._logger.info(f"Zdiff is {zdiff} delta_ov is {delta_ov}")
                        if self.laser_mode and self.laser:
                            #calculate the chunk distance
                            arc = track["z"] * math.radians(self.a_inc)
                            chunk_distance = chunk_distance + math.sqrt(arc**2 + x**2 + z**2)

                        cmdlist.append(f"G93 G91 G1 X{x:0.3f} A{a:0.3f} Z{z:0.3f} F{feed:0.1f}")
                    
                    if self.laser and chunk_distance and self.power_correct:
                        #figure out scaling of power here
                        calc_time = len(achunk) / (feed) #time in minutes to complete chunk
                        nf = chunk_distance/calc_time #calculated feed
                        sf = nf/self.laser_feed
                        if sf < self.min_correct:
                            sf = self.min_correct
                        if sf > self.max_correct:
                            sf = self.max_correct
                        scaled = int(self.laser_base * sf)
                        self._logger.debug(f"calc time: {calc_time}, nf: {nf}, sf: {sf}, scaled: {scaled}")
                        cmdlist[0] = cmdlist[0] + f" S{scaled}"
                    
                    #All modifications should be PRE injection
                    if self.inject:
                        if not isinstance(self.inject,tuple) and self.inject.startswith("S") and self.laser_mode:
                            m = re.search(r"S\s*=?\s*([0-9]+)", self.inject, re.IGNORECASE)
                            if m:
                                val = int(m.group(1))
                                # set laser state and base power
                                if val == 0:
                                    self.laser = False
                                    cmdlist.append("S0")
                                else:
                                    self.laser = True
                                    self.laser_base = val
                                    lc = "M4"
                                    if self.use_m3:
                                        lc="M3"
                                    cmdlist.append(f"{lc} S{val}")
                                    self._logger.info(f"Injected laser power command M4 S{val}, laser={'on' if self.laser else 'off'}")
                            else:
                                self._logger.warning(f"Unrecognized S-inject format: {self.inject}")
                            self.inject = None
                        else:
                            cmdlist[-1] = self._update_injection(cmdlist[-1], self.inject)
                            self.inject = None
                    # Loop until we are ready to send the next chunk
                    tms = round(time.time() * 1000)
                    while self.feedcontrol["next"] - tms > self.ms_threshold or self.buffer < bf_target:
                            time.sleep(self.ms_threshold/2000)
                            tms = round(time.time() * 1000)
                            if not self.running:
                                break

                    #self._logger.info(f"buffer is now at {self.buffer}")
                    self._printer.commands(cmdlist)
                    self.buffer_received = False
                    #in case RPM has changed
                    degrees_sec = (self.rpm * 360) / 60
                    time_unit = self.a_inc/degrees_sec * 1000 #ms
                    next_interval = int(degrees_chunk / degrees_sec * 1000)
                    self.feedcontrol["current"] = round(time.time() * 1000)
                    self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                    cmdlist = []
                    self.last_position = i
                    if not self.running:
                        break
                if self.laser and self.laser_stop:
                    self.running = False
                    self._printer.commands(["S0"])

        except Exception as e:
            self._logger.error(f"Exception in job thread: {e}", exc_info=True)
        self._logger.info("Thread ended")
        if self.laser:
            self._printer.commands(["S0"])

    def _start_geo(self):
        self.rock_work = []
        self.pump_work = []
        self._logger.debug("Starting geometric job")
        self.start_coords["x"] = self.current_x
        self.start_coords["z"] = self.current_z
        self.start_coords["a"] = self.current_a
        self.running = True

        radii = np.array(self.rock_main["radii"])
        angles = np.array(self.rock_main["angles"])
        num_points = len(radii)
        num_samples = self.geo_interp

        if num_points < self.geo_thresh:
            # Convert polar to Cartesian
            x = radii * np.cos(np.radians(angles))
            y = radii * np.sin(np.radians(angles))

            # Parameterize by cumulative path length
            ds = np.sqrt(np.diff(x)**2 + np.diff(y)**2)
            s = np.concatenate(([0], np.cumsum(ds)))

            # Interpolate to X points along the path
            s_uniform = np.linspace(0, s[-1], num_samples)
            x_new = np.interp(s_uniform, s, x)
            y_new = np.interp(s_uniform, s, y)

            # Convert back to polar
            new_radii = np.sqrt(x_new**2 + y_new**2)
            new_angles = np.degrees(np.unwrap(np.arctan2(y_new, x_new)))
        else:
            new_radii = radii
            new_angles = angles

        if self.gcode_geo:
            #back to cartesian!
            self.geo_gcode(new_radii, new_angles)
            self.running = False
            return

        #remove last value here
        new_radii = new_radii[:-1]
        new_angles = new_angles[:-1]
        # Calculate differences
        radius_diffs = np.diff(new_radii)
        angle_diffs = np.diff(new_angles)
        if len(angle_diffs) < 1000:
            for each in angle_diffs:
                self._logger.debug(each)

        #this seems to have been mostly corrected by unwraping, but leaving it in for now
        large_jumps = np.where(np.abs(angle_diffs) > 180)[0]
        if large_jumps.size > 0:
            self._logger.info(f"Large angle diff (>180 deg) at indices: {large_jumps}, values: {angle_diffs[large_jumps]}")
            msg=dict(title="Design Problem",
                      text="This design has a large angular jump. This is a known bug. Recreate your design with a fewer number of sample points.",
                      type="warning")
            self.send_le_error(msg)
            return
        # Append wrap-around difference
        radius_diffs = np.append(radius_diffs, new_radii[0] - new_radii[-1])
        #handles if we are travelling in the negative direction
        wrap_diff = new_angles[0] - new_angles[-1]
        wrap_diff = (wrap_diff + 180) % 360 - 180
        angle_diffs = np.append(angle_diffs, wrap_diff)
        #angle_diffs = np.append(angle_diffs, (new_angles[0] - new_angles[-1]) % 360 )

        self.geo_radii = radius_diffs
        self.geo_angles = angle_diffs
        self.geo_depth = np.zeros_like(self.geo_radii)

        
        
        if self.radial_depth:
            max_r = np.max(new_radii)
            depth_vals = np.zeros_like(self.geo_radii, dtype=float)

            for idx, z in enumerate(new_radii):
                if max_r and max_r != 0:
                    frac = z / max_r
                    if self.radial_depth < 0:
                        x = frac * self.radial_depth
                    else:
                        x = - (1.0 - frac) * (self.radial_depth)
                depth_vals[idx] = x
            if depth_vals.size:
                depth_diffs = np.roll(depth_vals, -1) - depth_vals
                self.geo_depth = depth_diffs
                self._logger.debug(self.geo_depth)
        self._logger.debug("Geo radii diffs: %s", self.geo_radii)
        self._logger.debug("Geo angle diffs: %s", self.geo_angles)

        self.jobThread = threading.Thread(target=self._geometric_thread).start()

    def _start_job(self):
        if self.running:
            return
        self.rock_work = []
        self.pump_work = []
        working_z = []
        working_x = []
        working_angles = []
        if self.rock_main and self.rock_main["type"] == "geometric":
            self._start_geo()
            return
        #additional array, might want to rethink how this works
        modifier = []
        mod_array = np.array(modifier)
        
        if self.pump_main:
            self.pump_work = self.create_working_path(self.pump_main, self.p_amp)
            #Other modifictions
            if self.pump_invert:
                self.pump_work["radii"] = np.array(self.pump_work["radii"])*-1
            working_x = self.pump_work["radii"]
            working_angles = self.pump_work["angles"]
        else:
            working_x = np.zeros_like(self.rock_main["radii"])

        if self.rock_main:
            #this is now a dict with radii and angle keys
            self.rock_work = self.create_working_path(self.rock_main, self.r_amp)
            working_z = self.rock_work["radii"]
            #default to rock containing our angle set
            working_angles = self.rock_work["angles"]
        else:
            working_z = np.zeros_like(self.pump_main["radii"])

        if self.ellipse:
            e_vals = []
            for deg in np.arange(0, 360, self.a_inc):
                e_rad = self._ellipse_rad(deg)
                e_vals.append(e_rad)
            #difference values
            e_a = np.array(e_vals)
            mod_array = np.roll(e_a, -1) - e_a
        else:
            mod_array = np.zeros_like(working_z)
        
        #self.working = list(zip_longest(self.rock_work, self.pump_work, mod_array, fillvalue=0))
        #self.working = np.array(self.working)
        #to get rock+pump working correctly, need to check if rock and pump angle sets are the same, if not resample pump
        self.working_x = working_x
        self.working_z = working_z
        self.working_angles = working_angles
        self.working_mod = mod_array

        if self.ecc_offset and self.pump_main and self.rock_main:
            self.working_x = np.zeros_like(working_z)
            msg = dict(
                        title="Warning!",
                        text="Eccentric offset of rocking rosette with a pumping rosette is not compatible. Ignoring pumping.",
                        type="warning")
            self.send_le_error(msg)

        self.start_coords["x"] = self.current_x
        self.start_coords["z"] = self.current_z
        self.start_coords["a"] = self.current_a
        self.running = True
        self._logger.debug(working_z)
        self._logger.debug(working_angles)
        self._logger.debug(working_x)
        self.jobThread = threading.Thread(target=self._job_thread).start()

    def _reset_gcode(self):
        self.pump_profile = None
        gcode = []
        return_gcode = []
        #reset A modulo
        self._logger.debug(f"current_a: {self.current_a}")
        theA = self.current_a % 360
        if self.relative_return:
            self.rr = True
        gcode.append(f"G92 A{theA}")
        return_gcode.append(f"G92 A{theA}")
        
        #TODO: If using B-angle, it is possible that start position X is less than end, need to take into account
        x,z,a = self.start_coords["x"], self.start_coords["z"], self.start_coords["a"]
        
        #rock/geo only
        if (len(self.rock_work) or len(self.geo_radii)) and not len(self.pump_work):
            #assume we are just going to back and then in/out
            if self.b_adjust: #do we need to compensate for the actual B-angle?
                if self.current_x > x:
                    self._logger.debug("current_x > than x")
                    gcode.append(f"G94 G91 G1 X5 F1000")
                    gcode.append(f"G90 G0 Z{z} A{a}")
                    return_gcode.append(f"G90 G0 SC_Z A{a}")
                    gcode.append(f"G90 G0 X{x}")
                    return_gcode.append(f"G90 G0 SC_X")
                else:
                    gcode.append(f"G94 G90 G0 Z{z} X{x}")
                    return_gcode.append(f"G94 G90 G0 SC_Z SC_X")
                    gcode.append(f"G0 A{a}")
                    return_gcode.append("G0 A{a}")
            else:
                gcode.append(f"G94 G90 G0 X{x}")
                return_gcode.append(f"G94 G90 G0 SC_X")
                gcode.append(f"G90 G0 Z{z} A{a}")
                return_gcode.append(f"G90 G0 SC_Z A{a}")

        #pump only
        if len(self.pump_work) and not len(self.rock_work):
            gcode.append(f"G94 G90 G0 Z{z}")
            gcode.append(f"G0 X{x} A{a}")
            return_gcode.append(f"G94 G90 G0 SC_Z")
            return_gcode.append(f"G0 SC_X A{a}")

        #rock and pump, need to get special cases
        if len(self.pump_work) and len(self.rock_work):
            if self.reset_priority == "pump":
                gcode.append(f"G94 G90 G0 Z{z}")
            if self.reset_priority == "rock":
                gcode.append(f"G94 G90 G0 X{x}")
            gcode.append(f"G94 G90 G0 Z{z} X{x}")
            gcode.append(f"G0 A{a}")
            return_gcode.append(f"G94 G90 G0 SC_Z SC_X")
            return_gcode.append(f"G0 A{a}")

        gcode.append("STOPCAP")
        gcode.append("M30")
        self.reset_cmds = False
        self._logger.debug(gcode)
        self._printer.commands(gcode)
        if self.relative_return and self.recording:
            self.recorded.extend(return_gcode)       

    def _stop_job(self):
        if not self.running:
            return
        self.running = False
        self.stopping = True

        if self.auto_reset:
            self.reset_cmds = True

    def _plotly_json(self,r,a,maxrad,minrad,lc="black"):
        #Using the plotly Python library instead of JavaScript as it seems to handle
        #polar coordinates much better

        fig = self.go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=r,
            theta=a,  # plotly expects degrees
            mode='lines',
            line_color=lc,   
        ))

        fig.update_layout(
            margin = dict(
            l=30,
            r=30,
            b=10,
            t=40,
            pad=4
            ),
            polar=dict(
                radialaxis=dict(visible=False,showline=False,autorange=False,range=(0,maxrad*1.1)),
                angularaxis=dict(rotation=180, direction="clockwise",showline=False)
            ),
            showlegend=False,
            title=dict(
                text=f"r max={maxrad:0.1f}<br>r min={minrad:0.1f}",
                font=dict(size=12),
                xanchor='center',
                yanchor='top',
                x=0.5,
            )
            
        )

        return fig.to_plotly_json()
    
    def geo_gcode(self, radii, angles):
        self.geo_gcode = False
        gcode = []
        #to cartesian
        x = radii * np.cos(np.radians(angles))
        y = radii * np.sin(np.radians(angles))

        diam = 2 * np.max(radii)
        #step-down and depth-of-cut, feedrate
        sd = self.geo_stepdown
        cd = self.geo_cutdepth
        fr = self.geo_feedrate
        pr = self.geo_plunge

        # Calculate depth passes
        pass_info = divmod(cd, sd)
        passes = pass_info[0]
        last_pass_depth = pass_info[1]
        self._logger.debug(f"Last pass depth: {last_pass_depth}")
        if last_pass_depth:
            total_passes = int(passes + 1)
        else:
            total_passes = int(passes)

        #comments
        gcode.append("(Geometric chuck pattern written by LE-RoseEngine plugin)")
        gcode.append(f"(Design width/diameter: {diam})")
        gcode.append(f"(Cut depth: {cd}, Max step down: {sd}, Feedrate: {fr})")
        gcode.extend(["G21","G90","M3 S1000","G4 P1","G0 X0.0 Y0.0"])
        gcode.append(f"G0 Z5.0")
        #move to first position
        for depth in range(1,total_passes+1):
            tocut = depth*sd
            self._logger.debug(f"depth to cut: {tocut}")
            if tocut > cd and last_pass_depth != 0.0:
                tocut = tocut - sd + last_pass_depth
                self._logger.debug(f"modified depth to cut: {tocut}")
            gcode.append(f"(Starting cut at depth: -{tocut})")
            gcode.append(f"G0 X{float(x[0]):.3f} Y{float(y[0]):.3f}")
            gcode.append(f"G1 Z-{tocut:.3f} F{pr}")
            for i in range(1, len(x)):
                gcode.append(f"G1 X{float(x[i]):.3f} Y{float(y[i]):.3f} F{fr}")
            gcode.append(f"G0 Z5")
            gcode.append(f"G0 X0 Y0")
        
        
        gcode.append("M30")
        filename = time.strftime("%Y%m%d-%H%M") + "_geometric.gcode"
        path_on_disk = "{}/templates/{}".format(self._settings.getBaseFolder("uploads"), filename)
        with open(path_on_disk,"w") as newfile:
            #write in comment stuff here
            for line in gcode:
                newfile.write(f"\n{line}")

            
    def write_gcode(self):
        filename = time.strftime("%Y%m%d-%H%M") + "roseengine.gcode"
        path_on_disk = "{}/{}".format(self._settings.getBaseFolder("watched"), filename)
        if self.relative_return:
            #need this inserted after G92 A0
            self.recorded.insert(1, "STARTCAP")
        with open(path_on_disk,"w") as newfile:
            #write in comment stuff here
            for line in self.recorded:
                newfile.write(f"\n{line}")
        self.recorded = []

    def is_api_protected(self):
        return True
    
    def get_api_commands(self):
        return dict(
            start_job=[],
            stop_job=[],
            jog=[],
            load_rosette=[],
            get_arc_length=[],
            goto_start=[],
            clear=[],
            update_rpm=[],
            parametric=[],
            geometric=[],
            recording=[],
            laser=[],
            save_geo=[]
        )
    
    def on_api_command(self, command, data):
        self._logger.debug(command)
        self._logger.debug(data)

        if command == "load_rosette":
            filePath = data["filepath"]
            type = data["type"]
            self.ecc_offset = float(data["ecc_offset"])
            rosette = self.load_rosette(filePath,type)
            s = rosette["special"]
            if type == "rock":
                self.rock_main = rosette
                r = list(self.rock_main["radii"])
                a = list(self.rock_main["angles"])
                json_figure = self._plotly_json(r,a,self.rock_main["max_radius"],minrad=self.rock_main["min_radius"],lc="blue")
                #data = dict(type="rock", special=s, radii=r, angles=a, maxrad=self.rock_main["max_radius"], minrad=self.rock_main["min_radius"])
                data = dict(type="rock", special=s, graph=json_figure)
                
            elif type == "pump":
                self.pump_main = rosette
                r = list(self.pump_main["radii"])
                a = list(self.pump_main["angles"])
                json_figure = self._plotly_json(r,a,self.pump_main["max_radius"],minrad=self.pump_main["min_radius"],lc="green")
                data = dict(type="pump", special=s, graph=json_figure)
                #data = dict(type="pump", special=s, radii=r, angles=a, maxrad=self.pump_main["max_radius"], minrad=self.pump_main["min_radius"])
                #self._logger.info(f"Loaded pump rosette: {self.pump_main}")
            
            self._logger.debug(data)
            self._plugin_manager.send_plugin_message('roseengine', data)
            if s:
                msg = dict(
                        title="Rosette Warning",
                        text="The loaded rosette contains rotational direction changes. Any other loaded rosettes will be ignored",
                        type="warning")
                self.send_le_error(msg)
            return
        
        if command == "parametric":
            rose_type = data["type"]
            wave_type = data["wave_type"]
            amp = float(data["amp"])
            peak = data["peak"]
            phase = data["phase"]
            lc = "black"
            #do some stuff
            rosette = self._parametric_sine(data)
            r = np.array(rosette["radii"])
            #just add to this so it looks reasonable when graphed
            r = r+50
            a = (rosette["angles"])
            
            self._logger.debug(rosette)
            if rose_type == "rock":
                self.rock_main = rosette
                lc = "blue"
            else:
                self.pump_main = rosette
                lc = "green"
            maxrad=int(amp)+50
            minrad=int(amp)
            r = list(r)
            a = list(a)
            json_figure = self._plotly_json(r,a,maxrad,minrad,lc=lc)
            returndata = dict(type=rose_type, radii=r, angles=a, special=False, graph=json_figure)
            self._plugin_manager.send_plugin_message('roseengine', returndata)
            return
        
        if command == "geometric":
            #list of stages
            self._logger.debug("Got geometric")
            stage_data = []
            for stage in data.get("stages", []):
                # Each stage should contain: p, q, radius, phase, internal
                stage_dict = {
                    "p": float(stage.get("p")),
                    "q": float(stage.get("q")),
                    "radius": float(stage.get("radius")),
                    "phase": float(stage.get("phase"))
                }
                stage_data.append(stage_dict)

            self.geo_points = int(data["samples"])
            self._logger.debug(stage_data)
            self._logger.debug(f"Sample points: {self.geo_points}")

            rosette = self._geometric(stage_data)
            self.rock_main = rosette
            r = list(self.rock_main["radii"])
            a = list(self.rock_main["angles"])
            s=True
            maxrad = self.rock_main["max_radius"]
            minrad = self.rock_main["min_radius"]

            json_figure = self._plotly_json(r,a,maxrad,minrad,lc="black")
            returndata = dict(type="geo", special=s, graph=json_figure)
            self._plugin_manager.send_plugin_message('roseengine', returndata) 

        
        if command == "save_geo":
            """
            Append current geometric chuck definition to uploads/rosette/saved_geos.json
            """
            try:
                if not hasattr(self, "geo") or not getattr(self.geo, "stages", None):
                    self._logger.warning("No geometric chuck stages available to save")
                    self._plugin_manager.send_plugin_message("roseengine", {"save_geo": "no_data"})
                    return

                rosette_dir = os.path.join(self._settings.getBaseFolder("uploads"), "rosette")
                os.makedirs(rosette_dir, exist_ok=True)
                file_path = os.path.join(rosette_dir, "saved_geos.json")

                entry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "type": "geometric",
                    "periods": self.geo.required_periods() if hasattr(self.geo, "required_periods") else None,
                    "samples": self.geo_points,
                    "stages": []
                }
                for st in self.geo.stages:
                    phase_deg = float(math.degrees(st.phase)) if hasattr(st, "phase") else 0.0
                    entry["stages"].append({
                        "p": int(getattr(st, "p", 0)),
                        "q": int(getattr(st, "q", 1)),
                        "radius": float(getattr(st, "R", 0.0)),
                        "phase": phase_deg
                    })

                # load existing array
                if os.path.exists(file_path):
                    with open(file_path, "r") as f:
                        try:
                            data = json.load(f)
                            if not isinstance(data, list):
                                data = []
                        except Exception:
                            data = []
                else:
                    data = []

                data.append(entry)
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)

                self._logger.info(f"Saved geometric chuck entry to {file_path}")
                #self._plugin_manager.send_plugin_message("roseengine", {"save_geo": "ok", "path": file_path})
            except Exception as e:
                self._logger.error(f"Failed to save geometric chuck: {e}", exc_info=True)
                #self._plugin_manager.send_plugin_message("roseengine", {"save_geo": "error", "error": str(e)})
            return
           
        if command == "start_job":
            self.use_scan = False
            self.rpm = float(data["rpm"])
            self.r_amp = float(data["r_amp"])
            self.p_amp = float(data["p_amp"])
            self.forward = bool(data["forward"])
            self.pump_invert = bool(data["pump_invert"])
            self.pump_offset = float(data["pump_offset"])
            self.b_adjust = bool(data["b_adjust"])
            self.bref = float(data["bref"])
            self.laser_base = int(data["laser_base"]) #should these be dynamic?
            self.laser_feed = int(data["laser_feed"])
            self.radial_depth = float(data["radial_depth"])
            self.pump_profile = data["pump_profile"]
            self.gcode_geo = bool(data["gcode_geo"]) 
            self._logger.info("ready to start job")
            if float(data["e_ratio"]) > 1.0 and not self.rock_main["type"] == "geometric":
                rad = float(data["e_rad"])
                ratio = float(data["e_ratio"])
                self.ellipse = {"a" : rad, "ratio" : ratio }
            else:
                self.ellipse = None
            if self.pump_profile:
                if self.pump_profile != "None":
                    profiles.createsplines(self, self.pump_profile)
                    self.use_scan = True
                    self._logger.info(self.spline)
                    self._logger.info(self.a_spline)
            self._start_job()
            return

        if command == "stop_job":
            self._logger.info("stopping job")
            self._stop_job()
            return

        if command == "jog":
            direction = data["direction"]
            dist = float(data["dist"])
            if direction == 'down':
                dir = "Z"
                dist=dist*-1

            elif direction == 'up':
                dir = "Z"

            elif direction == 'left':
                dir = "X"
                dist=dist*-1

            elif direction == 'right':
                dir = "X"
            
            elif direction == 'plus':
                dir = "A"

            elif direction == 'minus':
                dir = "A"
                dist=dist*-1

            if self.running and dir == "A":
                msg = dict(title="Rotation", text="Rotational movements not allowed while running", type="error")
                self.send_le_error(msg)
                return

            if self.running and abs(dist) > 5:
                msg = dict(title="Jog too large", text="Movements are restrict to 5mm or less while running", type="error")
                self.send_le_error(msg)
                return
            
            cmd = f"G94 G91 G21 G1 {dir}{dist} F1000"
            #if we are running, we can possibly just add to the last command in the chunk
            chunk_cmd = (dir, float(dist))
            if self.running:
                if not self.inject:
                    self.inject = chunk_cmd
                    #self._logger.info(f"Got inject: {chunk_cmd}")
                    return
            else:
                self._printer.commands(cmd)

        if command == "laser":
            self._logger.debug("Laser toggle")
            if not self.running:
                return
            if not self.laser:
                cmd = f"S{self.laser_base}"
                self.inject = cmd
                return
            else:
                cmd = "S0"
                self.inject = cmd
                return

        if command == "goto_start":
            if self.running:
                return
            self.reset_cmds = True
            return
        
        if command == "clear":
            if self.running:
                msg = {"title": "Stop First", "text": "You must stop the running job before clearing a rosette.", "type": "error"}
                self.send_le_error(msg)
                return
            if data["type"] == "rock":
                self.rock_main = []
                self.rock_work = []
            if data["type"] == "pump":
                self.pump_main = []
                self.pump_work = []
            return

        if command == "update_rpm":
            with self.rpm_lock:
                self.updated_rpm = float(data["rpm"])
            return
        
        if command == "recording":
            operation = data["op"]
            if operation == "start":
                if self.recording:
                    self.recording = False
                else:
                    self.recording = True
                self._logger.debug("Recording toggled")
                return
            if operation == "stop":
                self.write_gcode()
                self._logger.debug("Wrote recorded gcode")
                self.recording = False
                self.recorded = []
                #need to toggle button here
                returndata = dict(seticon="rec")
                self._plugin_manager.send_plugin_message('roseengine', returndata)
                return
            if operation == "trash":
                self.recorded = []
                self._logger.debug("Removed existing gcode")
                return
            
    def send_le_error(self, data):
        
        payload = dict(
            type="simple_notify",
            title=data["title"],
            text=data["text"],
            hide=True,
            delay=10000,
            notify_type=data["type"]
        )

        self._plugin_manager.send_plugin_message("latheengraver", payload)

    def hook_gcode_sending(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        if self.stopping and self.state == "Run":
            return (None, )
        if self.recording and not self.rr:
            self.recorded.append(cmd)
        if cmd == "STOPCAP":
            self.rr = False
            return (None,)


    ##~~ Softwareupdate hook

    def get_update_information(self):
        return {
            "roseengine": {
                "displayName": "Roseengine Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "paukstelis",
                "repo": "LE-RoseEngine",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/paukstelis/LE-RoseEngine/archive/{target_version}.zip",
            }
        }

__plugin_name__ = "Roseengine Plugin"
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = RoseenginePlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.filemanager.extension_tree": __plugin_implementation__.get_extension_tree,
        "octoprint.comm.protocol.gcode.sending": __plugin_implementation__.hook_gcode_sending,
    }
