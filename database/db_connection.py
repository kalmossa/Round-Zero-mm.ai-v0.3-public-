#!/usr/bin/env python3
"""
mm.ai - la connexion + les helpers pour PostgreSQL/Supabase
Auteur: Elias Lallouet
Date: 2026-03-25

quelques fonctions pour taper dans la bdd
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Charger le .env depuis la racine du projet (peu importe d'où on lance le script)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

# la config (a verifier)
# en local (pgAdmin4)
LOCAL_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'mmai_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432'))
}

# supabase (en prod)
SUPABASE_CONFIG = {
    'dbname': os.getenv('SUPABASE_DB', 'postgres'),
    'user': os.getenv('SUPABASE_USER', 'postgres'),
    'password': os.getenv('SUPABASE_PASSWORD', ''),
    'host': os.getenv('SUPABASE_HOST', ''),
    'port': int(os.getenv('SUPABASE_PORT', '5432')),
}

# Choisir la config (change selon l'environnement)
USE_SUPABASE = os.getenv('USE_SUPABASE', 'False').lower() == 'true'
DB_CONFIG = SUPABASE_CONFIG if USE_SUPABASE else LOCAL_CONFIG


# la connexion
def get_connection():
    """Retourne une connexion à la BDD"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion: {e}")
        return None


def get_cursor(conn, dict_cursor=True):
    """Retourne un curseur (optionnellement en mode dict)"""
    if dict_cursor:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()


# les fonctions CRUD pour les fighters
def get_fighter_by_id(fighter_id):
    """Récupère un fighter par son ID"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM fighters WHERE id = %s", (fighter_id,))
        fighter = cur.fetchone()
        cur.close()
        conn.close()
        return dict(fighter) if fighter else None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None


def get_fighter_by_name(name):
    """Récupère un fighter par son nom"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT * FROM fighters WHERE name ILIKE %s",
            (f"%{name}%",)
        )
        fighter = cur.fetchone()
        cur.close()
        conn.close()
        return dict(fighter) if fighter else None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None


def get_all_fighters(
    weight_class=None,
    gender=None,
    current_league=None,
    name_search=None,
    limit=100,
    offset=0,
    order_by="base_elo DESC NULLS LAST",
):
    """
    recupere les fighters avec des filtres optionnels + la pagination.

    params :
        weight_class:   filtre exact sur weight_class_current (ex: 'Heavyweight')
        gender:         'M' ou 'F'
        current_league: filtre exact sur current_league (ex: 'UFC', 'PFL', 'Bellator')
        name_search:    recherche partielle insensible a la casse (ILIKE %q%)
        limit:          nombre max de resultats (defaut 100)
        offset:         decalage pour la pagination (defaut 0)
        order_by:       la clause ORDER BY (defaut 'base_elo DESC NULLS LAST').
                        le NULLS LAST evite que les fighters sans base_elo
                        remontent en premier dans le ranking.

    renvoie une list[dict] : les rows des fighters.
    """
    conn = get_connection()
    if not conn:
        return []

    try:
        cur = get_cursor(conn)

        query = "SELECT * FROM fighters WHERE 1=1"
        params = []

        if weight_class:
            query += " AND weight_class_current = %s"
            params.append(weight_class)

        if gender:
            query += " AND gender = %s"
            params.append(gender)

        if current_league:
            query += " AND current_league = %s"
            params.append(current_league)

        if name_search:
            query += " AND name ILIKE %s"
            params.append(f"%{name_search}%")

        # order BY est inline (safe : pas d'input utilisateur via API) ; limit/offset parametres.
        query += f" ORDER BY {order_by} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        fighters = cur.fetchall()
        cur.close()
        conn.close()

        return [dict(f) for f in fighters]

    except Exception as e:
        print(f"❌ Erreur: {e}")
        return []


def count_fighters(
    weight_class=None,
    gender=None,
    current_league=None,
    name_search=None,
):
    """
    Compte le nombre total de fighters matchant les filtres (sans LIMIT/OFFSET).
    Necessaire pour la pagination cote API (afficher 'page X / Y').
    """
    conn = get_connection()
    if not conn:
        return 0

    try:
        cur = get_cursor(conn)
        query = "SELECT COUNT(*) AS n FROM fighters WHERE 1=1"
        params = []

        if weight_class:
            query += " AND weight_class_current = %s"
            params.append(weight_class)
        if gender:
            query += " AND gender = %s"
            params.append(gender)
        if current_league:
            query += " AND current_league = %s"
            params.append(current_league)
        if name_search:
            query += " AND name ILIKE %s"
            params.append(f"%{name_search}%")

        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row["n"]) if row else 0
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 0


