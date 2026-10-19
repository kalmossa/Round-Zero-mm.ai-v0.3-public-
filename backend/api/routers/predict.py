"""
Router /predict
Endpoint de prédiction de combat : POST /predict

Flow :
  1. Charge fighter1 et fighter2 depuis data_loader (BDD ou sample)
  2. Charge l'historique de combats des deux fighters
  3. Appelle MatchupPredictor.predict_fight()
  4. Reformate la réponse avec les noms (au lieu de "Fighter 1" / "Fighter 2")
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.datasource.data_loader import (
    get_fighter_by_id,
    get_fight_history,
)
from src.ml.matchup_predictor import MatchupPredictor
from api.schemas.predict import PredictRequest, PredictionOut, FighterSummary

router = APIRouter(prefix="/predict", tags=["predict"])

_predictor = MatchupPredictor()  # Instance partagée (stateless, pas de cache à purger)


@router.post(
    "",
    response_model=PredictionOut,
    summary="Prédire l'issue d'un combat",
    responses={
        404: {"description": "Un des deux fighters est introuvable"},
        400: {"description": "Les deux fighters doivent être différents"},
    },
)
def predict_fight(body: PredictRequest) -> dict:
    """
    Prédit le vainqueur d'un hypothétique combat entre deux fighters.

    **Formule** : 40% Elo dynamique + 35% skills + 25% contexte (forme récente, âge)

    **Exemple** :
    ```json
    { "fighter1_id": 1, "fighter2_id": 2 }
    ```

    Retourne :
    - `winner_name` : nom du vainqueur prédit
    - `fighter1_win_prob` / `fighter2_win_prob` : probabilités (somme = 1)
    - `confidence` : à quel point la prédiction est tranchée (0 = 50/50, 1 = certain)
    - `method` : probabilités KO/TKO, Submission, Decision
    - `key_factors` : facteurs explicatifs
    - `breakdown` : poids de chaque composante (elo, skills, context)
    """
    if body.fighter1_id == body.fighter2_id:
        raise HTTPException(
            status_code=400,
            detail="fighter1_id et fighter2_id doivent être différents",
        )

    # --- Chargement des fighters ---
    f1 = get_fighter_by_id(body.fighter1_id)
    if f1 is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fighter id={body.fighter1_id} introuvable",
        )
    f2 = get_fighter_by_id(body.fighter2_id)
    if f2 is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fighter id={body.fighter2_id} introuvable",
        )

    # --- Historique de combats ---
    h1 = get_fight_history(f1["id"]) or []
    h2 = get_fight_history(f2["id"]) or []

    # --- Prédiction ---
    result = _predictor.predict_fight(f1, f2, h1, h2)

    # --- Reformatage de la réponse (noms réels au lieu de "Fighter 1" / "Fighter 2") ---
    winner_name = f1["name"] if result["winner"] == "Fighter 1" else f2["name"]

    return {
        "fighter1": _to_summary(f1),
        "fighter2": _to_summary(f2),
        "winner_name": winner_name,
        "fighter1_win_prob": result["fighter1_win_prob"],
        "fighter2_win_prob": result["fighter2_win_prob"],
        "confidence": result["confidence"],
        "method": result["method"],
        "key_factors": _humanize_factors(result["key_factors"], f1["name"], f2["name"]),
        "breakdown": result["breakdown"],
        "fighter1_dynamic_elo": result["fighter1_elo"],
        "fighter2_dynamic_elo": result["fighter2_elo"],
        "fighter1_skills": result["fighter1_skills"],
        "fighter2_skills": result["fighter2_skills"],
    }


#  Helpers

def _to_summary(f: dict) -> dict:
    """Extrait les champs FighterSummary depuis un dict _row_to_fighter."""
    return {
        "id": f["id"],
        "name": f["name"],
        "weight_class": f.get("weight_class", "Unknown"),
        "base_elo": f.get("base_elo", 1500.0),
        "age": f.get("age", 28),
        "record_wins": f.get("record_wins", 0),
        "record_losses": f.get("record_losses", 0),
        "record_draws": f.get("record_draws", 0),
    }


def _humanize_factors(factors: list[str], name1: str, name2: str) -> list[str]:
    """
    Remplace "F1:" / "F2:" dans les key_factors par les vrais prénoms.

    Exemple : "✅ F1: Elo supérieur (+140)" → "✅ Jon Jones: Elo supérieur (+140)"
    """
    result = []
    for f in factors:
        f = f.replace("F1:", f"{name1}:").replace("F2:", f"{name2}:")
        result.append(f)
    return result
