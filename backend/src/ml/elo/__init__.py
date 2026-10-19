"""
Package ELO de MM.AI — tout le moteur de notation Elo vit ICI.

Contenu :
  - engine.py   : le calcul Elo (parcours d'historique, point fixe, rescale)
  - leagues.py  : barème de force des ligues (data/league_coefficients.json)
  - explain.py  : OUTIL de test — détaille l'Elo d'un fighter combat par combat

Données : data/league_coefficients.json (barème éditable).
Doc      : claude_elo.md (à la racine du projet).

Ce __init__ ré-exporte l'API publique pour que `from ml.elo import X` marche.
"""

from .engine import (  # noqa: F401
    # calcul principal
    compute_elo_from_history,
    compute_elo_timeline,
    compute_elo_timeline_from_history,
    batch_compute_all_elos,
    # estimation adversaire
    get_opponent_elo_and_certainty,
    estimate_opp_elo_from_record,
    estimate_opp_elo_from_rank,
    classify_promotion,
    # init / facteurs
    elo_from_fm,
    k_factor,
    finish_multiplier,
    # constantes
    _ELO_DEFAULT,
    _ELO_MIN,
    _ELO_MAX,
    # compat legacy
    DynamicEloCalculator,
)
from .leagues import (  # noqa: F401
    get_league_strength,
    strength_to_base_elo,
    strength_to_tier,
    country_default_strength,
)
