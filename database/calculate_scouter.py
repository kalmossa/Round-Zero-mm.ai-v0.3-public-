#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mm.ai - le calcul du Scouter Rating + du Recent Form Score
recalcule pour CHAQUE fighter :

  1. recent_form_score  (0-1)   - forme sur les 5 derniers combats
  2. scouter_rating     (0-100) - note globale "capacite actuelle"

pourquoi une v2 ?
la v1 lisait des tables qui ont ete supprimees du schema depuis (v_fighter_career,
skills_profile, external_ratings, scouter_history). Le schema est devenu
MONO-TABLE (`fighters`, 62 colonnes). La v2 lit donc UNIQUEMENT la table plate
`fighters` + parse la colonne TEXT `fight_history` (JSON), exactement comme
api/app.py.

le modele (ce que j'ai choisi)
le scouter mesure la capacite ACTUELLE ("qui gagne ce soir"), pas le
palmares all-time. Consequence : les modificateurs de contexte (age, forme,
inactivite, momentum...) pesent FORT.

Deux natures d'information, combinees differemment :

  NIVEAU  (= "quel est son plafond")  -> MOYENNE PONDEREE des signaux de force,
          ramenee sur 0-100. On NE multiplie PAS ces signaux entre eux (ils
          mesurent la meme chose -> double comptage + explosion d'echelle).

  MODIF   (= "ajuste ce niveau ici/maintenant") -> SOMME AMORTIE de facteurs
          centres sur 1.0 :
                MODIF = clamp( 1 + Somme( poids_i * (facteur_i - 1) ), 0.78, 1.20 )
          Plus stable qu'un produit pur (ne peut pas exploser), et le poids de
          chaque facteur est explicite et reglable.

Formule finale :
    NIVEAU  = blend(base_elo, externes, qualite_carriere, profil)        [0-100]
    MODIF   = somme amortie(age, forme, inactivite, momentum, durabilite,
                            physique, style, activite)
    brut    = NIVEAU * MODIF
    scouter = moy_division + (brut - moy_division) * confiance   (shrinkage)

Le "shrinkage" ramene les combattants peu documentes (peu de combats, data
incomplete, adversaires inconnus) vers la moyenne de leur division : un
prospect regional a 3 combats contre des inconnus ne doit pas truster le top.

TOUS LES SIGNAUX PRIS EN COMPTE (colonne -> ou il entre)
  base_elo .......................... NIVEAU (colonne vertebrale, 40%)
  fightmatrix_rating_points ......... NIVEAU externes
  fightmatrix_540_metric ............ NIVEAU externes   (echelle a verifier, cf CONFIG)
  fightmatrix_quality_perf_pct ...... NIVEAU externes   (deja 0-100)
  ufc_official_rank ................. NIVEAU externes (rang -> score inverse)
  ufc_p4p_rank ...................... NIVEAU externes (elite cross-division)
  fight_history (JSON) .............. NIVEAU qualite carriere (elo adversaires)
  finish_rate_int ................... NIVEAU profil
  win_percentage_int ................ NIVEAU profil
  wins_by_ko_tko/submission/decision  NIVEAU profil (polyvalence du finisseur)
  split_decision_wins/losses ........ NIVEAU profil (qualite des decisions)
  is_ufc_champion ................... NIVEAU profil (pedigree)
  ufc_title_match_win ............... NIVEAU profil (pedigree)
  age / date_of_birth ............... MODIF F_age
  recent_form_score / last_5_results  MODIF F_forme
  days_inactive / is_active ......... MODIF F_inactivite
  current_streak .................... MODIF F_momentum
  losses_by_ko_tko + age ............ MODIF F_durabilite (menton x age)
  reach_inches / height_inches / stance  MODIF F_physique (vs moyenne division)
  first_sport ....................... MODIF F_style (base lutteur/grappleur)
  total_fights / career_debut_date .. MODIF F_activite (combats par an)
  total_fights / data_quality_score /
    is_verified / % adv. connus ..... CONFIANCE (shrinkage)

  TOUTES les valeurs numeriques (facteurs, poids, seuils) sont regroupees dans
  le bloc CONFIG ci-dessous. Elles SONT FAITES POUR CHANGER : tuner = editer
  une seule table. A calibrer empiriquement avec backend/src/ml/backtest.py
  (maximiser accuracy / minimiser brier) plutot qu'au doigt mouille.

USAGE
    py database/calculate_scouter.py                 # DRY-RUN (rien ecrit)
    py database/calculate_scouter.py --commit        # ecrit en BDD
    py database/calculate_scouter.py --fighter "Jon Jones" --verbose
    py database/calculate_scouter.py --active-only --commit

Pre-requis : lancer calculate_all_elos.py AVANT (la qualite de carriere lit le
base_elo deja converge des adversaires). Maintenance conseillee : 1x/mois.
"""

import sys
import math
import json
import re
import argparse
import unicodedata
from pathlib import Path
from datetime import date, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "database"))
from db_connection import get_connection  # noqa: E402


# config - toutes les constantes réglables sont ici (toutes commentées).
#  Modifie ces valeurs pour re-calibrer le scouter ; ne touche pas au reste.

# --- Poids du blend NIVEAU (somme ~1.0 ; renormalises si une brique manque) --
W_LEVEL_BASE_ELO = 0.40   # notre Elo chronologique (le plus fiable)
W_LEVEL_EXTERNAL = 0.18   # consensus des notes externes (FM / UFC)
W_LEVEL_CAREER   = 0.27   # qualite reelle des adversaires affrontes
W_LEVEL_PROFILE  = 0.15   # style / dominance / pedigree

# --- Normalisation Elo -> 0-100 (percentile auto-calibre au runtime) ---------
# probleme avec la logistique fixe (elo_center=1600, scale=180) :
#   La distribution reelle : min=1201, mediane=1532, max=1839.
#   Avec ELO_CENTER=1600, le meilleur fighter (1839) obtenait seulement 79/100.
#   Champions sous-notes, fighters moyens surestimes.
#
# la solution : interpolation segmentée sur 3 ancres calculées au runtime.
#   min  -> 5/100   |   mediane -> 50/100   |   max -> 95/100
#   (Les variables ELO_NORM_* sont ecrasees par calibrate_elo_norm().)
ELO_NEUTRAL  = 1500.0    # Elo suppose d'un adversaire totalement inconnu

# --- Externes ----------------------------------------------------------------
FM_POINTS_MAX  = 500.0    # fightmatrix_rating_points est sur ~0-500 -> /5
# FM 540 : echelle 0-1 (verifie en BDD : min=0, max=1.0, mediane=0.62).
# Etait divise par 500 → donnait 0.16 pour Kape (0.81) au lieu de 81.
# Correction : multiplier par 100 directement.
# FM_540_MAX = 500 n'est plus utilise mais conserve en commentaire pour reference.
RANK_SCORE_TOP = 100.0    # score d'un #1
RANK_SCORE_STEP = 2.0     # -2 pts par place (rang 15 -> 72)

# --- Qualite carriere --------------------------------------------------------
CAREER_RECENCY_HALFLIFE_Y = 5.0   # un combat de 5 ans pese moitie moins
CAREER_LOSS_TO_WEAK_MULT  = 0.5   # ampleur du malus "defaite contre faible"
CAREER_LOSS_TO_STRONG_SOFT = 0.3  # adoucit la defaite contre un fort
CAREER_FINISH_BONUS = 1.10        # un combat fini (KO/SUB) pese un peu plus
CAREER_RECENTER = 50.0            # recadrage des bonus/malus dans 0-100
#
# correctif adversaires inconnus — BUG majeur
#   Un adversaire non identifie en BDD recoit un elo estime depuis son rang
#   historique (ex: "#1 Heavyweight" → 1900). Mais ce rang peut venir d'un show
#   regional obscur ou rien ne signifie grand chose. Sans correction, un fighter
#   avec 20 adversaires "inconnus" bien classes gonfle artificiellement sa carriere.
#   Solution : regression vers la neutralite (opp_q=50) pour les inconnus.
#   CAREER_UNKNOWN_TRUST = 1.0 → confiance totale (comportement original, deconseille)
#   career_unknown_trust = 0.0 → tous les inconnus valent 50/100 (trop agressif)
#   CAREER_UNKNOWN_TRUST = 0.35 → bon equilibre : l'info du rang persiste mais devaluee
CAREER_UNKNOWN_TRUST = 0.35
#
# bonus victoire elite : battre quelqu'un d'exceptionnel (opp_q >= seuil) merite
# un bonus supplementaire (recompense les vrais grands combats).
# Seuil 82 = elo ~1870+ (top 3-5 d'une division), pas juste "solide UFC".
# Bonus 8 pts (etait 12 → reduire pour ne pas sur-crediter les prospects actifs).
CAREER_ELITE_WIN_THRESHOLD = 82.0   # opp_q au-dela duquel on ajoute un bonus (etait 75)
CAREER_ELITE_WIN_BONUS     = 8.0    # points bonus ajoutes au bonus standard   (etait 12)

# --- Facteurs d'AGE (pic ~27-31). Interpolation lineaire entre ces ancres. ---
#  (age, facteur). Tes reperes : 28 -> ~1.04, 35 -> ~0.92.
AGE_ANCHORS = [
    (18, 0.93), (21, 0.97), (24, 1.01), (27, 1.04), (31, 1.04),
    (33, 0.99), (35, 0.92), (37, 0.87), (39, 0.83), (42, 0.80), (50, 0.78),
]

# --- F_forme : recent_form_score (0-1) -> facteur [FORM_MIN, FORM_MAX] --------
FORM_MIN, FORM_MAX = 0.90, 1.10   # forme 0.5 = neutre (1.00)

# --- F_inactivite : days_inactive -> facteur ---------------------------------
#  Pour les combattants ACTIFS : penalite pleine (ring rust reel).
#  Pour les RETRAITES (is_active=False) : penalite douce (ils ont choisi
#  d'arreter, pas necesairement en baisse de forme, mais "ce soir" ils ne se
#  battent plus → doivent ceder leur place aux actifs dans le classement).
INACTIVITY_STEPS = [   # (jours_min, facteur) trie croissant
    (0,    1.00),
    (365,  0.98),   # > 1 an
    (540,  0.95),   # > 1.5 an
    (730,  0.90),   # > 2 ans
    (1095, 0.85),   # > 3 ans
]
# Scale de la penalite pour les retraites :
#   0.0 → aucune penalite (comportement original — BUG : GSP, Khabib dans top 15)
#   1.0 → penalite identique aux actifs
#   0.55 → penalite moderee (un retraite 3 ans perd ~8% au lieu de 15%)
INACTIVITY_RETIRED_SCALE = 0.55

# --- F_momentum : current_streak --------------------------------------------
MOMENTUM_WIN5  = 1.05   # serie >= +5
MOMENTUM_WIN3  = 1.03   # serie +3/+4
MOMENTUM_NEUTRAL = 1.00 # -2..+2
MOMENTUM_LOSS3 = 0.94   # serie <= -3

# --- F_durabilite : part des defaites par FINITION (KO+SUB) * age -----------
#  Un combattant souvent fini (au KO ou a la soumission) ET age = signal de
#  chute. Le KO pese plus que la soumission (menton > defense de soumission).
DURABILITY_FINISH_RATIO  = 0.40   # seuil (KO + 0.6*SUB) / defaites
DURABILITY_SUB_WEIGHT    = 0.60   # une defaite par soumission = 0.6 d'un KO
DURABILITY_AGE_GATE      = 33     # ne s'active qu'apres cet age
DURABILITY_FACTOR        = 0.95

# --- F_physique : allonge + taille vs moyenne de division + stance ----------
REACH_PER_INCH  = 0.006  # +/- par pouce d'allonge au-dessus/dessous de la moyenne
HEIGHT_PER_INCH = 0.003  # +/- par pouce de taille (signal plus faible que l'allonge)
REACH_CLAMP     = 0.04   # borne de l'effet morphologique
STANCE_SOUTHPAW = 0.015  # petit edge statistique gaucher
STANCE_SWITCH   = 0.008

# --- F_style : sport d'origine (base lutteur/grappleur favorise en MMA) ------
STYLE_GRAPPLER = 1.03    # wrestling / bjj / judo / sambo / grappling
STYLE_STRIKER  = 1.00    # boxe / muay-thai / karate / tkd (neutre)

# --- Niveau de competition (brique NIVEAU/profil) ---------------------------
#  Un combattant qui evolue/a evolue dans une grande organisation affronte une
#  opposition plus dure. Score 0-100 par ligue actuelle ; fallback selon
#  l'experience UFC (a-t-il deja combattu en UFC ?).
LEAGUE_TIER = {
    "UFC": 100.0, "PFL": 82.0, "BELLATOR": 82.0, "ONE": 80.0,
    "RIZIN": 78.0, "KSW": 72.0, "PRIDE": 95.0, "STRIKEFORCE": 88.0,
}
TIER_UFC_EXPERIENCE = 62.0   # pas la ligue listee mais un passe UFC avere
TIER_DEFAULT        = 45.0   # regional / inconnu

# --- F_activite : combats par an sur la carriere ----------------------------
ACTIVITY_HIGH  = 1.02    # >= 2.5 combats/an (tres actif, affute)
ACTIVITY_LOW   = 0.98    # < 0.7 combat/an (peu actif)

# --- POIDS de chaque facteur dans la somme amortie MODIF --------------------
#  Plus le poids est grand, plus le facteur deplace le scouter.
MODIF_WEIGHTS = {
    "age":        1.0,   # 1er predicteur du declin
    "form":       1.0,   # coeur du "ce soir"
    "inactivity": 1.0,
    "momentum":   0.5,   # recouvre la forme -> demi-poids (anti double comptage)
    "durability": 0.7,
    "physique":   0.3,   # signal faible mais reel
    "style":      0.2,   # tres faible
    "activity":   0.2,   # recouvre l'inactivite -> faible
}
MODIF_FLOOR, MODIF_CEIL = 0.78, 1.08   # garde-fou anti-explosion du produit
# MODIF_CEIL abaisse de 1.20 → 1.14 → 1.08 : avec level~88 et modif=1.14
# on atteignait raw=100 ce qui saturait le scouter. x1.08 = ±8% max,
# suffisant pour récompenser la forme sans capper tout le monde à 100.

# --- CONFIANCE / shrinkage --------------------------------------------------
CONF_FULL_FIGHTS = 15    # nb de combats au-dela duquel on fait pleine confiance
# Etait 8 → trop bas : un fighter a 9 combats atteignait deja c_fights=1.0.
# Avec 15 : 9 combats → c_fights = 0.60, 15 combats → 1.0. Plus discriminant.
#
# correctif poids confiance — BUG : avec conf_w_known = 0.20, un fighter avec
# 35% d'adversaires connus (ex. Natalia Silva 9/26) obtenait confiance=0.90
# car total_fights et data_quality_score dominaient largement.
# Resultat : shrinkage quasi nul → le score gonfle par des rangs regionaux
# n'etait pas corrige. On remonte CONF_W_KNOWN a 0.35 pour que le % d'adversaires
# identifiables pese vraiment dans la fiabilite du score.
CONF_W_FIGHTS  = 0.40    # poids du nb de combats          (etait 0.50)
CONF_W_QUALITY = 0.25    # poids de data_quality_score     (etait 0.30)
CONF_W_KNOWN   = 0.35    # poids du % d'adversaires en BDD (etait 0.20 — BUG)
CONF_VERIFIED_BONUS   = 1.05  # multiplicateur si is_verified
CONF_CHAMPION_BONUS   = 1.12  # champion UFC : preuve de qualite independante des adversaires en BDD
CONF_TOP3_BONUS       = 1.07  # top 3 UFC (rank 1-3) non champion
CONF_FLOOR = 0.15        # on garde toujours un minimum de signal propre

# --- Recent form score (0-1) ------------------------------------------------
RECENT_FORM_WEIGHTS = [1.0, 0.8, 0.6, 0.4, 0.2]   # du + recent au + ancien
RF_FINISH_BONUS = 0.05   # +/- si la (de)faite est une finition
RF_TOP_WIN_BONUS = 0.10  # battre un top (elo >= seuil)
RF_WEAK_LOSS_MALUS = 0.10  # perdre contre un faible
RF_TOP_ELO  = 2050.0
RF_WEAK_ELO = 1600.0


# les helpers numériques / parsing

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def norm_elo(elo):
    """
    Elo -> 0-100 par interpolation percentile segmentee auto-calibree.

    Trois ancres (calculees par calibrate_elo_norm depuis les elos reels) :
      ELO_NORM_MIN  (min reel) -> 5
      ELO_NORM_MED  (mediane)  -> 50   fighter median = exactement 50
      ELO_NORM_MAX  (max reel) -> 95   meilleur fighter actuel = 95 (pas 100 :
                                       100 = fighter mythique impossible)
    Entre ancres : interpolation lineaire. Hors bornes : extrapolation clampee.
    """
    if elo is None:
        return None
    try:
        elo = float(elo)
    except (TypeError, ValueError):
        return None
    lo, med, hi = ELO_NORM_MIN, ELO_NORM_MED, ELO_NORM_MAX
    if elo <= med:
        if med == lo:
            return 50.0
        return clamp(5.0 + (elo - lo) / (med - lo) * 45.0, 0.0, 50.0)
    else:
        if hi == med:
            return 50.0
        return clamp(50.0 + (elo - med) / (hi - med) * 45.0, 50.0, 100.0)


# Variables globales remplies par calibrate_elo_norm() (defaults raisonnables)
ELO_NORM_MIN = 1200.0
ELO_NORM_MED = 1532.0
ELO_NORM_MAX = 1839.0


def calibrate_elo_norm(rows):
    """
    Calcule ELO_NORM_MIN / MED / MAX depuis les elos reels du batch.
    A appeler une seule fois en debut de pipeline (avant process_all).
    """
    global ELO_NORM_MIN, ELO_NORM_MED, ELO_NORM_MAX
    elos = sorted(float(r["base_elo"]) for r in rows if r.get("base_elo") is not None)
    n = len(elos)
    if n < 10:
        return
    ELO_NORM_MIN = elos[0]
    ELO_NORM_MED = elos[n // 2]
    ELO_NORM_MAX = elos[-1]
    print(f"  Calibration elo : min={ELO_NORM_MIN:.0f}→5 | "
          f"med={ELO_NORM_MED:.0f}→50 | max={ELO_NORM_MAX:.0f}→95  "
          f"({n} fighters avec elo / {len(rows)} total)")



def parse_first_float(s):
    """Extrait le 1er nombre d'une chaine ('76\"' -> 76.0, '193 cm' -> 193.0)."""
    if s is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else None


def to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def norm_name(s):
    """Normalise un nom pour le matching : minuscule, sans accents/ponctuation."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


_SPLIT_OPP_RE = re.compile(r"^(.+?)\s+(#\d+\s+.+)$")


def split_opponent_name(opponent_text):
    """'Tatsuro Taira #3 Flyweight' -> ('Tatsuro Taira', '#3 Flyweight')."""
    if not opponent_text:
        return "", ""
    s = str(opponent_text).strip()
    m = _SPLIT_OPP_RE.match(s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""


# la méthode réelle est stockée dans le champ "date" du JSON (cf api/app.py)
_METHOD_RE = re.compile(
    r"^\s*(?:Technical\s+|Tech\s+|Tech\.\s+)?"
    r"(KO/TKO|KO|TKO|Submission|Sub|Decision|Dec|DQ|No\s+Contest|NC|Draw|Forfeit)",
    re.IGNORECASE,
)
_METHOD_NORM = {
    "ko/tko": "KO", "ko": "KO", "tko": "KO",
    "submission": "SUB", "sub": "SUB",
    "decision": "DEC", "dec": "DEC",
    "dq": "DQ", "no contest": "NC", "nc": "NC", "draw": "DRAW", "forfeit": "FF",
}


def parse_method(method_text):
    """Renvoie la methode normalisee : KO / SUB / DEC / DQ / NC / DRAW / ''."""
    if not method_text:
        return ""
    m = _METHOD_RE.match(str(method_text).strip())
    if not m:
        return ""
    return _METHOD_NORM.get(m.group(1).lower(), m.group(1).upper())


_EVENT_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def parse_event_date(event_text):
    """Extrait la date ISO d'un libelle d'event, ou None."""
    if not event_text:
        return None
    m = _EVENT_DATE_RE.search(str(event_text))
    if not m:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    except (ValueError, KeyError):
        return None


def estimate_elo_from_rank(rank_str):
    """
    Estime un Elo depuis un rang historique ('#3 Flyweight').
    Copie volontaire de elo_dynamic.estimate_elo_from_rank (script autonome).
    """
    if not rank_str:
        return ELO_NEUTRAL
    m = re.search(r"#(\d+)", str(rank_str))
    if not m:
        return ELO_NEUTRAL
    r = int(m.group(1))
    if r <= 1:
        return 1900.0
    if r <= 5:
        return 1900.0 - (r - 1) * 30
    if r <= 15:
        return 1780.0 - (r - 5) * 10.8
    if r <= 30:
        return 1672.0 - (r - 15) * 11.5
    if r <= 60:
        return 1500.0 - (r - 30) * 3.3
    return max(1200.0, 1400.0 - (r - 60) * 1.5)


def years_since(d):
    if d is None:
        return 10.0
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            return 10.0
    return (date.today() - d).days / 365.25


def load_fights(fight_history_raw):
    """Parse la colonne fight_history (TEXT JSON) -> liste de combats parses."""
    if not fight_history_raw:
        return []
    try:
        fh = json.loads(fight_history_raw) if isinstance(fight_history_raw, str) else fight_history_raw
    except (json.JSONDecodeError, TypeError):
        return []
    raw = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    out = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        opp_name, opp_rank = split_opponent_name(f.get("opponent"))
        out.append({
            "result": (f.get("result") or "").strip().upper(),
            "opponent_name": opp_name,
            "opponent_rank": opp_rank,
            # la "method" réelle est dans "date" (donnée scrapée, cf api/app.py)
            "method": parse_method(f.get("date") or f.get("method")),
            "event_date": parse_event_date(f.get("event")),
        })
    return out


#  niveau - briques 0-100

def level_external(row):
    """Consensus des notes externes (FM points / 540 / quality% / rangs UFC)."""
    parts = []
    pts = row.get("fightmatrix_rating_points")
    if pts is not None:
        parts.append(clamp(float(pts) / FM_POINTS_MAX * 100.0, 0, 100))
    m540 = row.get("fightmatrix_540_metric")
    if m540 is not None:
        # Scale 0-1 (verifie BDD) → *100 pour ramener en 0-100
        parts.append(clamp(float(m540) * 100.0, 0, 100))
    qpp = row.get("fightmatrix_quality_perf_pct")
    if qpp is not None:
        parts.append(clamp(float(qpp), 0, 100))   # deja 0-100
    for rk in (row.get("ufc_official_rank"), row.get("ufc_p4p_rank")):
        if rk is not None and int(rk) >= 1:
            parts.append(clamp(RANK_SCORE_TOP - (int(rk) - 1) * RANK_SCORE_STEP, 0, 100))
    return sum(parts) / len(parts) if parts else None


def level_profile(row, fights=None):
    """Style / dominance / pedigree -> 0-100 (remplace l'ancien skills_profile)."""
    parts = []   # (valeur, poids)

    fr = row.get("finish_rate_int")
    if fr is not None:
        parts.append((clamp(float(fr), 0, 100), 0.30))

    wp = row.get("win_percentage_int")
    if wp is not None:
        parts.append((clamp(float(wp), 0, 100), 0.25))

    # Polyvalence : finit-il debout ET au sol ?
    # Priorite 1 : colonnes BDD wins_by_* (remplies pour ~29 fighters seulement).
    # Priorite 2 : derive du fight_history parse (disponible pour presque tous).
    # Priorite 3 : estimation depuis finish_rate_int (dernier recours).
    ko  = to_int(row.get("wins_by_ko_tko"))
    sub = to_int(row.get("wins_by_submission"))
    dec = to_int(row.get("wins_by_decision"))
    if ko == 0 and sub == 0 and dec == 0:
        # Colonnes BDD vides (99.7% des fighters) → derive du fight_history
        if fights:
            ko  = sum(1 for f in fights if f["result"] == "W" and f["method"] == "KO")
            sub = sum(1 for f in fights if f["result"] == "W" and f["method"] == "SUB")
            dec = sum(1 for f in fights if f["result"] == "W" and f["method"] == "DEC")
        if ko == 0 and sub == 0 and dec == 0 and fr is not None:
            # Dernier recours : si finish_rate > 0, on sait qu'il finit
            # mais on ignore la methode → on attribue un seul bucket "finish"
            if float(fr) >= 50:
                ko = 1   # au moins un type de finition presente
    kinds = sum(1 for x in (ko, sub, dec) if x > 0)
    versatility = {0: 40.0, 1: 55.0, 2: 75.0, 3: 95.0}[kinds]
    parts.append((versatility, 0.15))

    # Qualite des victoires : trop de decisions partagees = moins dominant.
    wins = to_int(row.get("record_total_wins"))
    sdw = to_int(row.get("split_decision_wins"))
    if wins > 0:
        split_share = sdw / wins
        parts.append((clamp(100.0 - split_share * 50.0, 0, 100), 0.10))

    # Pedigree : champion / combats de titre gagnes.
    pedigree = 0.0
    if row.get("is_ufc_champion"):
        pedigree = 100.0
    else:
        pedigree = min(100.0, to_int(row.get("ufc_title_match_win")) * 25.0)
    parts.append((pedigree, 0.20))

    # Niveau de competition : ligue actuelle, ou experience UFC averee.
    # Poids monte de 0.18 → 0.30 : discriminateur UFC vs regional indispensable.
    # Sans ce poids, un regional bien fitte (beau record, bonnes stats) passe
    # un combattant UFC etabli. Ce facteur agit comme un "plancher de credibilite".
    parts.append((level_competition(row), 0.30))

    tw = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / tw if tw > 0 else None


def level_competition(row):
    """Score 0-100 du niveau d'opposition organisationnel (cf LEAGUE_TIER)."""
    league = (row.get("current_league") or "").strip().upper()
    if league in LEAGUE_TIER:
        return LEAGUE_TIER[league]
    has_ufc = (to_int(row.get("record_ufc_wins")) + to_int(row.get("record_ufc_losses"))) > 0
    return TIER_UFC_EXPERIENCE if has_ufc else TIER_DEFAULT


def level_career(fights, name_index, fighter_row):
    """
    Qualite de carriere : moyenne ponderee de la qualite des adversaires,
    modulee par le resultat, la methode et la recence. Renvoie (score|None,
    nb_known, nb_total).
    """
    if not fights:
        return None, 0, 0

    f_gender = (fighter_row.get("gender") or "M")
    f_wc = (fighter_row.get("weight_class_current") or "")
    weighted_sum = weight_total = 0.0
    nb_known = nb_total = 0

    for f in fights:
        res = f["result"]
        if res not in ("W", "L", "D"):
            continue
        nb_total += 1

        opp_elo, known = resolve_opponent_elo(
            f["opponent_name"], f["opponent_rank"], f_gender, f_wc, name_index)
        if known:
            nb_known += 1

        opp_q = norm_elo(opp_elo)   # 0-100

        # correctif adversaires inconnus : regression vers la neutralité (50).
        # Un "#1 regional" estime a 1900 elo n'est PAS equivalent a un vrai #1
        # UFC. On ne supprime pas l'info (le rang donne quand meme un signal)
        # mais on la devalue fortement via CAREER_UNKNOWN_TRUST.
        if not known:
            opp_q = opp_q * CAREER_UNKNOWN_TRUST + 50.0 * (1.0 - CAREER_UNKNOWN_TRUST)

        if res == "W":
            bonus = opp_q
            # Bonus supplementaire pour les victoires contre l'elite veritable :
            # battre un adversaire identifie ET de haut niveau merite plus.
            if known and opp_q >= CAREER_ELITE_WIN_THRESHOLD:
                bonus += CAREER_ELITE_WIN_BONUS
        elif res == "L":          # perdre vs faible = lourd ; vs fort = adouci
            bonus = -(100.0 - opp_q) * CAREER_LOSS_TO_WEAK_MULT + opp_q * CAREER_LOSS_TO_STRONG_SOFT
        else:                     # nul
            bonus = opp_q * 0.7

        mult = CAREER_FINISH_BONUS if f["method"] in ("KO", "SUB") else 1.0
        w = (0.5 ** (years_since(f["event_date"]) / CAREER_RECENCY_HALFLIFE_Y)) * mult
        weighted_sum += bonus * w
        weight_total += w

    if weight_total == 0:
        return None, nb_known, nb_total
    score = clamp(weighted_sum / weight_total + CAREER_RECENTER, 0, 100)
    return score, nb_known, nb_total


def resolve_opponent_elo(opp_name, opp_rank, f_gender, f_wc, name_index):
    """
    Trouve le base_elo d'un adversaire par son nom (matching BDD).
    Renvoie (elo, known_bool). known=False -> estimation depuis le rang.
    """
    cands = name_index.get(norm_name(opp_name))
    if cands:
        # Desambiguisation legere : meme genre puis meme division, sinon meilleur elo.
        pool = [c for c in cands if (c["gender"] or "M") == f_gender] or cands
        same_div = [c for c in pool if (c["wc"] or "") == f_wc]
        pick = (same_div or pool)
        pick = max(pick, key=lambda c: c["base_elo"] if c["base_elo"] is not None else -1)
        if pick["base_elo"] is not None:
            return float(pick["base_elo"]), True
    # Inconnu en BDD (ou sans elo) -> estimation depuis le rang historique.
    return estimate_elo_from_rank(opp_rank), False


def compute_level(row, fights, name_index):
    """Blend NIVEAU (0-100) + renvoie aussi les briques pour le verbose."""
    base = norm_elo(row.get("base_elo"))
    ext = level_external(row)
    career, nb_known, nb_total = level_career(fights, name_index, row)
    profile = level_profile(row, fights)   # fights → derive wins_by_method si colonnes vides

    bricks = {"base": base, "external": ext, "career": career, "profile": profile}
    weights = {
        "base": W_LEVEL_BASE_ELO, "external": W_LEVEL_EXTERNAL,
        "career": W_LEVEL_CAREER, "profile": W_LEVEL_PROFILE,
    }
    active = {k: w for k, w in weights.items() if bricks[k] is not None}
    tw = sum(active.values())
    if tw == 0:
        return None, bricks, nb_known, nb_total
    level = sum(bricks[k] * (active[k] / tw) for k in active)
    return level, bricks, nb_known, nb_total


#  modificateurs (centres sur 1.0)

def f_age(age):
    if age is None:
        return 1.0
    age = float(age)
    anchors = AGE_ANCHORS
    if age <= anchors[0][0]:
        return anchors[0][1]
    if age >= anchors[-1][0]:
        return anchors[-1][1]
    for (a0, v0), (a1, v1) in zip(anchors, anchors[1:]):
        if a0 <= age <= a1:
            return v0 + (v1 - v0) * (age - a0) / (a1 - a0)   # interpolation lineaire
    return 1.0


def f_form(recent_form_score):
    if recent_form_score is None:
        return 1.0
    return FORM_MIN + (FORM_MAX - FORM_MIN) * clamp(float(recent_form_score), 0, 1)


def f_inactivity(days_inactive, is_active):
    """
    Penalite d'inactivite / retraite.
    - Actif avec longue absence  → penalite pleine (ring rust documenté).
    - Retraite (is_active=False)  → penalite moderee (INACTIVITY_RETIRED_SCALE) :
      ils meritent une penalite "ce soir" mais moindre que le ring rust pur.
      Sans ce correctif, GSP (retraite 2019), Khabib, Fedor apparaissent
      dans le top 15 "qui gagne ce soir" ce qui est absurde.
    - days_inactive=None ET actif → pas de penalite (donnee manquante).
    """
    if days_inactive is None:
        return 1.0
    d = float(days_inactive)
    base_factor = INACTIVITY_STEPS[0][1]
    for threshold, val in INACTIVITY_STEPS:
        if d >= threshold:
            base_factor = val
    if not is_active:
        # retraite : penalite ecretee par inactivity_retired_scale
        base_factor = 1.0 + (base_factor - 1.0) * INACTIVITY_RETIRED_SCALE
    return base_factor


def parse_streak(streak_str):
    """'W5'->+5, 'L3'->-3, '+2'->+2, '0'->0 ..."""
    if streak_str is None:
        return 0
    s = str(streak_str).strip().upper()
    m = re.search(r"(\d+)", s)
    n = int(m.group(1)) if m else 0
    if s.startswith("L") or s.startswith("-"):
        return -n
    return n


def f_momentum(streak_str):
    s = parse_streak(streak_str)
    if s >= 5:
        return MOMENTUM_WIN5
    if s >= 3:
        return MOMENTUM_WIN3
    if s <= -3:
        return MOMENTUM_LOSS3
    return MOMENTUM_NEUTRAL


def f_durability(row, age):
    """Souvent fini (KO + soumission, le KO pesant plus) + age = signal de chute."""
    ko_losses = to_int(row.get("losses_by_ko_tko"))
    sub_losses = to_int(row.get("losses_by_submission"))
    total_losses = to_int(row.get("record_total_losses"))
    if total_losses <= 0 or age is None:
        return 1.0
    finish_ratio = (ko_losses + DURABILITY_SUB_WEIGHT * sub_losses) / total_losses
    if finish_ratio >= DURABILITY_FINISH_RATIO and age >= DURABILITY_AGE_GATE:
        return DURABILITY_FACTOR
    return 1.0


_GRAPPLER_KW = ("wrestl", "jiu", "bjj", "judo", "sambo", "grappl", "lutte")


def f_style(first_sport):
    if not first_sport:
        return 1.0
    s = str(first_sport).lower()
    return STYLE_GRAPPLER if any(k in s for k in _GRAPPLER_KW) else STYLE_STRIKER


def f_physique(row, div_size):
    """Allonge + taille vs moyenne de la division + petit edge de stance."""
    morpho = 0.0
    means = div_size.get(division_key(row)) or {}
    reach = parse_first_float(row.get("reach_inches"))
    if reach is not None and means.get("reach") is not None:
        morpho += (reach - means["reach"]) * REACH_PER_INCH
    height = parse_first_float(row.get("height_inches"))
    if height is not None and means.get("height") is not None:
        morpho += (height - means["height"]) * HEIGHT_PER_INCH
    factor = 1.0 + clamp(morpho, -REACH_CLAMP, REACH_CLAMP)
    stance = (row.get("stance") or "").lower()
    if "south" in stance:
        factor += STANCE_SOUTHPAW
    elif "switch" in stance:
        factor += STANCE_SWITCH
    return factor


def f_activity(row):
    """Combats par an sur la carriere : tres actif = affute, rare = rouille."""
    debut = row.get("career_debut_date")
    last = row.get("last_fight_date")
    total = to_int(row.get("total_fights"))
    if not debut or not last or total <= 0:
        return 1.0
    span = years_since(debut) - years_since(last)
    if span < 0.5:
        return 1.0
    per_year = total / span
    if per_year >= 2.5:
        return ACTIVITY_HIGH
    if per_year < 0.7:
        return ACTIVITY_LOW
    return 1.0


def compute_modif(row, age, recent_form, div_size):
    """Somme amortie des facteurs -> MODIF (clamp). Renvoie (modif, detail)."""
    factors = {
        "age":        f_age(age),
        "form":       f_form(recent_form),
        "inactivity": f_inactivity(row.get("days_inactive"), bool(row.get("is_active"))),
        "momentum":   f_momentum(row.get("current_streak")),
        "durability": f_durability(row, age),
        "physique":   f_physique(row, div_size),
        "style":      f_style(row.get("first_sport")),
        "activity":   f_activity(row),
    }
    deviation = sum(MODIF_WEIGHTS[k] * (factors[k] - 1.0) for k in factors)
    modif = clamp(1.0 + deviation, MODIF_FLOOR, MODIF_CEIL)
    return modif, factors


#  recent FORM score (0-1)

def compute_recent_form(fights, name_index, row):
    """Forme sur les 5 derniers combats (du fight_history)."""
    if not fights:
        return _recent_form_from_last5(row)
    recent = [f for f in fights if f["result"] in ("W", "L", "D")]
    recent.sort(key=lambda f: (f["event_date"] or date.min), reverse=True)
    recent = recent[:5]
    if not recent:
        return _recent_form_from_last5(row)

    f_gender = (row.get("gender") or "M")
    f_wc = (row.get("weight_class_current") or "")
    wsum = wtot = 0.0
    for i, f in enumerate(recent):
        res = f["result"]
        w = RECENT_FORM_WEIGHTS[i] if i < len(RECENT_FORM_WEIGHTS) else 0.1
        score = 1.0 if res == "W" else 0.5 if res == "D" else 0.0
        if f["method"] in ("KO", "SUB"):
            score += RF_FINISH_BONUS if res == "W" else (-RF_FINISH_BONUS if res == "L" else 0)
        opp_elo, _ = resolve_opponent_elo(f["opponent_name"], f["opponent_rank"], f_gender, f_wc, name_index)
        if res == "W" and opp_elo >= RF_TOP_ELO:
            score += RF_TOP_WIN_BONUS
        elif res == "L" and opp_elo < RF_WEAK_ELO:
            score -= RF_WEAK_LOSS_MALUS
        wsum += clamp(score, 0, 1) * w
        wtot += w
    return round(clamp(wsum / wtot, 0, 1), 3) if wtot else None


def _recent_form_from_last5(row):
    """Fallback : derive la forme depuis la colonne last_5_results (ex 'WWLWW')."""
    s = row.get("last_5_results")
    if not s:
        return None
    results = [c for c in str(s).upper() if c in ("W", "L", "D")]
    if not results:
        return None
    wsum = wtot = 0.0
    for i, r in enumerate(results[:5]):
        w = RECENT_FORM_WEIGHTS[i] if i < len(RECENT_FORM_WEIGHTS) else 0.1
        wsum += (1.0 if r == "W" else 0.5 if r == "D" else 0.0) * w
        wtot += w
    return round(clamp(wsum / wtot, 0, 1), 3) if wtot else None


#  confiance / shrinkage

def compute_confidence(row, nb_known, nb_total):
    c_fights = clamp(to_int(row.get("total_fights")) / CONF_FULL_FIGHTS, 0, 1)
    c_quality = clamp(to_int(row.get("data_quality_score")) / 100.0, 0, 1)
    c_known = (nb_known / nb_total) if nb_total > 0 else 0.5
    conf = (CONF_W_FIGHTS * c_fights
            + CONF_W_QUALITY * c_quality
            + CONF_W_KNOWN * c_known)
    if row.get("is_verified"):
        conf *= CONF_VERIFIED_BONUS
    # Statut champion / top 3 : preuve de qualite independante du matching BDD.
    # Un champion invaincu ne doit pas perdre 6 pts de shrinkage parce que
    # 8/17 de ses adversaires regionaux ne sont pas en BDD.
    if row.get("is_ufc_champion"):
        conf *= CONF_CHAMPION_BONUS
    elif to_int(row.get("ufc_official_rank")) in (1, 2, 3):
        conf *= CONF_TOP3_BONUS
    return clamp(conf, CONF_FLOOR, 1.0)


def division_key(row):
    wc = (row.get("weight_class_gendered") or row.get("weight_class_current") or "Unknown")
    return wc


#  pipeline

def build_name_index(rows):
    """{ nom_normalise: [ {id, base_elo, gender, wc}, ... ] } pour le matching."""
    idx = {}
    for r in rows:
        idx.setdefault(norm_name(r["name"]), []).append({
            "id": r["id"], "base_elo": r.get("base_elo"),
            "gender": r.get("gender"), "wc": r.get("weight_class_current"),
        })
    return idx


def build_division_size_means(rows):
    """Allonge ET taille moyennes par division (pour F_physique)."""
    acc = {}
    for r in rows:
        k = division_key(r)
        d = acc.setdefault(k, {"reach": [], "height": []})
        reach = parse_first_float(r.get("reach_inches"))
        if reach is not None:
            d["reach"].append(reach)
        height = parse_first_float(r.get("height_inches"))
        if height is not None:
            d["height"].append(height)
    out = {}
    for k, d in acc.items():
        out[k] = {
            "reach": (sum(d["reach"]) / len(d["reach"])) if d["reach"] else None,
            "height": (sum(d["height"]) / len(d["height"])) if d["height"] else None,
        }
    return out


def process_all(rows, verbose_name=None):
    """Calcule tout en 2 passes (raw -> moyennes division -> shrinkage)."""
    calibrate_elo_norm(rows)   # auto-calibre la normalisation elo sur la vraie distribution
    name_index = build_name_index(rows)
    div_size = build_division_size_means(rows)

    # ---- PASSE 1 : brut + recent_form pour chaque fighter ------------------
    results = {}
    div_raw = {}        # division -> [raw, ...]  (pour la moyenne de shrinkage)
    all_raw = []
    for r in rows:
        fights = load_fights(r.get("fight_history"))
        age = r.get("age")
        recent_form = compute_recent_form(fights, name_index, r)
        level, bricks, nb_known, nb_total = compute_level(r, fights, name_index)
        if level is None:
            results[r["id"]] = {"row": r, "scouter": None, "recent_form": recent_form}
            continue
        modif, factors = compute_modif(r, age, recent_form, div_size)
        raw = clamp(level * modif, 0, 100)
        conf = compute_confidence(r, nb_known, nb_total)
        dk = division_key(r)
        div_raw.setdefault(dk, []).append(raw)
        all_raw.append(raw)
        results[r["id"]] = {
            "row": r, "level": level, "bricks": bricks, "modif": modif,
            "factors": factors, "raw": raw, "conf": conf, "div": dk,
            "recent_form": recent_form, "nb_known": nb_known, "nb_total": nb_total,
        }

    # ---- moyennes de division (fallback global si division trop petite) ----
    global_mean = sum(all_raw) / len(all_raw) if all_raw else 50.0
    div_mean = {k: (sum(v) / len(v)) for k, v in div_raw.items()}

    # ---- PASSE 2 : shrinkage vers la moyenne de division -------------------
    for rid, res in results.items():
        if "raw" not in res:
            continue  # niveau manquant -> scouter deja a None en passe 1
        dk = res["div"]
        mean = div_mean.get(dk, global_mean) if len(div_raw.get(dk, [])) >= 5 else global_mean
        scouter = mean + (res["raw"] - mean) * res["conf"]
        # Cap à 97 : personne n'est parfait, 100 = fighter mythique impossible.
        res["scouter"] = round(clamp(scouter, 0, 97), 2)
        res["div_mean"] = round(mean, 1)

    if verbose_name:
        for res in results.values():
            if norm_name(res["row"]["name"]) == norm_name(verbose_name):
                _print_breakdown(res)
    return results


def _print_breakdown(res):
    r = res["row"]
    print(f"\n=== {r['name']} (id={r['id']}, {r.get('weight_class_gendered')}) ===")
    if res.get("scouter") is None:
        print("  scouter = NULL (aucun signal de niveau exploitable)")
        return
    b = res["bricks"]
    print("  NIVEAU briques :")
    for k in ("base", "external", "career", "profile"):
        v = b.get(k)
        print(f"    - {k:9s}: {('%.1f' % v) if v is not None else '  -- (manquant)'}")
    print(f"  NIVEAU blend   : {res['level']:.1f}")
    print("  MODIF facteurs :")
    for k, v in res["factors"].items():
        print(f"    - {k:11s}: x{v:.3f}  (poids {MODIF_WEIGHTS[k]})")
    print(f"  MODIF total    : x{res['modif']:.3f}")
    print(f"  brut           : {res['raw']:.1f}")
    print(f"  confiance      : {res['conf']:.2f}  (adv. connus {res['nb_known']}/{res['nb_total']})")
    print(f"  moy. division  : {res.get('div_mean')}")
    print(f"  recent_form    : {res['recent_form']}")
    print(f"  >>> SCOUTER    : {res['scouter']}")


#  persistence

def write_results(conn, results):
    cur = conn.cursor()
    n = 0
    for rid, res in results.items():
        sc = res.get("scouter")
        rf = res.get("recent_form")
        if sc is None and rf is None:
            continue
        cur.execute("""
            UPDATE fighters SET
                scouter_rating    = COALESCE(%s, scouter_rating),
                recent_form_score = COALESCE(%s, recent_form_score)
            WHERE id = %s
        """, (sc, rf, rid))
        n += 1
        if n % 500 == 0:
            conn.commit()
    conn.commit()
    cur.close()
    return n


# le main

# Colonnes lues (toutes celles qui portent un signal). SELECT explicite pour
# documenter la dependance et eviter de tirer fight_history en double.
_SELECT_COLS = """
    id, name, gender, age, date_of_birth, nationality,
    weight_class_current, weight_class_gendered, weight_class_origin,
    height_inches, reach_inches, stance, first_sport,
    record_total_wins, record_total_losses, record_total_draws, record_total_nc,
    record_ufc_wins, record_ufc_losses, record_other_wins, record_other_losses,
    wins_by_ko_tko, wins_by_submission, wins_by_decision,
    losses_by_ko_tko, losses_by_submission, losses_by_decision,
    split_decision_wins, split_decision_losses,
    career_debut_date, last_fight_date, days_inactive, is_active,
    current_league, is_ufc_champion, ufc_title_match_win, total_fights,
    win_percentage_int, finish_rate_int, current_streak, last_5_results,
    recent_form_score, base_elo, scouter_rating,
    fightmatrix_rating_points, fightmatrix_540_metric, fightmatrix_quality_perf_pct,
    ufc_official_rank, ufc_p4p_rank, data_quality_score, is_verified, fight_history
"""


def main():
    ap = argparse.ArgumentParser(description="MM.AI - Scouter Rating v2")
    ap.add_argument("--commit", action="store_true", help="Ecrit en BDD (sinon dry-run)")
    ap.add_argument("--fighter", help="Limite l'affichage detaille a ce fighter")
    ap.add_argument("--active-only", action="store_true", help="Ne traiter que is_active=TRUE")
    ap.add_argument("--verbose", action="store_true", help="Detail complet du fighter cible")
    args = ap.parse_args()

    print("=" * 72)
    print("  MM.AI - Calcul du Scouter Rating (v2.0 maximal)")
    print("=" * 72)
    print(f"  Mode : {'ECRITURE BDD (--commit)' if args.commit else 'DRY-RUN (lecture seule)'}")

    conn = get_connection()
    if conn is None:
        print("[KO] Connexion BDD impossible")
        sys.exit(1)

    # NB : le matching d'adversaires a besoin de TOUTE la base (meme en --fighter)
    # pour retrouver le base_elo des opponents -> on charge toujours tout le monde.
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    where = "WHERE is_active = TRUE" if args.active_only else ""
    cur.execute(f"SELECT {_SELECT_COLS} FROM fighters {where}")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    print(f"  Fighters charges : {len(rows)}")

    results = process_all(rows, verbose_name=(args.fighter if args.verbose else None))

    scored = [res["scouter"] for res in results.values() if res.get("scouter") is not None]
    if scored:
        scored_sorted = sorted(scored, reverse=True)
        print(f"  Scoutes : {len(scored)} | moyenne {sum(scored)/len(scored):.1f} "
              f"| max {scored_sorted[0]:.1f} | min {min(scored):.1f}")

    # Top 15 pour controle visuel rapide
    top = sorted((r for r in results.values() if r.get("scouter") is not None),
                 key=lambda r: r["scouter"], reverse=True)[:15]
    print("\n  Top 15 scouter :")
    for res in top:
        r = res["row"]
        print(f"    {res['scouter']:5.1f}  {r['name'][:30]:30s} {r.get('weight_class_gendered') or '':18s}")

    if args.fighter and not args.verbose:
        for res in results.values():
            if norm_name(res["row"]["name"]) == norm_name(args.fighter):
                _print_breakdown(res)

    if args.commit:
        n = write_results(conn, results)
        print(f"\n[OK] {n} fighters mis a jour (scouter_rating + recent_form_score)")
    else:
        print("\n[DRY-RUN] rien ecrit. Relance avec --commit pour persister.")
    conn.close()
    print("=" * 72)


if __name__ == "__main__":
    main()
