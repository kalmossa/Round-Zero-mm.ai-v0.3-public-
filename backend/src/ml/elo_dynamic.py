# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
SHIM de compatibilité — le code Elo a déménagé dans le package `ml.elo`.

  ancien : from ml.elo_dynamic import compute_elo_from_history
  nouveau : from ml.elo import compute_elo_from_history   (préférer celui-ci)

Ce fichier ne fait que ré-exporter depuis ml/elo/engine.py pour ne casser
aucun import existant. Le VRAI code est dans backend/src/ml/elo/engine.py.
"""

from ml.elo.engine import *        # noqa: F401,F403
from ml.elo.engine import (        # noqa: F401  (noms privés non pris par *)
    _ELO_DEFAULT,
    _ELO_MIN,
    _ELO_MAX,
    compute_elo_from_history,
    compute_elo_timeline_from_history,
    batch_compute_all_elos,
    elo_from_fm,
    DynamicEloCalculator,
)
