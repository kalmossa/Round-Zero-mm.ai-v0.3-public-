"""
mm.ai - barème de force des ligues MMA (pour le moteur Elo).

Remplace l'ancien système des 5 tiers en dur par une table de données
extensible (data/league_coefficients.json). Chaque ligue a un score de force
`strength` 0-100 (100 = UFC). On en déduit :
  - base_elo  : l'Elo d'un adversaire INCONNU qui combat dans cette ligue
  - tier      : un bucket 0-4 (sert au spread + certitude, repris d'elo_dynamic)

Ordre de résolution quand on a un nom d'événement :
  1. Ligue reconnue (nom ou alias)         -> sa force propre
  2. Pas de ligue mais un pays détecté     -> défaut du pays (country_defaults)
  3. Rien                                   -> global_default (le + bas)

POUR ÉTENDRE LE BARÈME : édite data/league_coefficients.json (voir claude_elo.md
pour le prompt qui génère les 50-100 ligues), puis relance calculate_all_elos.
"""

from __future__ import annotations

import json
import re as _re
from pathlib import Path
from typing import Dict, Optional

# data/league_coefficients.json (remonte depuis backend/src/ml/elo/)
_JSON_PATH = Path(__file__).resolve().parents[4] / "data" / "league_coefficients.json"

# -- Conversion strength (0-100) -> base_elo --------------------------------
# base_elo = ELO_FLOOR + strength * ELO_PER_POINT
_ELO_FLOOR     = 700.0
_ELO_PER_POINT = 10.5     # strength 100 -> 1750 ; 50 -> 1225 ; 10 -> 805
_GLOBAL_FALLBACK_STRENGTH = 6.0   # si le JSON est introuvable


def strength_to_base_elo(strength: float) -> float:
    return _ELO_FLOOR + float(strength) * _ELO_PER_POINT


def strength_to_tier(strength: float, tier_hint: Optional[int] = None) -> int:
    """Bucket 0-4 (pour réutiliser les tables spread/certitude par tier)."""
    if tier_hint is not None:
        return int(tier_hint)
    if strength >= 75: return 4
    if strength >= 50: return 3
    if strength >= 30: return 2
    if strength >= 12: return 1
    return 0


# -- Adjectifs/gentilés -> clé pays (pour la détection pays dans un event) ---
_COUNTRY_KEYWORDS = {
    "russia": ["russia", "russian", "russie", "moscow"],
    "brazil": ["brazil", "brazilian", "brasil", "brasileiro", "sao paulo"],
    "usa": ["usa", "american", "united states", "vegas", "las vegas", "california", "texas", "florida"],
    "japan": ["japan", "japanese", "tokyo", "saitama", "osaka"],
    "poland": ["poland", "polish", "polska", "warsaw"],
    "kazakhstan": ["kazakhstan", "kazakh", "almaty", "astana"],
    "china": ["china", "chinese", "shanghai", "beijing"],
    "united kingdom": ["england", "british", "london", "manchester", "uk ", "scotland", "wales"],
    "france": ["france", "french", "paris", "français"],
    "canada": ["canada", "canadian", "montreal", "toronto"],
    "mexico": ["mexico", "mexican", "méxico", "mexicano"],
    "south korea": ["korea", "korean", "seoul"],
    "thailand": ["thailand", "thai", "bangkok"],
    "uae": ["uae", "abu dhabi", "dubai", "emirates"],
    "australia": ["australia", "australian", "sydney", "melbourne", "perth"],
    "georgia": ["georgia", "georgian", "tbilisi"],
    "ukraine": ["ukraine", "ukrainian", "kyiv", "kiev"],
    "netherlands": ["netherlands", "dutch", "holland", "amsterdam", "rotterdam"],
    "czech republic": ["czech", "prague", "praha"],
    "new zealand": ["new zealand", "auckland"],
    "ireland": ["ireland", "irish", "dublin"],
    "romania": ["romania", "romanian", "bucharest"],
    "sweden": ["sweden", "swedish", "stockholm"],
    "germany": ["germany", "german", "berlin", "münchen", "munich"],
    "south africa": ["south africa", "johannesburg", "cape town"],
    "india": ["india", "indian", "mumbai", "delhi"],
    "bahrain": ["bahrain", "manama"],
    "philippines": ["philippines", "filipino", "manila"],
}


