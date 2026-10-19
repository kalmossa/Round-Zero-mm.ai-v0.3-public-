"""
mm.ai - OUTIL DE TEST DE L'ELO (debug / vérification)

Détaille, combat par combat, COMMENT l'Elo d'un combattant est calculé :
adversaire, Elo de l'adversaire utilisé + SA SOURCE (bdd / FM / rang / record+ligue
/ ligue seule) + certitude, facteur K, proba attendue, et le delta d'Elo gagné/perdu.

Sert à comprendre les résultats bizarres ("pourquoi X > Y ?") et à régler la
formule. LECTURE SEULE (n'écrit jamais en base).

USAGE
    py database/elo_tool.py "Ciryl Gane"
    py database/elo_tool.py --id 360
    py database/elo_tool.py "Aspinall" "Gane"        # compare 2 fighters (résumé)

NOTE : l'Elo "brut" calculé ici utilise les base_elo des adversaires DÉJÀ stockés
en base (post-rescale). Le batch officiel (calculate_all_elos.py) fait un point
fixe puis un rescale par division -> le base_elo stocké peut donc différer un peu
du "brut" affiché ici. Cet outil sert à voir la MÉCANIQUE, pas le chiffre final
au pixel près.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "database"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

import db_connection as db  # noqa: E402
from ml.elo import elo_from_fm, k_factor, finish_multiplier, _ELO_DEFAULT, get_league_strength  # noqa: E402
from ml.elo.engine import get_opponent_elo_and_certainty, _recency_mult  # noqa: E402
from calculate_all_elos import parse_event_date, parse_method, strip_rank  # noqa: E402


def _opp_source_label(fight, elos, fm_points):
    """Reproduit l'ordre de priorité de get_opponent_elo_and_certainty pour
    afficher D'OÙ vient l'Elo de l'adversaire."""
    oid = fight.get("opponent_id")
    if oid is not None and oid in elos:
        return "BDD"
    if oid is not None and oid in fm_points:
        return "FM"
    if fight.get("opponent_rank") and re.search(r"#(\d+)", str(fight.get("opponent_rank"))):
        return "rang"
    if fight.get("opponent_wins") is not None and fight.get("opponent_losses") is not None:
        return "record+ligue"
    return "ligue"


def load_context(cur):
    # on precharge 3 tables de correspondance utilisees a chaque combat :
    #  - name_to_id : nom (minuscule) -> id, pour retrouver l'adversaire en bdd
    #  - fm_points  : id -> points FightMatrix (sert si l'adversaire a pas d'Elo)
    #  - base_elos  : id -> base_elo deja stocke (la meilleure estim d'adversaire)
    cur.execute("SELECT id, name FROM fighters")
    name_to_id = {r[1].lower(): r[0] for r in cur.fetchall()}
    cur.execute("SELECT id, fightmatrix_rating_points FROM fighters WHERE fightmatrix_rating_points IS NOT NULL")
    fm_points = {r[0]: float(r[1]) for r in cur.fetchall()}
    cur.execute("SELECT id, base_elo FROM fighters WHERE base_elo IS NOT NULL")
    base_elos = {r[0]: float(r[1]) for r in cur.fetchall()}
    return name_to_id, fm_points, base_elos


def parse_fighter_history(fh_raw, name_to_id):
    import json
    try:
        fh = json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
    except Exception:
        return []
    # le JSON peut etre soit {"fights": [...]} soit directement une liste
    fights = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    parsed = []
    for f in fights or []:
        if not isinstance(f, dict):
            continue
        result = (f.get("result") or "").strip().upper()
        if result not in ("W", "L", "D"):
            continue  # on ignore NC / combats sans resultat clair
        # separe le nom de l'adversaire de son rang eventuel ("#3 Jon Jones")
        opp_name, opp_rank = strip_rank(f.get("opponent"))
        opp_id = name_to_id.get(opp_name.lower()) if opp_name else None
        # date : on prend event_date si elle est deja ISO, sinon on la devine
        # depuis le nom de l'evenement (ex "UFC 285" -> date connue)
        ev_date = f.get("event_date")
        if not (ev_date and re.match(r"^\d{4}-\d{2}-\d{2}$", str(ev_date))):
            ev_date = parse_event_date(f.get("event"))
        # record adversaire au moment du combat ("18-1" -> wins=18, losses=1)
        opp_w = opp_l = None
        rec = f.get("opponent_record")
        if rec:
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(rec))
            if m:
                opp_w, opp_l = int(m.group(1)), int(m.group(2))
        parsed.append({
            "result": result, "opponent_id": opp_id, "opponent_name": opp_name,
            "opponent_rank": opp_rank, "opponent_wins": opp_w, "opponent_losses": opp_l,
            "event_date": ev_date, "event_raw": f.get("event") or "",
            "method": parse_method(f.get("date") or f.get("method")),
        })
    return parsed


