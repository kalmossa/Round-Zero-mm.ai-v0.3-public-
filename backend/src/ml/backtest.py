# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
Backtesting / Validation du modele MM.AI

Evaluation **walk-forward (prequential)** de la regle de notation Elo.

POURQUOI PAS LE base_elo STOCKE ?
Le `base_elo` en BDD est calcule sur la carriere COMPLETE (fixed-point, voir
`batch_compute_all_elos`). L'utiliser pour "predire" un combat passe reviendrait
a tricher : la note connait deja le resultat (fuite temporelle / leakage).

LA BONNE METHODE
On rejoue TOUS les combats dans l'ordre chronologique GLOBAL. Pour chaque combat :
  1. on calcule P(vainqueur) a partir des Elo AVANT le combat (info passee seule) ;
  2. on enregistre prediction vs resultat reel ;
  3. PUIS on met a jour les deux Elo avec le resultat reel.
Chaque prediction n'utilise donc QUE le passe → zero leakage. C'est la facon
canonique d'evaluer un systeme Elo.

On valide ici la **regle Elo** (meme formule expected/K-factor que
`elo_dynamic.py`), pas les chiffres stockes au pixel pres : certitude = 1.0 (les
deux combattants sont en BDD) et une seule passe (pas de fixed-point), puisqu'on
s'interdit toute info future.

METRIQUES PRODUITES
  - accuracy           : % de combats ou le favori MM.AI l'emporte (hors nuls)
  - brier              : erreur quadratique moyenne des probabilites (0 = parfait,
                         0.25 = pile ou face). brier_skill = 1 - brier/0.25
  - log_loss           : log-vraisemblance negative (penalise les certitudes fausses)
  - ece                : Expected Calibration Error (ecart moyen confiance/realite)
  - calibration        : "quand MM.AI est sur a X%, il a raison Y% du temps"
  - by_confidence/method/year/experience : ventilations
  - baseline_record_accuracy : reference naive "le combattant au meilleur bilan
                         (a cet instant) gagne" — pour montrer l'apport du modele