# -- Chargement (mis en cache au 1er appel) ---------------------------------
_DATA: Optional[dict] = None
_NEEDLES: list = []   # [(regex, league_key, strength, tier_hint)], trié long->court


def _load() -> dict:
    global _DATA, _NEEDLES
    if _DATA is not None:
        return _DATA
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as fh:
            _DATA = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # Fallback minimal si le fichier manque : tout en global_default
        _DATA = {"global_default": {"strength": _GLOBAL_FALLBACK_STRENGTH},
                 "country_defaults": {}, "leagues": {}}

    # Construit la liste de "needles" (clé + alias), triée du + long au + court
    # pour éviter qu'un alias court (ex: "one") matche avant un long.
    needles = []
    for key, info in (_DATA.get("leagues") or {}).items():
        strength = info.get("strength", _GLOBAL_FALLBACK_STRENGTH)
        tier_hint = info.get("tier_hint")
        terms = [key] + list(info.get("aliases") or [])
        for term in terms:
            term = (term or "").strip().lower()
            if not term:
                continue
            # match "mot entier" (bornes non-alphanumériques) pour limiter les faux positifs
            rx = _re.compile(r"(?<![a-z0-9])" + _re.escape(term) + r"(?![a-z0-9])")
            needles.append((rx, key, float(strength), tier_hint, len(term)))
    needles.sort(key=lambda x: -x[4])   # plus long d'abord
    _NEEDLES = needles
    return _DATA


def _detect_country(text: str) -> Optional[str]:
    for country, kws in _COUNTRY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return country
    return None


def get_league_strength(event_raw: Optional[str]) -> Dict:
    """
    Renvoie un dict décrivant la force estimée de la ligue d'un événement :
        {
          "strength": float 0-100,
          "base_elo": float,        # Elo d'un adversaire inconnu de cette ligue
          "tier":     int 0-4,
          "name":     str,          # clé ligue / "country:xx" / "global_default"
          "matched_by": "league" | "country" | "default"
        }
    """
    data = _load()
    text = (event_raw or "").lower().strip()

    # 1) Ligue reconnue (le needle le + long qui matche gagne)
    if text:
        for rx, key, strength, tier_hint, _len in _NEEDLES:
            if rx.search(text):
                return {
                    "strength": strength,
                    "base_elo": strength_to_base_elo(strength),
                    "tier": strength_to_tier(strength, tier_hint),
                    "name": key,
                    "matched_by": "league",
                }

    # 2) Pays détecté dans le nom de l'événement
    if text:
        country = _detect_country(text)
        if country:
            cd = (data.get("country_defaults") or {}).get(country)
            if cd:
                strength = cd.get("strength", _GLOBAL_FALLBACK_STRENGTH)
                return {
                    "strength": strength,
                    "base_elo": strength_to_base_elo(strength),
                    "tier": strength_to_tier(strength),
                    "name": f"country:{country}",
                    "matched_by": "country",
                }

    # 3) Défaut global (le plus bas)
    gd = data.get("global_default") or {}
    strength = gd.get("strength", _GLOBAL_FALLBACK_STRENGTH)
    return {
        "strength": strength,
        "base_elo": strength_to_base_elo(strength),
        "tier": strength_to_tier(strength),
        "name": "global_default",
        "matched_by": "default",
    }


def country_default_strength(country: Optional[str]) -> float:
    """Force par défaut d'un pays (pour estimer via la nationalité d'un fighter)."""
    data = _load()
    cds = data.get("country_defaults") or {}
    if country:
        c = country.lower().strip()
        if c in cds:
            return cds[c].get("strength", _GLOBAL_FALLBACK_STRENGTH)
    return (cds.get("_default_country") or {}).get("strength", _GLOBAL_FALLBACK_STRENGTH)
