"""
MM.AI v0.3 - public showcase (NOT the real RoundZero algorithms).

mm.ai - l'API Flask (la demo du TFE)
lit la base Supabase via le .env et expose des endpoints JSON que le /frontend
consomme. sert aussi les fichiers statiques de ../frontend (comme ca pas de
souci de CORS).

pour lancer :
    py api/app.py
    -> http://localhost:5000
"""
from __future__ import annotations               # 437
 
import json as _json_top
import math as _math_top
import os
import re as _re_top
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

# MM.AI v0.3 = public showcase. Not the real RoundZero algorithms.
DEMO_NOTICE = ("MM.AI v0.3 - early public showcase. Simplified predictions, NOT the "
               "algorithms of the final product (RoundZero).")

# Module ML (calcul de la courbe d'Elo). Import tolerant : si le module ou
# numpy est indisponible, l'API demarre quand meme et la timeline est juste
# omise (feature non bloquante).
sys.path.insert(0, str(ROOT / "backend" / "src"))
try:
    from ml.elo_dynamic import (  # type: ignore
        compute_elo_timeline_from_history,
        compute_elo_from_history,
        _ELO_DEFAULT,
    )
    _ELO_AVAILABLE = True
except Exception:  # pragma: no cover
    compute_elo_timeline_from_history = None  # type: ignore
    _ELO_AVAILABLE = False

try:
    from ml.scouter_calc import compute_scouter, compute_scouter_debug  # type: ignore
    _SCOUTER_AVAILABLE = True
except Exception:  # pragma: no cover
    _SCOUTER_AVAILABLE = False

# Pont vers le LLM (analyses de combat redigees par IA). Import tolerant : si le
# module manque, l'API demarre quand meme et l'endpoint /analysis renvoie un
# fallback sans IA.
try:
    from llm import llm_available, generate_fight_analysis  # type: ignore
    _LLM_AVAILABLE = True
except Exception:  # pragma: no cover
    _LLM_AVAILABLE = False
    def llm_available() -> bool:  # type: ignore
        return False

load_dotenv(ROOT / ".env")

USE_SUPABASE = os.getenv("USE_SUPABASE", "True").lower() == "true"

if USE_SUPABASE:
    DB_CONFIG = {
        "host": os.getenv("SUPABASE_HOST"),
        "database": os.getenv("SUPABASE_DB", "postgres"),
        "user": os.getenv("SUPABASE_USER", "postgres"),
        "password": os.getenv("SUPABASE_PASSWORD"),
        "port": int(os.getenv("SUPABASE_PORT", "5432")),
    }
else:
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "mmai_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "port": int(os.getenv("DB_PORT", "5432")),
    }


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def serialize(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def row_to_dict(row, cols):
    return {c: serialize(v) for c, v in zip(cols, row)}


# Post-process : enrichit chaque row de fighter pour l'API publique

def compute_age_from_dob(dob):
    """Retourne l'age courant a partir d'une date de naissance (date ou str ISO)."""
    if not dob:
        return None
    if isinstance(dob, str):
        try:
            dob = date.fromisoformat(dob[:10])
        except (ValueError, TypeError):
            return None
    elif isinstance(dob, datetime):
        dob = dob.date()
    if not isinstance(dob, date):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# Pondération du form score : poids INVERSE de l'ancienneté.
# last_5_results stocké "ancien -> recent" : results[0] = plus vieux, results[-1] = plus recent.
# On veut donc des poids CROISSANTS pour donner plus d'importance aux combats recents.
# Les 3 derniers (positions 2,3,4) pesent ~70% du score.
_FORM_WEIGHTS    = [0.5, 0.7, 1.0, 1.1, 1.2]    # somme = 4.5
_FORM_VALUE_MAP  = {"W": 1.0, "D": 0.5, "L": 0.0}  # un nul = demi-credit


# Hierarchie des sources de fight_history (miroir de scrapers/scrape_mma.py).
# Une source >= _RECORD_AUTHORITATIVE_MIN fait foi sur record_total (override la
# colonne, meme avec moins de combats). En dessous -> filet "MAX".
_HISTORY_SOURCE_PRIORITY = {
    "tapology":        4,
    "ufcstats+scrape": 3,
    "event_scrape":    3,
    "ufc_fr":          2,
    "ufc":             2,
    "fightmatrix":     2,
    "underground":     1,
}
_RECORD_AUTHORITATIVE_MIN = 3


def _fight_history_source(fight_history_raw):
    """Renvoie la source d'un fight_history JSON ('tapology', 'fightmatrix', ...) ou ''."""
    if not fight_history_raw:
        return ""
    try:
        fh = _json.loads(fight_history_raw) if isinstance(fight_history_raw, str) else fight_history_raw
    except (_json.JSONDecodeError, TypeError):
        return ""
    return (fh.get("source") or "").strip().lower() if isinstance(fh, dict) else ""


def derive_record_from_history(fight_history_raw):
    """
    Recompte W/L/D/NC depuis fight_history (source de verite la plus fraiche).
    Le record_total_wins stocke en BDD peut etre stale ou faux (ex: scraper a
    rate un combat, ou une promotion a corrige son recap). fight_history est
    plus fiable car c'est la source brute.

    Retourne (wins, losses, draws, nc, total) ou None si parsing impossible.
    """
    if not fight_history_raw:
        return None
    try:
        fh = _json.loads(fight_history_raw) if isinstance(fight_history_raw, str) else fight_history_raw
    except (_json.JSONDecodeError, TypeError):
        return None
    if isinstance(fh, dict):
        fights = fh.get("fights") or []
    elif isinstance(fh, list):
        fights = fh
    else:
        return None
    if not fights:
        return None
    w, l, d, nc = 0, 0, 0, 0
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
    return (w, l, d, nc, len(fights))


def compute_recent_form_score(last_5_results):
    """
    Recalcule recent_form_score a la volee depuis last_5_results.
    Plus solide que la valeur stockee en BDD (qui peut etre stale apres un combat).

    Exemple Shevchenko 'L,D,W,W,W' :
        L*0.5 + D*0.7*0.5 + W*1.0 + W*1.1 + W*1.2 = 0 + 0.35 + 3.3 = 3.65
        weight total = 4.5
        score = 3.65/4.5 = 0.811 (au lieu de 0.530 avec l'ancienne formule).

    Renvoie None si pas de last_5.
    """
    if not last_5_results:
        return None
    results = [r.strip().upper() for r in str(last_5_results).split(",")
               if r.strip().upper() in ("W", "L", "D")]
    if not results:
        return None
    # Si moins de 5 combats, on aligne les poids sur la fin (les + recents)
    weights = _FORM_WEIGHTS[-len(results):]
    score = sum(_FORM_VALUE_MAP.get(r, 0.0) * w for r, w in zip(results, weights))
    total_w = sum(weights)
    return round(score / total_w, 3) if total_w > 0 else None


def compute_days_inactive(last_fight_date):
    """
    Recalcule days_inactive depuis last_fight_date (source de verite live).
    La colonne days_inactive en BDD est stale apres chaque combat -> on recalcule.
    """
    if not last_fight_date:
        return None
    if isinstance(last_fight_date, str):
        try:
            last_fight_date = date.fromisoformat(last_fight_date[:10])
        except (ValueError, TypeError):
            return None
    elif isinstance(last_fight_date, datetime):
        last_fight_date = last_fight_date.date()
    if not isinstance(last_fight_date, date):
        return None
    return max(0, (date.today() - last_fight_date).days)


def normalize_weight_class(wc):
    """Normalize women's weight class names.
    'Women Bantamweight'  → 'Women's Bantamweight'
    'Women Flyweight'     → 'Women's Flyweight'  (add missing apostrophe-s)
    'Women's Bantamweight' → unchanged (already correct)
    """
    if not wc:
        return wc
    # Case: starts with "Women " but NOT "Women's "
    if wc.startswith("Women ") and not wc.startswith("Women's "):
        return "Women's " + wc[6:]
    return wc


_MONTHS_ISO_ELO = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _elo_parse_date(f):
    ed = f.get("event_date")
    if ed and _re_top.match(r"^\d{4}-\d{2}-\d{2}$", str(ed)):
        return str(ed)
    ev = f.get("event") or ""
    m = _re_top.search(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[,\s]+"
        r"(\w+)\s+(\d+)(?:st|nd|rd|th)?,?\s*(\d{4})",
        ev, _re_top.IGNORECASE,
    )
    if m:
        mo = _MONTHS_ISO_ELO.get(m.group(1)[:3].lower())
        if mo:
            return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}"
    return None


def _elo_parse_opp_record(f):
    rec = f.get("opponent_record")
    if not rec:
        return None, None
    m = _re_top.match(r"(\d+)-(\d+)", str(rec))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


import unicodedata as _ucd

def _find_h2h(f1, f2):
    """Compte les victoires directes de f1 contre f2 depuis fight_history de f1.
    Retourne (wins_f1, wins_f2).
    On utilise uniquement l'historique de f1 pour éviter le double-comptage."""
    def _norm(name):
        if not name:
            return ""
        n = name.lower().strip()
        return ''.join(c for c in _ucd.normalize('NFD', n) if _ucd.category(c) != 'Mn')

    raw = f1.get("fight_history")
    if not raw:
        return 0, 0
    try:
        fh = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return 0, 0
    fights = (fh.get("fights") or []) if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])

    n2 = _norm(f2.get("name", ""))
    w1 = w2 = 0
    for fight in fights:
        opp = _norm(fight.get("opponent") or "")
        if opp and n2 and (n2 in opp or opp in n2):
            r = (fight.get("result") or "").strip().upper()
            if r == "W":   w1 += 1
            elif r == "L": w2 += 1
    return w1, w2


def compute_base_elo_dynamic(row, query_fn=None):
    """
    Calcule l'ELO dynamiquement depuis fight_history. Jamais stocké en BDD.

    Résolution de l'œuf/poule (sans récursion) :
      - Adversaire en BDD avec base_elo    → son base_elo (NOTRE elo)  ← ancre
      - Adversaire en BDD sans base_elo    → 1300
      - Adversaire absent de BDD           → tier de la promo (classify_promotion)

    ZÉRO FightMatrix (décision Elias 2026-06) : on n'ancre plus sur les points FM.

    query_fn : fonction query() de l'API (passée pour éviter forward-reference).
    Retourne None si pas de fight_history ou ELO non calculable.
    """
    if not _ELO_AVAILABLE:
        return None
    fh_raw = row.get("fight_history")
    if not fh_raw:
        return None
    try:
        fh = _json_top.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
        raw_fights = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    except Exception:
        return None
    if not raw_fights:
        return None

    # Normalise les fights
    fights_norm = []
    for f in raw_fights:
        if not isinstance(f, dict):
            continue
        result = (f.get("result") or "").strip().upper()
        if result not in ("W", "L", "D"):
            continue
        opp_w, opp_l = _elo_parse_opp_record(f)
        opp_id = f.get("opponent_id")
        try:
            opp_id = int(opp_id) if opp_id is not None else None
        except (ValueError, TypeError):
            opp_id = None
        fights_norm.append({
            "result":          result,
            "opponent_id":     opp_id,
            "opponent_wins":   opp_w,
            "opponent_losses": opp_l,
            "event_date":      _elo_parse_date(f),
            "event_raw":       f.get("event") or "",
            "method":          f.get("date") or f.get("method") or "",
        })

    if not fights_norm:
        return None

    # Lookup base_elo (NOTRE elo) des adversaires (1 requête bulk) — zéro FM.
    opp_base: dict = {}
    opp_ids_in_db: set = set()
    opp_ids = [f["opponent_id"] for f in fights_norm if f.get("opponent_id")]
    if opp_ids and query_fn is not None:
        try:
            ph = ",".join(["%s"] * len(opp_ids))
            rows_base = query_fn(
                f"SELECT id, base_elo FROM fighters WHERE id IN ({ph})",
                tuple(opp_ids),
            )
            for r in rows_base:
                opp_ids_in_db.add(r["id"])
                if r.get("base_elo") is not None:
                    opp_base[r["id"]] = float(r["base_elo"])
        except Exception:
            pass

    # Table de lookup ELO adversaires
    opp_elo_lookup: dict = {}
    for oid in opp_ids:
        if oid in opp_base:
            opp_elo_lookup[oid] = opp_base[oid]
        elif oid in opp_ids_in_db:
            opp_elo_lookup[oid] = 1300.0
        # sinon hors BDD : classify_promotion s'en charge via event_raw

    # Init sans FM : point de départ neutre (le record × ligue raffine ensuite).
    init = _ELO_DEFAULT

    try:
        elo = compute_elo_from_history(
            fights_norm,
            init_elo=init,
            elos=opp_elo_lookup,
            fm_points={},
        )
        return round(float(elo), 1)
    except Exception:
        return None


def compute_scouter_dynamic(row):
    """
    Wrapper → délègue à ml.scouter_calc.compute_scouter (module dédié).
    Voir docs/SCOUTER.md pour la méthodologie complète.
    """
    if _SCOUTER_AVAILABLE:
        return compute_scouter(row)
    # Fallback minimal si le module n'est pas chargé
    wins   = int(row.get("record_total_wins")  or 0)
    losses = int(row.get("record_total_losses") or 0)
    if wins + losses == 0:
        return None
    win_rate = wins / (wins + losses)
    return round(min(win_rate * 60 + 20, 100.0), 1)


