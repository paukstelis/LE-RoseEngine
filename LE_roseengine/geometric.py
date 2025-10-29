import math
import numpy as np
import logging
from fractions import Fraction
class Stage:
    def __init__(self, radius, p, q, phase=0.0, translation=0.0):
        # p or q may be negative to indicate inverted direction (previously 'internal')
        self.R = float(radius)
        self.p = int(p)
        self.q = int(q) if int(q) != 0 else 1
        self.phase = float(phase)
        self.translation = float(translation)

class GeometricChuck:
    def __init__(self):
        self.stages = []
        self._logger = logging.getLogger("octoprint.plugins.roseengine")
    def add_stage(self, radius, p, q, phase=0.0, translation=0.0):
        # p or q can be negative to indicate reversed direction (no 'internal' flag)
        self.stages.append(Stage(radius, p, q, phase, translation))

    def _angle_multipliers(self):
        """
        Compute Mn using integer p/q. Negative p or q encodes direction.
        Mn = Mn-1 + product_{k=1..n-1} (-V_k)
        where V_k = p_k / q_k (signed).
        """
        if not self.stages:
            return []

        Vs = []
        for st in self.stages:
            # V may be negative if p or q carry a negative sign
            Vs.append(st.p / st.q)
        self._logger.info(Vs)
        M = [1.0]
        for n in range(1, len(Vs)):
            prod = 1.0
            for j in range(0, n):
                prod *= -Vs[j]
            M.append(M[-1] + prod)
        self._logger.info(M)

        return M

    def required_periods(self):
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
        M = self._angle_multipliers()

        x = np.zeros_like(t)
        y = np.zeros_like(t)

        for st, Mn in zip(self.stages, M):
            theta_i = Mn * t + st.phase
            effective_R = st.R * (1.0 + st.translation)
            x += effective_R * np.cos(theta_i)
            y += effective_R * np.sin(theta_i)

        return t, x, y

    def generate_polar_path(self, num_points=2000, t_range=(0.0, 2*np.pi)):
        t, x, y = self.generate_xy(num_points=num_points, t_range=t_range)
        r = np.hypot(x, y)
        phi = np.arctan2(y, x)
        phi = np.unwrap(phi)
        return t, phi, r