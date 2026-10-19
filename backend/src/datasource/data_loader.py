"""
MM.AI - Data Loader
Pont entre la BDD PostgreSQL et les algorithmes ML.

Stratégie :
1. Si la connexion BDD fonctionne → charge le fighter depuis PostgreSQL
2. Sinon → fallback sur sample_data.py (mode démo offline)

Cela permet aux algos ML de fonctionner même sans BDD configurée.

Lancement standalone :
    python backend/src/datasource/data_loader.py
ou comme module (depuis backend/) :
    python -m src.datasource.data_loader
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# les imports (setup du chemin) — robuste, marche en standalone et comme module
# Les chemins du projet :
#   parents[0] = backend/src/datasource/
#   parents[1] = backend/src/
#   parents[2] = backend/
#   parents[3] = mm.ai/   (racine projet)
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]            # backend/
_PROJECT_ROOT = _HERE.parents[3]       # mm.ai/
_DATABASE = _PROJECT_ROOT / 'database'

# Backend dans le path → permet "from src.datasource.sample_data ..."
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Database dans le path → permet "import db_connection"
if str(_DATABASE) not in sys.path:
    sys.path.insert(0, str(_DATABASE))


# les imports (apres setup)

from src.datasource.sample_data import (  # noqa: E402
    get_fighter_by_id as _sample_by_id,
    get_fighter_by_name as _sample_by_name,
    get_fight_history as _sample_fight_history,
    list_all_fighters as _sample_list,
)

# Tente d'importer le module BDD. Si dotenv/psycopg2 manquent, on reste en mode sample.
try:
    import db_connection as db  # noqa: E402  (depuis database/)
    _DB_AVAILABLE = True
    _DB_IMPORT_ERROR = None
except Exception as e:
    db = None
    _DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)


# détection MODE

def is_db_connected() -> bool:
    """Retourne True si la BDD est joignable maintenant."""
    if not _DB_AVAILABLE or db is None:
        return False
    conn = db.get_connection()
    if conn is None:
        return False
    conn.close()
    return True


def data_source() -> str:
    """Retourne 'database' ou 'sample' selon ce qui est disponible."""
    return 'database' if is_db_connected() else 'sample'


# mapping BDD → format attendu par les algos ML

def _compute_age(dob) -> int:
    """
    Calcule l'âge en années depuis une date de naissance.
    Accepte : date, datetime, str 'YYYY-MM-DD', None.
    Retourne 28 (âge moyen UFC) si non calculable.
    """
    if dob is None:
        return 28
    try:
        if isinstance(dob, str):
            from datetime import datetime
            dob = datetime.strptime(dob[:10], "%Y-%m-%d").date()
        elif hasattr(dob, 'date'):
            dob = dob.date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return 28


def _parse_height_inches_to_cm(val) -> float:
    """
    Convertit "5'9\"" ou "69" ou 69.0 -> cm.
    Tolere : NULL, vide, formats varies. Retourne 0.0 si pas parsable.
    """
    if val is None or val == "":
        return 0.0
    s = str(val).strip().replace('"', '').replace("''", "'")
    # Format "5'9" ou "5' 9"
    import re as _re
    m = _re.match(r"^(\d+)'\s*(\d+)$", s)
    if m:
        return round((int(m.group(1)) * 12 + int(m.group(2))) * 2.54, 1)
    # Format pouces decimaux "69" ou "69.0"
    try:
        return round(float(s) * 2.54, 1)
    except (ValueError, TypeError):
        return 0.0


def _parse_reach_inches_to_cm(val) -> float:
    """Convertit '75.0\"' ou '75' ou 75.0 -> cm."""
    if val is None or val == "":
        return 0.0
    s = str(val).strip().replace('"', '')
    try:
        return round(float(s) * 2.54, 1)
    except (ValueError, TypeError):
        return 0.0


def _row_to_fighter(row):
    """
    Convertit une row de la table `fighters` (BDD) OU un dict sample_data vers
    le format attendu par les algos ML / l'API.

    Gere les 2 schemas :
      - BDD     : weight_class_current, height_inches, reach_inches, record_total_*
      - Sample  : weight_class,         height_cm,     reach_cm,     record_*
    """
    if row is None:
        return None

    # Helpers pour fallback BDD -> sample
    def _g(*keys, default=None):
        """Premier .get() non-None parmi plusieurs clefs possibles."""
        for k in keys:
            v = row.get(k)
            if v is not None and v != "":
                return v
        return default

    # Stats : noms specifiques au schema DB v2 (vue v_fighter_complete) ou sample_data
    stats = {
        'sig_str_per_min': float(_g('sig_str_landed_per_min', 'sig_str_per_min') or 0.0),
        'striking_accuracy': float(_g('sig_str_accuracy', 'striking_accuracy') or 0.0),
        'striking_defense': float(_g('sig_str_defense', 'striking_defense') or 0.0),
        'sig_str_absorbed_per_min': float(row.get('sig_str_absorbed_per_min') or 0.0),
        'ko_percentage': float(row.get('ko_percentage') or 0.0),
        'td_avg': float(row.get('td_avg') or 0.0),
        'td_accuracy': float(row.get('td_accuracy') or 0.0),
        'td_defense': float(row.get('td_defense') or 0.0),
        'sub_avg': float(row.get('sub_avg') or 0.0),
        'avg_control_time': float(row.get('avg_control_time') or 0.0),
        'ko_losses': int(row.get('ko_losses') or 0),
        'total_fights': int(row.get('total_fights') or 0),
        'total_wins': int(_g('record_total_wins', 'record_wins') or 0),
    }

    # height/reach : BDD stocke en pouces (string "5'9\"" ou "75.0\""), sample en cm directs
    height_cm = row.get('height_cm')
    if height_cm is None or height_cm == "" or height_cm == 0:
        height_cm = _parse_height_inches_to_cm(row.get('height_inches'))
    reach_cm = row.get('reach_cm')
    if reach_cm is None or reach_cm == "" or reach_cm == 0:
        reach_cm = _parse_reach_inches_to_cm(row.get('reach_inches'))

    dob = row.get('date_of_birth')
    return {
        'id': row['id'],
        'name': row['name'],
        'nickname': row.get('nickname'),
        'date_of_birth': dob,
        'age': _compute_age(dob),
        'nationality': row.get('nationality'),
        'weight_class': _g('weight_class_current', 'weight_class', default='Unknown'),
        'current_league': row.get('current_league'),
        'reach_cm': float(reach_cm or 0.0),
        'height_cm': float(height_cm or 0.0),
        'stance': row.get('stance') or 'Orthodox',
        'record_wins': int(_g('record_total_wins', 'record_wins') or 0),
        'record_losses': int(_g('record_total_losses', 'record_losses') or 0),
        'record_draws': int(_g('record_total_draws', 'record_draws') or 0),
        'base_elo': float(row.get('base_elo') or 1500.0),
        'stats': stats,
    }


# API publique

def get_fighter_by_id(fighter_id):
    """Charge un fighter par ID. BDD si dispo, sinon sample."""
    if is_db_connected():
        row = db.get_fighter_by_id(fighter_id)
        if row:
            return _row_to_fighter(row)
    raw = _sample_by_id(fighter_id)
    return _row_to_fighter(raw) if raw else None


def get_fighter_by_name(name):
    """Charge un fighter par nom (recherche partielle). BDD si dispo, sinon sample."""
    if is_db_connected():
        row = db.get_fighter_by_name(name)
        if row:
            return _row_to_fighter(row)
    raw = _sample_by_name(name)
    return _row_to_fighter(raw) if raw else None


def list_all_fighters():
    """Liste les noms de tous les fighters disponibles (CLI compat)."""
    if is_db_connected():
        rows = db.get_all_fighters(limit=500)
        if rows:
            return [r['name'] for r in rows]
    return _sample_list()


def list_fighters(
    limit: int = 20,
    offset: int = 0,
    weight_class: str | None = None,
    current_league: str | None = None,
    gender: str | None = None,
):
    """
    Liste de fighters au format ML (FighterOut shape) avec filtres + pagination.

    Retourne un dict :
      {
        "total":   int,         # total non pagine (pour calculer page X/Y)
        "limit":   int,
        "offset":  int,
        "results": list[dict],  # fighters au format _row_to_fighter
      }

    En mode sample (BDD offline), pagination/filtres appliques en memoire.
    """
    if is_db_connected():
        rows = db.get_all_fighters(
            weight_class=weight_class,
            current_league=current_league,
            gender=gender,
            limit=limit,
            offset=offset,
        )
        total = db.count_fighters(
            weight_class=weight_class,
            current_league=current_league,
            gender=gender,
        )
        return {
            "total":   total,
            "limit":   limit,
            "offset":  offset,
            "results": [_row_to_fighter(r) for r in rows if r],
        }

    # Fallback sample : pas de filtre BDD, on filtre en memoire
    from src.datasource.sample_data import SAMPLE_FIGHTERS
    pool = list(SAMPLE_FIGHTERS)
    if weight_class:
        pool = [f for f in pool if f.get("weight_class") == weight_class]
    # gender/current_league non disponibles dans sample_data -> on skip silencieusement
    total = len(pool)
    sliced = pool[offset : offset + limit]
    return {
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "results": sliced,
    }


def search_fighters_by_name(query: str, limit: int = 10) -> list[dict]:
    """
    Recherche de fighters par nom partiel (insensible casse).
    Retourne une liste de dicts au format _row_to_fighter.
    """
    if is_db_connected():
        rows = db.get_all_fighters(name_search=query, limit=limit)
        return [_row_to_fighter(r) for r in rows if r]

    # Fallback sample : filtre Python
    from src.datasource.sample_data import SAMPLE_FIGHTERS
    q = (query or "").lower().strip()
    if not q:
        return []
    matches = [f for f in SAMPLE_FIGHTERS if q in f.get("name", "").lower()]
    return matches[:limit]


def get_fight_history(fighter_id):
    """
    Historique des combats d'un fighter.
    En mode BDD : pas encore implémenté (table fights vide chez toi pour l'instant)
       → fallback sample
    En mode sample : retourne le sample.
    """
    return _sample_fight_history(fighter_id)


# debug / CLI

def main():
    print("=" * 60)
    print("  MM.AI - Data Loader (diagnostic)")
    print("=" * 60)

    print(f"\nMode dispo BDD : {_DB_AVAILABLE}")
    if not _DB_AVAILABLE:
        print(f"  Raison : {_DB_IMPORT_ERROR}")

    print(f"BDD connectee : {is_db_connected()}")
    print(f"Source active : {data_source()}")

    print("\nFighters disponibles :")
    for n in list_all_fighters():
        print(f"  - {n}")

    print("\nTest get_fighter_by_name('Jon Jones') :")
    f = get_fighter_by_name('Jon Jones')
    if f:
        print(f"  OK {f['name']} | Elo: {f['base_elo']} | "
              f"Record: {f['record_wins']}-{f['record_losses']}-{f['record_draws']}")
    else:
        print("  KO introuvable")


if __name__ == '__main__':
    main()
