"""
SHIM de compatibilité — le barème de ligues a déménagé dans `ml.elo.leagues`.
Le VRAI code est dans backend/src/ml/elo/leagues.py.
"""

from ml.elo.leagues import *        # noqa: F401,F403
from ml.elo.leagues import (        # noqa: F401
    get_league_strength,
    strength_to_base_elo,
    strength_to_tier,
    country_default_strength,
)
