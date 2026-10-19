# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
mm.ai - le calcul du Scouter Rating (la note "qui gagne ce soir")

=============================================================================  767
LE MODELE EN UNE PHRASE
=============================================================================
On part de l'ELO (et UNIQUEMENT de l'elo) qu'on transforme en une note de
base sur ~0-100, puis on le multiplie par une serie de coefficients de
contexte calcules a la volee depuis les donnees du fighter.

    scouter = base_elo_normalise  x  F_forme  x  F_streak  x  F_age  x  ...     /// formule de base 

C'est exactement le genre de formule "elo x 1.20 (en feu) x 0.84 (vieux)".
Chaque coefficient est centre sur 1.0 :
    > 1.0  => le fighter est avantage sur ce critere
    = 1.0  => neutre OU donnee manquante (on fait sans, jamais de 0 sournois)
    < 1.0  => malus

REGLES POSEES PAR ELIAS (a respecter scrupuleusement) :
  1. La BASE, c'est l'elo et RIEN d'autre. FightMatrix, le statut, les methodes
     de victoire, etc. ne touchent JAMAIS l'elo : ils ne bougent que le scouter
     (= ce sont des multiplicateurs).
  2. PAS de plafond a 100. Un phenomene peut depasser 100, c'est voulu.
  3. Donnee manquante => coefficient = 1.0 (on ignore, on n'invente rien).
  4. Un fighter INACTIF (is_active = False) n'a PAS de scouter -> None.
     Il garde son elo, mais il ne se bat plus "ce soir" donc pas de note.
  5. RIEN n'est pre-calcule ni mis en dur "par fighter" : tout est recalcule a
     CHAQUE appel depuis le row. Le seul truc fige, c'est l'elo (= l'entree).
     Les tables ci-dessous (courbe d'age, allonge moyenne par division, tiers
     de ligue...) sont des PARAMETRES DU MODELE, pas des valeurs de fighter.

Le scouter n'est JAMAIS stocke en bdd : il est recalcule a chaque appel de
l'API depuis les colonnes qu'on a deja (cf api/app.py -> /scouter).

pour s'en servir :
    from ml.scouter import compute_scouter
    note = compute_scouter(fighter_row_dict)   # un float, ou None
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Optional


# =============================================================================
# CONFIG - toutes les constantes reglables sont ici, et seulement ici.
# Pour recalibrer le scouter : on edite ce bloc, on ne touche pas au reste.
# =============================================================================

# --- 1) La BASE : elo -> note 0-100 ------------------------------------------
# On reutilise la courbe logistique de l'elo (la meme que la proba de victoire).
# C'est naturel : un ecart d'elo se lit deja en proba, donc en "niveau".
#
# REPERES DE LA COURBE (echelle purement ELO, pas de role predetermine) :
#     elo  <1000  en dessous de la moyenne (ca existe)
#     elo  ~1000  moyenne : orga moyenne, bilan equilibre (genre 4-4)  -> 50
#     elo  ~1500  bon niveau regional / gatekeeper                     -> ~68
#     elo  ~2000  haut niveau confirme                                 -> ~82
#     elo  ~2800  tre haut niveau                                      -> ~94
#     elo  ~3000  sommet de l'echelle actuelle                         -> ~95
# Chaque fighter a son propre elo selon sa carriere ; deux champions
# peuvent avoir des elos tres differents selon leur parcours.
#
# center=1000 (= la moyenne, qui vaut 50/100) ; scale=680 (etale le haut).
ELO_BASE_CENTER = 1000.0   # l'elo "moyen" qui vaut exactement 50/100
ELO_BASE_SCALE  = 680.0    # + grand = courbe plus douce (moins d'ecart entre niveaux)

# --- 2) F_forme : recent_form_score (0-1, 0.5 = neutre) ----------------------
# C'est LE coeur du "ce soir" -> grosse amplitude.
FORM_MIN, FORM_MAX = 0.82, 1.18    # +/- 18%

# --- 3) F_streak : current_streak (serie de victoires/defaites en cours) -----
# Les defaites en serie sont punies bien plus durement que les victoires sont
# recompensees (un mec sur 6 defaites, c'est rouge vif).
STREAK_WIN_PER  = 0.040   # +4% par victoire d'affilee...
STREAK_WIN_CAP  = 5       # ...plafonne a 5 (donc +20% max -> x1.20)
STREAK_LOSS_PER = 0.050   # -5% par defaite d'affilee...
STREAK_LOSS_CAP = 6       # ...plafonne a 6 (donc -30% max -> x0.70)

# --- 4) F_age : pic physique ~27-31, declin apres 33 -------------------------
# Interpolation lineaire entre ces ancres (age, coefficient).
AGE_ANCHORS = [
    (18, 0.92), (22, 0.97), (25, 1.00), (27, 1.04), (31, 1.04),
    (33, 1.00), (35, 0.94), (38, 0.84), (40, 0.80), (45, 0.78),
]

# --- 5) F_inactivite : ring rust (jours depuis le dernier combat) ------------
# Ne concerne QUE les actifs (les inactifs n'ont deja pas de scouter du tout).
INACTIVITY_STEPS = [   # (jours_min, coefficient), trie croissant
    (0,    1.00),
    (270,  1.00),   # < 9 mois : rythme normal, aucune penalite
    (455,  0.97),   # > 15 mois
    (730,  0.93),   # > 2 ans
    (1095, 0.88),   # > 3 ans
    (1460, 0.85),   # > 4 ans
]

# --- 6) F_finish : capacite a finir = BONUS PUR (jamais de malus) ------------
# Regle Elias : "si il met tout le monde KO -> des points en plus ; si il bat
# tout le monde aux points -> PAS de points en plus" (donc plancher = 1.0).
# On lit le taux de finition (% de victoires gagnees par KO/TKO ou soumission).
FINISH_MAX = 1.90    # 100% de finitions -> +20% ; 0% de finition -> x1.00

# --- 7) Les 4 metriques FightMatrix = 4 FACTEURS SEPARES ---------------------           ->   donnée manquante
# FM reste un MULTIPLICATEUR (jamais une source d'elo) MAIS on ne les moyenne
# PAS ensemble : chaque metrique FM est son propre coefficient, donc FM pese
# fortement (decision Elias). Chacune : donnee absente -> 1.0 (on fait sans).
#   - rating_points     (echelle FM ~0-3604, log) : domination accumulee
#   - quality_perf_pct  (0-100)                    : qualite des perfs vs attendu
#   - 540_metric        (0-1)                      : score de coherence FM
#   - big_league_record ('30-7-0')                 : winrate en grande ligue
FM_POINTS_REF = 3604.0    # le max de points FM qu'on voit en bdd (pour le log)
# Ranges volontairement larges : Elias veut que FM pese le plus de tous les facteurs.
# Les 4 s'empilent -> au mieux x1.18*1.14*1.10*1.10 ~ +63% ; au pire x0.88*0.90*0.92*0.92 ~ -30%.
FM_RATING_MIN, FM_RATING_MAX     = 0.88, 1.18   # rating_points (signal le plus fort)
FM_QUALITY_MIN, FM_QUALITY_MAX   = 0.90, 1.14   # quality_perf_pct (qualite des perfs)
FM_540_MIN, FM_540_MAX           = 0.92, 1.10   # 540_metric (coherence FM)
FM_BIGLEAGUE_MIN, FM_BIGLEAGUE_MAX = 0.92, 1.10 # winrate grande ligue

# --- 8) F_calendrier : force du calendrier (records des adversaires) ---------
# 100% a la volee : on lit "opponent_record" dans le fight_history (le record
# de l'adversaire AU MOMENT du combat) -> winrate. Moyenne ponderee par la
# recence (les combats recents comptent plus). Pas besoin de la BDD.
# Un mec qui bat/affronte des 20-2 vaut plus qu'un mec qui affronte des 4-8.
SCHED_NEUTRAL_WR  = 0.60   # winrate moyen d'adversaire considere "normal" -> 1.0
SCHED_MIN, SCHED_MAX = 0.92, 1.13
SCHED_HALFLIFE_Y  = 4.0    # un combat de 4 ans pese moitie moins

# --- 9) F_statut : reconnaissance de l'organisation + pedigree ---------------
STATUS_CHAMPION   = 1.12   # champion en titre
STATUS_RANK_TOP5  = 1.07   # rang 1-5
STATUS_RANK_TOP15 = 1.03   # rang 6-15
STATUS_P4P_BONUS  = 0.03   # petit plus si dans le top 15 pound-for-pound
STATUS_TITLE_PER  = 0.015  # +1.5% par victoire en combat de titre (pedigree)...
STATUS_TITLE_CAP  = 4      # ...plafonne a 4 (donc +6% max)

# --- 10) F_durabilite : le menton (defaites par finition) x age --------------
# Beaucoup de KO/soum encaisses ET un certain age = signal de chute. Le KO pese
# plus que la soumission (le menton part avant la defense au sol).
DURABILITY_SUB_WEIGHT = 0.6    # une defaite par soum = 0.6 d'une defaite par KO
DURABILITY_RATIO_GATE = 0.40   # il faut > 40% de defaites "finies" pour declencher
DURABILITY_AGE_GATE   = 32     # ...et avoir au moins cet age
DURABILITY_FACTOR     = 0.92   # le malus si les deux conditions sont reunies

# --- 11) F_physique : allonge + taille vs moyenne de division + stance -------
# En on-demand on n'a qu'UN fighter, donc on compare a des tables de moyennes
# par division (parametres du modele, pas des valeurs de fighter).
REACH_PER_INCH  = 0.004   # +/- 0.4% par pouce d'allonge vs la moyenne de division
HEIGHT_PER_INCH = 0.002   # +/- 0.2% par pouce de taille (signal plus faible que l'allonge)
REACH_CLAMP     = 0.035   # borne l'effet morphologique total a +/- 3.5%
STANCE_SOUTHPAW = 0.012   # petit edge statistique des gauchers
STANCE_SWITCH   = 0.006
DIVISION_AVG_REACH = {    # allonge moyenne (pouces) par (division, genre)
    ("flyweight", "M"): 66.5, ("bantamweight", "M"): 67.5, ("featherweight", "M"): 70.0,
    ("lightweight", "M"): 72.0, ("welterweight", "M"): 74.0, ("middleweight", "M"): 75.5,
    ("light heavyweight", "M"): 77.0, ("heavyweight", "M"): 78.5,
    ("strawweight", "W"): 62.0, ("flyweight", "W"): 64.5,
    ("bantamweight", "W"): 67.0, ("featherweight", "W"): 68.0,
}
DIVISION_AVG_HEIGHT = {   # taille moyenne (pouces) par (division, genre)
    ("flyweight", "M"): 65.0, ("bantamweight", "M"): 66.5, ("featherweight", "M"): 68.0,
    ("lightweight", "M"): 69.5, ("welterweight", "M"): 71.0, ("middleweight", "M"): 72.5,
    ("light heavyweight", "M"): 74.0, ("heavyweight", "M"): 75.5,
    ("strawweight", "W"): 63.5, ("flyweight", "W"): 65.0,
    ("bantamweight", "W"): 66.5, ("featherweight", "W"): 67.5,
}

# --- 12) F_categorie : combattre hors de sa categorie d'origine --------------
# Regle Elias : si la categorie actuelle != categorie d'origine, le combattant
# evolue hors de son poids naturel -> il perd des points.
WEIGHT_CLASS_AWAY = 0.94   # malus si weight_class_current != weight_class_origin

# --- 13) F_split : qualite des decisions (split = combat serre) --------------
# Regle Elias : une victoire en decision PARTAGEE (split) = un poil de moins
# (peu dominant) ; une defaite en split = un poil de plus (pas domine).
SPLIT_WIN_PEN   = 0.006    # -0.6% par victoire en split decision
SPLIT_LOSS_GAIN = 0.006    # +0.6% par defaite en split decision
SPLIT_CLAMP     = 0.05     # effet total borne a +/- 5%

# --- 14) F_experience : volume de carriere (proven-ness) ---------------------
# Un prospect a 3 combats est moins eprouve qu'un veteran a 30 combats.
# Effet doux, a rendements decroissants.
EXPERIENCE_ANCHORS = [   # (nb total de combats, coefficient)
    (0, 0.94), (5, 0.97), (10, 1.00), (20, 1.03), (35, 1.04),
]

# --- 15) F_niveau_ufc : part de la carriere passee au plus haut niveau -------
# record_ufc vs record_total : un combattant teste 25 fois en UFC est plus
# eprouve au sommet qu'un mec a 0 combat UFC. Centre : ~30% de carriere UFC = neutre.
UFC_SHARE_NEUTRAL = 0.30
UFC_LEVEL_MIN, UFC_LEVEL_MAX = 0.97, 1.06

# --- 16) F_winrate : taux de victoire sur la carriere (dominance) ------------
# win_percentage_int. Neutre vers 55% (un pro lambda gagne un peu plus qu'il ne
# perd). 80%+ = dominant, 40% = mediocre. Recoupe l'elo mais ajoute un signal direct.
WINRATE_NEUTRAL_PCT = 55.0
WINRATE_MIN, WINRATE_MAX = 0.95, 1.08

# --- 17) F_activite : rythme sur les dernieres annees (PENALITE seulement) ----
# Regle Elias : on penalise UNIQUEMENT celui qui combat peu (moins d'~1 combat
# par an) sur la periode recente. Pas de bonus pour les hyper-actifs. Distinct
# de l'inactivite (qui ne regarde QUE le dernier trou ; ici c'est la regularite).
ACTIVITY_WINDOW_YEARS   = 3.0    # fenetre "recente" sur laquelle on juge le rythme
ACTIVITY_TARGET_PER_YEAR = 1.0   # rythme attendu : >= 1 combat/an -> aucune penalite
ACTIVITY_MIN_CAREER_YEARS = 1.5  # carriere trop courte -> on ne juge pas (1.0)
ACTIVITY_PENALTY        = 0.06   # ampleur du malus quand le rythme manque
ACTIVITY_FLOOR          = 0.94   # malus max (un actif qui n'a quasi pas combattu)

# --- 18) F_ligue : niveau de l'organisation actuelle -------------------------
# Score par ligue. Au-dessus de 1.0 = grosse orga, en-dessous = regional connu.
# Ligue inconnue -> 1.0 (donnee manquante, on fait sans).
LEAGUE_FACTOR = {
    "UFC": 1.05, "PFL": 1.03, "BELLATOR": 1.03, "ONE": 1.03,
    "PRIDE": 1.05, "STRIKEFORCE": 1.04, "RIZIN": 1.02, "KSW": 1.01,
}
LEAGUE_REGIONAL = 0.98   # ligue listee mais hors du top -> petit malus de niveau

# --- 19) Garde-fou d'amplitude (LE curseur a regler avec Elias) --------------
# Le produit de TOUS les coefficients est borne ici. Ce n'est PLUS un outil de
# calibration mais un simple filet anti-anomalie : assez large pour laisser
# l'elite s'echapper (un champion "tout coche" pull away au lieu de plafonner
# avec les autres), assez serre pour qu'une donnee aberrante n'explose pas.
#   Plancher 0.45 : un naufrage complet (serie de defaites + vieux + fini) ~/2.
#   Plafond  1.90 : un profil parfait multiplie la base par ~1.9 (rarement atteint).
# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] GARDE-FOU — le PRODUIT est clampé [0.45 ; 1.90], PAS la note finale
# => on borne les déviations aberrantes, un phénomène peut quand même dépasser 100
# ═══════════════════════════════════════════════════════════════════
PRODUCT_FLOOR = 0.45
PRODUCT_CEIL  = 1.90


# =============================================================================
# Helpers (parsing tolerant : on ne plante jamais sur une donnee bizarre)
# =============================================================================

def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(v, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _first_float(s) -> Optional[float]:
    """Extrait le 1er nombre d'une chaine ('76\"' -> 76.0, '188 cm' -> 188.0)."""
    if s is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else None


def _parse_height_inches(s) -> Optional[float]:
    """
    Taille en pouces. Gere les deux formats de la bdd :
      - pieds'pouces : "6'1\"" -> 6*12 + 1 = 73.0
      - pouces secs  : "73"    -> 73.0
    """
    if s is None:
        return None
    txt = str(s)
    m = re.search(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)?", txt)
    if m:   # format pieds'pouces
        feet = int(m.group(1))
        inches = float(m.group(2)) if m.group(2) else 0.0
        return feet * 12 + inches
    return _first_float(txt)


def _age_from_dob(dob) -> Optional[int]:
    """Age exact depuis la date de naissance (source de verite > colonne age)."""
    if not dob:
        return None
    if isinstance(dob, str):
        try:
            dob = date.fromisoformat(dob[:10])
        except (ValueError, TypeError):
            return None
    if isinstance(dob, datetime):
        dob = dob.date()
    if not isinstance(dob, date):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _age_of(row: dict) -> Optional[int]:
    """L'age, depuis la DOB en priorite, sinon la colonne age."""
    age = _age_from_dob(row.get("date_of_birth"))
    if age is None:
        age = _safe_int(row.get("age")) or None
    return age


def _days_inactive(row: dict) -> Optional[int]:
    """Jours depuis le dernier combat. None si on ne sait pas."""
    d = row.get("days_inactive")
    if d is not None:
        try:
            return int(d)
        except (ValueError, TypeError):
            pass
    last = row.get("last_fight_date")
    if not last:
        return None
    if isinstance(last, str):
        try:
            last = date.fromisoformat(last[:10])
        except (ValueError, TypeError):
            return None
    if isinstance(last, datetime):
        last = last.date()
    return max(0, (date.today() - last).days)


def _parse_streak(streak) -> int:
    """'W5'/'5W' -> +5, 'L3'/'3L' -> -3, '+2' -> +2, '0' -> 0. Illisible -> 0."""
    if streak is None:
        return 0
    s = str(streak).strip().upper()
    m = re.search(r"(\d+)", s)
    n = int(m.group(1)) if m else 0
    return -n if ("L" in s or s.startswith("-")) else n


def _norm_wc(wc) -> str:
    """Normalise un nom de categorie pour comparaison (sans genre ni ponctuation)."""
    s = (wc or "").lower()
    s = s.replace("women's", "").replace("women", "").replace("'s", "")
    return re.sub(r"[^a-z ]", " ", s).strip()


def _is_active(row: dict) -> bool:
    """
    Actif sauf si is_active vaut explicitement False.
    (is_active inconnu/None -> on considere actif : donnee manquante, on fait sans.)
    """
    return row.get("is_active") is not False


def _iter_fights(row: dict):
    """
    Parcourt le fight_history (colonne TEXT JSON) et rend pour chaque combat :
        (result 'W'/'L'/'D', opponent_winrate|None, years_ago|None)
    opponent_winrate vient du champ 'opponent_record' ('15-0' -> 1.0).
    Tolerant : si rien de parsable, ne rend rien (le facteur sera neutre).
    """
    raw = row.get("fight_history")
    if not raw:
        return
    try:
        fh = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return
    fights = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    today = date.today()
    for f in fights:
        if not isinstance(f, dict):
            continue
        res = (f.get("result") or "").strip().upper()

        # winrate de l'adversaire depuis son record au moment du combat
        owr = None
        m = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(f.get("opponent_record") or ""))
        if m:
            w, l = int(m.group(1)), int(m.group(2))
            if w + l > 0:
                owr = w / (w + l)

        # anciennete du combat (en annees) pour la ponderation recence
        years_ago = None
        ed = f.get("event_date")
        if ed:
            try:
                d = date.fromisoformat(str(ed)[:10])
                years_ago = max(0.0, (today - d).days / 365.25)
            except (ValueError, TypeError):
                pass

        yield res, owr, years_ago


# =============================================================================
# La BASE : elo -> note 0-100 (la seule source du "niveau brut")
# =============================================================================

# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] BASE ELO→/100 — sigmoïde centrée sur 1000 (= 50/100)
# SEULE source du niveau brut. FightMatrix + tout le reste = multiplicateurs UNIQUEMENT.
# ═══════════════════════════════════════════════════════════════════
def _base_from_elo(elo: float) -> float:   # traduction scouter lisible user
    """
    Transforme l'elo en note de base via une sigmoide centree sur ELO_BASE_CENTER.
    100 / (1 + e^-(elo - center)/scale)  ->  borne naturellement entre 0 et 100.
    """
    return 100.0 / (1.0 + math.exp(-(elo - ELO_BASE_CENTER) / ELO_BASE_SCALE))


# petit utilitaire : mappe une valeur 0-1 (neutre a 0.5) vers [lo, hi] centre sur 1.0
def _around_one(x01: float, lo: float, hi: float, neutral: float = 0.5) -> float:
    x01 = max(0.0, min(1.0, x01))
    if x01 >= neutral:
        return 1.0 + (x01 - neutral) / (1.0 - neutral) * (hi - 1.0)
    return 1.0 - (neutral - x01) / neutral * (1.0 - lo)


# =============================================================================
# Les FACTEURS (chacun renvoie un multiplicateur centre sur 1.0)
# Convention : donnee manquante -> on renvoie 1.0 (neutre, on fait sans).
# =============================================================================

# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] DONNÉE MANQUANTE → 1.0 (neutre, jamais un 0 fabriqué)
# Convention appliquée à TOUS les f_* — voir le `return 1.0` ci-dessous
# ═══════════════════════════════════════════════════════════════════
def f_forme(row: dict) -> float:
    """Forme recente = recent_form_score (5 derniers combats ponderes). 0.5 = neutre."""
    rfs = _safe_float(row.get("recent_form_score"))
    if rfs is None:
        return 1.0
    return _around_one(rfs, FORM_MIN, FORM_MAX)


def f_streak(row: dict) -> float:    # winrate de la serie en cours (victoires/defaites) -> multiplicateur important
    """Serie en cours. Victoires -> bonus plafonne ; defaites -> malus profond."""
    s = _parse_streak(row.get("current_streak"))
    if s > 0:
        return 1.0 + min(s, STREAK_WIN_CAP) * STREAK_WIN_PER
    if s < 0:
        return 1.0 - min(-s, STREAK_LOSS_CAP) * STREAK_LOSS_PER
    return 1.0


def f_age(row: dict) -> float:
    """Courbe d'age : pic ~27-31, declin progressif ensuite (interpolation)."""
    age = _age_of(row)
    if age is None:
        return 1.0
    if age <= AGE_ANCHORS[0][0]:
        return AGE_ANCHORS[0][1]
    if age >= AGE_ANCHORS[-1][0]:
        return AGE_ANCHORS[-1][1]
    for (a0, v0), (a1, v1) in zip(AGE_ANCHORS, AGE_ANCHORS[1:]):
        if a0 <= age <= a1:
            return v0 + (v1 - v0) * (age - a0) / (a1 - a0)
    return 1.0


def f_inactivite(row: dict) -> float:
    """Ring rust (actifs uniquement). None -> 1.0 (on ne sait pas)."""
    d = _days_inactive(row)
    if d is None:
        return 1.0
    factor = INACTIVITY_STEPS[0][1]
    for threshold, val in INACTIVITY_STEPS:
        if d >= threshold:
            factor = val
    return factor


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] F_FINISH — bonus PUR, jamais de malus (règle posée par Elias)
# tout en décisions → x1.00 ; tout en KO/soum → +20%
# ═══════════════════════════════════════════════════════════════════
def f_finish(row: dict) -> float:
    """
    Capacite a finir = BONUS PUR. Tout en KO/soum -> +20% ; tout en decision ->
    x1.00 (pas de malus). On lit finish_rate_int, sinon on derive des colonnes
    de methodes de victoire.
    """
    fr = _safe_float(row.get("finish_rate_int"))
    if fr is None:
        wins = _safe_int(row.get("record_total_wins"))
        finishes = _safe_int(row.get("wins_by_ko_tko")) + _safe_int(row.get("wins_by_submission"))
        if wins <= 0:
            return 1.0
        fr = finishes / wins * 100.0
    fr = max(0.0, min(100.0, fr))
    return 1.0 + (fr / 100.0) * (FINISH_MAX - 1.0)


# --- Les 4 metriques FightMatrix, chacune son propre facteur (FM pese fort) ---
# FM ne touche jamais l'elo : ce sont des multiplicateurs du scouter. Donnee
# absente -> 1.0 (on fait sans). On ne les moyenne PAS : elles s'empilent.

def f_fm_rating(row: dict) -> float:
    """FM rating_points : domination accumulee (echelle log ~0-3604)."""
    pts = _safe_float(row.get("fightmatrix_rating_points"))
    if pts is None or pts <= 0:
        return 1.0
    score01 = min(1.0, math.log1p(pts) / math.log1p(FM_POINTS_REF))
    return _around_one(score01, FM_RATING_MIN, FM_RATING_MAX)


def f_fm_quality(row: dict) -> float:
    """FM quality_perf_pct : qualite des perfs vs attendu (0-100, neutre 50)."""
    qp = _safe_float(row.get("fightmatrix_quality_perf_pct"))
    if qp is None or qp <= 0:
        return 1.0
    return _around_one(qp / 100.0, FM_QUALITY_MIN, FM_QUALITY_MAX)


def f_fm_540(row: dict) -> float:
    """FM 540_metric : score de coherence FM (0-1, neutre 0.5)."""
    m540 = _safe_float(row.get("fightmatrix_540_metric"))
    if m540 is None or m540 <= 0:
        return 1.0
    return _around_one(max(0.0, min(1.0, m540)), FM_540_MIN, FM_540_MAX)


def f_fm_bigleague(row: dict) -> float:
    """FM big_league_record ('30-7-0') : winrate en grande ligue (neutre 0.5)."""
    mbl = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(row.get("fightmatrix_big_league_record") or ""))
    if not mbl:
        return 1.0
    w, l = int(mbl.group(1)), int(mbl.group(2))
    if w + l == 0:
        return 1.0
    return _around_one(w / (w + l), FM_BIGLEAGUE_MIN, FM_BIGLEAGUE_MAX)