def _get_query_fn():
    """Retourne la fonction query() après sa définition (résout le forward-ref)."""
    return query  # type: ignore  # noqa: F821 — défini plus bas, appelé à l'exécution


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] LIVE — âge, forme, record recalculés à chaque requête, jamais stale
# principe "single source of truth" : stocké = source brute ; calculé = ce qu'on envoie
# ═══════════════════════════════════════════════════════════════════   -------------------------------------------------------------------------------------
def postprocess_fighter(row):
    """
    Mute un row de fighter avant envoi a l'API :
      - age recalcule depuis date_of_birth (source de verite, evite les valeurs stales)
      - weight_class_display : "Flyweight W" / "Flyweight M" suivant le gender
      - recent_form_score recalcule a la volee (pondere recents > anciens)
      - days_inactive recalcule depuis last_fight_date (live, pas stale)
    """
    if not isinstance(row, dict):
        return row

    # Age frais depuis DOB (override la colonne age statique de la BDD)
    dob = row.get("date_of_birth")
    computed_age = compute_age_from_dob(dob)
    if computed_age is not None:
        row["age"] = computed_age

    # Days inactive frais depuis last_fight_date (la colonne stockee se perime)
    computed_inactive = compute_days_inactive(row.get("last_fight_date"))
    if computed_inactive is not None:
        row["days_inactive"] = computed_inactive

    # Normalize women's weight class names (ex: "Women Bantamweight" → "Women's Bantamweight")
    if row.get("weight_class_current"):
        row["weight_class_current"] = normalize_weight_class(row["weight_class_current"])
    if row.get("weight_class_origin"):
        row["weight_class_origin"] = normalize_weight_class(row["weight_class_origin"])

    # Weight class avec suffixe genre pour l'affichage public.
    # Source de verite = colonne generee weight_class_gendered (migration 009).
    # Fallback si la migration n'est pas encore appliquee.
    wcg = row.get("weight_class_gendered")
    if wcg:
        row["weight_class_display"] = wcg
    else:
        wc = row.get("weight_class_current")
        g = row.get("gender")
        if wc and wc != "Unknown":
            suffix = " W" if g == "F" else " M"
            row["weight_class_display"] = f"{wc}{suffix}"
        else:
            row["weight_class_display"] = wc or "Unknown"

    # Recent form score : on recalcule a la volee (la valeur stockee peut etre stale).
    fresh_form = compute_recent_form_score(row.get("last_5_results"))
    if fresh_form is not None:
        row["recent_form_score"] = fresh_form

    # Record W/L/D : HIERARCHIE DE SOURCES (decision Elias, juin 2026, elargie).
    # Ordre : Tapology > UFC Stats / event_scrape > FightMatrix > colonne brute.
    #   - Si le fight_history vient d'une source AUTORITAIRE (priorite >= seuil :
    #     tapology, ufcstats, event_scrape) -> il fait FOI : on override la colonne
    #     meme si ca FAIT BAISSER le record (ex: FM comptait un combat fantome).
    #   - Sinon (histo FightMatrix / aucun) -> FILET "MAX" : on garde la somme de
    #     combats la plus elevee (ne jamais laisser un re-scrape incomplet baisser
    #     un record correct).
    derived = derive_record_from_history(row.get("fight_history"))
    fh_source = _fight_history_source(row.get("fight_history"))
    stored_total = (
        (row.get("record_total_wins")   or 0)
        + (row.get("record_total_losses") or 0)
        + (row.get("record_total_draws")  or 0)
        + (row.get("record_total_nc")     or 0)
    )
    # Le scraper est responsable de corriger record_total_* via
    # _recompute_record_from_history. L'API utilise les colonnes stockees telles
    # quelles — deriver le record depuis fight_history ici introduit des erreurs
    # quand Tapology inclut des combats non-MMA dans son historique.

    # Methodes W/L recomposees depuis fight_history. Source de verite = l'historique
    # (jamais statique) : quand on a 5+ combats parses, l'historique fait autorite
    # et on OVERRIDE les colonnes stockees (elles peuvent etre stales apres un
    # re-scrape ou un import). En dessous de 5 combats, on garde la valeur stockee
    # uniquement si elle existe (fallback). fight_history n'est present que sur le
    # detail (SELECT *), donc sans effet sur les listes.
    methods = derive_methods_from_history(row.get("fight_history"))
    if methods:
        cols = ("wins_by_ko_tko", "wins_by_submission", "wins_by_decision",
                "losses_by_ko_tko", "losses_by_submission", "losses_by_decision")
        for k in cols:
            row[k] = methods[k]
        wins_total = row.get("record_total_wins") or 0
        if wins_total > 0:
            finishes = methods["wins_by_ko_tko"] + methods["wins_by_submission"]
            row["finish_rate_int"] = round(finishes * 100 / wins_total)

    # notes_translations : normalise en dict (psycopg2 peut renvoyer une str JSON)
    nt = row.get("notes_translations")
    if isinstance(nt, str):
        try:
            row["notes_translations"] = _json.loads(nt)
        except (_json.JSONDecodeError, TypeError):
            row["notes_translations"] = {}
    elif not isinstance(nt, dict):
        row["notes_translations"] = {}

    # base_elo : on laisse la valeur BDD telle quelle (NULL si purgé).
    # Recalculé uniquement par database/calculate_all_elos.py (batch).
    # Le compute live (compute_base_elo_dynamic) n'écrase plus le NULL —
    # ça produisait un elo fantôme gonflé par les elos adversaires d'autres
    # divisions non purgées (ex. Oliveira 2368 alors que LW purgés).

    return row


def postprocess_many(rows):
    for r in rows:
        postprocess_fighter(r)
    return rows


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [row_to_dict(r, cols) for r in cur.fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


# le mapping continent → pays (pour /api/fighters?continent=EU etc.)

CONTINENT_COUNTRIES: dict[str, list[str]] = {
    "NA": [
        "United States", "Canada", "Mexico", "Puerto Rico",
        "Dominican Republic", "Cuba", "Panama", "Costa Rica",
        "Guatemala", "Honduras", "El Salvador", "Nicaragua",
        "Jamaica", "Trinidad and Tobago", "Bahamas", "Barbados",
    ],
    "SA": [
        "Brazil", "Colombia", "Ecuador", "Peru", "Chile",
        "Argentina", "Venezuela", "Bolivia", "Paraguay", "Uruguay",
        "Guyana", "Suriname",
    ],
    "EU": [
        "Russia", "United Kingdom", "England", "Scotland", "Wales",
        "Northern Ireland", "Ireland", "Netherlands", "Poland", "Sweden",
        "Norway", "Germany", "France", "Italy", "Spain", "Georgia",
        "Czech Republic", "Romania", "Ukraine", "Serbia", "Croatia",
        "Hungary", "Slovakia", "Finland", "Denmark", "Belgium",
        "Switzerland", "Portugal", "Austria", "Lithuania", "Latvia",
        "Estonia", "Slovenia", "Bosnia", "Bosnia and Herzegovina",
        "Albania", "North Macedonia", "Moldova", "Greece", "Bulgaria",
        "Belarus", "Turkey", "Armenia", "Azerbaijan", "Luxembourg",
        "Iceland", "Montenegro", "Kosovo", "Cyprus", "Malta",
        "Andorra", "San Marino", "Liechtenstein",
    ],
    "AS": [
        "Japan", "South Korea", "China", "Kazakhstan", "Kyrgyzstan",
        "Tajikistan", "Uzbekistan", "Turkmenistan", "Mongolia",
        "Philippines", "Thailand", "Indonesia", "Singapore", "Malaysia",
        "India", "Vietnam", "Pakistan", "Sri Lanka", "Bangladesh",
        "Taiwan", "Hong Kong", "Iran", "Israel", "Jordan",
        "Saudi Arabia", "UAE", "United Arab Emirates", "Iraq",
        "Syria", "Lebanon", "Qatar", "Kuwait", "Bahrain", "Oman",
        "Myanmar", "Cambodia", "Laos", "Nepal", "Afghanistan",
    ],
    "OC": [
        "Australia", "New Zealand", "Guam", "Fiji",
        "Papua New Guinea", "Samoa", "Tonga",
    ],
    "AF": [
        "South Africa", "Cameroon", "Nigeria", "Kenya", "Morocco",
        "Egypt", "Congo", "DR Congo", "Ghana", "Ethiopia", "Senegal",
        "Ivory Coast", "Côte d'Ivoire", "Rwanda", "Tanzania",
        "Uganda", "Algeria", "Tunisia", "Mozambique", "Angola",
        "Zimbabwe", "Zambia", "Madagascar", "Malawi",
    ],
}

# Flask app

app = Flask(__name__, static_folder=None)
CORS(app)

# l'auth (blueprint Flask, import apres pour éviter les imports circulaires)
# Import apres l'instanciation de l'app pour eviter les imports circulaires :
# auth.py importe get_conn depuis app via `from app import get_conn` au moment de
# l'appel, pas au module load.
from auth import auth_bp  # noqa: E402
app.register_blueprint(auth_bp)

# le panel admin (meme logique d'import tardif que auth)
from admin import admin_bp  # noqa: E402
app.register_blueprint(admin_bp)


# ---- Frontend statique -----------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_proxy(path: str):
    full = FRONTEND_DIR / path
    if full.is_file():
        return send_from_directory(FRONTEND_DIR, path)
    # Fallback : sert l'index si on demande une page HTML inexistante
    if not path.startswith("api/") and "." not in path:
        return send_from_directory(FRONTEND_DIR, "index.html")
    abort(404)


# ---- API JSON --------------------------------------------------------------

FIGHTER_LIST_COLS = """
    id, name, nickname, gender, age, date_of_birth, nationality,
    photo_url, photo_thumbnail_url,
    weight_class_current, weight_class_origin,
    CASE
        WHEN weight_class_current IS NULL OR weight_class_current = 'Unknown' OR weight_class_current = ''
        THEN COALESCE(weight_class_current, 'Unknown')
        ELSE weight_class_current || ' ' || CASE gender WHEN 'F' THEN 'W' ELSE 'M' END
    END AS weight_class_gendered,
    current_league,
    record_total_wins, record_total_losses, record_total_draws,
    record_ufc_wins, record_ufc_losses, record_ufc_draws,
    wins_by_ko_tko, wins_by_submission, wins_by_decision,
    is_active, is_ufc_champion, ufc_title_match_win,
    win_percentage_int, finish_rate_int,
    current_streak, last_5_results,
    base_elo, scouter_rating,
    fightmatrix_rating_points, fightmatrix_quality_perf_pct,
    ufc_official_rank, ufc_p4p_rank,
    last_fight_date, days_inactive
""".strip()


@app.get("/api/health")
def health():
    try:
        query("SELECT 1;")
        return jsonify({"status": "ok", "db": "connected", "source": "supabase" if USE_SUPABASE else "local"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.get("/api/stats")
def stats():
    total = query_one("SELECT COUNT(*) AS n FROM fighters;")["n"]
    active = query_one("SELECT COUNT(*) AS n FROM fighters WHERE is_active = TRUE;")["n"]
    champions = query_one("SELECT COUNT(*) AS n FROM fighters WHERE is_ufc_champion = TRUE;")["n"]
    nationalities = query_one("SELECT COUNT(DISTINCT nationality) AS n FROM fighters WHERE nationality IS NOT NULL;")["n"]
    _ladder_sql = ", ".join(f"'{w}'" for w in _WC_LADDER)
    weight_classes = query_one(f"""
        SELECT COUNT(DISTINCT {_WC_CANON_SQL}) AS n
        FROM fighters
        WHERE weight_class_current IS NOT NULL
          AND weight_class_current != 'Unknown'
          AND weight_class_current != ''
          AND lower({_WC_CANON_SQL}) = ANY(ARRAY[{_ladder_sql}])
    """)["n"]
    total_fights = query_one("SELECT COALESCE(SUM(total_fights), 0) AS n FROM fighters;")["n"]
    avg_elo = query_one("SELECT AVG(fightmatrix_rating_points) AS n FROM fighters WHERE fightmatrix_rating_points IS NOT NULL;")
    return jsonify({
        "total_fighters": total,
        "active_fighters": active,
        "champions": champions,
        "nationalities": nationalities,
        "weight_classes": weight_classes,
        "total_fights": total_fights,
        "avg_fightmatrix_rating": serialize(avg_elo["n"]) if avg_elo and avg_elo["n"] else None,
    })


# Ladder de poids (ordre croissant) — sert a (1) trier les divisions proprement
# et (2) filtrer le bruit (valeurs parasites type "To Fight Fellow Bantamweight").
_WC_LADDER = [
    "atomweight", "strawweight", "flyweight", "bantamweight", "featherweight",
    "lightweight", "welterweight", "middleweight", "light heavyweight",
    "cruiserweight", "heavyweight", "super heavyweight",
]
_WC_LADDER_POS = {name: i for i, name in enumerate(_WC_LADDER)}

# SQL : retire le prefixe "Women's "/"Women " pour obtenir la division de base.
# Permet de fusionner "Flyweight"+F et "Women's Flyweight"+F (donnees incoherentes).
_WC_CANON_SQL = "regexp_replace(weight_class_current, '^Women''?s?[[:space:]]+', '', 'i')"


@app.get("/api/weight-classes")
def weight_classes():
    """Liste des divisions.

    - defaut (rankings, etc.) : noms normalises non genres (comportement historique).
    - ?gendered=1 (page Fighters) : liste CANONIQUE GENREE. On retire le prefixe
      "Women's", on regroupe par (division de base, genre) pour fusionner les
      doublons de stockage ("Flyweight"+F vs "Women's Flyweight"+F), on filtre le
      bruit (divisions hors ladder) et on ordonne hommes puis femmes par poids.
      Chaque entree porte un token `base|gender` consomme par /api/fighters.
    """
    gendered = (request.args.get("gendered") or "").strip().lower() in ("1", "true", "yes")

    if gendered:
        rows = query(f"""
            SELECT {_WC_CANON_SQL} AS base, gender, COUNT(*) AS count
            FROM fighters
            WHERE weight_class_current IS NOT NULL
              AND weight_class_current != 'Unknown'
              AND weight_class_current != ''
              AND gender IN ('M', 'F')
            GROUP BY 1, 2;
        """)
        merged: dict = {}
        for r in rows:
            base = (r["base"] or "").strip()
            key = base.lower()
            if key not in _WC_LADDER_POS:
                continue  # division inconnue / bruit -> on ignore
            mkey = (key, r["gender"])
            if mkey not in merged:
                merged[mkey] = {"base": base, "gender": r["gender"], "count": 0}
            merged[mkey]["count"] += r["count"]
        out = [{
            "value": f"{v['base']}|{v['gender']}",
            "base": v["base"],
            "gender": v["gender"],
            "count": v["count"],
        } for v in merged.values()]
        # Hommes d'abord (ladder croissant), puis femmes (ladder croissant).
        out.sort(key=lambda d: (0 if d["gender"] == "M" else 1,
                                _WC_LADDER_POS.get(d["base"].lower(), 99)))
        return jsonify(out)

    # Comportement historique : noms normalises non genres.
    rows = query("""
        SELECT
            CASE
              WHEN weight_class_current ~ '^Women [A-Z]' AND weight_class_current NOT LIKE 'Women''s %%'
              THEN 'Women''s ' || SUBSTRING(weight_class_current FROM 7)
              ELSE weight_class_current
            END AS name,
            COUNT(*) AS count
        FROM fighters
        WHERE weight_class_current IS NOT NULL AND weight_class_current != 'Unknown'
        GROUP BY 1
        ORDER BY 1;
    """)
    return jsonify(rows)


@app.get("/api/countries")
def countries():
    rows = query("""
        SELECT nationality AS name, COUNT(*) AS count
        FROM fighters
        WHERE nationality IS NOT NULL AND nationality != ''
        GROUP BY nationality
        ORDER BY count DESC, nationality ASC;
    """)
    return jsonify(rows)


@app.get("/api/fighters")
def list_fighters():
    """Liste paginee + filtres.

    Si `search` est passe, on utilise un scoring tiered + fuzzy (pg_trgm) :
      tier 4 - PREFIX     : LIKE 'query%' sur name/nickname        (relevance 100/95)
      tier 3 - TOKEN-START: regex (^|sep)query sur name/nickname   (relevance 80/75)
      tier 2 - SUBSTRING  : LIKE '%query%' sur name/nickname       (relevance 50/45)
      tier 1 - FUZZY      : pg_trgm similarity(name, query) > 0.30 (relevance 20-50)
                            (uniquement si query >= 4 chars pour éviter le bruit)
    Quand search est vide on garde l'ancien comportement avec le sort param.
    """
    search = (request.args.get("search") or "").strip()
    weight_class = (request.args.get("weight_class") or "").strip()
    country = (request.args.get("country") or "").strip()
    gender = (request.args.get("gender") or "").strip().upper()
    status = (request.args.get("status") or "").strip().lower()
    continent = (request.args.get("continent") or "").strip().upper()
    sort = request.args.get("sort", "rating")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    # Résoudre le continent en liste de pays
    continent_countries: list[str] = []
    if continent and continent != "ALL" and continent in CONTINENT_COUNTRIES:
        continent_countries = CONTINENT_COUNTRIES[continent]

    # Branche AVEC search : scoring tiered + fuzzy
    if search:
        # named params pour reutiliser :q facilement
        named: dict = {"q": search, "limit": limit, "offset": offset}

        extra_where = ["score > 0"]
        if weight_class and weight_class.lower() != "all":
            if "|" in weight_class:
                # Token genre "base|gender" (ex "Flyweight|F") : on matche sur la
                # division canonique (sans prefixe "Women's") + le genre.
                base, _, g = weight_class.partition("|")
                extra_where.append(f"LOWER({_WC_CANON_SQL}) = LOWER(%(wcbase)s) AND gender = %(wcg)s")
                named["wcbase"] = base
                named["wcg"] = g
            else:
                extra_where.append("weight_class_current = %(wc)s")
                named["wc"] = weight_class
        if country and country.lower() != "all":
            extra_where.append("nationality = %(country)s")
            named["country"] = country
        elif continent_countries:
            extra_where.append("nationality = ANY(%(cont_list)s)")
            named["cont_list"] = continent_countries
        if gender in ("M", "F"):
            extra_where.append("gender = %(gender)s")
            named["gender"] = gender
        if status == "active":
            extra_where.append("is_active = TRUE")
        elif status == "inactive":
            extra_where.append("is_active = FALSE")
        elif status == "champion":
            extra_where.append("is_ufc_champion = TRUE")
        extra_where_sql = " AND ".join(extra_where)

        # Le fuzzy est skippe si q < 4 chars (eviterait des matches aléatoires)
        sql = f"""
            WITH scored AS (
                SELECT {FIGHTER_LIST_COLS},
                CASE
                    WHEN LOWER(name) LIKE LOWER(%(q)s) || '%%'                          THEN 100
                    WHEN LOWER(COALESCE(nickname,'')) LIKE LOWER(%(q)s) || '%%'         THEN 95
                    WHEN LOWER(name) ~* ('(^|[[:space:]''\\-])' || LOWER(%(q)s))         THEN 80
                    WHEN LOWER(COALESCE(nickname,'')) ~* ('(^|[[:space:]''\\-])' || LOWER(%(q)s)) THEN 75
                    WHEN LOWER(name) LIKE '%%' || LOWER(%(q)s) || '%%'                  THEN 50
                    WHEN LOWER(COALESCE(nickname,'')) LIKE '%%' || LOWER(%(q)s) || '%%' THEN 45
                    WHEN char_length(%(q)s) >= 4 AND similarity(name, %(q)s)     > 0.30 THEN 20 + (similarity(name, %(q)s)     * 30)::int
                    WHEN char_length(%(q)s) >= 4 AND similarity(COALESCE(nickname,''), %(q)s) > 0.30 THEN 18 + (similarity(COALESCE(nickname,''), %(q)s) * 28)::int
                    ELSE 0
                END AS score
                FROM fighters
            )
            SELECT *, COUNT(*) OVER() AS total_count
            FROM scored
            WHERE {extra_where_sql}
            ORDER BY score DESC, fightmatrix_rating_points DESC NULLS LAST, record_total_wins DESC
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        rows = query(sql, named)
        total = rows[0]["total_count"] if rows else 0
        for r in rows:
            r.pop("total_count", None)
            r.pop("score", None)
        postprocess_many(rows)
        return jsonify({"fighters": rows, "total": total, "limit": limit, "offset": offset})

    # Branche SANS search : code original (sort/filtres uniquement)
    where = []
    params: list = []

    if weight_class and weight_class.lower() != "all":
        if "|" in weight_class:
            # Token genre "base|gender" (ex "Flyweight|F").
            base, _, g = weight_class.partition("|")
            where.append(f"LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s")
            params.append(base)
            params.append(g)
        else:
            where.append("weight_class_current = %s")
            params.append(weight_class)

    if country and country.lower() != "all":
        where.append("nationality = %s")
        params.append(country)
    elif continent_countries:
        where.append("nationality = ANY(%s)")
        params.append(continent_countries)

    if gender in ("M", "F"):
        where.append("gender = %s")
        params.append(gender)

    if status == "active":
        where.append("is_active = TRUE")
    elif status == "inactive":
        where.append("is_active = FALSE")
    elif status == "champion":
        where.append("is_ufc_champion = TRUE")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    order_map = {
        "rating": "fightmatrix_rating_points DESC NULLS LAST, record_total_wins DESC",
        "name": "name ASC",
        "wins": "record_total_wins DESC",
        "elo": "base_elo DESC NULLS LAST, fightmatrix_rating_points DESC NULLS LAST",
        "scouter": "COALESCE(scouter_rating, 0) DESC, base_elo DESC NULLS LAST",
        "ufc_rank": "ufc_official_rank ASC NULLS LAST",
        "recent": "last_fight_date DESC NULLS LAST",
    }
    order_sql = order_map.get(sort, order_map["rating"])

    sql = f"""
        SELECT {FIGHTER_LIST_COLS},
               COUNT(*) OVER() AS total_count
        FROM fighters
        {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])
    rows = query(sql, tuple(params))
    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)
    postprocess_many(rows)
    return jsonify({"fighters": rows, "total": total, "limit": limit, "offset": offset})


@app.get("/api/fighters/<int:fighter_id>")
def fighter_detail(fighter_id: int):
    row = query_one("SELECT * FROM fighters WHERE id = %s;", (fighter_id,))
    if not row:
        abort(404, description="Fighter not found")
    postprocess_fighter(row)

    # MM.AI rank : rang du fighter dans sa division, basé sur scouter_rating.
    # NULL si scouter_rating non calculé ou division inconnue.
    if row.get("weight_class_current"):
        rank_row = query_one("""
            WITH ranked AS (
                SELECT id,
                       RANK() OVER (
                           PARTITION BY weight_class_current
                           ORDER BY COALESCE(scouter_rating, 0) DESC,
                                    base_elo DESC NULLS LAST
                       ) AS mmai_rank
                FROM fighters
                WHERE weight_class_current = %s
            )
            SELECT mmai_rank FROM ranked WHERE id = %s
        """, (row["weight_class_current"], fighter_id))
        row["mmai_rank"] = rank_row["mmai_rank"] if rank_row else None
    else:
        row["mmai_rank"] = None

    return jsonify(row)


#  fight history : parsing + opponent matching (DB lookup)
#
# Le scraper stocke fight_history en JSON brut. Format actuel :
#   {"source": "...", "count": N, "fights": [
#     {"result": "W", "opponent": "Tatsuro Taira #3 Flyweight",
#      "event": "UFC 328 Chimaev vs. Strickland Saturday, May 9th 2026",
#      "date":  "TKO (Front Kick to the Body) Round 5",   <- contient en realite la methode
#      "method": ""}                                      <- toujours vide en pratique
#   ]}
#
# On parse ici :
#   - event  -> (event_name propre, date_iso, league_detectee)
#   - date   -> (method_short, method_detail, round_number)
#   - opponent -> (opponent_name, opponent_rank, opponent_id BDD si match)

import json as _json
import re as _re

# la division ladder - garde de compat entre catégories
# l'Elo est calculé PAR DIVISION independamment. deux fighters trop éloignés
# en poids peuvent pas etre comparés (2+ catégories d'écart = on bloque).

_WC_STRIP_RE = _re.compile(r"^Women'?s?\s+", _re.IGNORECASE)

_MEN_LADDER = [
    "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
    "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
]
_WOMEN_LADDER = [
    "Atomweight", "Strawweight", "Flyweight", "Bantamweight",
    "Featherweight", "Lightweight",
]


def _normalize_wc(wc):
    if not wc:
        return ""
    return _WC_STRIP_RE.sub("", str(wc)).strip()


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] GARDE-FOU DIVISION — bloque inter-genre ou divisions trop éloignées (HTTP 422)
# ═══════════════════════════════════════════════════════════════════
def _check_division_compat(f1: dict, f2: dict):
    """
    Retourne None si OK, ou un message d'erreur si trop eloignes.
    Laisse passer si la categorie est inconnue (pas de blocage).
    Adjacent (+/-1 division) est autorise.
    """
    g1 = ((f1.get("gender") or "M") + "").strip().upper()[:1]
    g2 = ((f2.get("gender") or "M") + "").strip().upper()[:1]

    if g1 != g2:
        return (
            f"Cross-gender matchups are not supported "
            f"({f1.get('name', '?')} competes in {'Men' if g1 == 'M' else 'Women'}'s, "
            f"{f2.get('name', '?')} in {'Men' if g2 == 'M' else 'Women'}'s)."
        )

    wc1 = _normalize_wc(f1.get("weight_class_current"))
    wc2 = _normalize_wc(f2.get("weight_class_current"))

    if not wc1 or not wc2 or wc1.lower() == "unknown" or wc2.lower() == "unknown":
        return None  # categorie inconnue -> on laisse passer

    ladder = _MEN_LADDER if g1 == "M" else _WOMEN_LADDER
    ladder_lower = [v.lower() for v in ladder]

    pos1 = next((i for i, v in enumerate(ladder_lower) if v == wc1.lower()), None)
    pos2 = next((i for i, v in enumerate(ladder_lower) if v == wc2.lower()), None)

    if pos1 is None or pos2 is None:
        return None  # categorie absente du ladder -> on laisse passer

    dist = abs(pos1 - pos2)
    # Blocage a partir de 3 categories d'ecart (3 ou 4...). 1-2 categories restent
    # autorisees (la pertinence baisse mais une prediction garde du sens).
    if dist > 2:
        return (
            f"These fighters are too far apart in weight class to compare "
            f"({wc1} vs {wc2}, {dist} divisions apart). "
            f"A prediction across 3 or more weight classes is not meaningful."
        )

    return None


