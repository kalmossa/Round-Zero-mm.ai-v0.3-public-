# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
mm.ai - l'algo ELO     #470

le principe de base :
  1. tu gagnes/perds des points selon QUI tu bats (ou contre qui tu perds)
  2. l'elo de depart vient du record x qualite des ligues du parcours
     (ZERO FightMatrix : c'est NOTRE elo, decision Elias 2026-06)
  3. le K-factor bouge selon l'experience (moins de combats = ca bouge plus)
  4. on est + ou - sur de l'elo de l'adversaire selon la source qu'on a :
       elo en bdd > rang #N > record V-D + tier de la promo > rien du tout
  5. la methode compte : KO/TKO x1.15, soumission x1.10, decision x1.00
  6. chaque adversaire inconnu prend un elo de base selon le prestige de la
     promo ou se passe le combat. un 0-0 a l'UFC c'est pas un 0-0 dans un
     petit show regional paumé.
"""

from __future__ import annotations

import math
import re as _re
from datetime import date
from typing import Dict, List, Optional, Tuple

# -- Réglages des 3 mécaniques 2026 (récence / champion / ligue du fighter) --
# Pondération par RÉCENCE : un combat perd de l'importance avec le temps.
# Demi-vie 5 ans -> un combat d'il y a 5 ans pèse 50%, 10 ans 25%, plancher 20%.
_RECENCY_HALFLIFE_YEARS = 5.0
_RECENCY_FLOOR          = 0.20
_TODAY                  = date.today()

# Bonus de CHAMPION (léger) appliqué avant le rescale, dans le batch.
_CHAMPION_BONUS = 75.0
# Pondération des TITRES / RÈGNES : crédit par combat de titre gagné
# (ufc_title_match_win), plafonné. Crédite aussi les ex-champions (règne passé).
_PER_TITLE_WIN    = 18.0
_TITLE_BONUS_CAP  = 150.0   # 200 → 150 : Jones/DC/Stipe capés à 150, Pantoja(5) = 90

# Escompte selon la LIGUE du fighter lui-même.
# Formule (x)^0.6 (sublinéaire) : creuse l'écart UFC vs top-orgs proches de 100.
#   UFC    (100) -> 0 pénalité
#   Bellator(84) -> ~131 pts   (avant: 40 seulement — trop doux)
#   PFL     (74) -> ~166 pts
#   Rizin   (71) -> ~175 pts
#   régional(~20)-> ~330 pts
_LEAGUE_PENALTY_MAX = 400.0


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] RÉCENCE — demi-vie 5 ans : combat d'il y a 10 ans → 25% du poids
# ═══════════════════════════════════════════════════════════════════
def _recency_mult(event_date: Optional[str], today: date = None) -> float:
    """Multiplicateur 0.20–1.00 selon l'ancienneté du combat (demi-vie 5 ans).
    Combat sans date -> 1.0 (pas de décote)."""
    if not event_date:
        return 1.0
    today = today or _TODAY
    try:
        y, m, d = str(event_date)[:10].split("-")
        years_ago = (today - date(int(y), int(m), int(d))).days / 365.25
    except (ValueError, TypeError):
        return 1.0
    if years_ago <= 0:
        return 1.0
    mult = 0.5 ** (years_ago / _RECENCY_HALFLIFE_YEARS)
    return max(_RECENCY_FLOOR, min(1.0, mult))

# Barème de ligues (data/league_coefficients.json). Import tolérant : si le
# module/fichier manque, on retombe sur l'ancien système des 5 tiers (plus bas).
try:
    from .leagues import get_league_strength  # type: ignore  (même package ml.elo)
    _LEAGUES_OK = True
except Exception:  # pragma: no cover
    try:
        from ml.elo.leagues import get_league_strength  # type: ignore
        _LEAGUES_OK = True
    except Exception:
        _LEAGUES_OK = False


# les tiers de promotions
# chaque tier donne l'elo de base d'un adversaire inconnu qui combat dans cette
# promo. (classé a la main selon le niveau mondial des orgas)

# tier 4 - l'elite mondiale (elo de base adversaire inconnu : 1700)
_PROMO_TIER4 = [
    'ufc', 'ultimate fighting championship',
    'one championship', 'one fc', 'one mma',
    'bellator',
    'pfl', 'professional fighters league',
    'strikeforce',
    'pride', 'pride fc', 'dream',
    'wec', 'world extreme cagefighting',
    'affliction',
]

# tier 3 - majeur / semi-majeur (elo de base : 1400)
_PROMO_TIER3 = [
    'lfa', 'legacy fighting alliance',
    'rizin', 'rizin ff',
    'invicta', 'invicta fc',
    'ksw', 'konfrontacja sztuk walki',
    'aca', 'acb', 'absolute championship',
    'm-1', 'm1 global', 'm-1 global',
    'efc', 'extreme fighting championship',
    'shooto',
    'deep',
    'pancrase',
    'titan fc',
    'cage warriors',
    'bamma',
    'wsof', 'world series of fighting',
    'contender series', "dana white's contender",
    'glory', 'glory kickboxing',
    'road fc',
    'jungle fight',
    'xfl', 'xtreme fighting league',
    'resurrection fighting alliance', 'rfa',
    'nac', 'naiza fc',
    'sigma',
    'acorns',
    'fight nights global', 'fight nights',
    'tuf', 'the ultimate fighter',
    'ufc fight pass',
    'sparta combat league',
    'combate americas',
    'immaf',
]

# tier 2 - regional serieux (elo de base : 1100)
_PROMO_TIER2 = [
    'brave cf', 'brave combat federation',
    'sfl', 'super fight league',
    'profc', 'pro fc',
    'nemmaf', 'new era',
    'eurasia fight nights',
    'afc', 'asian fighting championship',
    'power slap',
    'absolute mma',
    'cec', 'combat extreme championship',
    'tap out', 'tapout',
    'bushido',
    'pancrase',
    'colosseum battle',
    'naiza',
    'gcf',
    'gladiators',
    'nexus fc',
    'cffc', 'cage fury',
    'xmma',
    'hardrock mma',
    'victory fc',
    'strong style',
    'power cage',
    'fcf', 'fight club france',
    'oktagon',
    'uaew', 'uae warriors',
    'ares fc', 'ares combat',
    'superior challenge',
    'venator',
    'cwfc',
    'immortal fc',
    'nitro mma',
    'polaris',
    'combat mma',
    'thunder',
    'desert force',
    'wfc', 'world fighting championship',
    'dfl',
]

# tier 1 - petit regional / local (elo de base : 850)
# tout ce qui matche rien de connu tombe en tier 1 par defaut

# petite table pour retrouver le tier vite fait
_PROMO_LOOKUP: Dict[str, int] = {}
for _p in _PROMO_TIER4: _PROMO_LOOKUP[_p] = 4
for _p in _PROMO_TIER3: _PROMO_LOOKUP[_p] = 3
for _p in _PROMO_TIER2: _PROMO_LOOKUP[_p] = 2

# l'elo de base par tier pour un adversaire inconnu
# TIER 5 = UFC SEUL (bien séparé des autres orgas, même les top)
# tier 4 = Bellator / ONE / PFL / Pride / Strikeforce — bon niveau mais pas UFC
_TIER_BASE_ELO = {
    5: 1750.0,   # UFC — tier à part (seul à tier 5, via tier_hint=5 dans le JSON)
    4: 1640.0,   # Bellator / ONE / PFL / Pride / Strikeforce
    3: 1350.0,   # LFA / Rizin / Invicta / KSW ...
    2: 1050.0,   # BRAVE CF / SFL / ProFC ...
    1:  820.0,   # Petit régional
    0:  700.0,   # Inconnu total / show local
}

# la certitude par tier (on est moins sur des petits shows locaux)
# UFC (5) : certitude plus haute, les données et adversaires UFC sont connus
_TIER_CERTAINTY = {5: 0.70, 4: 0.60, 3: 0.50, 2: 0.42, 1: 0.36, 0: 0.30}


def classify_promotion(event_raw: Optional[str]) -> int:
    """
    recup le tier (0 a 4) d'une promo a partir du nom de l'evenement.
    en gros :
      1. on passe le texte en minuscule
      2. on cherche une correspondance dans les listes de tiers
      3. + qql regex pour les cas frequents (UFC Fight Night, ONE: ...)
    """
    if not event_raw:
        return 0
    text = str(event_raw).lower()

    # les cas les + frequents, traités direct avant de fouiller les tables
    if 'ufc' in text:        return 4
    if 'one championship' in text or ' one:' in text or 'one fc' in text: return 4
    if 'bellator' in text:   return 4
    if ' pfl ' in text or text.startswith('pfl') or 'professional fighters league' in text: return 4
    if 'strikeforce' in text: return 4
    if 'pride' in text and 'fc' in text: return 4
    if 'invicta' in text:    return 3
    if 'rizin' in text:      return 3
    if 'ksw' in text:        return 3
    if ' lfa ' in text or text.startswith('lfa') or 'legacy fighting' in text: return 3
    if 'contender series' in text: return 3
    if 'cage warriors' in text: return 3
    if 'aca' in text or 'acb' in text: return 3
    if 'm-1' in text or 'm1 global' in text: return 3
    if 'efc' in text and ('africa' in text or 'worldwide' in text): return 3
    if 'shooto' in text:     return 3
    if 'pancrase' in text:   return 3
    if ' deep ' in text or text.startswith('deep '): return 3
    if 'brave cf' in text or 'brave combat' in text: return 2
    if 'sfl' in text or 'super fight league' in text: return 2
    if 'profc' in text or 'pro fc' in text: return 2
    if 'oktagon' in text:    return 2
    if 'uae warriors' in text or 'uaew' in text: return 2
    if 'ares fc' in text or 'ares combat' in text: return 2
    if 'desert force' in text: return 2
    if 'naiza' in text:      return 2

    # sinon on decoupe en mots et on teste dans la table
    tokens = _re.split(r'[\s\-:_/]+', text)
    for length in (3, 2, 1):
        for i in range(len(tokens) - length + 1):
            phrase = ' '.join(tokens[i:i+length])
            if phrase in _PROMO_LOOKUP:
                return _PROMO_LOOKUP[phrase]

    return 1  # petit regional par defaut (pas 0, ca c'est inconnu total)


# les constantes
_ELO_MIN      = 600.0
_ELO_MAX      = 2900.0
_ELO_DEFAULT  = 950.0    # point de départ sans info (fighters régionaux peu connus)
# Mirror des constantes de leagues.py (pour P7 init sans FM)
_ELO_FLOOR     = 700.0   # base_elo d'une ligue force=0
_ELO_PER_POINT = 10.5    # force 100 -> 1750, 50 -> 1225
_FM_MAX       = 3604.0   # max FM observé en BDD
_FM_ELO_LOW   = 600.0    # ELO correspondant à FM très bas
_FM_ELO_HIGH  = 2600.0   # ELO correspondant à FM max


# init de l'elo a partir des points FM
def elo_from_fm(fm_points: float) -> float:
    """
    transforme les points FightMatrix (echelle log, de 15 a 3604+) en elo de
    depart, avec un petit log pour ecraser l'echelle.

    qql exemples :
      FM=15   -> ~1267   (petit fighter regional)
      FM=73   -> ~1613   (la mediane de la bdd)
      FM=500  -> ~2000   (bon fighter UFC)
      FM=1800 -> ~2350   (elite)
      FM=3604 -> ~2800   (top mondial)
    """
    if not fm_points or fm_points <= 0:
        return _ELO_DEFAULT
    ratio = math.log1p(fm_points) / math.log1p(_FM_MAX)
    return _FM_ELO_LOW + ratio * (_FM_ELO_HIGH - _FM_ELO_LOW)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] K-FACTOR — < 10 combats → K=96 (volatile) ; 30+ → K=48 (stable) -----------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════    puis inconnu
def k_factor(n_fights_in_db: int) -> float:
    """
    le K-factor change selon le nb de combats qu'on a en bdd.
    + un fighter a de combats trackés, + son elo est stable (ca bouge moins).
    """
    if n_fights_in_db < 10:
        return 96.0   # provisoire
    if n_fights_in_db < 30:
        return 72.0   # en développement
    return 48.0       # établi


# le bonus selon la methode de victoire
def finish_multiplier(method: Optional[str]) -> float:
    """une victoire par finition (KO/soum) vaut + qu'une decision aux points."""
    if not method:
        return 1.0
    m = str(method).upper()
    if m in ("KO", "TKO", "KO/TKO"):
        return 1.15
    if m == "SUB":
        return 1.10
    return 1.0


# estimer l'elo de l'adversaire quand il est pas dans la bdd
def estimate_opp_elo_from_rank(rank_str: Optional[str]) -> float:
    """
    estime l'elo d'un adversaire a partir de son rang dans la division.
    calibré sur la vraie distribution de la bdd.

      #1  → 1950  (champion / contender n°1)
      #5  → 1820
      #10 → 1720
      #15 → 1640
      #25 → 1530
      #50 → 1420
      #100+ → 1320
    """
    if not rank_str:
        return _ELO_DEFAULT
    m = _re.search(r"#(\d+)", str(rank_str))
    if not m:
        return _ELO_DEFAULT
    rank = int(m.group(1))
    if rank <= 1:   return 1950.0
    if rank <= 5:   return 1950.0 - (rank - 1) * 32.5   # #2=1917, #5=1820
    if rank <= 15:  return 1820.0 - (rank - 5) * 18.0   # #10=1730, #15=1640
    if rank <= 30:  return 1640.0 - (rank - 15) * 7.3   # #20=1603, #30=1530
    if rank <= 60:  return 1530.0 - (rank - 30) * 3.7   # #50=1420
    return max(1150.0, 1420.0 - (rank - 60) * 1.5)


# l'ecart d'elo possible au dessus/en dessous de la base, par tier
# UFC (5) : énorme dispersion (du parfait inconnu jusqu'a Jon Jones)
# tier 4 : top-orgs, bonne dispersion mais moins que l'UFC
# local : peu de dispersion (tout le monde est proche de la base)
_TIER_SPREAD = {5: 520, 4: 440, 3: 360, 2: 280, 1: 210, 0: 160}


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] ADVERSAIRE INCONNU — estimation elo par record V-D + tier de la promo
# crédibilité exponentielle : 1 fight→7%, 10 fights→51%, 30+→88%
# un 0-0 à l'UFC ≠ un 0-0 dans un petit show local
# ═══════════════════════════════════════════════════════════════════
def estimate_opp_elo_from_record(wins: int, losses: int, promo_tier: int = 1,     # estime élo pour fighter inconnu    ; voir leagues json   puis get_opponent_elo_and_certainty
                                 base_override: Optional[float] = None) -> Tuple[float, float]:
    """
    estime (elo, certitude) d'un adversaire a partir de son record V-D et de la promo.

    l'idée de la crédibilité :
      - le record dit qql chose, mais on lui fait + ou - confiance selon le
        nb de combats. un 3-0 ca veut dire bien moins qu'un 11-2.
      - la crédibilité suit une courbe exponentielle :
          1 fight  → 7%   (presque rien)
          5 fights → 30%
         10 fights → 51%
         20 fights → 76%
         30+ fights → 88%+
      - On part de la base du tier et on dévie selon win_rate × crédibilité.

    Exemples concrets :
      3-0 UFC  (tier 4) → base=1700 + (1.0-0.5)×450×0.19 = 1742   cert=0.38
      11-2 UFC (tier 4) → base=1700 + (0.85-0.5)×450×0.55 = 1786  cert=0.50
      0-3 UFC  (tier 4) → base=1700 + (0.0-0.5)×450×0.19 = 1657   cert=0.38
      3-0 SFL  (tier 2) → base=1050 + (1.0-0.5)×290×0.19 = 1077   cert=0.34
      11-2 SFL (tier 2) → base=1050 + (0.85-0.5)×290×0.55 = 1106  cert=0.44
    """
    # base_override = base_elo précis de la LIGUE (nouveau barème, continu) ;
    # sinon on retombe sur la base bucketée du tier (ancien système).
    tier_base   = base_override if base_override is not None else _TIER_BASE_ELO.get(promo_tier, 820.0)
    tier_spread = _TIER_SPREAD.get(promo_tier, 220)
    tier_cert   = _TIER_CERTAINTY.get(promo_tier, 0.32)

    total = int(wins) + int(losses)
    if total == 0:
        return tier_base, tier_cert

    win_rate    = int(wins) / total
    # Crédibilité exponentielle : 1-(e^(-total/14))
    # → converge vers 1.0 à partir de ~30 combats
    credibility = 1.0 - math.exp(-total / 14.0)

    deviation = (win_rate - 0.5) * tier_spread * credibility
    elo = tier_base + deviation

    # Bornes physiques : pas plus de ±70% du spread
    lo = tier_base - tier_spread * 0.70
    hi = tier_base + tier_spread * 0.70
    elo = max(lo, min(hi, elo))

    # La certitude augmente avec le nombre de combats (+0.08 par tranche de 5)
    certainty = min(tier_cert + credibility * 0.18, 0.72)

    return elo, certainty


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] CASCADE DE FIABILITÉ — 1.elo BDD → 2.rang #N → 3.record+tier → 4.tier seul
# 32% des combats ont un adversaire inconnu → ce code s'exécute énormément
# ═══════════════════════════════════════════════════════════════════
def get_opponent_elo_and_certainty(
    fight: Dict,
    elos: Dict[int, float],
    fm_points: Dict[int, float],
) -> Tuple[float, float]:
    """
    renvoie (elo_adversaire, certitude) selon la meilleure source qu'on a sous la main.

    l'ordre de priorité (du + fiable au - fiable) :
      1. elo deja en bdd (adversaire calculé)        -> certitude 1.00
      2. rang #N (FightMatrix, dans la division)     -> certitude 0.60-0.76
      3. record V-D + tier de la promo               -> certitude 0.30-0.72
         -> c'est le cas le + courant (32% des combats)
         -> un 3-0 SFL c'est pas un 3-0 UFC ni un 11-2 SFL (la grosse diff vs avant)
      4. juste le tier de la promo (pas de record)   -> certitude 0.30-0.42
      5. rien du tout                                -> certitude 0.28

    NOTE (décision Elias 2026-06) : on n'utilise PLUS les points de rating FM
    comme ancre d'elo. base_elo = NOTRE elo, basé uniquement sur qui on bat /
    perd. Les métriques FM restent dans le scouter, pas ici.

    la certitude module le K : K_reel = K_base x certitude x bonus_methode
    """
    opp_id     = fight.get("opponent_id")
    event      = fight.get("event_raw") or fight.get("event") or ""

    # Force de la ligue : nouveau barème granulaire (data/league_coefficients.json)
    # -> base_elo PROPRE à chaque ligue. Fallback ancien système des 5 tiers.
    if _LEAGUES_OK:
        league      = get_league_strength(event)
        promo_tier  = league["tier"]
        league_base = league["base_elo"]
    else:
        promo_tier  = classify_promotion(event)
        league_base = _TIER_BASE_ELO.get(promo_tier, 820.0)

    # 1. l'adversaire est deja en bdd avec un elo calculé
    if opp_id is not None and opp_id in elos:     # les ancres ----------------------------------------------------------------------------------------------
        return elos[opp_id], 1.00

    # 2. le rang #N dans la division (FM scrappe le rang a la date du combat)
    #    (les POINTS de rating FM ne sont plus utilisés — décision Elias 2026-06)
    rank_hint = fight.get("opponent_rank_current") or fight.get("opponent_rank")
    if rank_hint:
        m = _re.search(r"#(\d+)", str(rank_hint))
        if m:
            rank_elo   = estimate_opp_elo_from_rank(rank_hint)
            # un #50 a l'UFC c'est largement au dessus d'un #50 en ligue regionale
            # tier 5 = UFC : léger bonus (1.05) par rapport aux autres top-orgs
            tier_scale = {5: 1.05, 4: 1.00, 3: 0.92, 2: 0.82, 1: 0.72, 0: 0.65}
            adjusted   = rank_elo * tier_scale.get(promo_tier, 0.72)
            # certitude plafonnée à min(tier,4) pour que tier5 ne dépasse pas 0.76
            certainty  = 0.58 + min(promo_tier, 4) * 0.045   # 0.58–0.76
            return adjusted, certainty

    # 4. record V-D + base_elo PROPRE de la ligue (le cas le + courant)
    opp_w = fight.get("opponent_wins")
    opp_l = fight.get("opponent_losses")
    if opp_w is not None and opp_l is not None:  #  les patterns de promo ---------------------------------------------------------------------------------
        return estimate_opp_elo_from_record(int(opp_w), int(opp_l), promo_tier,
                                            base_override=league_base)

    # 5. juste la ligue (on a meme pas le record)
    return league_base, _TIER_CERTAINTY.get(promo_tier, 0.32)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] BOUCLE ELO — parcourt l'historique chronologiquement, combat par combat  ----------------- compute_elo_from_history--------------------------------------
