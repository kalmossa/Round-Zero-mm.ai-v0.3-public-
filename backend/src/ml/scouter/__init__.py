"""
Package SCOUTER de MM.AI — tout le calcul du scouter_rating vit ICI.

Contenu :
  - calc.py : compute_scouter / compute_scouter_debug (v2.0)

NOTE (juin 2026) : refonte du Scouter prévue APRÈS que l'Elo soit calibré
(voir claude_scouter.md, à venir). Pour l'instant on ne fait que ranger le code.

Ce __init__ ré-exporte l'API publique pour `from ml.scouter import X`.
"""

from .calc import compute_scouter, compute_scouter_debug  # noqa: F401
from .legacy import FighterScouter  # noqa: F401  (ancienne classe d'analyse)