def f_calendrier(row: dict) -> float:
    """
    Force du calendrier : winrate moyen des adversaires (depuis leur record au
    moment du combat), pondere par la recence. Calcule a la volee depuis le
    fight_history. Pas d'historique exploitable -> 1.0.
    """
    wsum = wtot = 0.0
    for _res, owr, years_ago in _iter_fights(row):
        if owr is None:
            continue
        recency = 0.5 ** ((years_ago or 0.0) / SCHED_HALFLIFE_Y)
        wsum += owr * recency
        wtot += recency
    if wtot == 0:
        return 1.0
    avg_wr = wsum / wtot
    # neutre = SCHED_NEUTRAL_WR ; on mappe autour de 1.0
    if avg_wr >= SCHED_NEUTRAL_WR:
        span = 1.0 - SCHED_NEUTRAL_WR
        return 1.0 + (avg_wr - SCHED_NEUTRAL_WR) / span * (SCHED_MAX - 1.0)
    return 1.0 - (SCHED_NEUTRAL_WR - avg_wr) / SCHED_NEUTRAL_WR * (1.0 - SCHED_MIN)


def f_statut(row: dict) -> float:
    """Reconnaissance de l'orga : champion / rang / P4P / pedigree de titres."""
    factor = 1.0

    if row.get("is_ufc_champion"):
        factor *= STATUS_CHAMPION
    else:
        rank = _safe_int(row.get("ufc_official_rank"), 0)
        if 1 <= rank <= 5:
            factor *= STATUS_RANK_TOP5
        elif 6 <= rank <= 15:
            factor *= STATUS_RANK_TOP15

    p4p = _safe_int(row.get("ufc_p4p_rank"), 0)
    if 1 <= p4p <= 15:
        factor *= 1.0 + STATUS_P4P_BONUS

    # pedigree : avoir gagne des combats de titre, c'est etre passe au sommet
    title_wins = _safe_int(row.get("ufc_title_match_win"))
    if title_wins > 0:
        factor *= 1.0 + min(title_wins, STATUS_TITLE_CAP) * STATUS_TITLE_PER

    return factor