def create_fighter(fighter_data):
    """
    crée un nouveau fighter en bdd.
    params : fighter_data = dict avec les donnees du fighter.
    renvoie l'id du fighter créé, ou None si ca foire.
    """
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        
        # Colonnes essentielles
        cur.execute("""
            INSERT INTO fighters (
                name, gender, date_of_birth, nationality, country_code,
                weight_class_current, record_total_wins, record_total_losses,
                record_total_draws, base_elo, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            fighter_data['name'],
            fighter_data.get('gender', 'M'),
            fighter_data.get('date_of_birth'),
            fighter_data.get('nationality'),
            fighter_data.get('country_code'),
            fighter_data['weight_class_current'],
            fighter_data.get('record_total_wins', 0),
            fighter_data.get('record_total_losses', 0),
            fighter_data.get('record_total_draws', 0),
            fighter_data.get('base_elo', 1500.00),
            fighter_data.get('is_active', True)
        ))
        
        fighter_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Fighter créé avec ID: {fighter_id}")
        return fighter_id
        
    except Exception as e:
        print(f"❌ Erreur création: {e}")
        conn.rollback()
        return None


def update_fighter(fighter_id, updates):
    """
    met a jour un fighter.
    params : fighter_id = l'id, updates = dict des champs a changer.
    """
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Construire la requête UPDATE dynamiquement
        set_clause = ", ".join([f"{key} = %s" for key in updates.keys()])
        values = list(updates.values()) + [fighter_id]
        
        query = f"UPDATE fighters SET {set_clause} WHERE id = %s"
        cur.execute(query, values)
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Fighter {fighter_id} mis à jour")
        return True
        
    except Exception as e:
        print(f"❌ Erreur mise à jour: {e}")
        conn.rollback()
        return False


def delete_fighter(fighter_id):
    """Supprime un fighter"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM fighters WHERE id = %s", (fighter_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Fighter {fighter_id} supprimé")
        return True
        
    except Exception as e:
        print(f"❌ Erreur suppression: {e}")
        conn.rollback()
        return False


# les fonctions pour les ratings
def update_scouter_rating(fighter_id, scouter_rating):
    """Met à jour le scouter rating d'un fighter"""
    return update_fighter(fighter_id, {'scouter_rating': scouter_rating})


def update_fightmatrix_rating(fighter_id, points):
    """Met a jour fightmatrix_rating_points directement sur fighters"""
    return update_fighter(fighter_id, {'fightmatrix_rating_points': points})


# les fonctions de stats
def get_fighter_count():
    """Retourne le nombre total de fighters"""
    conn = get_connection()
    if not conn:
        return 0
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM fighters WHERE is_active = TRUE")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except:
        return 0


def get_top_fighters_by_elo(limit=10, weight_class=None):
    """Retourne les meilleurs fighters par Elo"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        cur = get_cursor(conn)
        
        query = """
            SELECT name, weight_class_current, base_elo, scouter_rating,
                   record_total_wins || '-' || record_total_losses AS record
            FROM fighters
            WHERE is_active = TRUE
        """

        params = []
        if weight_class:
            query += " AND weight_class_current = %s"
            params.append(weight_class)
        
        query += " ORDER BY base_elo DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        fighters = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(f) for f in fighters]
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return []


# des exemples d'utilisation (lance le fichier direct pour tester la connexion)
if __name__ == "__main__":
    print("=" * 80)
    print("MM.AI - TEST CONNEXION BDD")
    print("=" * 80)
    
    # Test connexion
    conn = get_connection()
    if conn:
        print("✅ Connexion réussie!")
        conn.close()
    else:
        print("❌ Échec connexion")
        exit(1)
    
    # Compter les fighters
    count = get_fighter_count()
    print(f"\n📊 Nombre de fighters actifs: {count}")
    
    # Top 5 fighters
    print("\n🏆 Top 5 Fighters (Elo):")
    top = get_top_fighters_by_elo(5)
    for i, f in enumerate(top, 1):
        print(f"   {i}. {f['name']} ({f['weight_class_current']}) - Elo: {f['base_elo']} - Record: {f['record']}")

    print("\n➕ Exemple création fighter (decommenter pour tester):")
    new_fighter = {
        'name': 'Test Fighter',
        'gender': 'M',
        'date_of_birth': '1990-01-01',
        'nationality': 'USA',
        'country_code': 'USA',
        'weight_class_current': 'Welterweight',
        'record_total_wins': 10,
        'record_total_losses': 2
    }
    
    # Décommenter pour tester :
    # fighter_id = create_fighter(new_fighter)
    # if fighter_id:
    #     print(f"   Fighter créé avec ID: {fighter_id}")
    #     delete_fighter(fighter_id)
    #     print(f"   Fighter supprimé (test)")
    
    print("\n" + "=" * 80)
    print("✅ TESTS TERMINÉS")
    print("=" * 80)