_EVENT_DATE_RE = _re.compile(
    r'^(.+?)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Sun|Mon|Tue|Wed|Thu|Fri|Sat),?\s+'
    r'(January|February|March|April|May|June|July|August|September|October|November|December|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?,?\s*'
    r'(\d{4})\s*$',
    _re.IGNORECASE,
)

@app.get("/api/fighters/<int:fighter_id>/scouter")
def fighter_scouter_calc(fighter_id: int):
    """Calcule le Scouter Rating à la demande (appelé par le bouton Calculate Scouter)."""
    row = query_one("SELECT * FROM fighters WHERE id = %s;", (fighter_id,))
    if not row:
        abort(404, description="Fighter not found")
    postprocess_fighter(row)
    score = compute_scouter_dynamic(row)
    if score is None:
        return jsonify({"error": "not_enough_data"}), 422
    return jsonify({"scouter_rating": score})


@app.get("/api/fighters/<int:fighter_id>/scouter-debug")
def fighter_scouter_debug(fighter_id: int):
    """Détail du calcul Scouter pour un fighter (dev/calibration)."""
    row = query_one("SELECT * FROM fighters WHERE id = %s;", (fighter_id,))
    if not row:
        abort(404, description="Fighter not found")
    postprocess_fighter(row)
    if not _SCOUTER_AVAILABLE:
        return jsonify({"error": "scouter module not available"}), 503
    return jsonify(compute_scouter_debug(row))


_METHOD_RE = _re.compile(
    # Prefixe optionnel "Technical " ou "Tech " (Technical Submission, Technical KO, etc.)
    r'^\s*(?:Technical\s+|Tech\s+|Tech\.\s+)?'
    r'(KO/TKO|KO|TKO|Submission|Sub|Decision|Dec|DQ|No\s+Contest|NC|Draw|Forfeit)'
    r'\s*(?:\(([^)]+)\))?'
    r'\s*(?:Round\s+(\d+))?\s*$',
    _re.IGNORECASE,
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


def parse_fight_event(event_text):
    """
    'UFC 328 Chimaev vs. Strickland Saturday, May 9th 2026'
        -> ('UFC 328 Chimaev vs. Strickland', '2026-05-09')
    Retourne (event_name, date_iso_or_None).
    """
    if not event_text:
        return "", None
    s = str(event_text).strip()
    m = _EVENT_DATE_RE.match(s)
    if not m:
        return s, None
    event_name = m.group(1).strip().rstrip(" -:")
    try:
        d = date(int(m.group(4)), _MONTHS[m.group(2).lower()], int(m.group(3)))
        return event_name, d.isoformat()
    except (ValueError, KeyError):
        return event_name, None


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] PIÈGE DONNÉES — fight["date"] contient en réalité la MÉTHODE
# ex: "TKO (Punches) Round 1" est dans le champ "date", pas "method"
# ═══════════════════════════════════════════════════════════════════
def parse_fight_method(method_text):
    """
    'TKO (Front Kick to the Body) Round 5' -> ('TKO', 'Front Kick to the Body', 5)
    'Decision (Unanimous) Round 3'         -> ('DEC', 'Unanimous', 3)
    'KO Round 1'                           -> ('KO', '', 1)
    Retourne (method_short, detail, round_or_None).
    """
    if not method_text:
        return "", "", None
    m = _METHOD_RE.match(str(method_text).strip())
    if not m:
        return str(method_text).strip(), "", None
    method = _METHOD_NORMALIZE.get(m.group(1).lower(), m.group(1).upper())
    detail = (m.group(2) or "").strip()
    rnd = int(m.group(3)) if m.group(3) else None
    return method, detail, rnd


# Regroupement des methodes parsees en 3 buckets affiches dans le profil.
_KO_METHODS  = {"KO", "TKO", "KO/TKO"}
_SUB_METHODS = {"SUB"}
_DEC_METHODS = {"DEC"}


def derive_methods_from_history(fight_history_raw):
    """
    Recompose les compteurs de methodes (W/L par KO-TKO / Submission / Decision)
    depuis fight_history. Les colonnes wins_by_* / losses_by_* sont quasi toujours
    vides en BDD (MMA Underground non scrappable) -> on les reconstruit a la volee.
    Rappel : la "method" reelle est stockee dans le champ "date" (cf parse_fight_method).

    Retourne un dict de 6 compteurs, ou None si rien d'exploitable.
    """
    if not fight_history_raw:
        return None
    try:
        fh = _json.loads(fight_history_raw) if isinstance(fight_history_raw, str) else fight_history_raw
    except (_json.JSONDecodeError, TypeError):
        return None
    if isinstance(fh, dict):
        fights = fh.get("fights") or []
    elif isinstance(fh, list):
        fights = fh
    else:
        return None
    if not fights:
        return None

    c = {"wins_by_ko_tko": 0, "wins_by_submission": 0, "wins_by_decision": 0,
         "losses_by_ko_tko": 0, "losses_by_submission": 0, "losses_by_decision": 0}
    seen = False
    for f in fights:
        if not isinstance(f, dict):
            continue
        result = (f.get("result") or "").strip().upper()
        if result not in ("W", "L"):
            continue  # NC / Draw : pas compte dans les methodes
        method, _, _ = parse_fight_method(f.get("date") or f.get("method"))
        method = (method or "").upper()
        if method in _KO_METHODS:
            bucket = "ko_tko"
        elif method in _SUB_METHODS:
            bucket = "submission"
        elif method in _DEC_METHODS:
            bucket = "decision"
        else:
            continue  # DQ / methode non normalisable : ignore
        c[f"{'wins' if result == 'W' else 'losses'}_by_{bucket}"] += 1
        seen = True
    return c if seen else None