def f_durabilite(row: dict) -> float:
    """Le menton : beaucoup de defaites par finition (KO surtout) + age = chute."""
    age = _age_of(row) or 0
    total_losses = _safe_int(row.get("record_total_losses"))
    if total_losses <= 0 or age < DURABILITY_AGE_GATE:
        return 1.0
    ko_losses  = _safe_int(row.get("losses_by_ko_tko"))
    sub_losses = _safe_int(row.get("losses_by_submission"))
    finish_ratio = (ko_losses + DURABILITY_SUB_WEIGHT * sub_losses) / total_losses
    return DURABILITY_FACTOR if finish_ratio >= DURABILITY_RATIO_GATE else 1.0


def f_physique(row: dict) -> float:
    """Allonge + taille vs moyenne de la division (tables) + petit edge de stance."""
    morpho = 0.0

    reach = _first_float(row.get("reach_inches"))
    avg_reach = _division_avg(row, DIVISION_AVG_REACH)
    if reach is not None and avg_reach is not None:
        morpho += (reach - avg_reach) * REACH_PER_INCH

    height = _parse_height_inches(row.get("height_inches"))
    avg_height = _division_avg(row, DIVISION_AVG_HEIGHT)
    if height is not None and avg_height is not None:
        morpho += (height - avg_height) * HEIGHT_PER_INCH

    factor = 1.0 + max(-REACH_CLAMP, min(REACH_CLAMP, morpho))

    stance = (row.get("stance") or "").lower()
    if "south" in stance:
        factor *= 1.0 + STANCE_SOUTHPAW
    elif "switch" in stance:
        factor *= 1.0 + STANCE_SWITCH

    return factor