# formule : elo += K × (résultat − attendu)
# ═══════════════════════════════════════════════════════════════════    puis expected
def compute_elo_from_history(
    history: List[Dict],
    init_elo: float,
    elos: Dict[int, float],
    fm_points: Dict[int, float],
) -> float:
    """
    calcule l'elo d'un fighter en parcourant son historique dans l'ordre.

    les params :
        history   : la liste des combats, triés du + vieux au + recent
        init_elo  : l'elo de depart (calibré FM si on l'a, sinon la valeur par defaut)
        elos      : les elos actuels de tout le monde (pour retrouver les adversaires)
        fm_points : les points FM de tout le monde (pour estimer les adversaires)

    renvoie l'elo final, borné dans [600, 2800].
    """
    elo = init_elo

    # on trie dans l'ordre chronologique (le + vieux d'abord)
    fights_dated = [f for f in history if isinstance(f, dict) and f.get("event_date")]
    fights_dated.sort(key=lambda f: f["event_date"])     # .sort trie

    n_fights = len(fights_dated)

    for i, fight in enumerate(fights_dated):
        result = (fight.get("result") or "").strip().upper()
        if result not in ("W", "L", "D"):
            continue

        # l'elo de l'adversaire + a quel point on y croit
        opp_elo, certainty = get_opponent_elo_and_certainty(fight, elos, fm_points)

        # le resultat en chiffre : victoire=1, defaite=0, nul=0.5
        actual = 1.0 if result == "W" else 0.0 if result == "L" else 0.5

        # la proba attendue (la formule elo classique)
        # ── 📌 [DÉMO] L.493 : expected = logistique sur l'écart d'elo ───────── -----------------------------------------------------------------  puis K-FACTOR
        expected = 1.0 / (1.0 + 10.0 ** ((opp_elo - elo) / 400.0))

        # le K : experience × certitude × méthode × RÉCENCE
        # (un vieux combat — surtout une défaite de jeunesse — pèse moins)
        K = (k_factor(i) * certainty * finish_multiplier(fight.get("method"))  # ----------Vieux ou recent fight -----------------------------------------------
             * _recency_mult(fight.get("event_date")))

        # ── 📌 [DÉMO] L.501 : elo += K × (résultat − attendu) — TOUTE LA MAGIE ─
        elo += K * (actual - expected)

    return max(_ELO_MIN, min(_ELO_MAX, elo))