def split_opponent_name(opponent_text):
    """
    'Tatsuro Taira #3 Flyweight' -> ('Tatsuro Taira', '#3 Flyweight')
    'Cedric Doumbe'              -> ('Cedric Doumbe', '')
    """
    if not opponent_text:
        return "", ""
    s = str(opponent_text).strip()
    m = _re.match(r"^(.+?)\s+(#\d+\s+.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""


def _build_opponent_candidates(opponent_names):
    """
    Bulk lookup : prend une liste de noms, retourne {lower_name: [candidats...]}.
    Une seule requete SQL pour tous les adversaires (perf). Contrairement a un
    simple {name: id}, on garde TOUS les homonymes pour pouvoir desambiguiser
    ensuite (ex : deux "Alexander Volkov", un heavyweight + un lightweight).
    """
    if not opponent_names:
        return {}
    uniq = list({n.lower() for n in opponent_names if n})
    if not uniq:
        return {}
    placeholders = ",".join(["%s"] * len(uniq)) # sécurité contre SQL injection     
    rows = query(
        f"""SELECT id, name, gender, weight_class_current,
                   photo_thumbnail_url, photo_url,
                   ufc_official_rank, is_ufc_champion,
                   CASE
                       WHEN weight_class_current IS NULL OR weight_class_current = 'Unknown'
                            OR weight_class_current = ''
                       THEN COALESCE(weight_class_current, 'Unknown')
                       ELSE weight_class_current || ' '
                            || CASE gender WHEN 'F' THEN 'W' ELSE 'M' END
                   END AS weight_class_gendered
            FROM fighters WHERE LOWER(name) IN ({placeholders})""",
        tuple(uniq),
    )
    by_name: dict[str, list] = {}
    for r in rows:
        by_name.setdefault(r["name"].lower(), []).append(r)
    return by_name


def _pick_opponent_candidate(cands, opp_rank, profile_gender):
    """
    Choisit le bon homonyme parmi `cands` (liste de rows fighters de meme nom).
    Heuristique :
      1) division presente dans le rank historique (ex "#3 Heavyweight") ;
      2) sinon, meme genre que le combattant du profil ;
      3) sinon, le mieux classe UFC (rank le plus petit), sinon le premier.
    """
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    rank_l = (opp_rank or "").lower()
    if rank_l:
        for c in cands:
            base = _normalize_wc(c.get("weight_class_current")).lower()
            if base and base in rank_l:
                return c
    if profile_gender:
        same = [c for c in cands if (c.get("gender") or "") == profile_gender]
        if same:
            cands = same
            if len(cands) == 1:
                return cands[0]
    return sorted(cands, key=lambda c: (c.get("ufc_official_rank") or 999))[0]


# ---------------------------------------------------------------------------
# Matching event <-> fighter (carte d'event -> fiche cliquable)
# ---------------------------------------------------------------------------
def _norm_fighter_name(s):
    """Cle de matching robuste : minuscules, accents retires, ponctuation/espaces
    retires. 'Thiago Moises' == 'Thiago Móises', "Sean O'Malley" == 'Sean OMalley',
    'Jiri Prochazka' == 'Jiří Procházka'.

    DOIT rester synchro avec :
      - le SQL cote event_detail : regexp_replace(unaccent(lower(name)),'[^a-z0-9]','','g')
      - database/relink_event_fighters.py (meme normalisation Python)
    """
    if not s:
        return ""
    s = _ucd.normalize("NFKD", str(s))
    s = "".join(c for c in s if not _ucd.combining(c))
    return _re.sub(r"[^a-z0-9]+", "", s.lower())


def _pick_event_candidate(cands, bout_wc, want_gender):
    """Choisit le bon fighter parmi des homonymes pour un bout d'event.

    On a deux 'Bruno Silva', deux 'Joey Gomez'... -> on tranche avec le contexte
    du bout. Signaux par ordre de fiabilite :
      1) genre du bout (division 'Women's ...' ou genre de l'autre coin)
      2) division du bout == division du fighter
      3) a une current_league (UFC/PFL/ONE...) > sans ligue
      4) plus de combats > moins de combats
      5) meilleure data_quality_score
      6) id le plus petit (fiche la plus ancienne) en dernier recours
    """
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    pool = list(cands)
    if want_gender:
        same = [c for c in pool if (c.get("gender") or "") == want_gender]
        if same:
            pool = same
            if len(pool) == 1:
                return pool[0]
    base = _normalize_wc(bout_wc).lower() if bout_wc else ""
    if base:
        wc_match = [c for c in pool
                    if _normalize_wc(c.get("weight_class_current")).lower() == base]
        if wc_match:
            pool = wc_match
            if len(pool) == 1:
                return pool[0]
    return sorted(pool, key=lambda c: (
        0 if c.get("current_league") else 1,
        -(c.get("total_fights") or 0),
        -(c.get("data_quality_score") or 0),
        c.get("id") or 0,
    ))[0]


# Divisions par longueur decroissante : "light heavyweight" avant "heavyweight".
_DIVISION_WORDS = sorted(_WC_LADDER, key=len, reverse=True)


def _division_in_text(text):
    """Extrait le nom de division (minuscule) d'une chaine type '#3 Heavyweight'."""
    if not text:
        return ""
    t = str(text).lower()
    for name in _DIVISION_WORDS:
        if name in t:
            return name
    return ""


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] HISTORIQUE CLIQUABLE — matche chaque adversaire sur la BDD (lookup bulk par nom)
# désambiguïsation par genre/division pour les homonymes
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/fighters/<int:fighter_id>/history")
def fighter_history(fighter_id: int):
    """
    Renvoie l'historique des combats du fighter, parse et avec opponent_id
    matche a la BDD pour permettre des liens cliquables dans le frontend.

    Format de retour :
    {
      "fighter_id": 89,
      "source": "fightmatrix",
      "count": 19,
      "fights": [
        {
          "result": "W",
          "opponent_name": "Tatsuro Taira",
          "opponent_rank": "#3 Flyweight",
          "opponent_id": 90,           // null si pas dans la BDD
          "opponent_photo": "...",     // null si pas en BDD
          "event_name": "UFC 328 Chimaev vs. Strickland",
          "event_date": "2026-05-09",  // ISO ou null si parse impossible
          "method": "TKO",             // KO / TKO / SUB / DEC / DQ / NC / DRAW
          "method_detail": "Front Kick to the Body",
          "round": 5
        }, ...
      ]
    }
    """
    row = query_one("SELECT id, fight_history, gender FROM fighters WHERE id = %s;", (fighter_id,))
    if not row:
        abort(404, description="Fighter not found")
    profile_gender = row.get("gender")

    fh_raw = row.get("fight_history")
    if not fh_raw:
        return jsonify({"fighter_id": fighter_id, "source": None, "count": 0, "fights": []})

    # fight_history peut etre stocke en TEXT (string JSON) ou deja en dict
    try:
        fh = _json.loads(fh_raw) if isinstance(fh_raw, str) else fh_raw
    except _json.JSONDecodeError:
        return jsonify({"fighter_id": fighter_id, "source": "raw", "count": 0,
                        "fights": [], "error": "fight_history not valid JSON"})

    raw_fights = fh.get("fights") if isinstance(fh, dict) else (fh if isinstance(fh, list) else [])
    if not raw_fights:
        return jsonify({"fighter_id": fighter_id, "source": fh.get("source") if isinstance(fh, dict) else None,
                        "count": 0, "fights": []})

    # 1er pass : parse + collecte des noms d'opponents pour le lookup bulk
    parsed = []
    opponent_names = []
    for f in raw_fights:
        if not isinstance(f, dict):
            continue
        opp_name, opp_rank = split_opponent_name(f.get("opponent"))
        event_name, event_date = parse_fight_event(f.get("event"))
        # Date ISO explicite (fights Tapology) prioritaire sur le parse du champ event
        if f.get("event_date") and _re.match(r"^\d{4}-\d{2}-\d{2}$", str(f.get("event_date"))):
            event_date = f.get("event_date")
        # attention : la "method" reelle est dans le champ "date" (data scrappee).
        method, method_detail, rnd = parse_fight_method(f.get("date") or f.get("method"))
        parsed.append({
            "result": (f.get("result") or "").strip().upper() or None,
            "opponent_name": opp_name,
            "opponent_rank": opp_rank,
            "opponent_id": None,      # sera rempli ci-dessous
            "opponent_photo": None,
            "event_name": event_name,
            "event_date": event_date,
            "method": method,
            "method_detail": method_detail,
            "round": rnd,
        })
        if opp_name:
            opponent_names.append(opp_name)

    # 2eme pass : bulk lookup des candidats (tous les homonymes) en 1 requete
    cands_by_name = _build_opponent_candidates(opponent_names)

    # 3eme pass : choisir le bon homonyme + enrichir id/photo/rank.
    #   - opponent_rank_current : rang UFC ACTUEL, affiche UNIQUEMENT si l'adversaire
    #     est dans le top 15 actuel (ou champion). Sinon -> on retombe sur le rang
    #     historique scrapé, marqué "au moment du combat" côté frontend.
    for p in parsed:
        meta = _pick_opponent_candidate(
            cands_by_name.get(p["opponent_name"].lower()),
            p.get("opponent_rank"),
            profile_gender,
        )
        if not meta:
            p["opponent_rank_current"] = None
            continue
        p["opponent_id"] = meta["id"]
        p["opponent_photo"] = meta.get("photo_thumbnail_url") or meta.get("photo_url")
        wc = meta.get("weight_class_gendered") or meta.get("weight_class_current") or ""
        rank = meta.get("ufc_official_rank")

        # Garde-fou anti-donnee incoherente : si la division ACTUELLE de l'adversaire
        # contredit franchement la division DU COMBAT (>1 cran de ladder, ex donnee
        # erronee "Volkov Lightweight" alors que le combat etait en Heavyweight), on
        # n'affiche pas le rang "actuel" -> on retombe sur le rang historique
        # "at fight time". Un vrai changement de categorie adjacent (Jones LHW->HW)
        # reste tolere.
        hist_div = _division_in_text(p.get("opponent_rank"))
        cur_div = _normalize_wc(meta.get("weight_class_current")).lower()
        div_mismatch = (
            hist_div in _WC_LADDER_POS and cur_div in _WC_LADDER_POS
            and abs(_WC_LADDER_POS[hist_div] - _WC_LADDER_POS[cur_div]) > 1
        )

        if div_mismatch:
            p["opponent_rank_current"] = None
        elif meta.get("is_ufc_champion"):
            p["opponent_rank_current"] = f"Champion {wc}".strip()
        elif rank is not None and 1 <= int(rank) <= 15:
            p["opponent_rank_current"] = f"#{rank} {wc}".strip()
        else:
            p["opponent_rank_current"] = None

    # 3.5eme pass : rang HISTORIQUE "at fight time" depuis fm_historical_ranks.
    # Pour chaque combat dont l'adversaire est lie en BDD mais SANS rang scrappe
    # dans le nom, on cherche le rang FM a l'issue (trimestre) dont la date est la
    # plus proche AVANT la date du combat. On remplit opponent_rank -> le frontend
    # l'affiche automatiquement avec le label "at fight time". On n'ecrase JAMAIS
    # un rang deja scrappe (embarque dans le nom = plus precis/source-fidele).
    opp_ids_hist = list({
        p["opponent_id"] for p in parsed
        if p.get("opponent_id") and not p.get("opponent_rank") and p.get("event_date")
    })
    if opp_ids_hist:
        ph = ",".join(["%s"] * len(opp_ids_hist))
        hr_rows = query(
            f"""SELECT fighter_id, division, issue_date, rank
                FROM fm_historical_ranks
                WHERE fighter_id IN ({ph})
                ORDER BY fighter_id, issue_date""",
            tuple(opp_ids_hist),
        )
        # regroupe par adversaire : liste (date_iso, division, rang) triee par date asc
        by_fighter: dict = {}
        for r in hr_rows:
            by_fighter.setdefault(r["fighter_id"], []).append(
                (str(r["issue_date"]), r["division"], int(r["rank"]))
            )
        for p in parsed:
            if p.get("opponent_rank") or not p.get("opponent_id") or not p.get("event_date"):
                continue
            hist = by_fighter.get(p["opponent_id"])
            if not hist:
                continue
            fight_date = str(p["event_date"])
            before = [h for h in hist if h[0] <= fight_date]
            if not before:
                continue   # combat anterieur a la couverture FM -> on ne devine pas
            max_date = before[-1][0]                       # snapshot le + proche avant
            same = [h for h in before if h[0] == max_date]
            _, division, rk = min(same, key=lambda h: h[2])  # si plusieurs : meilleur rang
            p["opponent_rank"] = f"#{rk} {division}".strip()

    # 4eme pass : bulk lookup des event_names contre la table events
    event_names = list({p["event_name"] for p in parsed if p.get("event_name")})
    if event_names:
        placeholders = ",".join(["%s"] * len(event_names))   # sécurité contre SQL injection
        ev_rows = query(
            f"SELECT id, name FROM events WHERE LOWER(name) IN ({placeholders})",
            tuple(n.lower() for n in event_names),
        )
        event_name_to_id = {r["name"].lower(): r["id"] for r in ev_rows}
        for p in parsed:
            en = (p.get("event_name") or "").lower()
            if en in event_name_to_id:
                p["event_id"] = event_name_to_id[en]

    # ---- Elo timeline : evolution du base_elo combat par combat -------------
    # On recupere le base_elo (converge en BDD) des adversaires matches pour
    # servir d'opp_lookup, puis on rejoue l'historique chronologiquement. Le
    # dernier point APPROXIME le base_elo stocke (le batch officiel converge
    # par pool de division ; ici on fait une seule passe).
    elo_timeline: list = []
    if compute_elo_timeline_from_history is not None:
        opp_ids = list({p["opponent_id"] for p in parsed if p.get("opponent_id")})
        opp_elo_lookup: dict = {}
        if opp_ids:
            ph = ",".join(["%s"] * len(opp_ids))
            elo_rows = query(
                f"SELECT id, base_elo FROM fighters WHERE id IN ({ph})",
                tuple(opp_ids),
            )
            opp_elo_lookup = {
                r["id"]: float(r["base_elo"])
                for r in elo_rows if r.get("base_elo") is not None
            }
        try:
            elo_timeline = compute_elo_timeline_from_history(parsed, opp_elo_lookup)
        except Exception:
            elo_timeline = []

    # Tri final pour l'affichage : du combat le PLUS RECENT au plus ancien.
    # Les combats scrapes via ESPN/event sont stockes en fin de tableau mais
    # peuvent etre les plus recents -> sans ce tri ils apparaissent en bas.
    # Les combats sans date parseable (None) restent en fin de liste.
    parsed.sort(key=lambda p: (p.get("event_date") or "0000-00-00"), reverse=True)

    return jsonify({
        "fighter_id": fighter_id,
        "source": fh.get("source") if isinstance(fh, dict) else None,
        "count": len(parsed),
        "fights": parsed,
        "elo_timeline": elo_timeline,
    })


@app.get("/api/rankings")
def rankings():
    weight_class = (request.args.get("weight_class") or "").strip()
    country = (request.args.get("country") or "").strip()
    sort = request.args.get("sort", "fightmatrix")
    limit = min(int(request.args.get("limit", 25)), 100)

    # NOTE: pas de sort par scouter cote public (admin uniquement)
    sort_col = {
        "fightmatrix": "fightmatrix_rating_points DESC NULLS LAST",
        "elo": "base_elo DESC NULLS LAST",
        "ufc": "ufc_official_rank ASC NULLS LAST",
        "wins": "record_total_wins DESC",
    }.get(sort, "fightmatrix_rating_points DESC NULLS LAST")

    where = []
    params: list = []
    if weight_class and weight_class.lower() != "all":
        if "|" in weight_class:
            # Token genre "base|gender" (ex "Flyweight|F") : division canonique + genre.
            base, _, g = weight_class.partition("|")
            where.append(f"LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s")
            params.append(base)
            params.append(g)
        else:
            where.append("weight_class_current = %s")
            params.append(weight_class)
    if country and country.lower() != "all":
        where.append("nationality = %s")
        params.append(country)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        {where_sql}
        ORDER BY {sort_col}
        LIMIT %s;
    """
    params.append(limit)
    rows = query(sql, tuple(params))
    postprocess_many(rows)
    return jsonify({
        "weight_class": weight_class or "All",
        "country": country or "All",
        "sort": sort,
        "fighters": rows,
    })


@app.get("/api/top")
def top_fighters():
    """Top 5 non-champions toutes catégories confondues — pour la page d'accueil."""
    rows = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE (is_ufc_champion IS NULL OR is_ufc_champion = FALSE)
        ORDER BY fightmatrix_rating_points DESC NULLS LAST,
                 record_total_wins DESC
        LIMIT 5;
    """)
    postprocess_many(rows)
    return jsonify(rows)


@app.get("/api/champions")
def champions():
    """Tous les fighters flagges champions UFC."""
    rows = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE is_ufc_champion = TRUE
        ORDER BY weight_class_current;
    """)
    postprocess_many(rows)
    return jsonify(rows)