def _division_avg(row: dict, table: dict) -> Optional[float]:
    """Moyenne (allonge ou taille) de la division du fighter dans `table`."""
    wc = (row.get("weight_class_current") or "").lower()
    gender = "W" if (row.get("gender") == "F") else "M"
    for (div_name, div_gender), avg in table.items():
        if div_gender == gender and div_name in wc:
            return avg
    return None


def f_niveau_ufc(row: dict) -> float:
    """Part de la carriere passee en UFC (= teste au plus haut niveau)."""
    ufc = _safe_int(row.get("record_ufc_wins")) + _safe_int(row.get("record_ufc_losses"))
    total = _safe_int(row.get("total_fights"))
    if total <= 0:
        total = _safe_int(row.get("record_total_wins")) + _safe_int(row.get("record_total_losses"))
    if total <= 0:
        return 1.0
    share = min(1.0, ufc / total)
    return _around_one(share, UFC_LEVEL_MIN, UFC_LEVEL_MAX, neutral=UFC_SHARE_NEUTRAL)


def f_winrate(row: dict) -> float:
    """Taux de victoire sur la carriere (dominance directe, complement de l'elo)."""
    wp = _safe_float(row.get("win_percentage_int"))
    if wp is None:
        wins = _safe_int(row.get("record_total_wins"))
        losses = _safe_int(row.get("record_total_losses"))
        if wins + losses == 0:
            return 1.0
        wp = wins / (wins + losses) * 100.0
    # mappe autour de WINRATE_NEUTRAL_PCT (en 0-1 via /100, neutre = neutral/100)
    return _around_one(wp / 100.0, WINRATE_MIN, WINRATE_MAX, neutral=WINRATE_NEUTRAL_PCT / 100.0)


