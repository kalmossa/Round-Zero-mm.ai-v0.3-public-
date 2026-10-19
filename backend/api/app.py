"""
Point d'entree FastAPI pour MM.AI.

LANCEMENT
Depuis le dossier `backend/` :
    uvicorn api.app:app --reload

Puis ouvrir :
    http://localhost:8000/docs       (Swagger UI interactif)
    http://localhost:8000/redoc      (doc alternative)
    http://localhost:8000/health     (sanity check)

ARCHITECTURE
Cette couche HTTP ne contient AUCUNE logique metier. Elle se contente de :
  1. Recevoir une requete HTTP (avec validation Pydantic).
  2. Appeler data_loader (le pont BDD<->ML).
  3. Renvoyer la reponse en JSON (serialisation Pydantic).

Les algos ML (elo_dynamic, matchup_predictor, scouter) sont appeles depuis
les routers, jamais directement depuis app.py.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import fighters, predict
from src.datasource.data_loader import data_source, is_db_connected

app = FastAPI(
    title="MM.AI API",
    description=(
        "API REST pour le système de prédiction MMA (TFE Elias Lallouet). "
        "Expose les fighters, l'historique des combats, et les prédictions ML."
    ),
    version="0.1.0",
    contact={"name": "Elias Lallouet"},
)

# CORS
# Necessaire pour qu'un frontend React (servi sur localhost:3000 ou :5173)
# puisse appeler cette API sans etre bloque par la same-origin policy du
# navigateur. En prod il faudra restreindre allow_origins au domaine reel.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js / Create React App
        "http://localhost:5173",   # Vite (le defaut React+Vite)
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# routers
app.include_router(fighters.router)
app.include_router(predict.router)


# endpoints racine

@app.get("/", tags=["meta"], summary="Page d'accueil")
def root():
    """Petit message d'accueil + lien vers la doc."""
    return {
        "name": "MM.AI API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["meta"], summary="Sanity check du service")
def health():
    """
    Retourne l'etat de sante du service :
      - status: 'ok' si l'API repond
      - db_connected: True si la BDD Supabase est joignable
      - data_source: 'database' ou 'sample' (mode fallback offline)

    A utiliser pour les checks d'uptime et le debug rapide.
    """
    return {
        "status": "ok",
        "db_connected": is_db_connected(),
        "data_source": data_source(),
    }