@app.get("/api/divisions")
def divisions():
    """Pour chaque division, le top 5 + champion + total."""
    # Pre-fetch de tous les champions — requête directe, sans filtrage WC complexe.
    # Évite le bug où gender=NULL ou weight_class_gendered inconsistant cache le champion.
    all_champs = query(f"SELECT {FIGHTER_LIST_COLS} FROM fighters WHERE is_ufc_champion = TRUE")
    postprocess_many(all_champs)
    # Index (division_base_lower, gender_upper) → champion
    champ_lookup: dict = {}
    for f in all_champs:
        base = _normalize_wc(f.get("weight_class_current", "")).lower()
        g = (f.get("gender") or "M").upper()
        if base:
            champ_lookup[(base, g)] = f

    # _wcg_name : transforme weight_class_gendered en nom affichable propre,
    # ROBUSTE aux donnees incoherentes (certaines femmes ont "Bantamweight W",
    # d'autres "Women's Bantamweight W" avec DOUBLE marqueur de genre).
    # Strategie : detecter le genre (prefixe "Women" OU suffixe " W"), puis
    # nettoyer TOUS les marqueurs et reconstruire un seul "Women's <Div>".
    #   "Bantamweight W"          -> "Women's Bantamweight"
    #   "Women's Bantamweight W"  -> "Women's Bantamweight"  (etait "Women's Women's ...")
    #   "Women's Bantamweight"    -> "Women's Bantamweight"
    #   "Bantamweight M"          -> "Bantamweight"
    #   "Bantamweight"            -> "Bantamweight"
    _WCG_NAME = """
        CASE
          WHEN weight_class_gendered ~* '(^Women|[ ]W$)'
          THEN 'Women''s ' || regexp_replace(
                 regexp_replace(weight_class_gendered, '[ ][WM]$', ''),
                 '^Women''?s?[ ]+', '', 'i')
          ELSE regexp_replace(weight_class_gendered, '[ ]M$', '')
        END
    """
    # GROUP BY sur le NOM CALCULE UNIQUEMENT (pas la colonne gender brute).
    # Le nom encode deja le genre ("Women's X" = F, "X" = M) donc grouper par nom
    # fusionne tout dans UN seul pool par division. Evite les cartes en double
    # ("Women's Strawweight" x2) causees par 1 fighter parasite a gender='M'/NULL
    # mais classe dans une division feminine.
    weight_classes = query(f"""
        SELECT
            {_WCG_NAME} AS name,
            COUNT(*) AS count
        FROM fighters
        WHERE weight_class_gendered IS NOT NULL AND weight_class_current != 'Unknown'
        GROUP BY ({_WCG_NAME})
        ORDER BY 1;
    """)
    result = []
    for wc in weight_classes:
        # Genre derive du nom : "Women's ..." -> F, sinon M (source de verite unique)
        g = "F" if (wc["name"] or "").lower().startswith("women") else "M"
        top = query(f"""
            SELECT {FIGHTER_LIST_COLS}
            FROM fighters
            WHERE weight_class_gendered IS NOT NULL
              AND weight_class_current != 'Unknown'
              AND ({_WCG_NAME}) = %s
            ORDER BY is_ufc_champion DESC,
                     ufc_official_rank ASC NULLS LAST,
                     fightmatrix_rating_points DESC NULLS LAST
            LIMIT 5;
        """, (wc["name"],))
        postprocess_many(top)

        # Champion : pre-fetch fiable, fallback sur top si absent du lookup
        base = _normalize_wc(wc["name"]).lower()
        champ = champ_lookup.get((base, g)) \
             or next((f for f in top if f.get("is_ufc_champion")), None)

        result.append({
            "name": wc["name"],
            "count": wc["count"],
            "champion": champ,
            "top": top,
        })
    return jsonify(result)


# Divisions standard affichees dans le hub Rankings (du plus lourd au plus leger).
_RANK_MEN_ORDER = [
    "Heavyweight", "Light Heavyweight", "Middleweight", "Welterweight",
    "Lightweight", "Featherweight", "Bantamweight", "Flyweight",
]
_RANK_WOMEN_ORDER = [
    "Lightweight", "Featherweight", "Bantamweight", "Flyweight",
    "Strawweight", "Atomweight",
]


@app.get("/api/rankings/overview")
def rankings_overview():
    """Hub Rankings : P4P (H/F) + champion/#1/#2 par division.

    Retour :
      - p4p_men / p4p_women : top 15 par genre (ufc_p4p_rank croissant).
      - men / women : listes ordonnees du plus LOURD au plus LEGER, chaque entree
        = {base, gender, display, value, champion, rank1, rank2}. Seules les
        divisions ayant au moins un champion ou un #1 sont incluses.
    """
    p4p = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE ufc_p4p_rank IS NOT NULL AND ufc_p4p_rank > 0
        ORDER BY ufc_p4p_rank ASC
    """)
    postprocess_many(p4p)
    p4p_men = [f for f in p4p if (f.get("gender") or "M").upper() != "F"][:15]
    p4p_women = [f for f in p4p if (f.get("gender") or "M").upper() == "F"][:15]

    rows = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE is_ufc_champion = TRUE
           OR (ufc_official_rank IS NOT NULL AND ufc_official_rank BETWEEN 1 AND 3)
    """)
    postprocess_many(rows)
    buckets: dict = {}
    for f in rows:
        base = _normalize_wc(f.get("weight_class_current"))
        if not base or base.lower() not in _WC_LADDER_POS:
            continue
        g = (f.get("gender") or "M").upper()
        d = buckets.setdefault((base, g), {"champion": None, "rank1": None, "rank2": None, "rank3": None})
        if f.get("is_ufc_champion"):
            if not d["champion"]:
                d["champion"] = f
        elif f.get("ufc_official_rank") == 1 and not d["rank1"]:
            d["rank1"] = f
        elif f.get("ufc_official_rank") == 2 and not d["rank2"]:
            d["rank2"] = f
        elif f.get("ufc_official_rank") == 3 and not d["rank3"]:
            d["rank3"] = f

    def build(order, gender):
        out = []
        for base in order:
            d = buckets.get((base, gender))
            if not d or not (d["champion"] or d["rank1"] or d["rank2"]):
                continue
            out.append({
                "base": base,
                "gender": gender,
                "display": f"{base} {'W' if gender == 'F' else 'M'}",
                "value": f"{base}|{gender}",
                "champion": d["champion"],
                "rank1": d["rank1"],
                "rank2": d["rank2"],
                "rank3": d["rank3"],
            })
        return out

    return jsonify({
        "p4p_men": p4p_men,
        "p4p_women": p4p_women,
        "men": build(_RANK_MEN_ORDER, "M"),
        "women": build(_RANK_WOMEN_ORDER, "F"),
    })


@app.get("/api/rankings/division")
def rankings_division():
    """Classement d'UNE division : champion + top 15 UFC officiel + 10 on-the-bubble.

    Le classement officiel UFC (colonne `ufc_official_rank`, scrappee depuis
    UFC-FR) fait FOI pour l'ordre : champion (rank 0) en tete, puis rangs 1->15.
    - champion : tenant du titre UFC (is_ufc_champion).
    - top15    : fighters ACTIFS classes 1..15 a l'UFC, tries par ufc_official_rank.
    - bubble   : 10 actifs NON classes UFC, tries par base_elo (c'est la que
                 remontent les hors-UFC pertinents : Ngannou, Usman Nurmagomedov...).
    On exclut TOUJOURS les inactifs (is_active=FALSE) : un retraite (AJ, Nunes,
    de Randamie) n'a rien a faire dans un classement, peu importe son Elo.
    """
    wc = (request.args.get("wc") or "").strip()
    gender = (request.args.get("gender") or "M").strip().upper()[:1]
    if not wc:
        return jsonify({"error": "wc required"}), 400

    # Champion : tenant du titre (peut ne pas avoir de rank, ou rank 0 par convention)
    champion = query_one(f"""
        SELECT {FIGHTER_LIST_COLS} FROM fighters
        WHERE LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s AND is_ufc_champion = TRUE
        ORDER BY ufc_official_rank ASC NULLS LAST
        LIMIT 1
    """, (wc, gender))
    if champion:
        postprocess_fighter(champion)

    # Top 15 = classement UFC officiel, actifs, hors champion
    top15 = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s
          AND is_active = TRUE
          AND COALESCE(is_ufc_champion, FALSE) = FALSE
          AND ufc_official_rank IS NOT NULL
          AND ufc_official_rank BETWEEN 1 AND 15
        ORDER BY ufc_official_rank ASC, base_elo DESC NULLS LAST
        LIMIT 15
    """, (wc, gender))
    postprocess_many(top15)

    # On the bubble = actifs NON classes UFC, par Elo (hors-UFC pertinents remontent ici)
    bubble = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s
          AND is_active = TRUE
          AND COALESCE(is_ufc_champion, FALSE) = FALSE
          AND (ufc_official_rank IS NULL OR ufc_official_rank > 15)
        ORDER BY base_elo DESC NULLS LAST
        LIMIT 15
    """, (wc, gender))
    postprocess_many(bubble)

    total_row = query_one(f"""
        SELECT COUNT(*) AS n FROM fighters
        WHERE LOWER({_WC_CANON_SQL}) = LOWER(%s) AND gender = %s
    """, (wc, gender))

    return jsonify({
        "wc": wc,
        "gender": gender,
        "champion": champion,
        "top15": top15,
        "bubble": bubble,
        "total": total_row["n"] if total_row else 0,
    })


@app.get("/api/rankings/p4p")
def rankings_p4p():
    """Top P4P hommes + femmes (base : ufc_p4p_rank)."""
    rows = query(f"""
        SELECT {FIGHTER_LIST_COLS}
        FROM fighters
        WHERE ufc_p4p_rank IS NOT NULL AND ufc_p4p_rank > 0
        ORDER BY ufc_p4p_rank ASC
        LIMIT 50
    """)
    postprocess_many(rows)
    men   = [f for f in rows if (f.get("gender") or "M").upper() != "F"][:20]
    women = [f for f in rows if (f.get("gender") or "M").upper() == "F"][:20]
    return jsonify({"men": men, "women": women})


@app.get("/api/analytics")
def analytics():
    """Donnees agregees pour la page Analytics (graphes)."""
    # by_division : on utilise _WC_CANON_SQL pour normaliser le prefixe "Women's",
    # on ajoute le genre, et on filtre aux divisions connues du ladder (_WC_LADDER_POS).
    # Seuil HAVING >= 5 pour eviter les divisions parasites (1-2 fighters mal classes).
    by_division_raw = query(f"""
        SELECT {_WC_CANON_SQL} AS base,
               gender,
               COUNT(*) AS count,
               SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active
        FROM fighters
        WHERE weight_class_current IS NOT NULL
          AND weight_class_current != 'Unknown'
          AND weight_class_current != ''
          AND gender IN ('M', 'F')
        GROUP BY base, gender
        HAVING COUNT(*) >= 5
        ORDER BY count DESC;
    """)
    by_division = [
        {"base": r["base"].strip(), "gender": r["gender"],
         "count": int(r["count"] or 0), "active": int(r["active"] or 0)}
        for r in by_division_raw
        if (r["base"] or "").strip().lower() in _WC_LADDER_POS
    ]
    by_nationality = query("""
        SELECT nationality AS name, COUNT(*) AS count
        FROM fighters
        WHERE nationality IS NOT NULL
        GROUP BY nationality
        ORDER BY count DESC
        LIMIT 10;
    """)
    by_stance = query("""
        SELECT stance AS name, COUNT(*) AS count
        FROM fighters
        WHERE stance IS NOT NULL
        GROUP BY stance
        ORDER BY count DESC;
    """)
    age_dist = query("""
        SELECT
            CASE
                WHEN age < 25 THEN '< 25'
                WHEN age < 30 THEN '25-29'
                WHEN age < 35 THEN '30-34'
                WHEN age < 40 THEN '35-39'
                ELSE '40+'
            END AS name,
            COUNT(*) AS count
        FROM fighters
        WHERE age IS NOT NULL
        GROUP BY 1
        ORDER BY 1;
    """)
    finish_methods = query("""
        SELECT 'KO/TKO' AS name, SUM(wins_by_ko_tko) AS count FROM fighters
        UNION ALL SELECT 'Submission', SUM(wins_by_submission) FROM fighters
        UNION ALL SELECT 'Decision', SUM(wins_by_decision) FROM fighters;
    """)
    # Nationalites : top 20 (le frontend prend ce dont il a besoin)
    by_nationality_raw = query("""
        SELECT nationality AS name, COUNT(*) AS count
        FROM fighters
        WHERE nationality IS NOT NULL AND nationality != ''
        GROUP BY nationality
        ORDER BY count DESC
        LIMIT 20;
    """)
    by_nationality = [{"name": r["name"], "count": int(r["count"] or 0)} for r in by_nationality_raw]

    # Finish rate par division
    # On derive les pourcentages KO/Sub/Dec depuis les colonnes de bilan.
    # Seuil minimum intentionnellement bas (5) pour couvrir toutes les divisions.
    finish_by_div = []
    try:
        finish_by_div_raw = query(f"""
            SELECT {_WC_CANON_SQL} AS division,
                   gender,
                   COALESCE(SUM(wins_by_ko_tko),    0) AS ko_tko,
                   COALESCE(SUM(wins_by_submission), 0) AS sub,
                   COALESCE(SUM(wins_by_decision),   0) AS dec_wins
            FROM fighters
            WHERE weight_class_current IS NOT NULL
              AND weight_class_current != 'Unknown'
              AND weight_class_current != ''
              AND gender IN ('M', 'F')
            GROUP BY 1, 2
            HAVING (
                COALESCE(SUM(wins_by_ko_tko),    0)
              + COALESCE(SUM(wins_by_submission), 0)
              + COALESCE(SUM(wins_by_decision),   0)
            ) >= 5
            ORDER BY gender, division;
        """)
        for r in finish_by_div_raw:
            div_key = (r.get("division") or "").strip().lower()
            if div_key not in _WC_LADDER_POS:
                continue
            ko  = int(r.get("ko_tko")   or 0)
            sub = int(r.get("sub")      or 0)
            dec = int(r.get("dec_wins") or 0)
            tot = ko + sub + dec
            if tot == 0:
                continue
            finish_by_div.append({
                "division": (r.get("division") or "").strip(),
                "gender":   r.get("gender"),
                "ko_pct":   round(100 * ko  / tot, 1),
                "sub_pct":  round(100 * sub / tot, 1),
                "dec_pct":  round(100 * dec / tot, 1),
                "total":    tot,
            })
        finish_by_div.sort(key=lambda x: _WC_LADDER_POS.get(x["division"].lower(), 99))
    except Exception:
        pass   # degradation gracieuse : le frontend affiche "no data"

    # Win rate moyen par nationalite
    win_by_nat_out = []
    try:
        win_by_nat_raw = query("""
            SELECT nationality AS name,
                   COUNT(*) AS fighters,
                   ROUND(AVG(
                       CASE
                         WHEN (COALESCE(record_total_wins,0) + COALESCE(record_total_losses,0)) > 0
                         THEN 100.0 * COALESCE(record_total_wins,0)
                              / (COALESCE(record_total_wins,0) + COALESCE(record_total_losses,0))
                         ELSE NULL
                       END
                   )) AS avg_win_rate
            FROM fighters
            WHERE nationality IS NOT NULL
              AND nationality != ''
              AND COALESCE(record_total_wins,0) + COALESCE(record_total_losses,0) > 0
            GROUP BY nationality
            HAVING COUNT(*) >= 30
            ORDER BY avg_win_rate DESC NULLS LAST
            LIMIT 12;
        """)
        win_by_nat_out = [
            {"name": r["name"],
             "fighters": int(r["fighters"] or 0),
             "avg_win_rate": int(r["avg_win_rate"] or 0)}
            for r in win_by_nat_raw
            if r.get("avg_win_rate") is not None
        ]
    except Exception:
        pass

    # Couverture / qualite des donnees
    data_quality = {}
    try:
        dq = query_one("""
            SELECT
                COUNT(*)                                                          AS total,
                COUNT(CASE WHEN photo_url IS NOT NULL
                            OR photo_thumbnail_url IS NOT NULL THEN 1 END)        AS has_photo,
                COUNT(date_of_birth)                                              AS has_dob,
                COUNT(fight_history)                                              AS has_history,
                COUNT(CASE WHEN nationality IS NOT NULL
                            AND nationality != '' THEN 1 END)                     AS has_nationality,
                COUNT(CASE WHEN base_elo IS NOT NULL
                            AND ABS(base_elo - 1500) > 0.5 THEN 1 END)           AS has_elo,
                ROUND(COALESCE(AVG(COALESCE(total_fights,0)), 0))                AS avg_fights,
                MAX(COALESCE(total_fights, 0))                                   AS max_fights,
                COUNT(DISTINCT nationality)                                       AS country_count,
                COUNT(DISTINCT CASE WHEN weight_class_current IS NOT NULL
                               AND weight_class_current != 'Unknown'
                               THEN weight_class_current END)                     AS division_count
            FROM fighters;
        """)
        if dq:
            data_quality = {k: (int(float(v)) if v is not None else 0) for k, v in dq.items()}
    except Exception:
        pass

    return jsonify({
        "by_division":      by_division,
        "by_nationality":   by_nationality,
        "by_stance":        by_stance,
        "age_distribution": age_dist,
        "finish_methods":   finish_methods,
        "finish_by_div":    finish_by_div,
        "win_by_nat":       win_by_nat_out,
        "data_quality":     data_quality,
    })