def f_activite(row: dict) -> float:
    """
    Rythme sur les DERNIERES annees. PENALITE seulement (regle Elias) :
      - >= 1 combat/an recemment           -> 1.0 (aucune penalite, jamais de bonus)
      - moins                              -> malus proportionnel au manque
      - carriere trop courte / pas d'histo -> 1.0 (on ne juge pas)
    On compte les combats du fight_history tombant dans la fenetre recente.
    """
    years_ago_list = [y for _res, _owr, y in _iter_fights(row) if y is not None]
    if not years_ago_list:
        return 1.0

    # fenetre = min(fenetre standard, anciennete de la carriere) pour ne pas
    # punir un debutant qui n'a logiquement pas encore X combats.
    window = ACTIVITY_WINDOW_YEARS
    debut = row.get("career_debut_date")
    if debut:
        try:
            career_years = (date.today() - date.fromisoformat(str(debut)[:10])).days / 365.25
            window = min(window, career_years)
        except (ValueError, TypeError):
            pass
    if window < ACTIVITY_MIN_CAREER_YEARS:
        return 1.0

    recent_count = sum(1 for y in years_ago_list if y <= ACTIVITY_WINDOW_YEARS)
    rate = recent_count / window
    if rate >= ACTIVITY_TARGET_PER_YEAR:
        return 1.0
    deficit = ACTIVITY_TARGET_PER_YEAR - rate   # 0 (juste sous le seuil) .. 1 (rien)
    return max(ACTIVITY_FLOOR, 1.0 - deficit * ACTIVITY_PENALTY)


