"""
Pydantic schemas pour l'API fighters.

Un "schema" est un modele Pydantic qui :
  1. Valide la structure des donnees entrantes/sortantes (types, champs requis)
  2. Genere automatiquement la doc Swagger
  3. Serialise en JSON pour la reponse HTTP

FighterOut matche le dict retourne par data_loader.get_fighter_by_id().
Tous les champs sont optionnels (Optional) sauf id/name/weight_class car
le sample_data et la BDD peuvent avoir des trous.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class FighterOut(BaseModel):
    """Reponse de GET /fighters/{id} et GET /fighters/by-name/{name}."""

    id: int = Field(..., description="Identifiant unique du fighter en BDD")
    name: str = Field(..., description="Nom complet du fighter")
    nickname: Optional[str] = Field(None, description="Surnom (ex: 'Bones', 'Notorious')")
    date_of_birth: Optional[date] = Field(None, description="Date de naissance")
    nationality: Optional[str] = Field(None, description="Nationalite (ex: 'United States')")
    weight_class: str = Field(..., description="Division actuelle (ex: 'Heavyweight')")
    current_league: Optional[str] = Field(
        None,
        description=(
            "Ligue/promotion actuelle (UFC, PFL, ONE, KSW, RIZIN, Bellator, ...). "
            "NULL si fighter inactif (retraite) ou ligue non identifiable."
        ),
    )
    reach_cm: float = Field(0.0, description="Allonge en cm")
    height_cm: float = Field(0.0, description="Taille en cm")
    stance: Optional[str] = Field(None, description="Garde (Orthodox / Southpaw / Switch)")
    record_wins: int = Field(0, description="Victoires totales")
    record_losses: int = Field(0, description="Defaites totales")
    record_draws: int = Field(0, description="Nuls totaux")
    base_elo: float = Field(1500.0, description="Elo dynamique propriétaire (1000-2500)")
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Stats brutes (sig_str_per_min, td_avg, ko_percentage, etc.)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": 1,
                "name": "Jon Jones",
                "nickname": "Bones",
                "date_of_birth": "1987-07-19",
                "nationality": "United States",
                "weight_class": "Heavyweight",
                "current_league": "UFC",
                "reach_cm": 215.0,
                "height_cm": 193.0,
                "stance": "Orthodox",
                "record_wins": 27,
                "record_losses": 1,
                "record_draws": 0,
                "base_elo": 2150.0,
                "stats": {"sig_str_per_min": 4.3, "td_avg": 1.9},
            }
        }
    }


class FighterListResponse(BaseModel):
    """
    Reponse paginee de GET /fighters.

    Le client utilise total + limit + offset pour calculer le nombre de pages :
        n_pages = ceil(total / limit)
        current_page = offset / limit + 1
    """

    total: int = Field(..., description="Nombre total de fighters matchant les filtres (sans pagination)")
    limit: int = Field(..., description="Taille de page demandee")
    offset: int = Field(..., description="Decalage applique")
    results: list[FighterOut] = Field(default_factory=list, description="Fighters de la page courante")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total": 342,
                "limit": 20,
                "offset": 0,
                "results": [
                    {
                        "id": 1,
                        "name": "Jon Jones",
                        "weight_class": "Heavyweight",
                        "current_league": "UFC",
                        "base_elo": 2150.0,
                        "stats": {},
                    }
                ],
            }
        }
    }