@app.get("/api/backtest")
def backtest_report():
    """
    Rapport de validation walk-forward du modele Elo (accuracy, Brier, calibration,
    ventilations). Le rapport est PRE-CALCULE par `database/run_backtest.py` et
    stocke en JSON (le backtest rejoue tout l'historique : trop lourd pour une
    requete HTTP). On le sert tel quel.

    Renvoie 503 si le rapport n'a pas encore ete genere -> le frontend affiche
    un message "validation pas encore lancee" plutot que de planter.
    """
    report_path = ROOT / "data" / "backtest_report.json"
    if not report_path.exists():
        return jsonify({
            "available": False,
            "message": "Backtest report not generated yet. Run: py database/run_backtest.py",
        }), 503
    try:
        data = _json.loads(report_path.read_text(encoding="utf-8"))
        data["available"] = True
        return jsonify(data)
    except (_json.JSONDecodeError, OSError) as e:
        return jsonify({"available": False, "message": f"Report unreadable: {e}"}), 500


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] PRÉDICTION — heuristique pondérée à la main, PAS du ML
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/predict")
def predict():
    """Prediction simple via difference de FightMatrix rating + record + forme.
    NOTE: pure heuristique pour la demo - le vrai ML viendra dans /backend."""
    try:
        id1 = int(request.args.get("id1"))
        id2 = int(request.args.get("id2"))
    except (TypeError, ValueError):
        return jsonify({"error": "id1 et id2 sont requis (entiers)"}), 400
    if id1 == id2:
        return jsonify({"error": "Un fighter ne peut pas se combattre lui-meme"}), 400

    f1 = query_one("SELECT * FROM fighters WHERE id = %s;", (id1,))
    f2 = query_one("SELECT * FROM fighters WHERE id = %s;", (id2,))
    if not f1 or not f2:
        return jsonify({"error": "Fighter introuvable"}), 404

    # ELO + scouter + forme calculés dynamiquement depuis fight_history
    postprocess_fighter(f1)
    postprocess_fighter(f2)

    compat_err = _check_division_compat(f1, f2)
    if compat_err:
        return jsonify({
            "error": "division_too_far",
            "message": compat_err,
            "fighter1": {"id": f1["id"], "name": f1["name"], "weight_class": f1.get("weight_class_current"), "gender": f1.get("gender")},
            "fighter2": {"id": f2["id"], "name": f2["name"], "weight_class": f2.get("weight_class_current"), "gender": f2.get("gender")},
        }), 422

    # fight_class optionnel : division dans laquelle se fait le combat
    # (fourni par le front quand les 2 fighters viennent de divisions differentes)
    fight_class_raw = (request.args.get("fight_class") or "").strip()
    fight_class_norm = _normalize_wc(fight_class_raw) if fight_class_raw else None
    away1 = bool(fight_class_norm and fight_class_norm != _normalize_wc(f1.get("weight_class_current") or ""))
    away2 = bool(fight_class_norm and fight_class_norm != _normalize_wc(f2.get("weight_class_current") or ""))

    # ═══════════════════════════════════════════════════════════════════
    # 📌 [DÉMO] GRILLE DE POIDS — valeurs posées à la main pour coller au ressenti MMA
    # pas apprises sur des données → 100% explicable et débogable
    # ═══════════════════════════════════════════════════════════════════
    # --- La grille de poids du score "maison" (heuristique, PAS du ML) --------
    # Chaque facteur ajoute/retire des points. Valeurs posées À LA MAIN pour que
    # l'ordre colle au ressenti MMA -> pas apprises sur des données :
    #   base_elo ×0.5  : le niveau brut, c'est le gros du score (elo ~2000 -> ~1000 pts)
    #   wins ×8 / losses ×5 : le palmarès ; défaite punie un peu moins que victoire payée
    #   rang UFC       : bonus dégressif (#1 -> +180, #15 -> +12), le top compte
    #   champion +250  : une ceinture ça pèse lourd direct
    #   forme ×100     : les 5 derniers combats (0 à 1) modulent
    #   inactivité -80 : +1 an sans combattre = ring rust, on doute
    #   âge            : malus passé 35 ans (déclin réel), petit malus avant 22 (trop jeune)
    #   cross_div ×0.94: malus si combat hors de sa division (même coeff que f_categorie scouter)
    # Ensuite l'écart des 2 scores part dans une logistique -> win% (cf _winprob_from_scores).
    def score(f, fighting_away=False):
        s = 0.0
        rating = f.get("base_elo") or f.get("fightmatrix_rating_points") or 100
        s += float(rating) * 0.5
        wins = f.get("record_total_wins") or 0
        losses = f.get("record_total_losses") or 0
        s += wins * 8 - losses * 5
        if f.get("ufc_official_rank"):
            s += max(0, 16 - int(f["ufc_official_rank"])) * 12
        if f.get("is_ufc_champion"):
            s += 250
        form = f.get("recent_form_score")
        if form is not None:
            s += float(form) * 100
        if (f.get("days_inactive") or 0) > 365:
            s -= 80
        age = f.get("age") or 30
        if age >= 36: s -= (age - 35) * 12
        elif age <= 22: s -= (23 - age) * 8
        if fighting_away:
            s *= 0.94
        return max(s, 1.0)

    s1 = score(f1, away1)     # ----------------------------------------------- score facteurs 
    s2 = score(f2, away2)
    total = s1 + s2
    p1 = round(100 * s1 / total, 1)
    p2 = round(100 - p1, 1)

    method_hint = None
    finish_rate_1 = f1.get("finish_rate_int") or 0
    finish_rate_2 = f2.get("finish_rate_int") or 0
    winner = f1 if p1 > p2 else f2
    finish_winner = finish_rate_1 if p1 > p2 else finish_rate_2
    if finish_winner > 60:
        ko_share = (winner.get("wins_by_ko_tko") or 0)
        sub_share = (winner.get("wins_by_submission") or 0)
        method_hint = "KO/TKO" if ko_share >= sub_share else "Submission"
    else:
        method_hint = "Decision"

    return jsonify({
        "demo_notice": DEMO_NOTICE,
        "fighter1": {
            "id": f1["id"], "name": f1["name"], "nickname": f1.get("nickname"),
            "photo_url": f1.get("photo_url") or f1.get("photo_thumbnail_url"),
            "weight_class": f1.get("weight_class_current"),
            "record": [f1.get("record_total_wins"), f1.get("record_total_losses"), f1.get("record_total_draws")],
            "rating": serialize(f1.get("fightmatrix_rating_points")),
            "win_prob": p1,
            "score": round(s1, 1),
        },
        "fighter2": {
            "id": f2["id"], "name": f2["name"], "nickname": f2.get("nickname"),
            "photo_url": f2.get("photo_url") or f2.get("photo_thumbnail_url"),
            "weight_class": f2.get("weight_class_current"),
            "record": [f2.get("record_total_wins"), f2.get("record_total_losses"), f2.get("record_total_draws")],
            "rating": serialize(f2.get("fightmatrix_rating_points")),
            "win_prob": p2,
            "score": round(s2, 1),
        },
        "predicted_winner_id": f1["id"] if p1 > p2 else f2["id"],
        "method_hint": method_hint,
        "confidence": abs(p1 - p2),
        "model": "heuristic-v0 (FightMatrix rating + record + UFC rank + form + inactivity)",
        "disclaimer": "Prediction heuristique de demo. Le modele ML final (Elo + Scouter) viendra ensuite dans /backend.",
    })


# ---- Erreurs ---------------------------------------------------------------

# Échelle de la logistique des probabilités de victoire (en "points de score").
# Plus c'est PETIT, plus les probas s'écartent vite. Calibré pour qu'un écart
# typique de ~95 pts donne ~61% (un favori léger, pas 50/50 écrasé).
_WINPROB_SCALE = 500.0

# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] LOGISTIQUE SUR L'ÉCART — évite la compression vers 50% d'un ratio simple
# écart typique ~95 pts → ~61% (favori léger réaliste, pas 50/50 écrasé)
# ═══════════════════════════════════════════════════════════════════
def _winprob_from_scores(s1: float, s2: float, scale: float = _WINPROB_SCALE):
    """Proba de victoire (p1, p2) via la logistique sur l'ÉCART des scores.
    La base commune des deux scores s'annule -> fini la compression vers 50%."""
    p1 = 1.0 / (1.0 + 10.0 ** ((s2 - s1) / scale))
    p1 = round(100.0 * p1, 1)
    return p1, round(100.0 - p1, 1)


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] MATCHMAKING COMPLET — score détaillé + tale of the tape + breakdown + H2H
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/matchmaking")
def matchmaking():
    """Analyse complete d'un matchup : prediction + tale of the tape +
    breakdown des facteurs + style matchup. Pour la page Matchmaking."""
    try:
        id1 = int(request.args.get("id1"))
        id2 = int(request.args.get("id2"))
    except (TypeError, ValueError):
        return jsonify({"error": "id1 et id2 sont requis"}), 400
    if id1 == id2:
        return jsonify({"error": "Memes fighters"}), 400

    f1 = query_one("SELECT * FROM fighters WHERE id = %s;", (id1,))
    f2 = query_one("SELECT * FROM fighters WHERE id = %s;", (id2,))
    if not f1 or not f2:
        return jsonify({"error": "Fighter introuvable"}), 404

    # Postprocess : ELO dynamique (depuis fight_history), scouter dynamique, age frais, etc.
    postprocess_fighter(f1)
    postprocess_fighter(f2)

    compat_err = _check_division_compat(f1, f2)
    if compat_err:
        return jsonify({
            "error": "division_too_far",
            "message": compat_err,
            "fighter1": {"id": f1["id"], "name": f1["name"], "weight_class": f1.get("weight_class_current"), "gender": f1.get("gender")},
            "fighter2": {"id": f2["id"], "name": f2["name"], "weight_class": f2.get("weight_class_current"), "gender": f2.get("gender")},
        }), 422

    # fight_class optionnel : division dans laquelle se fait le combat
    fight_class_raw = (request.args.get("fight_class") or "").strip()
    fight_class_norm = _normalize_wc(fight_class_raw) if fight_class_raw else None
    away1 = bool(fight_class_norm and fight_class_norm != _normalize_wc(f1.get("weight_class_current") or ""))
    away2 = bool(fight_class_norm and fight_class_norm != _normalize_wc(f2.get("weight_class_current") or ""))

    # ---- Score breakdown (utilise base_elo dynamique apres postprocess) ------
    h2h_w1, h2h_w2 = _find_h2h(f1, f2)
    _H2H_BONUS = 80

    # Même grille de poids que /api/predict (heuristique posée à la main, pas du ML)
    # mais ici on garde le détail POSTE PAR POSTE dans un dict, pour l'afficher
    # dans le breakdown du front. base_elo ×0.5 = le gros du score.
    #   h2h +80 : bonus au fighter qui mène les confrontations directes passées.
    #   cross_div -6% : malus si combat hors de sa division (même coeff que f_categorie scouter)
    def breakdown(f, h2h_wins, opp_h2h_wins, fighting_away=False):
        b = {}
        rating = float(f.get("base_elo") or f.get("fightmatrix_rating_points") or 100)
        b["rating"]      = rating * 0.5
        b["wins_bonus"]  = (f.get("record_total_wins") or 0) * 8
        b["losses_pen"]  = -(f.get("record_total_losses") or 0) * 7
        b["ufc_rank"]    = max(0, 16 - int(f["ufc_official_rank"])) * 12 if f.get("ufc_official_rank") else 0
        b["champion"]    = 210 if f.get("is_ufc_champion") else 0
        b["form"]        = float(f["recent_form_score"]) * 130 if f.get("recent_form_score") is not None else 0
        b["inactivity"]  = -80 if (f.get("days_inactive") or 0) > 365 else 0
        age = f.get("age") or 30
        # pénalité âge : commence à 35 ans (déclin MMA réel dès 35+), -18 pts/an
        if age >= 35:   b["age_pen"] = -(age - 34) * 22
        elif age <= 22: b["age_pen"] = -(23 - age) * 8
        else:           b["age_pen"] = 0
        # head-to-head : bonus au fighter qui a dominé les confrontations directes
        b["h2h"] = _H2H_BONUS if h2h_wins > opp_h2h_wins else 0
        subtotal = max(sum(b.values()), 1.0)
        if fighting_away:
            b["cross_division_pen"] = -round(subtotal * 0.06)
        b["total"] = max(sum(b.values()), 1.0)
        return b

    b1 = breakdown(f1, h2h_w1, h2h_w2, away1)
    b2 = breakdown(f2, h2h_w2, h2h_w1, away2)
    p1, p2 = _winprob_from_scores(b1["total"], b2["total"])    # gagnant ----------------------

    # ---- Style matchup ---------------------------------------------------
    def style(f):
        wins = max(f.get("record_total_wins") or 1, 1)
        ko_rate  = round(100 * (f.get("wins_by_ko_tko")     or 0) / wins)
        sub_rate = round(100 * (f.get("wins_by_submission") or 0) / wins)
        dec_rate = round(100 * (f.get("wins_by_decision")   or 0) / wins)
        if ko_rate >= 50:        label = "Striker"
        elif sub_rate >= 40:     label = "Grappler"
        elif dec_rate >= 50:     label = "Decision artist"
        elif ko_rate + sub_rate >= 60: label = "Finisher"
        else:                    label = "Polyvalent"
        return {"label": label, "ko_pct": ko_rate, "sub_pct": sub_rate, "dec_pct": dec_rate,
                "finish_rate": f.get("finish_rate_int") or (ko_rate + sub_rate)}

    s1 = style(f1)
    s2 = style(f2)

    # ---- Method hint -----------------------------------------------------
    winner = f1 if p1 > p2 else f2
    sw = s1 if p1 > p2 else s2
    if sw["finish_rate"] >= 60 and sw["ko_pct"] >= sw["sub_pct"]:
        method = "KO/TKO"
    elif sw["finish_rate"] >= 50 and sw["sub_pct"] > sw["ko_pct"]:
        method = "Submission"
    else:
        method = "Decision"

    # ---- Round hint (purement heuristique pour la demo) ------------------
    if method == "Decision":
        round_hint = "Distance complete (5 rounds)" if f1.get("is_ufc_champion") or f2.get("is_ufc_champion") else "Distance complete (3 rounds)"
    elif sw["ko_pct"] >= 70:
        round_hint = "Round 1-2"
    else:
        round_hint = "Round 2-3"

    # ---- Tale of the tape ------------------------------------------------
    def tape(f):
        return {
            "age":            f.get("age"),
            "height_inches":  f.get("height_inches"),
            "reach_inches":   f.get("reach_inches"),
            "stance":         f.get("stance"),
            "weight_class":   f.get("weight_class_current"),
            "nationality":    f.get("nationality"),
        }

    def card(f, prob, score_b, st, fighting_away=False):
        return {
            "id": f["id"], "name": f["name"], "nickname": f.get("nickname"),
            "photo_url": f.get("photo_url") or f.get("photo_thumbnail_url"),
            "record": [f.get("record_total_wins") or 0,
                       f.get("record_total_losses") or 0,
                       f.get("record_total_draws") or 0],
            "rating": serialize(f.get("fightmatrix_rating_points")),
            "base_elo": serialize(f.get("base_elo")),
            "scouter_rating": float(f["scouter_rating"]) if f.get("scouter_rating") is not None else None,
            "win_prob": prob,
            "score_total": round(score_b["total"], 1),
            "breakdown": {k: round(v, 1) for k, v in score_b.items() if k != "total"},
            "tape": tape(f),
            "style": st,
            "is_champion": bool(f.get("is_ufc_champion")),
            "ufc_rank": f.get("ufc_official_rank"),
            "current_streak": f.get("current_streak"),
            "last_5_results": f.get("last_5_results"),
            "fighting_away": fighting_away,
        }

    return jsonify({
        "demo_notice": DEMO_NOTICE,
        "fighter1": card(f1, p1, b1, s1, away1),
        "fighter2": card(f2, p2, b2, s2, away2),
        "predicted_winner_id": winner["id"],
        "predicted_winner_name": winner["name"],
        "method_hint": method,
        "round_hint": round_hint,
        "confidence": abs(p1 - p2),
        "confidence_label": (
            "Pari serre" if abs(p1 - p2) < 10
            else "Confiance moderee" if abs(p1 - p2) < 25
            else "Confiance haute" if abs(p1 - p2) < 50
            else "Tres haute"
        ),
        "fight_class": fight_class_raw or None,
        "cross_division": bool(fight_class_raw and (away1 or away2)),
        "model": "heuristic-v0",
        "disclaimer": "Demo : heuristique pondérée. Le ML calibre arrivera dans /backend.",
    })