def f_ligue(row: dict) -> float:
    """Niveau de l'organisation actuelle (UFC > regional). Inconnue -> 1.0."""
    league = (row.get("current_league") or "").strip().upper()
    if not league:
        return 1.0
    if league in LEAGUE_FACTOR:
        return LEAGUE_FACTOR[league]
    return LEAGUE_REGIONAL   # ligue connue mais hors du top -> petit malus


def f_categorie(row: dict) -> float:
    """Malus si le fighter combat hors de sa categorie d'origine."""
    cur = _norm_wc(row.get("weight_class_current"))
    ori = _norm_wc(row.get("weight_class_origin"))
    if cur and ori and cur != ori:
        return WEIGHT_CLASS_AWAY
    return 1.0


def f_split(row: dict) -> float:
    """
    Qualite des decisions : une victoire en split (combat serre) retire un poil ;
    une defaite en split en redonne un poil. Effet total borne a +/- SPLIT_CLAMP.
    """
    sw = _safe_int(row.get("split_decision_wins"))
    sl = _safe_int(row.get("split_decision_losses"))
    delta = -sw * SPLIT_WIN_PEN + sl * SPLIT_LOSS_GAIN
    return 1.0 + max(-SPLIT_CLAMP, min(SPLIT_CLAMP, delta))


