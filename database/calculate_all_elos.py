"""
mm.ai - le calcul batch des base_elo (DIVISION PAR DIVISION)

recalcule le `base_elo` de TOUS les fighters en bdd, en séparant les calculs
par catégorie de poids + genre (les hommes et les femmes partagent pas la meme
échelle Elo).

pour s'en servir :
    py database/calculate_all_elos.py            # dry-run (ecrit rien)
    py database/calculate_all_elos.py --commit   # applique vraiment en bdd
    py database/calculate_all_elos.py --commit --verbose

l'algo en gros :
    1. on charge fight_history + gender + weight_class_current de tout le monde
    2. on groupe par (weight_class normalisée, gender) -> des pools indépendants
    3. pour chaque pool :
         a. tout le monde part de sa valeur d'init (seed FM ou valeur par defaut)
         b. iteration Elo standard jusqu'a ce que ca converge
         c. les adversaires hors-pool -> estimés depuis leur rang (certitude 0.6)
    4. on fusionne tout et on ecrit base_elo en bdd

pourquoi diviser par division :
    l'Elo d'un lourd a 2000 doit pas etre comparé a l'Elo d'une mouche (F) a
    1800 : les échelles sont indépendantes. chaque division converge vers sa
    propre distribution.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

# on bricole les chemins pour retrouver les imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "database"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

import db_connection as db   # type: ignore  # noqa: E402
from ml.elo_dynamic import batch_compute_all_elos, elo_from_fm  # type: ignore  # noqa: E402
from ml.elo.engine import compute_elo_from_history  # type: ignore  # noqa: E402


# normalisation du weight_class
_WC_NORMALIZE_RE = re.compile(r"^Women'?s?\s+", re.IGNORECASE)


def normalize_wc(wc: Optional[str]) -> str:
    """
    normalise le nom de catégorie : enleve le préfixe 'Women ' / 'Women's '.
    'Women Flyweight' -> 'Flyweight'
    "Women's Bantamweight" -> 'Bantamweight'
    'Flyweight' -> 'Flyweight' (on touche pas)
    """
    if not wc:
        return ""
    return _WC_NORMALIZE_RE.sub("", str(wc)).strip()


# le parsing (memes regex que dans api/app.py)

_EVENT_DATE_RE = re.compile(
    r'^(.+?)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Sun|Mon|Tue|Wed|Thu|Fri|Sat),?\s+'
    r'(January|February|March|April|May|June|July|August|September|October|November|December|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?,?\s*'
    r'(\d{4})\s*$',
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r'^\s*(?:Technical\s+|Tech\s+|Tech\.\s+)?'
    r'(KO/TKO|KO|TKO|Submission|Sub|Decision|Dec|DQ|No\s+Contest|NC|Draw|Forfeit)'
    r'\s*(?:\(([^)]+)\))?'
    r'\s*(?:Round\s+(\d+))?\s*$',
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_METHOD_NORMALIZE = {
    "ko/tko": "KO/TKO", "ko": "KO", "tko": "TKO",
    "submission": "SUB", "sub": "SUB",
    "decision": "DEC", "dec": "DEC",
    "dq": "DQ", "no contest": "NC", "nc": "NC",
    "draw": "DRAW", "forfeit": "FORFEIT",
}


def parse_event_date(event_text: Optional[str]) -> Optional[str]:
    if not event_text:
        return None
    m = _EVENT_DATE_RE.match(str(event_text).strip())
    if not m:
        return None
    try:
        d = date(int(m.group(4)), _MONTHS[m.group(2).lower()], int(m.group(3)))
        return d.isoformat()
    except (ValueError, KeyError):
        return None


def parse_method(method_text: Optional[str]) -> str:
    if not method_text:
        return ""
    m = _METHOD_RE.match(str(method_text).strip())
    if not m:
        return ""
    return _METHOD_NORMALIZE.get(m.group(1).lower(), m.group(1).upper())


def strip_rank(opp_text: Optional[str]) -> tuple[str, str]:
    if not opp_text:
        return "", ""
    s = str(opp_text).strip()
    m = re.match(r"^(.+?)\s+(#\d+\s+.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""


# on construit l'historique depuis la bdd
def build_history_from_db(
    verbose=False,
    include_inactive=False,
) -> Tuple[Dict[int, List[Dict]], Dict[int, Dict], Dict[int, float]]:
    """
    charge tous les fighters + leur fight_history + les points FM.

    renvoie :
      - all_history  : { fighter_id: [combat, ...] }
      - fighter_meta : { fighter_id: {"weight_class": str, "gender": str} }
      - fm_points    : { fighter_id: float }  - pour l'init de l'Elo
    """
    conn = db.get_connection()
    if not conn:
        raise RuntimeError("Impossible de se connecter a la BDD. Verifie .env")

    cur = conn.cursor()

    # 1) un index nom -> id (pour retrouver les adversaires)
    cur.execute("SELECT id, name FROM fighters")
    name_to_id = {row[1].lower(): row[0] for row in cur.fetchall()}
    if verbose:
        print(f"[build] {len(name_to_id)} fighters indexés")

    # 2) les points FM pour l'init
    cur.execute("SELECT id, fightmatrix_rating_points FROM fighters WHERE fightmatrix_rating_points IS NOT NULL")
    fm_points: Dict[int, float] = {row[0]: float(row[1]) for row in cur.fetchall()}
    if verbose:
        print(f"[build] {len(fm_points)} fighters avec des points FM (seed Elo)")

    # 3) le fight_history + les meta (genre, division)
    # Par défaut : seulement les fighters actifs (is_active=TRUE).
    # --include-inactive pour recalculer tout le monde (plus long, utile au 1er run).
    active_filter = "" if include_inactive else "AND (is_active = TRUE OR is_ufc_champion = TRUE)"
    cur.execute(f"""
        SELECT id, fight_history, gender, weight_class_current, is_ufc_champion, ufc_title_match_win
        FROM fighters
        WHERE fight_history IS NOT NULL
        {active_filter}
    """)
    all_history: Dict[int, List[Dict]] = {}
    fighter_meta: Dict[int, Dict] = {}
    n_total_fights = 0

    for fid, fh_raw, gender, wc_raw, is_champ, title_wins in cur.fetchall():
        fighter_meta[fid] = {
            "weight_class": normalize_wc(wc_raw) or "Unknown",
            "gender": (gender or "M").strip().upper()[:1],
            "is_champion": bool(is_champ),
            "title_wins": int(title_wins) if title_wins else 0,
        }
        if not fh_raw:
            continue
        try:
            fh = json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
        except (json.JSONDecodeError, TypeError):
            continue

        fights = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
        if not fights:
            continue

        parsed = []
        for f in fights:
            if not isinstance(f, dict):
                continue
            result = (f.get("result") or "").strip().upper()
            if result not in ("W", "L", "D"):
                continue
            opp_name, opp_rank = strip_rank(f.get("opponent"))
            opp_id = name_to_id.get(opp_name.lower()) if opp_name else None

            # la date : on prend l'ISO direct (Tapology) sinon on parse le champ event (FM)
            ev_date = f.get("event_date")
            if not (ev_date and re.match(r"^\d{4}-\d{2}-\d{2}$", str(ev_date))):
                ev_date = parse_event_date(f.get("event"))

            # le record de l'adversaire au moment du combat (Tapology : "6-3") -> V/D pour l'Elo
            opp_w = opp_l = None
            rec = f.get("opponent_record")
            if rec:
                m_rec = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(rec))
                if m_rec:
                    opp_w, opp_l = int(m_rec.group(1)), int(m_rec.group(2))

            parsed.append({
                "result":          result,
                "opponent_id":     opp_id,
                "opponent_rank":   opp_rank,
                "opponent_wins":   opp_w,
                "opponent_losses": opp_l,
                "event_date":      ev_date,
                "event_raw":       f.get("event") or "",   # sert a classify_promotion()
                "method":          parse_method(f.get("date") or f.get("method")),
            })
        if parsed:
            all_history[fid] = parsed
            n_total_fights += len(parsed)

    conn.close()
    if verbose:
        print(f"[build] {len(all_history)} fighters avec historique | {n_total_fights} combats total")
    return all_history, fighter_meta, fm_points


# on ecrit les elos en bdd
def write_elos_to_db(elos: Dict[int, float], commit: bool, verbose: bool):
    conn = db.get_connection()
    if not conn:
        raise RuntimeError("Impossible de se connecter a la BDD pour ecrire")
    cur = conn.cursor()
    n = 0
    for fid, elo in elos.items():
        cur.execute("UPDATE fighters SET base_elo = %s WHERE id = %s", (elo, fid))
        n += 1
        if verbose and n % 100 == 0:
            print(f"[write] {n}/{len(elos)} ...")
    if commit:
        conn.commit()
        print(f"[write] OK COMMIT : {n} fighters mis a jour")
    else:
        conn.rollback()
        print(f"[write] DRY-RUN (--commit pas specifie) : {n} updates simules, rollback effectue")
    conn.close()


# le main
def compute_single_elo(fighter_id: int, commit: bool, verbose: bool):
    """Calcule et écrit le base_elo d'un seul fighter sans toucher aux autres."""
    conn = db.get_connection()
    if not conn:
        raise RuntimeError("Impossible de se connecter a la BDD.")
    cur = conn.cursor()

    # meta du fighter cible
    cur.execute("SELECT name, fight_history, fightmatrix_rating_points FROM fighters WHERE id = %s", (fighter_id,))
    row = cur.fetchone()
    if not row:
        print(f"[--id] Aucun fighter avec id={fighter_id}")
        conn.close()
        return 1
    name, fh_raw, fm_pts = row
    print(f"[--id] Calcul ELO pour : {name} (id={fighter_id})")

    if not fh_raw:
        print("[--id] Pas de fight_history en BDD -> ELO impossible a calculer")
        conn.close()
        return 1

    # charger les ELOs existants comme référence pour les adversaires
    cur.execute("SELECT id, base_elo FROM fighters WHERE base_elo IS NOT NULL")
    elos: Dict[int, float] = {r[0]: float(r[1]) for r in cur.fetchall()}

    # charger les FM points pour estimer les adversaires sans ELO
    cur.execute("SELECT id, fightmatrix_rating_points FROM fighters WHERE fightmatrix_rating_points IS NOT NULL")
    fm_points_all: Dict[int, float] = {r[0]: float(r[1]) for r in cur.fetchall()}

    # index nom -> id pour retrouver les adversaires
    cur.execute("SELECT id, name FROM fighters")
    name_to_id = {r[1].lower(): r[0] for r in cur.fetchall()}
    conn.close()

    # parser le fight_history
    try:
        fh = json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
    except (json.JSONDecodeError, TypeError):
        print("[--id] fight_history invalide (JSON mal formé)")
        return 1

    fights_raw = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    history = []
    for f in (fights_raw or []):
        if not isinstance(f, dict):
            continue
        result = (f.get("result") or "").strip().upper()
        if result not in ("W", "L", "D"):
            continue
        opp_name, opp_rank = strip_rank(f.get("opponent"))
        opp_id = name_to_id.get(opp_name.lower()) if opp_name else None
        ev_date = f.get("event_date")
        if not (ev_date and re.match(r"^\d{4}-\d{2}-\d{2}$", str(ev_date or ""))):
            ev_date = parse_event_date(f.get("event"))
        opp_w = opp_l = None
        rec = f.get("opponent_record")
        if rec:
            m_rec = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(rec))
            if m_rec:
                opp_w, opp_l = int(m_rec.group(1)), int(m_rec.group(2))
        history.append({
            "result":          result,
            "opponent_id":     opp_id,
            "opponent_rank":   opp_rank,
            "opponent_wins":   opp_w,
            "opponent_losses": opp_l,
            "event_date":      ev_date,
            "event_raw":       f.get("event") or "",
            "method":          parse_method(f.get("date") or f.get("method")),
        })

    if not history:
        print("[--id] Aucun combat valide dans le fight_history")
        return 1

    init_elo = elo_from_fm(float(fm_pts)) if fm_pts else 1300.0
    new_elo = compute_elo_from_history(history, init_elo, elos, fm_points_all)

    print(f"[--id] {len(history)} combats parsés | init={init_elo:.1f} -> base_elo={new_elo:.1f}")

    write_elos_to_db({fighter_id: new_elo}, commit=commit, verbose=verbose)
    return 0