# la timeline : la courbe d'elo combat par combat (pour le graph sur la fiche)
def compute_elo_timeline(
    history: List[Dict],
    init_elo: float,
    elos: Dict[int, float],
    fm_points: Dict[int, float],
) -> List[Dict]:
    """
    renvoie l'evolution de l'elo combat apres combat (pour faire le graphique).
    """
    elo = init_elo
    fights_dated = [f for f in history if isinstance(f, dict) and f.get("event_date")]
    fights_dated.sort(key=lambda f: f["event_date"])

    timeline = []
    for i, fight in enumerate(fights_dated):
        result = (fight.get("result") or "").strip().upper()
        if result not in ("W", "L", "D"):
            continue

        opp_elo, certainty = get_opponent_elo_and_certainty(fight, elos, fm_points)
        actual   = 1.0 if result == "W" else 0.0 if result == "L" else 0.5
        expected = 1.0 / (1.0 + 10.0 ** ((opp_elo - elo) / 400.0))
        K = (k_factor(i) * certainty * finish_multiplier(fight.get("method"))
             * _recency_mult(fight.get("event_date")))

        prev = elo
        elo += K * (actual - expected)

        timeline.append({
            "date":        fight.get("event_date"),
            "elo":         round(elo, 1),
            "delta":       round(elo - prev, 1),
            "result":      result,
            "method":      fight.get("method"),
            "opponent_id": fight.get("opponent_id"),
            "opp_elo_used": round(opp_elo, 0),
            "certainty":   certainty,
        })

    return timeline


