# LE-RoseEngine

The LE-RoseEngine plugin is designed to integrate with OctoPrint to allow CNC-based real-time control in a manner analogous to a Rose Engine or other ornamental lathes. This plugin provides an intuitive interface for configuring the parameters, simulating the resulting patterns, and sending commands to the connected hardware for real-time operation.

## Features
- **SVG-based rosettes**: Rocking and pumping rosettes are created as continuous path SVG files. Arbitrary centers can be defined by creating a circle object with the id `center`
- **Arbitrary plane**: Rosettes can rock or pump in an arbitrary plane based on the defined tool angle (B-axis angle)
- **Elliptical chuck emulation**: Any defined rosette can follow an elliptical rather than circular pattern 
- **Geometric Chuck**: Define and adjust the stages of the chuck, including radius, gear ratios, and phase offsets.
- **Pattern Simulation**: Visualize the resulting patterns directly in the browser before executing them on the hardware.
- **Hardware Control**: Send commands to the connected Rose Engine hardware for real-time operation. 

## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/paukstelis/LE-RoseEngine/archive/master.zip

## Configuration

The plugin provides several configuration options to customize the behavior of the geometric chuck and the resulting patterns. These options can be accessed through the plugin's settings in the OctoPrint interface.
