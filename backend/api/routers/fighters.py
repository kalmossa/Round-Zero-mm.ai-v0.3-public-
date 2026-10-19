"""
Router /fighters
Endpoints HTTP qui exposent l'acces aux fighters.

Pattern utilise :
  - On NE touche PAS directement a la BDD ici. On passe par data_loader
    (le seul pont BDD<->code metier dans le projet).
  - HTTPException 404 si fighter introuvable.
  - La response_model = FighterOut force Pydantic a valider/serialiser
    le dict retourne par data_loader -> garantit que la doc Swagger est juste.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from src.datasource.data_loader import (
    get_fighter_by_id,
    list_fighters,
    search_fighters_by_name,
)
from api.schemas.fighter import FighterOut, FighterListResponse

router = APIRouter(prefix="/fighters", tags=["fighters"])


#  important - ordre des routes :
#  /search doit etre declare AVANT /{fighter_id}, sinon FastAPI matche
#  "search" comme un fighter_id et essaie de le caster en int -> 422.


@router.get(
    "",
    response_model=FighterListResponse,
    summary="Liste paginee de fighters (avec filtres)",
)
def list_endpoint(
    limit: int = Query(20, ge=1, le=100, description="Nombre max de resultats (1-100)"),
    offset: int = Query(0, ge=0, description="Decalage pour la pagination"),
    weight_class: Optional[str] = Query(
        None,
        description="Filtre exact sur la division actuelle (ex: 'Heavyweight', 'Lightweight')",
    ),
    current_league: Optional[str] = Query(
        None,
        description="Filtre exact sur la ligue (ex: 'UFC', 'PFL', 'Bellator', 'ONE')",
    ),
    gender: Optional[str] = Query(
        None,
        pattern="^[MF]$",
        description="'M' ou 'F'",
    ),
) -> dict:
    """
    Retourne une page de fighters triee par base_elo decroissant.

    **Exemples** :
      - `/fighters` : top 20 par Elo, toutes ligues confondues
      - `/fighters?current_league=UFC&limit=10` : top 10 UFC
      - `/fighters?weight_class=Heavyweight&gender=M` : heavyweights masculins
      - `/fighters?offset=20&limit=20` : page 2
    """
    return list_fighters(
        limit=limit,
        offset=offset,
        weight_class=weight_class,
        current_league=current_league,
        gender=gender,
    )


@router.get(
    "/search",
    response_model=list[FighterOut],
    summary="Rechercher des fighters par nom (partiel, insensible casse)",
)
def search_endpoint(
    q: str = Query(..., min_length=2, max_length=80, description="Nom partiel (>= 2 caracteres)"),
    limit: int = Query(10, ge=1, le=50, description="Nombre max de resultats"),
) -> list[dict]:
    """
    Recherche dans le champ `name`. ILIKE %q% en BDD.

    **Exemples** :
      - `/fighters/search?q=jones` : tous les fighters dont le nom contient 'jones'
      - `/fighters/search?q=da+silva&limit=5`
    """
    return search_fighters_by_name(q, limit=limit)


@router.get(
    "/{fighter_id}",
    response_model=FighterOut,
    summary="Recuperer un fighter par son ID",
    responses={
        404: {"description": "Fighter introuvable"},
    },
)
def read_fighter(
    fighter_id: int = Path(..., ge=1, description="ID du fighter en BDD"),
) -> dict:
    """
    Retourne toutes les infos d'un fighter (bio + records + base_elo + stats).

    Source : si la BDD Supabase est joignable, lit depuis PostgreSQL.
    Sinon, fallback sur le sample_data offline (mode demo).
    """
    fighter = get_fighter_by_id(fighter_id)
    if fighter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fighter id={fighter_id} introuvable",
        )
    return fighter
