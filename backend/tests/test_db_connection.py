"""
Test rapide de la connexion BDD.

Usage :
    cd backend
    python -m tests.test_db_connection

Pas un vrai test pytest (pas d'assertions strictes) — c'est un diagnostic
qui imprime ce qui marche et ce qui ne marche pas.
"""

import sys
from pathlib import Path

# Forcer UTF-8 sur stdout pour les emojis et accents (Windows cp1252)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Ajouter database/ au path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'database'))


def main():
    print("=" * 60)
    print("  MM.AI - DIAGNOSTIC CONNEXION BDD")
    print("=" * 60)

    # 1) .env présent ?
    env_path = ROOT / '.env'
    print(f"\n[1] Fichier .env : {env_path}")
    if env_path.exists():
        print("    [OK] trouvé")
    else:
        print("    [KO] MANQUANT — copie .env.example en .env et remplis le mot de passe")
        return 1

    # 2) Import psycopg2 + dotenv ?
    print("\n[2] Modules Python :")
    try:
        import psycopg2  # noqa
        print("    [OK] psycopg2 installé")
    except ImportError:
        print("    [KO] psycopg2 MANQUANT — fais : pip install -r requirements.txt")
        return 1
    try:
        import dotenv  # noqa
        print("    [OK] python-dotenv installé")
    except ImportError:
        print("    [KO] python-dotenv MANQUANT — fais : pip install -r requirements.txt")
        return 1

    # 3) Connexion réelle ?
    print("\n[3] Connexion à PostgreSQL :")
    import db_connection as db
    print(f"    Host  : {db.DB_CONFIG['host']}")
    print(f"    Port  : {db.DB_CONFIG['port']}")
    print(f"    DB    : {db.DB_CONFIG['dbname']}")
    print(f"    User  : {db.DB_CONFIG['user']}")
    print(f"    Pass  : {'*' * len(db.DB_CONFIG['password']) if db.DB_CONFIG['password'] else '(vide!)'}")

    conn = db.get_connection()
    if conn is None:
        print("    [KO] Connexion échouée")
        print("    ->Vérifie que PostgreSQL tourne (services Windows)")
        print("    ->Vérifie le mot de passe dans .env")
        return 1
    conn.close()
    print("    [OK] Connexion OK !")

    # 4) Tables présentes ?
    print("\n[4] Tables :")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    expected = ['elo_history', 'external_ratings', 'fighters', 'fights',
                'predictions', 'skills_profile', 'statistics', 'users']
    for t in expected:
        flag = "[OK]" if t in tables else "[KO]"
        print(f"    {flag} {t}")
    cur.close()
    conn.close()

    # 5) Compte fighters
    print("\n[5] Données :")
    n = db.get_fighter_count()
    print(f"    {n} fighter(s) actif(s) en BDD")

    # 6) Test data_loader (le pont)
    print("\n[6] Test du data_loader :")
    sys.path.insert(0, str(ROOT / 'backend'))
    from src.datasource.data_loader import get_fighter_by_name, data_source
    print(f"    Source active : {data_source()}")
    f = get_fighter_by_name('Jon Jones')
    if f:
        print(f"    [OK] Jon Jones chargé : Elo={f['base_elo']}, "
              f"Record={f['record_wins']}-{f['record_losses']}")
    else:
        print("    [KO] Jon Jones introuvable")

    print("\n" + "=" * 60)
    print("  [OK] DIAGNOSTIC TERMINE")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