L'entree est volontairement decouplee de la BDD (fonction pure, testable). Le
chargement depuis Postgres vit dans `database/run_backtest.py`.
"""

from __future__ import annotations

import math
from typing import List, Dict, Optional

# On reutilise les constantes + le multiplicateur de finition du VRAI modele,
# pour valider exactement la regle de calcul utilisee en production.
try:
    from .elo_dynamic import _BASE_RATING, _K_BASE, _ELO_MIN, _ELO_MAX, _finish_multiplier
except Exception:  # pragma: no cover - exécution hors package
    _BASE_RATING, _K_BASE, _ELO_MIN, _ELO_MAX = 1500.0, 32.0, 1000.0, 2500.0

    def _finish_multiplier(method: Optional[str]) -> float:
        if not method:
            return 1.0
        m = str(method).upper()
        if m in ("KO", "TKO", "KO/TKO"):
            return 1.10
        if m == "SUB":
            return 1.08
        return 1.0


_EPS = 1e-15
_CALIB_EDGES = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0001]


def _method_group(method: Optional[str]) -> str:
    """Regroupe la methode normalisee en KO/TKO / Submission / Decision / Other."""
    m = (method or "").upper()
    if m in ("KO", "TKO", "KO/TKO"):
        return "KO/TKO"
    if m in ("SUB", "SUBMISSION"):
        return "Submission"
    if m in ("DEC", "DECISION"):
        return "Decision"
    return "Other"


def run_backtest(
    fights: List[Dict],
    *,
    base_rating: float = _BASE_RATING,
    k_base: float = _K_BASE,
    elo_min: float = _ELO_MIN,
    elo_max: float = _ELO_MAX,
    min_fights: int = 2,
) -> Dict:
    """
    Evalue la regle Elo en walk-forward sur une liste de combats DEDUPLIQUEE.

    Args :
      fights : liste de dicts, un par combat physique (PAS deux fois) :
               { "date": "YYYY-MM-DD", "a_id": int, "b_id": int,
                 "result": "W"|"L"|"D" (du point de vue de a),
                 "method": "KO"|"TKO"|"SUB"|"DEC"|... (normalise, optionnel) }
      min_fights : experience minimale (combats deja disputes) exigee des DEUX
               combattants pour qu'un combat compte dans les metriques "headline"
               (evite le bruit de demarrage a froid ou tout le monde est a 1500).
               La ventilation `by_experience` couvre, elle, TOUS les combats.

    Retourne un rapport (dict JSON-serialisable).
    """
    fights = sorted((f for f in fights if f.get("date")), key=lambda f: f["date"])

    elo: Dict[int, float] = {}
    wins: Dict[int, int] = {}
    nf: Dict[int, int] = {}

    samples: List[Dict] = []
    draws = 0

    for f in fights:
        a, b = f["a_id"], f["b_id"]
        res = (f.get("result") or "").upper()
        method = f.get("method")

        ra = elo.get(a, base_rating)
        rb = elo.get(b, base_rating)
        p_a = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

        ea, eb = nf.get(a, 0), nf.get(b, 0)
        exp_min = min(ea, eb)

        if res in ("W", "L"):
            actual_a = 1.0 if res == "W" else 0.0

            if abs(p_a - 0.5) < 1e-9:
                fav_correct = 0.5          # egalite stricte de notes -> pas de favori
                conf = 0.5
            else:
                fav_is_a = p_a > 0.5
                fav_correct = 1.0 if (fav_is_a == (res == "W")) else 0.0
                conf = p_a if fav_is_a else 1.0 - p_a

            wa, wb = wins.get(a, 0), wins.get(b, 0)
            if wa > wb:
                base_correct = 1.0 if res == "W" else 0.0
            elif wa < wb:
                base_correct = 1.0 if res == "L" else 0.0
            else:
                base_correct = 0.5

            samples.append({
                "p_a": p_a,
                "actual_a": actual_a,
                "fav_correct": fav_correct,
                "conf": conf,
                "method": _method_group(method),
                "year": str(f["date"])[:4],
                "exp_min": exp_min,
                "base_correct": base_correct,
            })
        elif res in ("D", "DRAW"):
            actual_a = 0.5
            draws += 1
        else:
            continue  # NC / DQ / inconnu : n'affecte ni metriques ni Elo

        # Mise a jour Elo (somme nulle : delta_b = -delta_a a K identique)
        K = k_base * _finish_multiplier(method)
        delta = K * (actual_a - p_a)
        elo[a] = max(elo_min, min(elo_max, ra + delta))
        elo[b] = max(elo_min, min(elo_max, rb - delta))

        if res == "W":
            wins[a] = wins.get(a, 0) + 1
        elif res == "L":
            wins[b] = wins.get(b, 0) + 1
        nf[a] = ea + 1
        nf[b] = eb + 1

    main = [s for s in samples if s["exp_min"] >= min_fights]
    return _aggregate(main, samples, draws, len(fights), len(elo), min_fights, base_rating, k_base)


#  Agregation

def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _brier(s):
    return (s["p_a"] - s["actual_a"]) ** 2


def _logloss(s):
    p = min(1.0 - _EPS, max(_EPS, s["p_a"]))
    y = s["actual_a"]
    return -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))


def _calibration(samples):
    bins = []
    n_total = len(samples)
    ece = 0.0
    for i in range(len(_CALIB_EDGES) - 1):
        lo, hi = _CALIB_EDGES[i], _CALIB_EDGES[i + 1]
        grp = [s for s in samples if lo <= s["conf"] < hi]
        if not grp:
            bins.append({
                "label": f"{int(lo * 100)}–{int(min(hi, 1.0) * 100)}%",
                "predicted": round((lo + min(hi, 1.0)) / 2 * 100, 1),
                "observed": None, "n": 0,
            })
            continue
        predicted = _mean(s["conf"] for s in grp) * 100
        observed = _mean(s["fav_correct"] for s in grp) * 100
        ece += (len(grp) / n_total) * abs(observed - predicted) if n_total else 0.0
        bins.append({
            "label": f"{int(lo * 100)}–{int(min(hi, 1.0) * 100)}%",
            "predicted": round(predicted, 1),
            "observed": round(observed, 1),
            "n": len(grp),
        })
    return bins, round(ece / 100, 4)


def _group_accuracy(samples, key):
    out: Dict[str, Dict] = {}
    for s in samples:
        k = s[key]
        d = out.setdefault(k, {"n": 0, "correct": 0.0, "brier_sum": 0.0})
        d["n"] += 1
        d["correct"] += s["fav_correct"]
        d["brier_sum"] += _brier(s)
    return out


def _aggregate(main, all_samples, draws, n_fights_total, n_fighters,
               min_fights, base_rating, k_base):
    n = len(main)

    if n == 0:
        overall = {
            "n": 0, "accuracy": None, "brier": None, "brier_skill": None,
            "log_loss": None, "ece": None, "baseline_record_accuracy": None,
            "lift_vs_baseline": None,
        }
        calibration = []
    else:
        accuracy = _mean(s["fav_correct"] for s in main)
        brier = _mean(_brier(s) for s in main)
        logloss = _mean(_logloss(s) for s in main)
        base_acc = _mean(s["base_correct"] for s in main)
        calibration, ece = _calibration(main)
        overall = {
            "n": n,
            "accuracy": round(accuracy * 100, 2),
            "brier": round(brier, 4),
            "brier_skill": round(1.0 - brier / 0.25, 4),
            "log_loss": round(logloss, 4),
            "ece": ece,
            "baseline_record_accuracy": round(base_acc * 100, 2),
            "lift_vs_baseline": round((accuracy - base_acc) * 100, 2),
        }

    def fmt_group(raw, label_key="label"):
        out = []
        for k, d in raw.items():
            out.append({
                label_key: k,
                "n": d["n"],
                "accuracy": round(d["correct"] / d["n"] * 100, 2) if d["n"] else None,
                "brier": round(d["brier_sum"] / d["n"], 4) if d["n"] else None,
            })
        return out

    by_method = sorted(fmt_group(_group_accuracy(main, "method"), "method"),
                       key=lambda x: -x["n"])
    by_year = sorted(fmt_group(_group_accuracy(main, "year"), "year"),
                     key=lambda x: x["year"])

    # Ventilation par experience sur TOUS les combats (montre le cold-start).
    def exp_bucket(e):
        if e == 0:
            return "0 (debut)"
        if e <= 2:
            return "1–2"
        if e <= 5:
            return "3–5"
        if e <= 9:
            return "6–9"
        return "10+"

    for s in all_samples:
        s["_expb"] = exp_bucket(s["exp_min"])
    exp_order = {"0 (debut)": 0, "1–2": 1, "3–5": 2, "6–9": 3, "10+": 4}
    by_experience = sorted(fmt_group(_group_accuracy(all_samples, "_expb"), "bucket"),
                           key=lambda x: exp_order.get(x["bucket"], 9))

    return {
        "params": {
            "base_rating": base_rating,
            "k_base": k_base,
            "min_fights_for_metrics": min_fights,
            "method": "walk-forward prequential Elo (no leakage)",
        },
        "coverage": {
            "fighters_tracked": n_fighters,
            "fights_backtested_total": n_fights_total,
            "fights_in_metrics": n,
            "fights_below_experience_threshold": len(all_samples) - n,
            "draws_excluded": draws,
        },
        "overall": overall,
        "calibration": calibration,
        "by_method": by_method,
        "by_year": by_year,
        "by_experience": by_experience,
    }
