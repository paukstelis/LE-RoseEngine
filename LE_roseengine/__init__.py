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
from svgelements import *
from itertools import zip_longest
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
        #contains all the raw values that can be transformed into working values
        self.rock_main = {}
        self.pump_main = {}
        self.rock_work = []
        self.pump_work = []
        self.working = []
        self.last_position = None
        self.chunk = 10
        self.buffer = 0
        self.buffer_received = True
        self.modifiers = {"amp": 1, "phase": 0, "forward": True}

        self.jobThread = None
        self.buffer = None
        self.feedcontrol =  {"current": 0, "next": 0}
        self.start_coords = {"x": None, "z": None, "a": None}
        self.ms_threshold = 100

        self.rpm = 0
        self.phase = 0
        self.amp = 1
        self.forward = True

    def initialize(self):
        self.datafolder = self.get_plugin_data_folder()
        self._event_bus.subscribe("LATHEENGRAVER_SEND_POSITION", self.get_position)
        #self._event_bus.unsubscribe...

    def get_settings_defaults(self):
        return dict(
            increment=0.5,
            smooth_points=12,
            tool_length=135,
            default_segments=1,
            chunks=5,
            )
    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.initialize()

    @property
    def allowed(self):
        if self._settings is None:
            return ""
        else:
            return str(self._settings.get(["allowed"]))
        
    def get_settings_defaults(self):
            return ({'allowed': 'png, gif, jpg, txt, stl, svg'})

    def get_extension_tree(self, *args, **kwargs):
        return {'model': {'png': ["png", "jpg", "jpeg", "gif", "txt", "stl", "svg"]}}
    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/roseengine.js", "js/plotly-latest.min.js"],
            "css": ["css/roseengine.css"],
            "less": ["less/roseengine.less"]
        }
    
    def on_event(self, event, payload):
        if event == "plugin_latheengraver_send_position":
            self.get_position(event, payload) 
    
    def get_position(self, event, payload):
        #self._logger.info(payload)
        self.current_x = payload["x"]
        self.current_z = payload["z"]
        self.current_a = payload["a"]
        self.buffer = payload["bf"]
        #self._logger.info(f"buffer from payload {self.buffer}")
        self.buffer_received = True
    
    def create_working_path(self, rosette, amp):
        self._logger.info(rosette["radii"][0])
        rl = rosette["radii"]
        radii = np.array(rl)
        #first apply any amplitude modifiers
        radii = np.array(radii) * amp
        #generate differences
        newradii = np.diff(radii)

        return newradii
    
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

    def resample_path_to_polar(self, matrix, path: Path, center=(0, 0), points=720):
        total_length = path.length()
        step = total_length / points
        cx, cy = center
        centerpoint  = Point(cx, cy)
        angles = []
        radii = []
        #this should all be possible with svgeelements functions, but I don't know how to do it yet
        for i in range(points):
            pos = i * step
            pt = path.point(pos / total_length)
            dx = pt.x - cx
            dy = pt.y - cy
            tp = matrix.transform_point(Point(dx, dy))
            r = math.hypot(tp[0], tp[1])
            theta = i * (360 / points)
            angles.append(theta)
            radii.append(r)
        return angles, radii

    def load_rosette(self, filepath):
        folder = self._settings.getBaseFolder("uploads")
        filename = f"{folder}/{filepath}"
        center = None
        #Do some error checking to verify it is SVG
        svg = SVG.parse(filename, reify=True)
        for e in svg.elements():
            if getattr(e, 'id', None) == 'center':
                if isinstance(e, (Circle, Ellipse)):
                    center = (e.cx, e.cy)

        if not center:
            self._logger.error("No center id found in SVG file.")
            return
        
        matrix = svg[0].transform.inverse()
        transformed_center = matrix.transform_point(Point(center[0], center[1]))
        for e in svg.elements():
            if isinstance(e, Path):
                angles, radii = self.resample_path_to_polar(matrix, e, center=center, points=int(360/self.a_inc))
                np.array(angles)
                np.array(radii)
        #circularize
        angles = np.append(angles, angles[0])
        radii = np.append(radii, radii[0])

        #get radius info
        max_radius = np.max(radii)
        min_radius = np.min(radii)
        max_idx = np.argmax(radii)
        #sets max radius of rosette at A=0 for easy reference
        radii = np.roll(radii, -max_idx)
        rosette = {"radii": radii, "angles": angles, "max_radius": max_radius, "min_radius": min_radius, "center": transformed_center}
        #self._logger.info(rosette)
        return rosette

    def _job_thread(self):  
        self._logger.info("Starting job thread")
        bf_target = 80
        dir = "" if self.forward else "-"
        
        while self.running:
            #A-axis reset
            cmdlist = []
            cmdlist.append("G92 A0")
            self.buffer = 0
            bf_target = 60 #should be able to calculate this value based on rpm and 0.5sec report time
            tms = round(time.time() * 1000)
            self.feedcontrol["current"] = tms
            degrees_sec = (self.rpm * 360) / 60
            degrees_chunk = self.chunk * self.a_inc
            next_interval = int(degrees_chunk / degrees_sec * 1000)  # in milliseconds
            self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval

            for i in range(0, len(self.working), self.chunk):
                feed = (360/self.a_inc) * self.rpm
                cmdchunk = self.working[i:i+self.chunk]
                #self.buffer = 0
                for cmd in cmdchunk:
                    #can add variable conditional if  we want to swap X and Z
                    cmdlist.append(f"G93 G91 G1 A{dir}{self.a_inc} X{cmd[1]:0.3f} Z{cmd[0]:0.3f} F{feed:0.1f}")
                #self._logger.info(cmdlist)
                if self.inject:
                    cmdlist[-1] = self._update_injection(cmdlist[-1], self.inject)
                    self.inject = None
                # Loop until we are ready to send the next chunk
                tms = round(time.time() * 1000)
                while self.feedcontrol["next"] - tms > 10 or self.buffer < bf_target:
                        tms = round(time.time() * 1000)
                        if not self.running:
                            break

                self._logger.info(f"buffer is now at {self.buffer}")
                self._printer.commands(cmdlist)
                self.buffer_received = False
                degrees_sec = (self.rpm * 360) / 60
                next_interval = int(degrees_chunk / degrees_sec * 1000)
                self.feedcontrol["current"] = round(time.time() * 1000)
                self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                cmdlist = []
                self.last_position = i
                if not self.running:
                    break
        self._logger.info("Thread ended")

    def _start_job(self):
        if self.running:
            return
        if self.rock_work:
            self.rock_work = self.create_working_path(self.rock_main, self.amp)
            self._logger.info(f"Rock work list: {self.rock_work}")
        if self.pump_work:
            self.pump_work = self.create_working_path(self.pump_main, self.pump_amp)
            self._logger.info(f"Pump work list: {self.rock_work}")
        self.working = list(zip_longest(self.rock_work, self.pump_work, fillvalue=0))
        self._logger.info(f"Working list: {self.working}")
        self.start_coords["x"] = self.current_x
        self.start_coords["z"] = self.current_z
        self.start_coords["a"] = 0.0
        self.running = True
        #self._logger.info(self.start_coords)
        self.jobThread = threading.Thread(target=self._job_thread).start()

    def _stop_job(self):
        if not self.running:
            return
        self.running = False

    def is_api_protected(self):
        return True
    
    def get_api_commands(self):
        return dict(
            start_job=[],
            stop_job=[],
            jog=[],
            load_rosette=[],
            get_arc_length=[],
            goto_start=[]
        )
    
    def on_api_command(self, command, data):
        self._logger.info(command)
        self._logger.info(data)

        if command == "load_rosette":
            filePath = data["filepath"]
            type = data["type"]
            rosette = self.load_rosette(filePath)
            if type == "rock":
                self.rock_main = rosette
                r = list(self.rock_main["radii"])
                a = list(self.rock_main["angles"])
                data = dict(type="rock", radii=r, angles=a, maxrad=self.rock_main["max_radius"], minrad=self.rock_main["min_radius"])
                
            elif type == "pump":
                self.pump_main = rosette
                r = list(self.pump_main["radii"])
                a = list(self.pump_main["angles"])
                data = dict(type="pump", radii=r, angles=a, maxrad=self.pump_main["max_radius"], minrad=self.pump_main["min_radius"])
                self._logger.info(f"Loaded pump rosette: {self.pump_main}")
            
            self._logger.info(data)
            self._plugin_manager.send_plugin_message('roseengine', data)
            return
        
        if command == "start_job":
            self.rpm = float(data["rpm"])
            self.amp = float(data["amp"])
            self.forward = bool(data["forward"])
            self._logger.info("ready to start job")
            self._start_job()

        if command == "stop_job":
            self._logger.info("stoping job")
            self._stop_job()

        if command == "jog":
            direction = data["direction"]
            if direction == 'down':
                dir = "Z"
                dist = "-1"
            elif direction == 'up':
                dir = "Z"
                dist = "1"
            elif direction == 'left':
                dir = "X"
                dist = "-1"
            elif direction == 'right':
                dir = "X"
                dist = "1"

            cmd = f"G94 G91 G21 G1 {dir}{dist} F1000"
            #if we are running, we can possibly just add to the last command in the chunk
            chunk_cmd = (dir, float(dist))
            if self.running:
                if not self.inject:
                    self.inject = chunk_cmd
                    self._logger.info(f"Got inject: {chunk_cmd}")
                    return
            else:
                self._printer.commands(cmd)

        if command == "goto_start":
            if self.running:
                return
            x,z,a = self.start_coords["x"], self.start_coords["z"], self.start_coords["a"]
            cmd = f"G94 G90 G0 X{x} Z{z} A{a}"
            self._printer.commands(cmd)
            return
            




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
        "octoprint.filemanager.extension_tree": __plugin_implementation__.get_extension_tree
    }