def f_experience(row: dict) -> float:
    """Volume de carriere : un prospect est moins eprouve qu'un veteran (doux)."""
    tf = _safe_int(row.get("total_fights"))
    if tf <= 0:
        # pas de total_fights -> on tente la somme des records
        tf = _safe_int(row.get("record_total_wins")) + _safe_int(row.get("record_total_losses"))
    if tf <= 0:
        return 1.0
    if tf <= EXPERIENCE_ANCHORS[0][0]:
        return EXPERIENCE_ANCHORS[0][1]
    if tf >= EXPERIENCE_ANCHORS[-1][0]:
        return EXPERIENCE_ANCHORS[-1][1]
    for (n0, v0), (n1, v1) in zip(EXPERIENCE_ANCHORS, EXPERIENCE_ANCHORS[1:]):
        if n0 <= tf <= n1:
            return v0 + (v1 - v0) * (tf - n0) / (n1 - n0)
    return 1.0


# =============================================================================
# Le point d'entree principal
# =============================================================================

# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] _FACTORS — la liste complète des ~20 coefficients multiplicatifs
# chacun une fonction f_*  |  ordre = affichage debug uniquement (produit commutatif)
# ═══════════════════════════════════════════════════════════════════             ------------------------------  finish par exemple    puis scouter dynamique ds app.py 
# l'ordre est juste pour l'affichage debug ; le produit est commutatif. -----------------------------------------------------------  postprocess_fighter(row):
_FACTORS = (
    ("forme",       f_forme),        # forme recente (5 derniers)        -- gros poids
    ("streak",      f_streak),       # serie W/L en cours                -- gros poids
    ("age",         f_age),          # courbe d'age (pic 27-31)
    ("inactivite",  f_inactivite),   # ring rust (actifs only)
    ("finish",      f_finish),       # capacite a finir (bonus pur)
    ("fm_rating",   f_fm_rating),    # FM rating_points       \
    ("fm_quality",  f_fm_quality),   # FM quality_perf_pct      } 4 facteurs FM
    ("fm_540",      f_fm_540),       # FM 540_metric            } separes (FM pese fort)
    ("fm_bigleague", f_fm_bigleague),# FM big_league_record    /
    ("calendrier",  f_calendrier),   # winrate des adversaires (a la volee)
    ("statut",      f_statut),       # champion / rang / P4P / titres
    ("durabilite",  f_durabilite),   # menton (KO encaisses x age)
    ("physique",    f_physique),     # allonge + taille vs division + stance
    ("categorie",   f_categorie),    # hors de sa categorie d'origine ?
    ("split",       f_split),        # qualite des decisions (split)
    ("experience",  f_experience),   # volume de carriere
    ("niveau_ufc",  f_niveau_ufc),   # part de carriere au plus haut niveau
    ("winrate",     f_winrate),      # taux de victoire carriere
    ("activite",    f_activite),     # rythme recent (penalite seulement)
    ("ligue",       f_ligue),        # niveau de l'organisation actuelle
)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] ENTRÉE PRINCIPALE — compute_scouter(row) → float | None
# JAMAIS stocké en BDD, recalculé à chaque appel API depuis les colonnes existantes
# ═══════════════════════════════════════════════════════════════════     
def compute_scouter(row: dict) -> Optional[float]:
    """
    Calcule le Scouter Rating a partir d'un row de fighter (recalcul complet,
    rien n'est mis en cache ni en dur par fighter).

    Renvoie None si :
      - le fighter est inactif (is_active = False)  -> pas de scouter, juste l'elo
      - il n'a aucun combat (impossible a evaluer)
      - on n'a pas d'elo de base (la base, c'est l'elo : sans lui, rien)

    Sinon :  scouter = base_elo_normalise  x  clamp(produit des facteurs)
    (pas de plafond a 100 : un phenomene peut depasser, c'est voulu)
    """
    if not _is_active(row):
        return None

    wins   = _safe_int(row.get("record_total_wins"))
    losses = _safe_int(row.get("record_total_losses"))
    if wins + losses == 0:
        return None

    elo = _safe_float(row.get("base_elo"))
    if elo is None:
        return None
    base = _base_from_elo(elo)

    product = 1.0
    for _, fn in _FACTORS:
        product *= fn(row)
    # 📌 [DÉMO] clamp du produit [0.45 ; 1.90] — PAS la note finale (cf. PRODUCT_FLOOR)   # puis FACTORS en haut
    product = max(PRODUCT_FLOOR, min(PRODUCT_CEIL, product))

    return round(base * product, 1)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] DEBUG — détail complet : base + chaque facteur + produit brut + final
