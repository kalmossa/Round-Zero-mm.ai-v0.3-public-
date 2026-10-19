# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
SHIM de compatibilité — le code Scouter a déménagé dans le package `ml.scouter`.
Le VRAI code est dans backend/src/ml/scouter/calc.py.

  ancien : from ml.scouter_calc import compute_scouter
  nouveau : from ml.scouter import compute_scouter   (préférer celui-ci)
"""

from ml.scouter.calc import *      # noqa: F401,F403
from ml.scouter.calc import compute_scouter, compute_scouter_debug  # noqa: F401