def find_fighter(cur, query):
    if query.isdigit():
        cur.execute("SELECT id, name, fight_history, fightmatrix_rating_points, base_elo, weight_class_current, gender FROM fighters WHERE id=%s", (int(query),))
    else:
        cur.execute("SELECT id, name, fight_history, fightmatrix_rating_points, base_elo, weight_class_current, gender FROM fighters WHERE name ILIKE %s ORDER BY base_elo DESC NULLS LAST LIMIT 1", (f"%{query}%",))
    return cur.fetchone()


def explain(cur, query, ctx, brief=False):
    name_to_id, fm_points, base_elos = ctx
    row = find_fighter(cur, query)
    if not row:
        print(f"  /!\\ Aucun fighter trouvé pour '{query}'")
        return None
    fid, name, fh_raw, fm, stored_elo, wc, gender = row
    fm = float(fm) if fm is not None else None
    init_elo = elo_from_fm(fm) if fm else _ELO_DEFAULT

    # On ne veut PAS utiliser le propre Elo stocké du fighter comme adversaire.
    elos = {k: v for k, v in base_elos.items() if k != fid}

    parsed = parse_fighter_history(fh_raw, name_to_id)
    parsed.sort(key=lambda f: f.get("event_date") or "0000")

    print("=" * 96)
    print(f"  {name}  (id={fid})   division={wc} [{gender}]")
    print(f"  FM points={fm}  ->  Elo d'init={init_elo:.0f}   |   base_elo STOCKÉ (post-rescale)={stored_elo}")
    print(f"  {len(parsed)} combats exploitables")
    print("=" * 96)

    if brief:
        return {"name": name, "stored": stored_elo, "init": init_elo, "n": len(parsed)}

    print(f"  {'date':10s} {'res':3s} {'adversaire':24s} {'ligue':16s} {'oppElo(src,cert)':22s} {'K':5s} {'att%':5s} {'d_elo':7s} {'Elo'}")
    print("  " + "-" * 92)

    elo = init_elo
    for i, fight in enumerate(parsed):
        # estimation de l'Elo adversaire + a quel point on y croit (certitude 0-1)
        opp_elo, cert = get_opponent_elo_and_certainty(fight, elos, fm_points)
        src = _opp_source_label(fight, elos, fm_points)   # juste pour afficher la source
        league = get_league_strength(fight.get("event_raw"))["name"]
        # resultat reel : W=1, D=0.5, L=0
        actual = 1.0 if fight["result"] == "W" else 0.0 if fight["result"] == "L" else 0.5
        # proba attendue de gagner (formule Elo standard, ecart sur 400 pts)
        expected = 1.0 / (1.0 + 10.0 ** ((opp_elo - elo) / 400.0))
        rec = _recency_mult(fight.get("event_date"))      # vieux combat = poids moindre
        # K final = K de base (selon experience) module par certitude, methode (KO/sub) et recence
        K = k_factor(i) * cert * finish_multiplier(fight.get("method")) * rec
        prev = elo
        elo += K * (actual - expected)                    # le coeur de l'Elo : on ajuste sur la surprise
        opp = (fight.get("opponent_name") or "?")[:23]
        oppinfo = f"{opp_elo:.0f}({src[:4]},{cert:.2f})"
        print(f"  {str(fight.get('event_date'))[:10]:10s} {fight['result']:3s} {opp:24s} "
              f"{league[:15]:16s} {oppinfo:22s} {K:5.0f} {expected*100:4.0f}% "
              f"{elo-prev:+7.1f} {elo:6.0f}")

    print("  " + "-" * 92)
    print(f"  Elo BRUT final (avant rescale par division) : {elo:.0f}")
    print(f"  base_elo STOCKÉ (après rescale 600-2800)    : {stored_elo}")
    print("  NB : le K inclut la RÉCENCE (vieux combats = K plus petit). Le bonus")
    print("       champion (+75) et l'escompte ligue sont appliqués dans le BATCH")
    print("       (calculate_all_elos.py), pas ici -> relance le batch pour les voir.")
    print("=" * 96)
    return {"name": name, "raw_final": elo, "stored": stored_elo}


def main():
    ap = argparse.ArgumentParser(description="Détaille le calcul Elo d'un combattant (debug)")
    ap.add_argument("query", nargs="+", help="nom(s) ou id(s) de fighter")
    ap.add_argument("--id", action="store_true", help="(optionnel) forcer recherche par id")
    args = ap.parse_args()

    conn = db.get_connection()
    if not conn:
        print("ERREUR : pas de connexion BDD (.env).")
        return 1
    cur = conn.cursor()
    ctx = load_context(cur)

    brief = len(args.query) > 1
    for q in args.query:
        explain(cur, q, ctx, brief=brief)
        print()

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
