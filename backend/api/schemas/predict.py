"""
Pydantic schemas pour POST /predict.

PredictRequest  → body de la requête (2 IDs de fighters)
PredictionOut   → réponse complète avec probabilités, méthode, facteurs clés
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Requête de prédiction : 2 fighters identifiés par leur ID."""

    fighter1_id: int = Field(..., ge=1, description="ID du premier fighter")
    fighter2_id: int = Field(..., ge=1, description="ID du second fighter")

    model_config = {
        "json_schema_extra": {
            "example": {
                "fighter1_id": 1,
                "fighter2_id": 2,
            }
        }
    }


class FighterSummary(BaseModel):
    """Résumé minimal d'un fighter dans la réponse de prédiction."""

    id: int
    name: str
    weight_class: str
    base_elo: float
    age: int
    record_wins: int
    record_losses: int
    record_draws: int


class PredictionOut(BaseModel):
    """Réponse complète de POST /predict."""

    fighter1: FighterSummary = Field(..., description="Infos du fighter 1")
    fighter2: FighterSummary = Field(..., description="Infos du fighter 2")

    winner_name: str = Field(..., description="Nom du vainqueur prédit")
    fighter1_win_prob: float = Field(..., description="Probabilité de victoire fighter 1 (0-1)")
    fighter2_win_prob: float = Field(..., description="Probabilité de victoire fighter 2 (0-1)")
    confidence: float = Field(..., description="Indice de confiance de la prédiction (0-1)")

    method: dict[str, float] = Field(
        ...,
        description="Probabilités par méthode de victoire (KO/TKO, Submission, Decision)",
    )
    key_factors: list[str] = Field(
        default_factory=list,
        description="Facteurs clés qui expliquent la prédiction",
    )
    breakdown: dict[str, float] = Field(
        ...,
        description="Décomposition du score : elo, skills, context",
    )

    fighter1_dynamic_elo: float = Field(..., description="Elo dynamique calculé pour fighter 1")
    fighter2_dynamic_elo: float = Field(..., description="Elo dynamique calculé pour fighter 2")
    fighter1_skills: dict[str, Any] = Field(default_factory=dict, description="Profil de skills fighter 1")
    fighter2_skills: dict[str, Any] = Field(default_factory=dict, description="Profil de skills fighter 2")

    model_config = {
        "json_schema_extra": {
            "example": {
                "fighter1": {
                    "id": 1, "name": "Jon Jones", "weight_class": "Heavyweight",
                    "base_elo": 1820.0, "age": 37, "record_wins": 27,
                    "record_losses": 1, "record_draws": 0,
                },
                "fighter2": {
                    "id": 2, "name": "Ciryl Gane", "weight_class": "Heavyweight",
                    "base_elo": 1680.0, "age": 34, "record_wins": 11,
                    "record_losses": 2, "record_draws": 0,
                },
                "winner_name": "Jon Jones",
                "fighter1_win_prob": 0.6842,
                "fighter2_win_prob": 0.3158,
                "confidence": 0.3684,
                "method": {"KO/TKO": 0.31, "Submission": 0.22, "Decision": 0.47},
                "key_factors": [
                    "✅ F1: Elo supérieur (+140)",
                    "✅ F1: Grappling dominant (+28)",
                ],
                "breakdown": {"elo": 0.61, "skills": 0.71, "context": 0.56},
                "fighter1_dynamic_elo": 1843.0,
                "fighter2_dynamic_elo": 1703.0,
                "fighter1_skills": {"striking": 72.0, "grappling": 78.0},
                "fighter2_skills": {"striking": 68.0, "grappling": 50.0},
            }
        }
    }