def main():
    p = argparse.ArgumentParser(description="Calcule base_elo de tous les fighters (par division)")
    p.add_argument("--commit",           action="store_true", help="Applique les changements en BDD")
    p.add_argument("--verbose", "-v",    action="store_true", help="Affiche la progression")
    p.add_argument("--max-iter",         type=int,   default=25,  help="Iterations max par division (defaut 25)")
    p.add_argument("--threshold",        type=float, default=1.0, help="Seuil de convergence (defaut 1.0)")
    p.add_argument("--include-inactive", action="store_true",
                   help="Recalcule aussi les fighters inactifs (plus lent). Par defaut : actifs + champions seulement.")
    p.add_argument("--id",               type=int,   default=None,
                   help="Calcule le base_elo d'un seul fighter (par ID) sans toucher aux autres.")
    args = p.parse_args()

    if args.id is not None:
        return compute_single_elo(args.id, commit=args.commit, verbose=args.verbose)

    print("=" * 62)
    print("  MM.AI - Calcul batch base_elo (par division)")
    print("=" * 62)
    if not args.include_inactive:
        print("  [filtre] fighters actifs + champions seulement (--include-inactive pour tout le monde)")

    print("\n1) Construction de l'historique + FM points...")
    all_history, fighter_meta, fm_points = build_history_from_db(
        verbose=args.verbose,
        include_inactive=args.include_inactive,
    )
    if not all_history:
        print("Aucun fighter avec fight_history. Abort.")
        return 1

    # on groupe par (weight_class, gender) -> un pool par division
    groups: Dict[tuple, Dict[int, List[Dict]]] = defaultdict(dict)
    for fid, hist in all_history.items():
        meta = fighter_meta.get(fid, {})
        wc = meta.get("weight_class") or "Unknown"
        g  = meta.get("gender") or "M"
        groups[(wc, g)][fid] = hist

    print(f"\n   Divisions trouvées ({len(groups)} pools) :")
    for (wc, g), grp in sorted(groups.items()):
        gender_label = "Women" if g == "F" else "Men"
        n_fm = sum(1 for fid in grp if fid in fm_points)
        print(f"     {wc:22s} ({gender_label:5s}) — {len(grp):4d} fighters  ({n_fm} avec FM seed)")

    # le calcul Elo, indépendant pour chaque division
    print(f"\n2) Calcul ELO par division (max {args.max_iter} iters, seuil {args.threshold} pts)...")
    all_elos: Dict[int, float] = {}

    for (wc, g), group_history in sorted(groups.items()):
        gender_label = "Women" if g == "F" else "Men"
        label = f"{wc} ({gender_label})"
        # les points FM filtrés sur ce pool
        pool_fm = {fid: fm_points[fid] for fid in group_history if fid in fm_points}
        pool_champs = {fid for fid in group_history if fighter_meta.get(fid, {}).get("is_champion")}
        pool_titles = {fid: fighter_meta[fid]["title_wins"] for fid in group_history
                       if fighter_meta.get(fid, {}).get("title_wins")}
        print(f"\n  -- {label} : {len(group_history)} fighters ({len(pool_fm)} FM seeded, {len(pool_champs)} champ) --")
        group_elos = batch_compute_all_elos(
            group_history,
            fm_points=pool_fm,
            max_iters=args.max_iter,
            convergence_threshold=args.threshold,
            verbose=args.verbose,
            champion_ids=pool_champs,
            title_wins=pool_titles,
        )
        all_elos.update(group_elos)

    # la distribution globale + le top de chaque division
    vals = sorted(all_elos.values())
    if vals:
        print(f"\n3) Distribution finale (tous pools confondus) :")
        print(f"   min   : {vals[0]:.1f}")
        print(f"   max   : {vals[-1]:.1f}")
        print(f"   median: {vals[len(vals)//2]:.1f}")
        print(f"   moy   : {sum(vals)/len(vals):.1f}")

        # le top 3 de chaque division
        conn = db.get_connection()
        cur = conn.cursor()
        print(f"\n   Top 3 par division :")
        for (wc, g), grp in sorted(groups.items()):
            if len(grp) < 2:
                continue
            gender_label = "Women" if g == "F" else "Men"
            top3 = sorted(
                [(fid, all_elos[fid]) for fid in grp if fid in all_elos],
                key=lambda x: -x[1],
            )[:3]
            print(f"   {wc} ({gender_label}) :")
            for fid, e in top3:
                cur.execute("SELECT name FROM fighters WHERE id=%s", (fid,))
                r = cur.fetchone()
                name = r[0] if r else f"id={fid}"
                print(f"     {e:7.1f}  {name}")
        conn.close()

    print(f"\n4) Ecriture en BDD ({'COMMIT' if args.commit else 'DRY-RUN'})...")
    write_elos_to_db(all_elos, commit=args.commit, verbose=args.verbose)

    print("\nFini.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