# ═══════════════════════════════════════════════════════════════════
# 📌 [DÉMO] ANALYSE IA — envoie toutes nos données au LLM, fallback propre sans clé
# le LLM RÉDIGE l'explication, il ne prédit PAS (les calculs = Elo + Scouter)
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/matchmaking/analysis")     # MATCHMAKING ANALYSIS
def matchmaking_analysis():
    """Analyse de combat REDIGEE par un LLM a partir de toutes nos donnees.

    Renvoie un paragraphe d'analyse + le vainqueur pressenti + un % de fiabilite
    (a la maniere du data_score : plus bas si des donnees manquent ou si le
    combat est serre). Si aucune cle LLM n'est configuree dans le .env, on
    retombe sur une analyse "de secours" generee sans IA -> le site marche
    quand meme.
    """
    try:
        id1 = int(request.args.get("id1"))
        id2 = int(request.args.get("id2"))
    except (TypeError, ValueError):
        return jsonify({"error": "id1 et id2 sont requis"}), 400
    if id1 == id2:
        return jsonify({"error": "Memes fighters"}), 400

    f1 = query_one("SELECT * FROM fighters WHERE id = %s;", (id1,))
    f2 = query_one("SELECT * FROM fighters WHERE id = %s;", (id2,))
    if not f1 or not f2:
        return jsonify({"error": "Fighter introuvable"}), 404

    postprocess_fighter(f1)
    postprocess_fighter(f2)

    # --- Score "maison" (meme logique que /api/matchmaking) pour donner au LLM
    #     un point d'ancrage chiffre coherent avec le reste du site. -----------
    _h2h_w1, _h2h_w2 = _find_h2h(f1, f2)

    def _score(f, h2h_wins, opp_h2h_wins):
        rating = float(f.get("base_elo") or f.get("fightmatrix_rating_points") or 100)
        s = rating * 0.5
        s += (f.get("record_total_wins") or 0) * 8
        s -= (f.get("record_total_losses") or 0) * 5
        if f.get("ufc_official_rank"):
            s += max(0, 16 - int(f["ufc_official_rank"])) * 12
        if f.get("is_ufc_champion"):
            s += 250
        if f.get("recent_form_score") is not None:
            s += float(f["recent_form_score"]) * 100
        age = f.get("age") or 30
        if age >= 35:
            s -= (age - 34) * 18
        if h2h_wins > opp_h2h_wins:
            s += 80
        return max(s, 1.0)

    s1, s2 = _score(f1, _h2h_w1, _h2h_w2), _score(f2, _h2h_w2, _h2h_w1)
    p1, p2 = _winprob_from_scores(s1, s2)

    # --- Completude des donnees par fighter (0-100). Sert de garde-fou pour la
    #     fiabilite : on ne peut pas etre tres confiant si on n'a presque rien. -
    # ── 📌 [DÉMO] COMPLÉTUDE — 8 checks → plafonne la fiabilité IA si données manquantes
    def _completeness(f):
        checks = [
            f.get("base_elo") is not None and abs(float(f.get("base_elo") or 1500) - 1500) > 0.5,
            f.get("scouter_rating") is not None,
            f.get("recent_form_score") is not None,
            (f.get("record_total_wins") or 0) + (f.get("record_total_losses") or 0) > 0,
            f.get("height_inches") is not None,
            f.get("reach_inches") is not None,
            f.get("age") is not None,
            (f.get("total_fights") or 0) >= 3,
        ]
        return round(100 * sum(1 for c in checks if c) / len(checks))

    c1, c2 = _completeness(f1), _completeness(f2)
    data_completeness = round((c1 + c2) / 2)

    # --- Bloc texte envoye au LLM ------------------------------------------
    def _line(f):
        return (
            f"- {f.get('name')} ({f.get('nickname') or 'sans surnom'}) : "
            f"Elo={f.get('base_elo')}, Scouter/100={f.get('scouter_rating')}, "
            f"forme(0-1)={f.get('recent_form_score')}, "
            f"record={f.get('record_total_wins') or 0}-{f.get('record_total_losses') or 0}-{f.get('record_total_draws') or 0}, "
            f"KO={f.get('wins_by_ko_tko')}, sub={f.get('wins_by_submission')}, "
            f"age={f.get('age')}, taille_in={f.get('height_inches')}, allonge_in={f.get('reach_inches')}, "
            f"stance={f.get('stance')}, division={f.get('weight_class_current')}, "
            f"rang_ufc={f.get('ufc_official_rank')}, champion={bool(f.get('is_ufc_champion'))}, "
            f"streak={f.get('current_streak')}, completude_donnees={_completeness(f)}%"
        )

    _h2h_total = _h2h_w1 + _h2h_w2
    if _h2h_total > 0:
        _h2h_ctx = (
            f"Confrontations directes entre les deux fighters : "
            f"{f1.get('name')} {_h2h_w1}-{_h2h_w2} {f2.get('name')} "
            f"({'avantage ' + f1.get('name') if _h2h_w1 > _h2h_w2 else 'avantage ' + f2.get('name') if _h2h_w2 > _h2h_w1 else 'egalite'}).\n"
        )
    else:
        _h2h_ctx = "Aucun combat direct precedent retrouve dans les donnees.\n"

    prompt_data = (
        f"Combat a analyser :\n{_line(f1)}\n{_line(f2)}\n\n"
        f"{_h2h_ctx}"
        f"Notre modele maison donne : {f1.get('name')} {p1}% vs {f2.get('name')} {p2}%.\n"
        f"Completude moyenne des donnees : {data_completeness}%.\n"
        "Rends ton analyse en JSON comme demande."
    )

    heuristic_winner = f1["name"] if p1 >= p2 else f2["name"]

    # --- Appel IA (ou fallback sans IA) ------------------------------------
    lang = (request.args.get("lang") or "en").lower()
    if llm_available():
        result = generate_fight_analysis(prompt_data, lang=lang)
    else:
        result = {"source": "no_key", "analysis": "", "reliability": None,
                  "predicted_winner": ""}

    used_fallback = result.get("source") in ("no_key", "error") or not result.get("analysis")
    if used_fallback:
        # Analyse de secours, rédigée sans IA à partir des chiffres.
        # Localisée selon `lang` (EN par défaut ; les langues non gérées retombent sur EN).
        ecart = abs(p1 - p2)
        result["predicted_winner"] = heuristic_winner
        result["reliability"] = round(min(95, data_completeness * 0.6 + min(ecart, 50)))
        gap_key = "tight" if ecart < 10 else "moderate" if ecart < 25 else "clear"
        _FALLBACK = {
            "en": {
                "tight": "close", "moderate": "moderate", "clear": "clear",
                "tpl": ("{w} is the favorite ({p}%). The gap on paper is {g}. "
                        "Read based on Elo, recent form and record. "
                        "Reliability is capped by data completeness ({d}%)."),
                "hint": " (Add an LLM key in the .env for a full AI-written analysis.)",
            },
            "fr": {
                "tight": "serré", "moderate": "modéré", "clear": "net",
                "tpl": ("{w} part favori ({p}%). L'écart sur le papier est {g}. "
                        "Lecture basée sur l'Elo, la forme récente et le record. "
                        "La fiabilité est limitée par la complétude des données ({d}%)."),
                "hint": " (Ajoute une clé LLM dans le .env pour une analyse rédigée par IA.)",
            },
        }
        fb = _FALLBACK.get(lang, _FALLBACK["en"])
        result["analysis"] = fb["tpl"].format(
            w=heuristic_winner, p=max(p1, p2), g=fb[gap_key], d=data_completeness
        ) + ("" if llm_available() else fb["hint"])

    return jsonify({
        "fighter1": {"id": f1["id"], "name": f1["name"], "win_prob": p1, "data_completeness": c1},
        "fighter2": {"id": f2["id"], "name": f2["name"], "win_prob": p2, "data_completeness": c2},
        "predicted_winner": result.get("predicted_winner") or heuristic_winner,
        "reliability": result.get("reliability"),
        "analysis": result.get("analysis"),
        "data_completeness": data_completeness,
        "source": result.get("source", "no_key"),
        "ai_enabled": llm_available(),
    })