# utilisé pour la page méthodologie et la calibration manuelle
# ═══════════════════════════════════════════════════════════════════
def compute_scouter_debug(row: dict) -> dict:
    """
    Detail complet du calcul (base, chaque facteur, produit, final).
    Pour verifier la calibration sur des fighters connus et alimenter la page methodo.
    """
    if not _is_active(row):
        return {"scouter": None, "reason": "inactif (les inactifs n'ont pas de scouter)"}

    wins   = _safe_int(row.get("record_total_wins"))
    losses = _safe_int(row.get("record_total_losses"))
    if wins + losses == 0:
        return {"scouter": None, "reason": "aucun combat"}

    elo = _safe_float(row.get("base_elo"))
    if elo is None:
        return {"scouter": None, "reason": "pas d'elo de base"}

    base = _base_from_elo(elo)
    factors = {name: round(fn(row), 4) for name, fn in _FACTORS}
    raw_product = 1.0
    for v in factors.values():
        raw_product *= v
    product = max(PRODUCT_FLOOR, min(PRODUCT_CEIL, raw_product))
    final = round(base * product, 1)

    return {
        "scouter":         final,
        "base_elo":        round(elo, 1),
        "base_score":      round(base, 2),     # l'elo ramene sur 0-100
        "factors":         factors,            # chaque multiplicateur, dans l'ordre
        "product_raw":     round(raw_product, 4),
        "product_clamped": round(product, 4),
        "amplitude":       [PRODUCT_FLOOR, PRODUCT_CEIL],
        "inputs": {
            "wins":            wins,
            "losses":          losses,
            "recent_form":     _safe_float(row.get("recent_form_score")),
            "streak":          row.get("current_streak"),
            "age":             _age_of(row),
            "days_inactive":   _days_inactive(row),
            "finish_rate":     _safe_float(row.get("finish_rate_int")),
            "fm_points":       _safe_float(row.get("fightmatrix_rating_points")),
            "fm_quality_pct":  _safe_float(row.get("fightmatrix_quality_perf_pct")),
            "fm_540":          _safe_float(row.get("fightmatrix_540_metric")),
            "fm_big_league":   row.get("fightmatrix_big_league_record"),
            "is_champion":     row.get("is_ufc_champion"),
            "rank":            row.get("ufc_official_rank"),
            "p4p_rank":        row.get("ufc_p4p_rank"),
            "title_wins":      _safe_int(row.get("ufc_title_match_win")),
            "weight_current":  row.get("weight_class_current"),
            "weight_origin":   row.get("weight_class_origin"),
            "split_wins":      _safe_int(row.get("split_decision_wins")),
            "split_losses":    _safe_int(row.get("split_decision_losses")),
            "total_fights":    _safe_int(row.get("total_fights")),
            "reach":           _first_float(row.get("reach_inches")),
            "height":          _parse_height_inches(row.get("height_inches")),
            "stance":          row.get("stance"),
            "ufc_record":      f"{_safe_int(row.get('record_ufc_wins'))}-{_safe_int(row.get('record_ufc_losses'))}",
            "win_pct":         _safe_float(row.get("win_percentage_int")),
            "career_debut":    row.get("career_debut_date"),
            "current_league":  row.get("current_league"),
        },
    }
