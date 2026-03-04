import os 
import time
import math
import numpy as np
from svgpathtools import svg2paths, Path
from scipy.interpolate import CubicSpline
from scipy.interpolate import RectBivariateSpline
from scipy.integrate import quad
from scipy.optimize import root_scalar

#this is being adapted from Profiler plugin

def createsplines(_plugin, filepath):
    folder = _plugin._settings.getBaseFolder("uploads")
    filename = f"{folder}/{filepath}"
    ind_v = []
    dep_v = []
    datapoints = []
    segments = []
    current_segment = []
    with open(filename,"r") as file:
        for line in file:
            stripped_line = line.strip()
            if stripped_line == ";X":
                axis = 'X'
            if stripped_line == ";Z":
                axis = 'Z'
            if stripped_line == "NEXTSEGMENT":
                segments.append(current_segment)
                current_segment = []
                continue
            if not stripped_line.startswith(";"):
                # Split the line by comma and convert to floats
                try:
                    parts = [float(x) for x in stripped_line.split(",")]
                    # Pad to 3 elements
                    while len(parts) < 3:
                        parts.append(0.0)
                    current_segment.append(parts)
                except ValueError:
                    pass
    if not len(segments):
        segments.append(current_segment)
    
    arr = np.array(segments)
    #sort, must be increasing
    if axis == 'Z':
        for seg in segments:
            seg.sort(key=lambda x: x[1])
        ind_v = [x[1] for x in segments[0]]
        dep_v = [x[0] for x in segments[0]]
        ind_vals = arr[0, :, 1]
        A_vals = arr[:, 0, 2]
        baseline_dep = arr[0, :, 0]
        dep_raw = arr[:, :, 0]
        dep_grid = dep_raw - baseline_dep

    if _plugin.axis == 'X':
        for seg in segments:
            seg.sort(key=lambda x: x[0])
        ind_v = [x[0] for x in segments[0]]
        dep_v = [x[1] for x in segments[0]]
        ind_vals = arr[0, :, 0]
        A_vals = arr[:, 0, 2]
        baseline_dep = arr[0, :, 1]
        dep_raw = arr[:, :, 1]
        dep_grid = dep_raw - baseline_dep

    _plugin.spline = CubicSpline(ind_v, dep_v)


    #do any ind_val offsets here?
    current_max = ind_v[-1]
    current_min = ind_v[0]
    
    sort_idx = np.argsort(ind_vals)
    ind_vals = ind_vals[sort_idx]
    dep_grid = dep_grid[:, sort_idx]

    _plugin._logger.info(ind_vals)
    _plugin._logger.info(dep_grid)
    A_radians = np.deg2rad(np.mod(A_vals, 360.0))
    if A_vals[-1] != 360:
        A_radians = np.append(A_radians, 2 * np.pi)
        dep_grid = np.vstack([dep_grid, dep_grid[0]])
    _plugin.a_spline = RectBivariateSpline(A_radians, ind_vals, dep_grid, kx=3, ky=3, s=0)

def ovality_mod(_plugin, x, a_deg):

    zdiff = _plugin.spline(x)
    a_wrapped = np.deg2rad(np.mod(a_deg, 360.0))
    adiff = _plugin.a_spline.ev(a_wrapped, x)
    _plugin._logger.debug(f"Z diff from X: {zdiff} Z diff from rot {adiff} at {a_deg}")
    #does it make sense to have both of these or can I just use adiff?
    #after contemplation, this won't be useful with recorded gcode, so it makes sense to just use adiffink
    #need to have zdiff as well if we want to start at zero and just traverse, but make it some setting
    if _plugin.use_zdiff:
        return zdiff+adiff
    else:
        return adiff

def convert_svg(_plugin, SVG_FILE):
    folder = _plugin._settings.getBaseFolder("uploads")
    filename = f"{folder}/{SVG_FILE}"
    paths, attributes = svg2paths(filename)
    if not paths:
        raise ValueError("No paths in SVG")

    profile_path = None
    axis_path = None

    for path, attr in zip(paths, attributes):
        pid = attr.get("id", "").lower()
        if pid == "axis":
            axis_path = path
        else:
            profile_path = path

    if profile_path is None:
        raise ValueError("No profile path found in SVG")
    xmin, xmax, ymin, ymax = profile_path.bbox()
    #total x distance in mm
    xdist = abs(xmax - xmin)
    zdist = abs(ymax - ymin)
    samples_per_rev = max(1, int(round(360 / _plugin.a_inc)))
    mm_per_step = _plugin.curve_mm_rev / samples_per_rev
    samples = int(xdist / mm_per_step)
    _plugin._logger.debug(f"Calculating curvilinear path samples. spr: {samples_per_rev}, mm_step: {mm_per_step}, samples: {samples}")
    t_vals = np.linspace(0.0, 1.0, samples)
    curve_pts = np.array([profile_path.point(t) for t in t_vals])
    x_design = curve_pts.real - xmin
    z_design = curve_pts.imag
    z_design = z_design - ymin
    svgspline = CubicSpline(x_design, z_design)
    sample_positions = np.arange(samples, dtype=float) * mm_per_step
    sample_positions = np.clip(sample_positions, 0.0, xdist)
    curve_z = svgspline(sample_positions)
    _plugin.curve["xstep"] = mm_per_step
    _plugin.curve["xdist"] = xdist
    _plugin.curve["zdist"] = zdist
    _plugin.curve["x"] = sample_positions #probably only need to store this for coordinate case...
    _plugin.curve["z"] = curve_z
    _plugin._logger.debug(_plugin.curve)

   