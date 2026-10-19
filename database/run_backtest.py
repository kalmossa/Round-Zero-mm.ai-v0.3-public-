"""
run_backtest.py — Validation walk-forward du modele Elo MM.AI.

Charge les fight_history de la BDD, construit un flux GLOBAL de combats
deduplique (chaque combat physique une seule fois), rejoue tout dans l'ordre
chronologique et evalue la regle Elo SANS fuite temporelle (voir
backend/src/ml/backtest.py). Ecrit un rapport JSON consomme par /api/backtest.

USAGE :
    py database/run_backtest.py                 # calcule + ecrit data/backtest_report.json
    py database/run_backtest.py --min-fights 3  # seuil d'experience pour le headline
    py database/run_backtest.py --out chemin.json
    py database/run_backtest.py --quiet

NOTE : ne touche PAS a la BDD (lecture seule). Idempotent.
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, date, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "database"))

from ml.backtest import run_backtest        # noqa: E402
from db_connection import get_connection    # noqa: E402

DEFAULT_OUT = ROOT / "data" / "backtest_report.json"

#  Parsing dates + methodes (formats scrappes)

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_TEXT_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)


def parse_date(fight) -> str | None:
    """Retourne 'YYYY-MM-DD' depuis un fight, ou None. NE PAS lire le champ
    'date' (il contient la methode dans les donnees scrappees)."""
    # 1) champ event_date deja ISO ?
    for key in ("event_date", "fight_date"):
        v = fight.get(key)
        if v:
            m = _ISO_RE.search(str(v))
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 2) date textuelle embarquee dans 'event'
    ev = fight.get("event")
    if ev:
        m = _TEXT_DATE_RE.search(str(ev))
        if m:
            try:
                d = date(int(m.group(3)), _MONTHS[m.group(1).lower().rstrip(".")],
                         int(m.group(2)))
                return d.isoformat()
            except (ValueError, KeyError):
                pass
    return None


_METHOD_RE = re.compile(
    r"(submission|sub|tko|ko/tko|ko|decision|dec|dq|no\s*contest|nc|draw)",
    re.IGNORECASE,
)


def normalize_method(fight) -> str | None:
    """Methode normalisee (KO/TKO/SUB/DEC/...) depuis le champ 'date' (qui porte
    la methode reelle), fallback 'method'."""
    raw = fight.get("date") or fight.get("method")
    if not raw:
        return None
    m = _METHOD_RE.search(str(raw))
    if not m:
        return None
    tok = m.group(1).lower().replace(" ", "")
    return {
        "submission": "SUB", "sub": "SUB",
        "tko": "TKO", "ko/tko": "KO/TKO", "ko": "KO",
        "decision": "DEC", "dec": "DEC",
        "dq": "DQ", "nocontest": "NC", "nc": "NC", "draw": "DRAW",
    }.get(tok)


def _norm_result(raw) -> str | None:
    if not raw:
        return None
    r = str(raw).strip().upper()
    if r.startswith("W"):
        return "W"
    if r.startswith("L"):
        return "L"
    if r.startswith("D"):
        return "D"
    return None


def _strip_rank(name: str) -> str:
    """'Tatsuro Taira #3 Flyweight' -> 'tatsuro taira'."""
    return name.split("#")[0].strip().lower()


#  Chargement + deduplication en flux global

def load_global_fights(conn, verbose=True):
    cur = conn.cursor()
    cur.execute("SELECT id, name, fight_history FROM fighters WHERE fight_history IS NOT NULL")
    rows = cur.fetchall()

    name_to_id = {}
    for fid, name, _ in rows:
        if name:
            name_to_id.setdefault(name.strip().lower(), fid)

    stats = {"raw_rows": 0, "no_result": 0, "no_opponent_in_db": 0,
             "no_date": 0, "kept_sides": 0, "fighters_with_history": 0}

    seen = {}  # (lo_id, hi_id, date) -> fight dict (du point de vue de lo_id)

    for fid, name, fh_raw in rows:
        if not fh_raw:
            continue
        try:
            fh = json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
        except (json.JSONDecodeError, TypeError):
            continue
        fights = fh.get("fights") if isinstance(fh, dict) else fh
        if not isinstance(fights, list):
            continue
        stats["fighters_with_history"] += 1

        for f in fights:
            if not isinstance(f, dict):
                continue
            stats["raw_rows"] += 1

            result = _norm_result(f.get("result"))
            if not result:
                stats["no_result"] += 1
                continue

            opp_id = name_to_id.get(_strip_rank(f.get("opponent") or ""))
            if not opp_id or opp_id == fid:
                stats["no_opponent_in_db"] += 1
                continue

            d = parse_date(f)
            if not d:
                stats["no_date"] += 1
                continue

            stats["kept_sides"] += 1

            lo, hi = (fid, opp_id) if fid < opp_id else (opp_id, fid)
            key = (lo, hi, d)
            if key in seen:
                continue  # combat deja capture depuis l'autre cote

            # Normaliser le resultat du point de vue de lo
            res_lo = result if fid == lo else ({"W": "L", "L": "W", "D": "D"}[result])
            seen[key] = {
                "date": d,
                "a_id": lo,
                "b_id": hi,
                "result": res_lo,
                "method": normalize_method(f),
            }

    if verbose:
        print(f"  fighters avec historique : {stats['fighters_with_history']}")
        print(f"  lignes de combat brutes  : {stats['raw_rows']}")
        print(f"    - sans resultat W/L/D  : {stats['no_result']}")
        print(f"    - adversaire hors BDD  : {stats['no_opponent_in_db']}")
        print(f"    - sans date exploitable: {stats['no_date']}")
        print(f"  combats physiques uniques: {len(seen)}")

    return list(seen.values()), stats


def main():
    ap = argparse.ArgumentParser(description="Backtest walk-forward du modele Elo MM.AI")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="chemin du rapport JSON")
    ap.add_argument("--min-fights", type=int, default=2,
                    help="experience min (combats deja disputes) des deux combattants pour le headline")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    verbose = not args.quiet

    conn = get_connection()
    if verbose:
        print("Chargement + deduplication des combats...")
    fights, load_stats = load_global_fights(conn, verbose=verbose)
    conn.close()

    if verbose:
        print(f"Backtest sur {len(fights)} combats (min_fights={args.min_fights})...")
    report = run_backtest(fights, min_fights=args.min_fights)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["load_stats"] = load_stats

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    ov = report["overall"]
    print("\n------------ RESULTATS ------------")
    if ov["n"]:
        print(f"  Combats evalues    : {ov['n']}")
        print(f"  Accuracy (favori)  : {ov['accuracy']} %")
        print(f"  Baseline (bilan)   : {ov['baseline_record_accuracy']} %  "
              f"(apport modele : +{ov['lift_vs_baseline']} pts)")
        print(f"  Brier              : {ov['brier']}  (skill {ov['brier_skill']})")
        print(f"  Log loss           : {ov['log_loss']}")
        print(f"  Calibration (ECE)  : {ov['ece']}")
    else:
        print("  Aucun combat exploitable (verifier resolution adversaires / dates).")
    print(f"\n[OK] Rapport ecrit : {out}")


if __name__ == "__main__":
    main()
