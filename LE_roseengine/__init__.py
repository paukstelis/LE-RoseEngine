# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

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
        self.working = []
        self.recorded = []
        self.last_position = None
        self.chunk = 10
        self.buffer = 0
        self.buffer_received = True
        #self.modifiers = {"amp": 1, "phase": 0, "forward": True}

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
        self.reset_cmds = False
        self.state = None
        self.stopping = False

        self.rock_para = False
        self.pump_para = False

        self.ellipse = None

        #geometric chuck
        self.geo = geometric.GeometricChuck()
        self.geo_radii = None
        self.geo_angles = None
        
        #coordinate tracking
        self.current_a = None
        self.current_b = None
        self.current_x = None
        self.current_z = None

    def initialize(self):
        self.datafolder = self.get_plugin_data_folder()
        self._event_bus.subscribe("LATHEENGRAVER_SEND_POSITION", self.get_position)
        #self._event_bus.unsubscribe...

        self.a_inc = float(self._settings.get(["a_inc"]))
        self.chunk  = int(self._settings.get(["chunk"]))
        self.bf_target = int(self._settings.get(["bf_threshold"]))
        self.ms_threshold = int(self._settings.get(["ms_threshold"]))
        self.auto_reset = bool(self._settings.get(["auto_reset"]))

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
            auto_reset=False,
            geo_stages=3,
            )
    
    def get_template_configs(self):
        return [
            dict(type="settings", name="Rose Engine", custom_bindings=False)
        ]
    
    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.initialize()

    def get_extension_tree(self, *args, **kwargs):
        return {'model': {'png': ["png", "jpg", "jpeg", "gif", "txt", "stl", "svg"]}}
    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
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
        #self._logger.info(rosette["radii"][0])
        #Need to update so it returns both radii and angles now
        rl = rosette["radii"]
        an = rosette["angles"]
        radii = np.array(rl)
        angles = np.array(an)

        radii = np.array(radii) * amp
        #generate differences
        newradii = np.roll(radii, -1) - radii
        newangles = np.roll(angles, -1) - angles

        return newradii, newangles
    
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
                                phase=np.radians(stage["phase"]),
                                internal=False
                                )
                self._logger.debug("Added stage")
        #leave out "pen" for now
        self.geo.set_pen(radius=0)
        periods = self.geo.required_periods()
        self._logger.debug(f"Periods: {periods}")
        t, angles, radii = self.geo.generate_polar_path(num_points=6000, t_range=(0, 2*np.pi * periods * 2))
        self._logger.debug(radii)
        self._logger.debug(angles)
        angles = np.unwrap(angles)
        angles = np.degrees(angles)
        #calculate min, max
        max_radius = np.max(radii)
        min_radius = np.min(radii)
        max_idx = np.argmax(radii)
        radii = np.roll(radii, -max_idx)
        angles = np.roll(angles, -max_idx)

        # Offset angles so first is 0
        #angle_offset = angles[0]
        #angles = (angles - angle_offset) % 360
        #if not np.isclose(angles[-1], 360) and not np.isclose(angles[0], angles[-1]):
        #    angles = np.append(angles, 360.0)
        #    radii = np.append(radii, radii[0])
            
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

    def resample_path_to_polar(self, path, center=None):
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

    def load_rosette(self, filepath):
        folder = self._settings.getBaseFolder("uploads")
        filename = f"{folder}/{filepath}"
        paths, attributes = svg2paths(filename)
        path = paths[0]  # assume single path
        center = None
        special_case = False
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
        
        max_radius = np.max(radii)
        min_radius = np.min(radii)
        self._logger.debug(f"First/last radii/angle: {radii[0]} {angles[0]} {radii[-1]} {angles[-1]}")
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

        if len(angles) > expected_points:
            special_case = True

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
        try:
            bf_target = self.bf_target
            dir = "" if self.forward else "-"
            #this reverses direction, but would also have to reverse list to truly be in reverse
            degrees_sec = (self.rpm * 360) / 60
            degrees_chunk = self.chunk * self.a_inc
            loop_start = None
            loop_end = None
            cmdlist = []
            cmdlist.append("G92 A0")
            cmdlist.append("M3 S1000")
            while self.running:
                self.buffer = 0
                degrees_sec = (self.rpm * 360) / 60
                degrees_chunk = self.chunk * self.a_inc
                time_unit = self.a_inc/degrees_sec * 1000 #ms
                tms = round(time.time() * 1000)
                self.feedcontrol["current"] = tms
                
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

                    feed = (360/self.a_inc) * self.rpm
                    rchunk = self.geo_radii[i:i+self.chunk]
                    achunk = self.geo_angles[i:i+self.chunk]
                    #self.buffer = 0
                    #need to know the actual angle so we know where we are for ellipse
                    for c in range(0, len(rchunk)):
                        a = achunk[c]
                        z = rchunk[c]
                        x = 0
                        if self.b_adjust:
                            #self._logger.info(f"initial x, z: {x} {z}")
                            #initial test assume reference frame at -90 
                            bangle = math.radians(self.current_b - self.bref) *-1
                            x = x*math.cos(bangle) + z*math.sin(bangle)
                            z = -z*math.sin(bangle) + z*math.cos(bangle)
                            #self._logger.info(f"modified x, z: {x} {z}")
                        cmdlist.append(f"G93 G91 G1 X{x:0.3f} A{a:0.3f} Z{z:0.3f} F{feed:0.1f}")
                    #All modifications should be PRE injection
                    if self.inject:
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
        except Exception as e:
            self._logger.error(f"Exception in job thread: {e}", exc_info=True)
        self._logger.info("Geometric Thread ended")

    def _job_thread(self):  
        self._logger.info("Starting job thread")
        #phase offsets applied here to the working array
        phasecmds = []
        pump_rad_start = 0
        if self.pump_offset:
            #base the roll on self.a_inc
            roll = int(self.pump_offset/self.a_inc)
            #determine absolute value at this position from main
            zero_pump = self.pump_main["radii"][0]
            pump_rad_start = zero_pump - self.pump_main["radii"][roll]
            self._logger.debug(f"pump phase offset X value: {pump_rad_start}")
            self.working[:, 1] = np.roll(self.working[:, 1], roll)
            phasecmds.append(f"G0 G91 X{pump_rad_start:0.3f}")

        try:
            bf_target = self.bf_target
            dir = "" if self.forward else "-"
            #this reverses direction, but would also have to reverse list to truly be in reverse
            degrees_sec = (self.rpm * 360) / 60
            degrees_chunk = self.chunk * self.a_inc
            loop_start = None
            loop_end = None
            cmdlist = []
            cmdlist.append("G92 A0")
            cmdlist.append("M3 S1000")
            if len(phasecmds):
                cmdlist.extend(phasecmds)
            while self.running:
                #A-axis reset
                #cmdlist.append("G92 A0")
                #self._logger.info(f"x:{self.current_x} z:{self.current_z}")
                self.buffer = 0
                degrees_sec = (self.rpm * 360) / 60
                degrees_chunk = self.chunk * self.a_inc
                time_unit = self.a_inc/degrees_sec * 1000 #ms
                tms = round(time.time() * 1000)
                if loop_start:
                    self._logger.debug(f"loop time ms: {tms - loop_start}")
                loop_start = tms
                self.feedcontrol["current"] = tms
                
                #first chunk will be full size
                #next_interval = time_unit*self.chunk
                next_interval = int(degrees_chunk / degrees_sec * 1000)  # in milliseconds
                self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                #self._logger.info(f"Next interval at {self.rpm} RPM, {next_interval}, bf_target {bf_target}")
                current_angle = 0
                for i in range(0, len(self.working), self.chunk):
              
                    with self.rpm_lock:
                        if self.updated_rpm > 0:
                            #self._logger.info("Updating RPM")
                            self.rpm = self.updated_rpm
                            self.updated_rpm = 0.0
                            degrees_sec = (self.rpm * 360) / 60
                            next_interval = int(degrees_chunk / degrees_sec * 1000)  

                    feed = (360/self.a_inc) * self.rpm
                    cmdchunk = self.working[i:i+self.chunk]
                    #self.buffer = 0
                    #need to know the actual angle so we know where we are for ellipse
                    current_angle = i * self.a_inc
                    for cmd in cmdchunk:
                        x = cmd[1]
                        z = cmd[0]
                        mod = cmd[2]
                        #modify z values if we have elliptical chuck setting
                        if self.ellipse:
                            z = z + mod
                        current_angle = current_angle + self.a_inc

                        if self.b_adjust:
                            #self._logger.info(f"initial x, z: {x} {z}")
                            #initial test assume reference frame at -90 
                            bangle = math.radians(self.current_b - self.bref) *-1
                            x = x*math.cos(bangle) + z*math.sin(bangle)
                            z = -z*math.sin(bangle) + z*math.cos(bangle)
                            #self._logger.info(f"modified x, z: {x} {z}")

                        cmdlist.append(f"G93 G91 G1 A{dir}{self.a_inc} X{x:0.3f} Z{z:0.3f} F{feed:0.1f}")
                    #All modifications should be PRE injection
                    if self.inject:
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
        except Exception as e:
            self._logger.error(f"Exception in job thread: {e}", exc_info=True)
        self._logger.info("Thread ended")

    def _start_geo(self):
        #specific for geometric
        self._logger.debug("Starting geometric job")

        #this works a little different, as we need both radii and angles
        self.start_coords["x"] = self.current_x
        self.start_coords["z"] = self.current_z
        self.start_coords["a"] = 0.0
        self.running = True
        self.geo_radii, self.geo_angles = self.create_working_path(self.rock_main, 1)
        # Remove large negative/positive jumps at the end of geo_angles
        cleaned_radii = []
        cleaned_angles = []
        for i in range(len(self.geo_angles)):
            # Check difference to next angle (wrap at end)
            if i < len(self.geo_angles) - 1:
                diff = self.geo_angles[i+1] - self.geo_angles[i]
                if abs(diff) > 180:
                    # Stop before the large jump
                    break
            cleaned_radii.append(self.geo_radii[i])
            cleaned_angles.append(self.geo_angles[i])

        self.geo_radii = np.array(cleaned_radii)
        self.geo_angles = np.array(cleaned_angles)
        for each in self.geo_angles:
            self._logger.debug(each)
        self.jobThread = threading.Thread(target=self._geometric_thread).start()

    def _start_job(self):
        if self.running:
            return
        if self.rock_main and self.rock_main["type"] == "geometric":
            self._start_geo()
            return
        #additional array, might want to rethink how this works
        modifier = []
        mod_array = np.array(modifier)
        if self.rock_main:
            self.rock_work, _ = self.create_working_path(self.rock_main, self.r_amp)
        if self.pump_main:
            self.pump_work, _ = self.create_working_path(self.pump_main, self.p_amp)
            #Other modifictions
            if self.pump_invert:
                self.pump_work = np.array(self.pump_work)*-1
        if self.ellipse:
            e_vals = []
            for deg in np.arange(0, 360, self.a_inc):
                e_rad = self._ellipse_rad(deg)
                e_vals.append(e_rad)
            #difference values
            e_a = np.array(e_vals)
            mod_array = np.roll(e_a, -1) - e_a
    
        self.working = list(zip_longest(self.rock_work, self.pump_work, mod_array, fillvalue=0))
        self.working = np.array(self.working)
        self.start_coords["x"] = self.current_x
        self.start_coords["z"] = self.current_z
        self.start_coords["a"] = 0.0
        self.running = True
        self._logger.debug(self.working)
        self.jobThread = threading.Thread(target=self._job_thread).start()

    def _reset_gcode(self):
        gcode = []
        #reset A modulo
        self._logger.debug(f"current_a: {self.current_a}")
        theA = self.current_a % 360
        gcode.append(f"G92 A{theA}")
        x,z,a = self.start_coords["x"], self.start_coords["z"], self.start_coords["a"]
        if self.rock_main and not self.pump_main:
            #assume we are just going to back and then in/out
            gcode.append(f"G94 G90 G0 X{x}")
            gcode.append(f"G90 G0 Z{z} A{a}")
        if self.pump_main and not self.rock_main:
            gcode.append(f"G94 G90 G0 Z{z}")
            gcode.append(f"G0 X{x} A{a}")
        if self.pump_main and self.rock_main:
            gcode.append(f"G94 G90 G0 Z{z} X{x}")
            gcode.append(f"G0 A0")
        gcode.append("M30")
        self.reset_cmds = False
        self._printer.commands(gcode)
        

    def _stop_job(self):
        if not self.running:
            return
        self.running = False
        self.stopping = True

        if self.auto_reset:
            self.reset_cmds = True
            
    def write_gcode(self):
        filename = time.strftime("%Y%m%d-%H%M") + "roseengine.gcode"
        path_on_disk = "{}/{}".format(self._settings.getBaseFolder("watched"), filename)
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
        )
    
    def on_api_command(self, command, data):
        self._logger.debug(command)
        self._logger.debug(data)

        if command == "load_rosette":
            filePath = data["filepath"]
            type = data["type"]
            rosette = self.load_rosette(filePath)
            s = rosette["special"]
            if type == "rock":
                self.rock_main = rosette
                r = list(self.rock_main["radii"])
                a = list(self.rock_main["angles"])
                data = dict(type="rock", special=s, radii=r, angles=a, maxrad=self.rock_main["max_radius"], minrad=self.rock_main["min_radius"])
                
            elif type == "pump":
                self.pump_main = rosette
                r = list(self.pump_main["radii"])
                a = list(self.pump_main["angles"])
                data = dict(type="pump", special=s, radii=r, angles=a, maxrad=self.pump_main["max_radius"], minrad=self.pump_main["min_radius"])
                #self._logger.info(f"Loaded pump rosette: {self.pump_main}")
            
            #self._logger.info(data)
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
            amp = data["amp"]
            peak = data["peak"]
            phase = data["phase"]
            returndata = dict(type=rose_type, radii=None, angles=None, special=False, maxrad=f"{wave_type}", minrad=f"Amp:{amp}, Periods:{peak}")
            #do some stuff
            rosette = self._parametric_sine(data)
            self._logger.debug(rosette)
            if rose_type == "rock":
                self.rock_main = rosette
            else:
                self.pump_main = rosette
            self._plugin_manager.send_plugin_message('roseengine', returndata)
            return
        
        if command == "geometric":
            #list of stages
            import plotly.graph_objects as go
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
            self._logger.debug(stage_data)
            rosette = self._geometric(stage_data)
            self.rock_main = rosette
            r = list(self.rock_main["radii"])
            a = list(self.rock_main["angles"])
            s=True
            maxrad = self.rock_main["max_radius"]
            minrad = self.rock_main["min_radius"]
            #self._logger.debug(r)
            #self._logger.debug(a)
            title=""

            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=r,
                theta=a,  # plotly expects degrees
                mode='lines',
                
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
                    radialaxis=dict(visible=False,showline=False,autorange=True),
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

            json_figure = fig.to_plotly_json()

            returndata = dict(type="geo", special=s, graph=json_figure)

            self._plugin_manager.send_plugin_message('roseengine', returndata) 

   
        if command == "start_job":
            self.rpm = float(data["rpm"])
            self.r_amp = float(data["r_amp"])
            self.p_amp = float(data["p_amp"])
            self.forward = bool(data["forward"])
            self.pump_invert = bool(data["pump_invert"])
            self.pump_offset = float(data["pump_offset"])
            self.b_adjust = bool(data["b_adjust"])
            self.bref = float(data["bref"])
            self._logger.info("ready to start job")
            if float(data["e_ratio"]) > 1.0 and not self.geometric:
                rad = float(data["e_rad"])
                ratio = float(data["e_ratio"])
                self.ellipse = {"a" : rad, "ratio" : ratio }
            else:
                self.ellipse = None
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
        if self.recording:
            self.recorded.append(cmd)

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
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


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Roseengine Plugin"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
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
