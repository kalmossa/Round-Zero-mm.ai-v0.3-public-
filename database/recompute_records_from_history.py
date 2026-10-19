#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mm.ai - recalcule record_total_* depuis le fight_history Tapology.

POURQUOI ?
Les bilans (W-D-L) affiches etaient faux : aucune hierarchie de sources n'etait
appliquee entre deux scrapes. Selon la source qui scrappait en DERNIER (ou la
"regle du MAX" cote API qui gardait le plus gros total), un record FightMatrix
(amateurs inclus) ou un historique partiel ecrasait le record Tapology pourtant
fiable. Exemples observes sur la fight-card UFC :
    Steve Garcia  21-6  chez nous  vs  19-5  Tapology   (FM sur-comptait)
    Chandler      19-8  chez nous  vs  23-10 Tapology   (historique partiel)
    Gaethje       26-5  chez nous  vs  27-5  Tapology   (stale)

DECISION ELIAS (juin 2026) : HIERARCHIE DE SOURCES
    Tapology  >  UFC-FR = FightMatrix  >  Underground
Tapology fait foi sur le record. Ce script applique retroactivement cette regle
a TOUTE la base, sans avoir a re-scraper tout le monde : pour chaque fighter dont
le fight_history stocke vient de Tapology, on recompte W/L/D/NC depuis cet
historique et on ecrase record_total_* (meme si ca fait BAISSER le record).

Les fighters SANS historique Tapology ne sont pas touches (le filet "MAX" cote
api/app.py continue de les gerer).

USAGE :
    py database/recompute_records_from_history.py                 # dry-run (lecture seule)
    py database/recompute_records_from_history.py --commit        # ecrit en BDD
    py database/recompute_records_from_history.py --commit --limit 50

Apres --commit, pense a relancer les ratings qui dependent du record :
    py database/calculate_all_elos.py --commit
    py database/calculate_scouter.py --commit
"""

import sys
import json
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "database"))
from db_connection import get_connection  # noqa: E402

# La meme hierarchie que le scraper (scrapers/scrape_mma.py::SOURCE_PRIORITY).
# Duplique ici volontairement pour que ce script database/ reste autonome
# (pas d'import croise vers scrapers/).
SOURCE_PRIORITY = {
    "tapology":        4,
    "ufcstats+scrape": 3,
    "event_scrape":    3,
    "ufc_fr":          2,
    "ufc":             2,
    "fightmatrix":     2,
    "underground":     1,
    "unknown":         0,
}
# Source de fight_history >= ce seuil -> fait foi sur record_total (tapology,
# ufcstats, event_scrape). En dessous (fightmatrix...) -> on ne touche a rien.
RECORD_AUTHORITATIVE_MIN = 3


def record_from_authoritative_history(fh_raw):
    """
    (w, l, d, nc) si fh_raw est un fight_history d'une source AUTORITAIRE
    (tapology / ufcstats / event_scrape) lisible et non vide, sinon None
    (-> on ne touche pas a ce fighter).
    """
    if not fh_raw:
        return None
    try:
        fh = json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(fh, dict):
        return None
    if SOURCE_PRIORITY.get((fh.get("source") or "").strip().lower(), 0) < RECORD_AUTHORITATIVE_MIN:
        return None
    fights = fh.get("fights") or []
    if not fights:
        return None
    w = l = d = nc = 0
    for f in fights:
        if not isinstance(f, dict):
            continue
        r = (f.get("result") or "").strip().upper()
        if r == "W":
            w += 1
        elif r == "L":
            l += 1
        elif r == "D":
            d += 1
        elif r in ("NC", "N/C"):
            nc += 1
    return (w, l, d, nc)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="Ecrit en BDD (sinon dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="Limite le nombre de fighters traites (test)")
    args = ap.parse_args()

    print("=" * 70)
    print("  RECOMPUTE record_total_* depuis fight_history Tapology")
    print(f"  Mode : {'ECRITURE BDD (--commit)' if args.commit else 'DRY-RUN (lecture seule)'}")
    print("=" * 70)

    conn = get_connection()
    if not conn:
        print("/!\\ Connexion BDD echouee (verifie .env)")
        sys.exit(1)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name,
               record_total_wins, record_total_losses,
               record_total_draws, record_total_nc,
               fight_history
        FROM fighters
        WHERE fight_history IS NOT NULL AND fight_history <> ''
        ORDER BY id
        """
    )
    rows = cur.fetchall()

    scanned = changed = 0
    for fid, name, w0, l0, d0, nc0, fh_raw in rows:
        if args.limit is not None and scanned >= args.limit:
            break
        scanned += 1
        rec = record_from_authoritative_history(fh_raw)
        if rec is None:
            continue
        w, l, d, nc = rec
        cur_total = (w0 or 0, l0 or 0, d0 or 0, nc0 or 0)
        if cur_total == (w, l, d, nc):
            continue
        changed += 1
        old_s = f"{w0 or 0}-{l0 or 0}-{d0 or 0}" + (f"-{nc0}nc" if nc0 else "")
        new_s = f"{w}-{l}-{d}" + (f"-{nc}nc" if nc else "")
        print(f"  id={fid:<6} {name[:32]:<32} {old_s:>12}  ->  {new_s}")
        if args.commit:
            cur.execute(
                """
                UPDATE fighters
                SET record_total_wins = %s, record_total_losses = %s,
                    record_total_draws = %s, record_total_nc = %s
                WHERE id = %s
                """,
                (w, l, d, nc, fid),
            )

    print("-" * 70)
    print(f"  Fighters scannes : {scanned}")
    print(f"  Records corriges : {changed}")

    if args.commit:
        conn.commit()
        print("  -> COMMIT effectue.")
        print("  Pense a relancer : calculate_all_elos.py --commit puis calculate_scouter.py --commit")
    else:
        print("  [DRY-RUN] rien ecrit. Relance avec --commit pour persister.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
