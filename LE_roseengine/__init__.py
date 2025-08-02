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
        self.last_position = None
        self.chunk = 5
        self.modifiers = {"amp": 1, "phase": 0, "forward": True}

        self.jobThread = None
        self.buffer = None
        self.feedcontrol =  {"current": 0, "next": 0}
        self.ms_threshold = 100

        self.rpm = 0
        self.phase = 0
        self.amp = 1
        self.forward = True

    def initialize(self):
        self.datafolder = self.get_plugin_data_folder()
        self.smooth_points = int(self._settings.get(["smooth_points"]))
        self.a_inc  = float(self._settings.get(["increment"]))
        self.tool_length = float(self._settings.get(["tool_length"]))
        self._event_bus.subscribe("SEND_POSITION", self.get_position)
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
    
    def get_position(self, event, payload):
        self.current_x = payload["x"]
        self.current_z = payload["z"]
        self.current_a = payload["a"]
        self._logger.info(f"Payload: {self.current_x} {self.current_z} {self.current_a}")
    
    def create_working_path(self, rosette):
        phase = self.phase
        amp = self.amp

        radii = rosette["radii"]
        #first apply any amplitude modifiers
        radii = np.array(radii) * amp
        #generate differences
        newradii = np.diff(radii)

        return newradii
    
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
                if not isinstance(e.segments[-1], Close):
                    self._logger.info("Path isn't closed. Abort")
                    return
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
        self._logger.info(rosette)
        return rosette

    def _job_thread(self):  

        tms = round(time.time() * 1000)
        self.feedcontrol["current"] = tms
        degrees_sec = (self.rpm * 360) / 60
        degrees_chunk = self.chunk * self.a_inc
        next_interval = degrees_chunk / degrees_sec * 1000  # in milliseconds
        self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
        dir = "" if self.forward else "-"

        while self.running:
            #A-axis reset
            cmdlist = []
            cmdlist.append("G92 A0")
            for i in range(0, len(self.rock_work), self.chunk):
                tms = round(time.time() * 1000)
                feed = (360/self.a_inc) * self.rpm
                cmdchunk = self.rock_work[i:i+self.chunk]
                for cmd in cmdchunk:
                    cmdlist.append(f"G93 G91 G0 A{dir}{self.a_inc} Z{cmd:0.2f} F{feed:0.1f}")
                if self.inject:
                    cmdlist.append(self.inject)
                    self.inject = None
                # Loop until we are ready to send the next chunk
                while self.feedcontrol["next"] - tms > self.ms_threshold:
                    tms = round(time.time() * 1000)
                # Reset timestamps and send command chunk, recalculate next interval if RPM has changed
                self._printer.send_command(cmdlist)
                degrees_sec = (self.rpm * 360) / 60
                next_interval = degrees_chunk / degrees_sec * 1000
                self.feedcontrol["current"] = round(time.time() * 1000)
                self.feedcontrol["next"] = self.feedcontrol["current"] + next_interval
                
                cmdlist = []
                self.last_position = i
                if not self.running:
                    break
            if not self.running:
                break

        """        
        while self.running:
            #A-axis reset
            cmdlist.append("G92 A0")
            for i in range(0, len(self.rock_work), self.chunk):
                #feed = self.a_inc * 360 * self.rpm
                feed = (360/self.a_inc) * self.rpm
                cmdchunk = self.rock_work[i:i+self.chunk]
                for cmd in cmdchunk:
                    cmdlist.append(f"G93 G91 G0 A{self.a_inc} Z{cmd:0.2f} F{feed:0.1f}")
                if self.inject:
                    cmdlist.append(self.inject)
                    self.inject = None
                while self.buffer < 95:
                    time.sleep(0.1)
                self._printer.send_command(cmdlist)
                cmdlist = []
                self.last_position = i
                time.sleep(0.01)
                if not self.running:
                    break
            if not self.running:
                break
        """

    def _start_job(self):
        if self.running:
            return
        self.running = True
        self.jobThread = threading.Thread(target=self._job_thread)
        self.jobThread.start()

    def _stop_job(self):
        if not self.running:
            return
        self.running = False
        self.jobThread.stop()

    def hook_gcode_received(self, comm_instance, line, *args, **kwargs):
        if 'MPos' in line or 'WPos' in line and self.running:
            match = re.search(r'Bf:(\d+),\d+', line)
            if not match is None:
                self.buffer = int(match.groups(1)[0])

    def is_api_protected(self):
        return True
    
    def get_api_commands(self):
        return dict(
            job_control=[],
            move=["direction", "distance", "axis"],
            load_rosette=[],
            get_arc_length=[],
            goto_start=[]
        )
    
    def on_api_command(self, command, data):
        
        if command == "load_rosette":
            filePath = data["filepath"]
            type = data["type"]
            rosette = self.load_rosette(filePath)
            if type == "rock":
                self.rock_main = rosette
                #self.rock_work = rosette["radii"].tolist()
                self._logger.info(f"Loaded rock rosette: {self.rock_main}")
            elif type == "pump":
                self.pump_main = rosette
                #self.pump_work = rosette["radii"].tolist()
                self._logger.info(f"Loaded pump rosette: {self.pump_main}")
            return
        
        if command == "job_control":
            if "start" in data:
                #collect all our settings
                self._start_job()
            if "stop" in data:
                self._stop_job()

        if command == "move":
            direction = data.get("direction")
            distance = float(data.get("distance"))
            axis = data.get("axis")
            cmd = f"G94 G91 G21 G0 {axis}{direction}{distance} F1000"
            if self.running:
                if not self.inject:
                    self.inject = cmd
                    return
            else:
                self._printer.send_command(cmd)

        if command == "goto_start":
            cmd = f"G94 G90 G0 X{self.start_x} Z{self.start_z} A{self.start_A}"
            self._printer.send_command(cmd)
            




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
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.hook_gcode_received
    }