def compute_elo_timeline_from_history(history, opp_lookup=None):
    """
    petit wrapper pour rester compatible avec api/app.py (l'ancienne signature).

    `history`    : les combats deja parsés par l'api (result, opponent_id,
                   event_date, method...). l'api donne deja un event_date ISO.
    `opp_lookup` : { opponent_id: base_elo } des adversaires retrouvés en bdd.

    renvoie la timeline elo combat par combat. attention : c'est juste une approx
    pour l'affichage (une seule passe, sans rescale par division ni seed FM), donc
    le dernier point s'approche du base_elo stocké sans toujours le coller pile.
    """
    elos = dict(opp_lookup) if opp_lookup else {}
    return compute_elo_timeline(history, init_elo=_ELO_DEFAULT, elos=elos, fm_points={})


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] POINT FIXE — calcule les elos de TOUT le monde par itérations
# résout "A dépend de B dépend de A" → converge en 5-12 tours (max_change < 0.5)
# ═══════════════════════════════════════════════════════════════════
def batch_compute_all_elos(
    all_history: Dict[int, List[Dict]],
    fm_points: Dict[int, float],
    max_iters: int = 20,
    convergence_threshold: float = 0.5,
    verbose: bool = True,
    champion_ids: Optional[set] = None,
    title_wins: Optional[Dict[int, int]] = None,
) -> Dict[int, float]:
    """
    calcule l'elo de tous les fighters d'un coup (iteration jusqu'au point fixe).

    le souci poule/oeuf : l'elo de A depend de B qui depend de A...
    la solution : on initialise depuis le record x qualite des ligues, puis on
    re-itere jusqu'a ce que ca se stabilise. (PLUS d'init FM — decision Elias.)

    les params :
        all_history  : { fighter_id: [combat, ...] }
        fm_points    : conservé pour compat de signature mais IGNORÉ (zéro FM)
        max_iters    : garde-fou (en vrai ca converge en 5-12 tours)
        convergence_threshold : on s'arrete quand max_change < seuil (en points elo)
        verbose      : affiche l'avancement

    renvoie { fighter_id: base_elo }.
    """
    # l'init (reste constante, c'est le point de depart a CHAQUE tour)
    # ═══════════════════════════════════════════════════════════════════
    # 📌 [DÉMO] DÉCISION CLÉ — ZÉRO FightMatrix : base_elo = NOTRE Elo, pas un dérivé FM
    # ═══════════════════════════════════════════════════════════════════
    # ZÉRO FightMatrix (décision Elias 2026-06) : base_elo = NOTRE elo, dérivé
    # uniquement du record × qualité des ligues du parcours. Les points FM ne
    # servent PLUS d'ancre (ils restent dans le scouter).
    #
    # Formule init :
    #   base = 950 + (ligue_avg_base - 700) × 0.5 × career_depth
    #          + (win_rate - 0.5) × 300 × career_depth
    #
    # Exemples (avant iterations) :
    #   Khabib 29-0, avg_str≈70  -> 950 + 367 + 150 = ~1467
    #   GSP    26-2, avg_str≈88  -> 950 + 440 + 128 = ~1518
    #   Silva  34-10,avg_str≈80  -> 950 + 420 +  82 = ~1452
    #   8-1 régional, str≈6      -> 950 +  19 +  67 = ~1036
    init_elos: Dict[int, float] = {}
    n_fm_seeded = 0  # gardé à 0 : plus aucun seed FM
    for fid in all_history:
        hist = all_history[fid]
        wins   = sum(1 for f in hist if isinstance(f, dict) and f.get("result") == "W")
        losses = sum(1 for f in hist if isinstance(f, dict) and f.get("result") == "L")
        total  = wins + losses
        if total < 3:
            init_elos[fid] = _ELO_DEFAULT
        else:
            win_rate = wins / total
            if _LEAGUES_OK:
                strs = [get_league_strength(f.get("event_raw", ""))["strength"]
                        for f in hist if isinstance(f, dict)]
                avg_str = sum(strs) / len(strs) if strs else 6.0
            else:
                avg_str = 20.0
            league_base  = _ELO_FLOOR + avg_str * _ELO_PER_POINT
            career_depth = min(1.0, total / 15.0)
            win_bonus    = (win_rate - 0.5) * 300.0 * career_depth
            raw_init     = (_ELO_DEFAULT
                            + (league_base - _ELO_FLOOR) * 0.5 * career_depth
                            + win_bonus)
            init_elos[fid] = max(_ELO_DEFAULT, min(2000.0, raw_init))

    if verbose:
        print(f"[ELO batch] {len(init_elos)} fighters | init 100% record×ligue (zéro FM)")

    # au depart, la table des adversaires = les elos d'init
    elos: Dict[int, float] = dict(init_elos)

    # ═══════════════════════════════════════════════════════════════════
    # 📌 [DÉMO] ITÉRATIONS — à chaque tour, on repart du même init, seule la
    # table des adversaires bouge → convergence propre, sans accumulation d'erreurs
    # ═══════════════════════════════════════════════════════════════════
    # l'iteration jusqu'au point fixe.
    # a chaque tour :
    #   - on REPART du meme init_elo (seed FM ou valeur par defaut) pour chaque fighter
    #   - seule la table des adversaires (elos) bouge
    # comme ca ca converge proprement, sans accumuler les erreurs
    for it in range(1, max_iters + 1):
        new_elos: Dict[int, float] = {}
        max_change = 0.0

        for fid, history in all_history.items():
            new_elo = compute_elo_from_history(
                history,
                init_elo=init_elos[fid],  # toujours le meme point de depart   -------------------------------------------------------------------
                elos=elos,                  # la table des adversaires du tour en cours
                fm_points=fm_points,
            )
            change = abs(new_elo - elos[fid])
            if change > max_change:
                max_change = change
            new_elos[fid] = round(new_elo, 2)

        elos = new_elos

        if verbose:
            vals = sorted(elos.values())
            n = len(vals)
            print(f"[ELO batch] Iter {it:2d} : max_change={max_change:.2f} | "
                  f"min={vals[0]:.0f} P25={vals[n//4]:.0f} med={vals[n//2]:.0f} "
                  f"P75={vals[3*n//4]:.0f} max={vals[-1]:.0f}")

        # 📌 [DÉMO] ARRÊT — quand max_change < 0.5 pt Elo, c'est convergé
        if max_change < convergence_threshold:
            if verbose:
                print(f"[ELO batch] convergé en {it} tour(s).")
            break
    else:
        if verbose:
            print(f"[ELO batch] /!\\ max iterations ({max_iters}) atteint sans converger a fond.")

    # ═══════════════════════════════════════════════════════════════════
    # 📌 [DÉMO] POST-TRAITEMENT : ① escompte ligue → ② bonus champion → ③ rescale [600,2800]
    # ═══════════════════════════════════════════════════════════════════
    # -- Ajustements AVANT rescale (ils changent l'ordre relatif) -----------
    # (a) ESCOMPTE LIGUE : on tire vers le bas les fighters qui n'évoluent
    #     jamais au top niveau (moyenne de force des ligues de leur carrière).
    #     UFC(100) -> 0 pénalité ; régional(~20) -> grosse pénalité.
    for fid, history in all_history.items():
        if fid not in elos:
            continue
        strengths = []
        for f in history:
            if isinstance(f, dict):
                try:
                    if _LEAGUES_OK:
                        strengths.append(get_league_strength(f.get("event_raw"))["strength"])
                except Exception:
                    pass
        if strengths:
            avg_str = sum(strengths) / len(strengths)
            # formule sublinéaire (exposant 0.6) : creuse l'écart entre UFC (100)
            # et les top-orgs proches (Bellator 84, PFL 74...).
            # UFC    (100) -> 0 pénalité
            # Bellator(84) -> 400 × (16/100)^0.6 ≈ 131 pts
            # PFL     (74) -> 400 × (26/100)^0.6 ≈ 167 pts
            # Rizin   (71) -> 400 × (29/100)^0.6 ≈ 178 pts
            # régional(20) -> 400 × (80/100)^0.6 ≈ 328 pts
            raw     = max(0.0, min(1.0, (100.0 - avg_str) / 100.0))
            penalty = _LEAGUE_PENALTY_MAX * (raw ** 0.6)
            elos[fid] = elos[fid] - penalty

    # (b) BONUS CHAMPION + TITRES/RÈGNES.
    #     - détenteur actuel de ceinture -> +_CHAMPION_BONUS
    #     - crédit par combat de titre gagné (même ex-champion) -> règne valorisé
    champ_set = champion_ids or set()
    tw = title_wins or {}
    for fid in list(elos.keys()):
        bonus = 0.0
        if fid in champ_set:
            bonus += _CHAMPION_BONUS
        n_title = tw.get(fid) or 0
        if n_title > 0:
            bonus += min(n_title * _PER_TITLE_WIN, _TITLE_BONUS_CAP)
        if bonus:
            elos[fid] = elos[fid] + bonus

    # ═══════════════════════════════════════════════════════════════════
    # 📌 [DÉMO] RESCALE FINAL — étire tout sur [600, 2800] en préservant l'ordre relatif
    # ═══════════════════════════════════════════════════════════════════
    # rescale final -> on garantit la plage 600-2800
    # ca garde la distribution et l'ordre relatif, ca etire juste l'echelle
    TARGET_MIN, TARGET_MAX = 600.0, 2800.0
    cur_min = min(elos.values())
    cur_max = max(elos.values())
    span = cur_max - cur_min
    if span > 0:
        elos = {
            fid: round(TARGET_MIN + (v - cur_min) / span * (TARGET_MAX - TARGET_MIN), 2)
            for fid, v in elos.items()
        }
        if verbose:
            vals = sorted(elos.values())
            n = len(vals)
            print(f"[ELO batch] Apres rescale : min={vals[0]:.0f} P25={vals[n//4]:.0f} "
                  f"med={vals[n//2]:.0f} P75={vals[3*n//4]:.0f} max={vals[-1]:.0f}")

    return elos


# vieux truc gardé juste pour pas casser les imports qui existent encore ailleurs
class DynamicEloCalculator:
    """stub de compat (sert quasi + a rien mais des fichiers l'importent encore)."""
    K_FACTOR    = 36
    BASE_RATING = 1400

    def calculate_dynamic_elo(self, fighter_id, base_elo, age=30, recent_fights=None, opponent_ratings=None):
        return base_elo

    def predict_outcome(self, elo1: float, elo2: float):
        exp1 = 1.0 / (1.0 + 10.0 ** ((elo2 - elo1) / 400.0))
        return round(exp1, 4), round(1.0 - exp1, 4)