@app.get("/api/events")
def events_list():
    """Liste des events.

    Params :
      - limit, page    : pagination
      - promotion      : filtre 'UFC', 'PFL', etc. (ILIKE)
      - status         : 'upcoming' | 'completed' | 'cancelled'
      - year           : 4-digit year
      - sort           : 'asc' (date ASC) | 'desc' (date DESC, default)
      - search         : recherche fuzzy + tiered sur le nom de l'event
    """
    limit = min(int(request.args.get("limit", 30)), 100)
    page = max(int(request.args.get("page", 1)), 1)
    offset = (page - 1) * limit
    promotion = (request.args.get("promotion") or "").strip()
    status = (request.args.get("status") or "").strip()
    year = (request.args.get("year") or "").strip()
    sort = (request.args.get("sort") or "desc").strip().lower()
    search = (request.args.get("search") or "").strip()

    where = []
    params: list = []
    if promotion:
        where.append("promotion ILIKE %s")
        params.append(f"%{promotion}%")
    # Date-based logic (NEW)
    # On ne se fie plus a la colonne `status` stockee en BDD (qui est figee au scrape).
    # Au lieu de ca, on filtre par date avec un chevauchement d'1 jour :
    #   - upcoming : date >= today - 1 day  (event futur, ou hier)
    #   - results  : date <= today - 1 day  (event hier, ou avant)
    #   - Les events d'hier apparaissent dans LES DEUX (chevauchement 1 jour)
    if status == "upcoming":
        where.append("date >= (CURRENT_DATE - INTERVAL '1 day')")
    elif status == "completed":
        where.append("date <= (CURRENT_DATE - INTERVAL '1 day')")
    elif status == "cancelled":
        where.append("status = 'cancelled'")
    # "Road to UFC" = série distincte, exclue des queries UFC propres
    if promotion.upper() == "UFC":
        where.append("name NOT ILIKE 'Road to UFC%%'")
    if year:
        where.append("EXTRACT(YEAR FROM date) = %s")
        params.append(int(year))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # effective_status : calcule "upcoming/completed" dynamiquement.
    # Priorite 1 : si au moins 1 bout a un winner_id -> l'event est completed,
    #   peu importe la date (evite le badge "UPCOMING" le lendemain d'un event).
    # Priorite 2 : si la date est encore a venir -> upcoming.
    # Priorite 3 : sinon -> completed.
    EFFECTIVE_STATUS_SQL = """
        CASE
          WHEN status = 'cancelled' THEN 'cancelled'
          WHEN EXISTS (
            SELECT 1 FROM event_fights ef2
            WHERE ef2.event_id = e.id AND ef2.winner_id IS NOT NULL
          ) THEN 'completed'
          WHEN date >= CURRENT_DATE THEN 'upcoming'
          ELSE 'completed'
        END AS effective_status
    """

    # Branche AVEC search : scoring tiered + fuzzy comme pour fighters
    if search:
        named: dict = {"q": search, "limit": limit, "offset": offset}
        extra_where = ["score > 0"]
        if promotion:
            extra_where.append("promotion ILIKE %(promo)s")
            named["promo"] = f"%{promotion}%"
        if status == "upcoming":
            extra_where.append("date >= (CURRENT_DATE - INTERVAL '1 day')")
        elif status == "completed":
            extra_where.append("date <= (CURRENT_DATE - INTERVAL '1 day')")
        elif status == "cancelled":
            extra_where.append("status = 'cancelled'")
        if year:
            extra_where.append("EXTRACT(YEAR FROM date) = %(year)s")
            named["year"] = int(year)
        extra_sql = " AND ".join(extra_where)

        sql = f"""
            WITH scored AS (
                SELECT e.id, e.name, e.promotion, e.date, e.venue, e.city, e.country,
                       e.tapology_url, e.slug, e.status, e.poster_url,
                       {EFFECTIVE_STATUS_SQL},
                       (SELECT COUNT(*) FROM event_fights ef WHERE ef.event_id = e.id) AS fight_count,
                       CASE
                         WHEN LOWER(name) LIKE LOWER(%(q)s) || '%%'                  THEN 100
                         WHEN LOWER(name) ~* ('(^|[[:space:]\\-:])' || LOWER(%(q)s)) THEN 80
                         WHEN LOWER(name) LIKE '%%' || LOWER(%(q)s) || '%%'          THEN 50
                         WHEN char_length(%(q)s) >= 4 AND similarity(name, %(q)s) > 0.30
                              THEN 20 + (similarity(name, %(q)s) * 30)::int
                         ELSE 0
                       END AS score
                FROM events e
            )
            SELECT * FROM scored WHERE {extra_sql}
            ORDER BY score DESC, date DESC NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        rows = query(sql, named)
        for r in rows:
            r.pop("score", None)
        total_q = query_one(f"SELECT COUNT(*) AS n FROM events {where_sql}", tuple(params))
        return jsonify({
            "events": rows,
            "total": total_q["n"] if total_q else len(rows),
            "page": page,
            "limit": limit,
        })

    order_dir = "ASC NULLS LAST" if sort == "asc" else "DESC NULLS LAST"

    rows = query(f"""
        SELECT id, name, promotion, date, venue, city, country,
               tapology_url, slug, status, poster_url,
               {EFFECTIVE_STATUS_SQL},
               (SELECT COUNT(*) FROM event_fights ef WHERE ef.event_id = e.id) AS fight_count
        FROM events e
        {where_sql}
        ORDER BY date {order_dir}
        LIMIT %s OFFSET %s
    """, tuple(params) + (limit, offset))

    total = query_one(f"SELECT COUNT(*) AS n FROM events {where_sql}", tuple(params))

    return jsonify({
        "events": rows,
        "total": total["n"] if total else 0,
        "page": page,
        "limit": limit,
    })


@app.get("/api/events/last")
def last_event():
    """Dernier event UFC complété avec bouts Main Card — pour la homepage."""
    promotion = (request.args.get("promotion") or "UFC").strip().upper()

    # Dernière carte UFC par DATE (passée), que les résultats soient scrappés ou non.
    # Choix produit (Elias, juin 2026) : on affiche toujours la dernière carte réelle ;
    # si les résultats ne sont pas encore scrappés, tant pis — au moins le bon event/date.
    ev = query_one("""
        SELECT id, name, promotion, date, venue, city, country, poster_url, slug
        FROM events
        WHERE promotion ILIKE %s
          AND name NOT ILIKE 'Road to UFC%%'
          AND date <= CURRENT_DATE
        ORDER BY date DESC
        LIMIT 1
    """, (promotion,))

    if not ev:
        return jsonify(None)

    fights_raw = query("""
        SELECT
            ef.id, ef.bout_order, ef.card_section,
            ef.weight_class, ef.rounds, ef.is_title_fight,
            ef.method, ef.method_detail, ef.round_num, ef.time_str,
            ef.winner_id, ef.winner_name, ef.status,
            ef.fighter1_id, ef.fighter2_id,
            ef.fighter1_name, ef.fighter2_name,
            f1.name AS f1_name_db, f1.photo_thumbnail_url AS f1_photo,
            f1.record_total_wins  AS f1_wins,
            f1.record_total_losses AS f1_losses,
            f1.record_total_draws  AS f1_draws,
            f1.ufc_official_rank AS f1_rank,
            f1.is_ufc_champion   AS f1_champ,
            f2.name AS f2_name_db, f2.photo_thumbnail_url AS f2_photo,
            f2.record_total_wins  AS f2_wins,
            f2.record_total_losses AS f2_losses,
            f2.record_total_draws  AS f2_draws,
            f2.ufc_official_rank AS f2_rank,
            f2.is_ufc_champion   AS f2_champ
        FROM event_fights ef
        LEFT JOIN fighters f1 ON ef.fighter1_id  = f1.id
        LEFT JOIN fighters f2 ON ef.fighter2_id  = f2.id
        WHERE ef.event_id = %s
          AND COALESCE(ef.status, '') != 'cancelled'
        ORDER BY
          CASE
            WHEN COALESCE(ef.card_section, 'Main Card') ILIKE '%%Prelim%%' THEN 1
            ELSE 0
          END ASC,
          ef.bout_order ASC
    """, (ev["id"],))

    bouts = []
    for f in fights_raw:
        wid  = f.get("winner_id")
        wname = (f.get("winner_name") or "").strip().lower()
        f1id, f2id = f.get("fighter1_id"), f.get("fighter2_id")
        f1nm = (f.get("f1_name_db") or f.get("fighter1_name") or "").lower()
        f2nm = (f.get("f2_name_db") or f.get("fighter2_name") or "").lower()
        if wid and f1id and wid == f1id:
            f1_win, f2_win = True, False
        elif wid and f2id and wid == f2id:
            f1_win, f2_win = False, True
        elif wname:
            f1_win = bool(wname == f1nm)
            f2_win = bool(wname == f2nm)
        else:
            f1_win = f2_win = False

        bouts.append({
            "card_section":  f.get("card_section") or "Main Card",
            "bout_order":    f.get("bout_order"),
            "weight_class":  normalize_weight_class(f.get("weight_class")),
            "rounds":        f.get("rounds"),
            "is_title_fight": bool(f.get("is_title_fight")),
            "method":        f.get("method"),
            "method_detail": f.get("method_detail"),
            "round_num":     f.get("round_num"),
            "time_str":      f.get("time_str"),
            "status": (
                "completed"
                if (f.get("winner_id") or f.get("winner_name") or f.get("method"))
                else "upcoming"
            ),
            "winner_name": f.get("winner_name"),
            "fighter1": {
                "id":          f.get("fighter1_id"),
                "name":        f.get("f1_name_db") or f.get("fighter1_name"),
                "photo":       f.get("f1_photo"),
                "record":      [f.get("f1_wins") or 0, f.get("f1_losses") or 0, f.get("f1_draws") or 0],
                "rank":        f.get("f1_rank"),
                "is_champion": bool(f.get("f1_champ")),
                "is_winner":   f1_win,
            },
            "fighter2": {
                "id":          f.get("fighter2_id"),
                "name":        f.get("f2_name_db") or f.get("fighter2_name"),
                "photo":       f.get("f2_photo"),
                "record":      [f.get("f2_wins") or 0, f.get("f2_losses") or 0, f.get("f2_draws") or 0],
                "rank":        f.get("f2_rank"),
                "is_champion": bool(f.get("f2_champ")),
                "is_winner":   f2_win,
            },
        })

    ev["bouts"] = bouts
    return jsonify(ev)


@app.get("/api/events/<int:event_id>")
def event_detail(event_id: int):
    """Detail complet d'un event avec tous les bouts."""
    ev = query_one("""
        SELECT *,
               CASE
                 WHEN status = 'cancelled' THEN 'cancelled'
                 WHEN EXISTS (
                   SELECT 1 FROM event_fights ef2
                   WHERE ef2.event_id = events.id AND ef2.winner_id IS NOT NULL
                 ) THEN 'completed'
                 WHEN date >= CURRENT_DATE THEN 'upcoming'
                 ELSE 'completed'
               END AS effective_status
        FROM events WHERE id = %s
    """, (event_id,))
    if not ev:
        return jsonify({"error": "Event introuvable"}), 404

    fights_raw = query("""
        SELECT
            ef.*,
            f1.name AS f1_name_db, f1.photo_thumbnail_url AS f1_photo,
            f1.weight_class_current AS f1_wc, f1.nationality AS f1_nat,
            f1.ufc_official_rank AS f1_rank, f1.is_ufc_champion AS f1_champ,
            f1.record_total_wins AS f1_wins, f1.record_total_losses AS f1_losses,
            f1.record_total_draws AS f1_draws, f1.gender AS f1_gender,
            f2.name AS f2_name_db, f2.photo_thumbnail_url AS f2_photo,
            f2.weight_class_current AS f2_wc, f2.nationality AS f2_nat,
            f2.ufc_official_rank AS f2_rank, f2.is_ufc_champion AS f2_champ,
            f2.record_total_wins AS f2_wins, f2.record_total_losses AS f2_losses,
            f2.record_total_draws AS f2_draws, f2.gender AS f2_gender
        FROM event_fights ef
        LEFT JOIN fighters f1 ON ef.fighter1_id = f1.id
        LEFT JOIN fighters f2 ON ef.fighter2_id = f2.id
        WHERE ef.event_id = %s
        ORDER BY ef.bout_order ASC
    """, (event_id,))

    sections: dict[str, list] = {}
    for f in fights_raw:
        sec = f.get("card_section") or "Main Card"
        sections.setdefault(sec, [])
        bout_wc = normalize_weight_class(f.get("weight_class"))

        # Determiner le vainqueur de facon ROBUSTE :
        #   1. winner_id == fighterX_id  (fiable, vient de archivefg/UFCStats)
        #   2. sinon winner_name == nom du fighter (fallback Tapology/ESPN)
        wid = f.get("winner_id")
        wname = (f.get("winner_name") or "").strip().lower()
        f1id, f2id = f.get("fighter1_id"), f.get("fighter2_id")
        f1nm = (f.get("f1_name_db") or f.get("fighter1_name") or "").lower()
        f2nm = (f.get("f2_name_db") or f.get("fighter2_name") or "").lower()
        if wid and f1id and wid == f1id:
            f1_win, f2_win = True, False
        elif wid and f2id and wid == f2id:
            f1_win, f2_win = False, True
        elif wname:
            f1_win = wname == f1nm
            f2_win = wname == f2nm
        else:
            f1_win = f2_win = False
        bout = {
            "id": f["id"],
            "bout_order": f["bout_order"],
            "weight_class": bout_wc,
            "weight_lbs": f.get("weight_lbs"),
            "rounds": f.get("rounds"),
            "is_title_fight": bool(f.get("is_title_fight")),
            "is_interim_title": bool(f.get("is_interim_title")),
            "method": f.get("method"),
            "method_detail": f.get("method_detail"),
            "round_num": f.get("round_num"),
            "time_str": f.get("time_str"),
            # Un bout avec un vainqueur (winner_id/name) OU une methode est completed,
            # peu importe le 'status' stocke (qui peut etre fige a 'upcoming').
            "status": (
                "completed"
                if (f.get("winner_id") or f.get("winner_name") or f.get("method"))
                else (f.get("status") or "upcoming")
            ),
            "winner_name": f.get("winner_name"),
            "fighter1": {
                "id": f.get("fighter1_id"),
                "name": f.get("f1_name_db") or f.get("fighter1_name"),
                "photo": f.get("f1_photo"),
                "nationality": f.get("f1_nat"),
                "weight_class": normalize_weight_class(f.get("f1_wc")),
                "gender": f.get("f1_gender"),
                "record": [f.get("f1_wins") or 0, f.get("f1_losses") or 0, f.get("f1_draws") or 0],
                "rank": f.get("f1_rank"),
                "is_champion": bool(f.get("f1_champ")),
                "is_winner": f1_win,
            },
            "fighter2": {
                "id": f.get("fighter2_id"),
                "name": f.get("f2_name_db") or f.get("fighter2_name"),
                "photo": f.get("f2_photo"),
                "nationality": f.get("f2_nat"),
                "weight_class": normalize_weight_class(f.get("f2_wc")),
                "gender": f.get("f2_gender"),
                "record": [f.get("f2_wins") or 0, f.get("f2_losses") or 0, f.get("f2_draws") or 0],
                "rank": f.get("f2_rank"),
                "is_champion": bool(f.get("f2_champ")),
                "is_winner": f2_win,
            },
        }
        sections[sec].append(bout)

    # Fallback name→id pour les fighters sans FK dans event_fights.
    # Matching ROBUSTE (corrige les 2 symptomes : combattant grise alors qu'il est
    # en BDD, et lien pointant vers le mauvais doublon) :
    #   - cle normalisee (sans accents/apostrophes/ponctuation) -> 'Moises'/'O'Malley'
    #   - on garde TOUS les homonymes puis on tranche avec le contexte du bout
    #     (genre + division) via _pick_event_candidate.
    # NB : la source de verite reste les FK stockees ; ce fallback ne s'applique
    # qu'aux bouts sans fighterX_id (relink via database/relink_event_fighters.py).
    unlinked = []   # (fdata, bout_wc, bout_gender, norm_key)
    for sec_bouts in sections.values():
        for bout in sec_bouts:
            bwc = bout.get("weight_class") or ""
            # genre du bout : marqueur "women" dans la division, sinon genre d'un
            # coin deja lie (les bouts MMA sont same-gender).
            bgender = "F" if _re.search(r"women", bwc, _re.I) else None
            if not bgender:
                for side in ("fighter1", "fighter2"):
                    if bout[side].get("gender"):
                        bgender = bout[side]["gender"]
                        break
            for side in ("fighter1", "fighter2"):
                fdata = bout[side]
                nm = fdata.get("name")
                if not fdata.get("id") and nm:
                    unlinked.append((fdata, bwc, bgender, _norm_fighter_name(nm)))

    if unlinked:
        cols = ("id, name, gender, weight_class_current, "
                "current_league, total_fights, data_quality_score")
        cands_by_norm: dict[str, list] = {}

        def _add_rows(rows):
            for r in rows:
                lst = cands_by_norm.setdefault(_norm_fighter_name(r.get("name")), [])
                if not any(c["id"] == r["id"] for c in lst):
                    lst.append(r)

        # A. match exact en minuscules — toujours dispo (couvre l'ASCII).
        raw_lowers = list({u[0]["name"].lower() for u in unlinked})
        if raw_lowers:
            ph = ",".join(["%s"] * len(raw_lowers))
            _add_rows(query(f"SELECT {cols} FROM fighters WHERE LOWER(name) IN ({ph})",
                            tuple(raw_lowers)))

        # B. match tolerant accents/ponctuation — best-effort (extension unaccent).
        # Si unaccent absent, on ignore : le backfill relink_event_fighters.py couvre.
        norm_keys = list({u[3] for u in unlinked if u[3]})
        if norm_keys:
            try:
                _add_rows(query(
                    f"SELECT {cols} FROM fighters "
                    f"WHERE regexp_replace(unaccent(lower(name)), '[^a-z0-9]', '', 'g') "
                    f"= ANY(%s)",
                    (norm_keys,),
                ))
            except Exception:
                pass

        for fdata, bwc, bgender, nkey in unlinked:
            pick = _pick_event_candidate(cands_by_norm.get(nkey), bwc, bgender)
            if pick:
                fdata["id"] = pick["id"]

    ev["card_sections"] = [
        {"name": sec, "bouts": sorted(bouts, key=lambda b: (0 if b["is_title_fight"] else 1, b["bout_order"]))}
        for sec, bouts in sections.items()
    ]
    ev.pop("awards", None)
    ev["awards"] = query_one("SELECT awards FROM events WHERE id=%s", (event_id,))
    if ev["awards"]:
        raw = ev["awards"].get("awards")
        ev["awards"] = raw if isinstance(raw, list) else []

    return jsonify(ev)


@app.get("/api/events/slug/<slug>")
def event_by_slug(slug: str):
    ev = query_one("SELECT id FROM events WHERE slug = %s", (slug,))
    if not ev:
        return jsonify({"error": "Event introuvable"}), 404
    return event_detail(ev["id"])


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found", "detail": str(e.description) if hasattr(e, "description") else "404"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "server error", "detail": str(e)}), 500


# ---- Boot ------------------------------------------------------------------

def main():
    port = int(os.getenv("PORT", "5000"))
    print(f"\n  MM.AI demo - http://localhost:{port}")
    print(f"  Source : {'Supabase' if USE_SUPABASE else 'PostgreSQL local'}\n")
    try:
        query("SELECT 1;")
        print("  [OK] connexion BDD")
    except Exception as e:
        print(f"  [ERREUR] BDD : {e}")
        sys.exit(1)
    # En prod (Render) l'host doit etre 0.0.0.0 pour etre accessible de l'exterieur.
    # En local on reste sur 127.0.0.1 par defaut (sauf si PORT est defini = prod).
    is_prod = os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PRODUCTION")
    host = "0.0.0.0" if is_prod else "127.0.0.1"
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
