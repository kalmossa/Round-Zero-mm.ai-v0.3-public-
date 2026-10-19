"""
recompute_from_history.py
Recalcule depuis le fight_history deja en BDD (sans rescraper) :
  - last_5_results   (ex: "W,L,W,W,L")
  - wins_by_ko_tko / wins_by_submission / wins_by_decision
  - losses_by_ko_tko / losses_by_submission / losses_by_decision
  - career_debut_date (date du combat le plus ancien)

Utile quand le scraper Tapology n'a pas rempli ces champs
alors que le fight_history contient toute l'info.

USAGE :
    py database/recompute_from_history.py           # dry-run (affiche sans ecrire)
    py database/recompute_from_history.py --commit  # ecrit en BDD
"""

import sys
import re
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "database"))
from db_connection import get_connection


# --------------------------------------------------------------------------
# Classifie la methode d'un combat depuis le champ "date" du fight_history
# (convention projet : le champ "date" stocke la methode, pas la date)
# ex: "TKO (Flying Knee & Punches) Round 1" -> "tko"
#     "Submission (Triangle Choke) Round 2"  -> "sub"
#     "Decision (Unanimous)"                  -> "dec"
# --------------------------------------------------------------------------

def _classify_method(date_field: str) -> str:
    """Retourne 'ko_tko', 'sub', 'dec', ou '' si inconnu."""
    d = (date_field or "").lower()
    if re.search(r"\b(ko|tko|ko/tko|knockout|technical knockout)\b", d):
        return "ko_tko"
    if re.search(r"\b(sub|submission|choke|lock|bar|kimura|guillotine|triangle|rear.naked)\b", d):
        return "sub"
    if re.search(r"\bdec(ision)?\b", d):
        return "dec"
    return ""


def recompute_fighter(fh_raw: str) -> dict | None:
    """
    Parse le fight_history JSON et retourne un dict avec les champs a mettre a jour.
    Retourne None si rien a recalculer.
    """
    try:
        fh = json.loads(fh_raw)
    except Exception:
        return None

    fights = fh.get("fights", [])
    if not fights:
        return None

    # Filtre : on ne garde que les combats MMA (pas grappling, annules, etc.)
    # Les combats grappling n'ont pas de result W/L/D clair
    mma_fights = [
        f for f in fights
        if f.get("result") in ("W", "L", "D", "NC")
    ]
    if not mma_fights:
        return None

    updates = {}

    # last_5_results (les 5 premiers = les plus recents, fight_history est newest-first)
    last5 = [f["result"] for f in mma_fights[:5]]
    if last5:
        updates["last_5_results"] = ",".join(last5)

    # wins_by_* / losses_by_*
    wins_ko = wins_sub = wins_dec = 0
    losses_ko = losses_sub = losses_dec = 0

    for f in mma_fights:
        method = _classify_method(f.get("date", ""))
        if f["result"] == "W":
            if method == "ko_tko":    wins_ko  += 1
            elif method == "sub":     wins_sub += 1
            elif method == "dec":     wins_dec += 1
        elif f["result"] == "L":
            if method == "ko_tko":   losses_ko  += 1
            elif method == "sub":    losses_sub += 1
            elif method == "dec":    losses_dec += 1

    # On ecrase seulement si on a trouve au moins quelque chose
    total_methods = wins_ko + wins_sub + wins_dec + losses_ko + losses_sub + losses_dec
    if total_methods > 0:
        updates["wins_by_ko_tko"]      = wins_ko
        updates["wins_by_submission"]  = wins_sub
        updates["wins_by_decision"]    = wins_dec
        updates["losses_by_ko_tko"]    = losses_ko
        updates["losses_by_submission"] = losses_sub
        updates["losses_by_decision"]  = losses_dec

    # career_debut_date (combat le plus ancien avec une date ISO)
    dates = []
    for f in mma_fights:
        ed = f.get("event_date", "")
        if ed and re.match(r"\d{4}-\d{2}-\d{2}", ed):
            dates.append(ed)
    if dates:
        updates["career_debut_date"] = min(dates)

    return updates if updates else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Ecrire en BDD (defaut: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Limiter a N fighters (0=tous)")
    args = parser.parse_args()

    conn = get_connection()
    if not conn:
        print("Connexion DB impossible"); return

    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, fight_history
        FROM fighters
        WHERE fight_history IS NOT NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} fighters avec fight_history")

    updated = 0
    skipped = 0
    total = 0

    for fid, name, fh_raw in rows:
        if args.limit and total >= args.limit:
            break
        total += 1

        upd = recompute_fighter(fh_raw)
        if not upd:
            skipped += 1
            continue

        if args.commit:
            set_parts = [f"{col} = %s" for col in upd]
            vals = list(upd.values()) + [fid]
            cur.execute(
                f"UPDATE fighters SET {', '.join(set_parts)} WHERE id = %s",
                vals,
            )
        else:
            # dry-run : affiche les premiers cas
            if updated < 10:
                print(f"  [{fid}] {name}")
                for k, v in upd.items():
                    print(f"      {k} = {v!r}")

        updated += 1

    if args.commit:
        conn.commit()
        print(f"\n  COMMIT : {updated} fighters mis a jour, {skipped} ignores (pas de combats)")
    else:
        print(f"\n  DRY-RUN : {updated} fighters seraient mis a jour (lance avec --commit)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
