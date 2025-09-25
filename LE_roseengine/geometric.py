import numpy as np
from fractions import Fraction
import math
class Stage:
    def __init__(self, radius, p, q, phase=0.0, internal=False, translation=0.0):
        """
        radius : float      # distance from this wheel's center to the next pivot (or pen if last)
        p, q    : ints      # gear ratio p:q relative to previous stage
        phase   : float     # radians, additive phase for this stage
        internal: bool      # True = internal gearing (angle sign flips)
        """
        self.R = float(radius)
        self.p = float(p)
        self.q = float(q)
        self.phase = float(phase)
        self.internal = bool(internal)
        self.translation = float(translation)

class GeometricChuck:
    def __init__(self):
        self.stages = []
        self.pen_radius = 0.0  # extra offset on the last stage (like a hole radius on final wheel)
        self.pen_phase  = 0.0  # pen’s local phase on the last wheel

    def add_stage(self, radius, p, q, phase=0.0, internal=False, translation=0.0):
        self.stages.append(Stage(radius, p, q, phase, internal, translation))

    def set_pen(self, radius, phase=0.0):
        """Optional: pen offset on the last stage."""
        self.pen_radius = float(radius)
        self.pen_phase  = float(phase)

    def _angle_multipliers(self):
        """
        Returns cumulative multipliers a_i such that
        theta_i(t) = a_i * t + phase_i_eff
        where a_i = Π_{j=1..i} s_j * (p_j/q_j), s_j = -1 for internal, +1 for external.
        """
        
        a = []
        acc = 1.0
        for st in self.stages:
            ratio = Fraction(st.p).limit_denominator(1000) / Fraction(st.q).limit_denominator(1000)
            s = -1.0 if st.internal else 1.0
            acc *= s * ratio
            a.append(acc)
        return a
    
    def required_periods(self):
        """
        Find number of 2π cycles needed for a closed curve,
        accounting for dependent angular frequencies.
        """
        if not self.stages:
            return 1
        multipliers = self._angle_multipliers()
        # Convert to Fractions for accurate LCM calculation
        fracs = [Fraction(m).limit_denominator(1000) for m in multipliers]
        denoms = [abs(frac.denominator) for frac in fracs]
        # Remove duplicates and dependent multiples
        unique_denoms = set(denoms)
        return math.lcm(*unique_denoms)

    def generate_xy(self, num_points=2000, t_range=(0.0, 2*np.pi)):
        if not self.stages:
            raise ValueError("No stages added.")

        t = np.linspace(t_range[0], t_range[1], num_points)
        a = self._angle_multipliers()

        x = np.zeros_like(t)
        y = np.zeros_like(t)

        for st, ai in zip(self.stages, a):
            theta_i = ai * t + st.phase
            # apply translation offset
            effective_R = st.R * (1.0 + st.translation)
            x += effective_R * np.cos(theta_i)
            y += effective_R * np.sin(theta_i)

        if self.pen_radius != 0.0:
            theta_last = a[-1] * t + (self.stages[-1].phase + self.pen_phase)
            x += self.pen_radius * np.cos(theta_last)
            y += self.pen_radius * np.sin(theta_last)

        return t, x, y

    def generate_polar_path(self, num_points=2000, t_range=(0.0, 2*np.pi)):
        """
        Convert the planar path to polar coordinates relative to the fixed origin.
        For plotting on a polar axis, use angle = phi(t), radius = r(t).
        """
        t, x, y = self.generate_xy(num_points=num_points, t_range=t_range)
        r   = np.hypot(x, y)
        phi = np.unwrap(np.arctan2(y, x))
        return t, phi, r