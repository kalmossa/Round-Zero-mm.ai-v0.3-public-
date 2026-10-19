# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
Prédicteur de Matchup — Elo (40%) + Skills (35%) + Contexte (25%)

############################################################################
##  (!)  PAS BRANCHE AU SITE - sandbox FastAPI uniquement  (!)            ##
############################################################################
Ce predictor tourne SEULEMENT dans la sandbox FastAPI (backend/api, port 8001,
la Swagger UI optionnelle). Le SITE en prod (Flask, api/app.py) NE s'en sert
PAS : il fait sa propre heuristique pondérée inline dans predict()/matchmaking().

Pourquoi pas branché :
  - il a besoin de stats détaillées (striking/grappling/cardio/chin via
    skills_calculator) qu'on n'a PAS pour tous les fighters ;
  - son Elo passe par DynamicEloCalculator qui est un STUB (il renvoie le
    base_elo tel quel, cf ml/elo/engine.py) -> pas le vrai moteur Elo.
Donc en l'état = une maquette / piste, pas le moteur de prédiction du site.

-> À L'ORAL : ne présente PAS ça comme ce qui prédit sur le site. Le vrai code
   de prédiction du site est dans api/app.py (score heuristique + logistique).
"""

import numpy as np
from typing import Dict, List
from .elo_dynamic import DynamicEloCalculator
from .skills_calculator import SkillsCalculator, SkillsProfile


class MatchupPredictor:
    """Prédit l'issue d'un combat"""
    
    # Coeffs d'avantage de style (calibrés à la main, pas appris) : qui mange qui.
    # Ex: un wrestler face à un striker -> son grappling compte ×1.3 et le striking
    # de l'autre ×0.8. Classique "le lutteur amène le boxeur au sol".
    STYLE_ADVANTAGES = {
        ('striker', 'wrestler'): {'striking': 1.2, 'grappling': 0.7},
        ('wrestler', 'striker'): {'grappling': 1.3, 'striking': 0.8},
        ('striker', 'bjj'): {'striking': 1.15, 'ground_game': 0.7},
        ('bjj', 'striker'): {'ground_game': 1.4, 'striking': 0.75},
        ('wrestler', 'bjj'): {'grappling': 1.15, 'ground_game': 0.9},
        ('bjj', 'wrestler'): {'ground_game': 1.3, 'grappling': 0.9}
    }
    
    def __init__(self):
        self.elo_calc = DynamicEloCalculator()
        self.skills_calc = SkillsCalculator()
    
    def predict_fight(
        self,
        f1_data: Dict,
        f2_data: Dict,
        f1_history: List[Dict],
        f2_history: List[Dict],
        context: Dict = None
    ) -> Dict:
        """Prédiction complète"""
        
        context = context or {}
        
        # 1. Elos Dynamiques
        f1_elo = self.elo_calc.calculate_dynamic_elo(
            f1_data['id'], f1_data['base_elo'], f1_data['age'],
            f1_history[-5:],
            [f.get('opponent_elo', 1500) for f in f1_history[-5:]]
        )
        f2_elo = self.elo_calc.calculate_dynamic_elo(
            f2_data['id'], f2_data['base_elo'], f2_data['age'],
            f2_history[-5:],
            [f.get('opponent_elo', 1500) for f in f2_history[-5:]]
        )
        
        # 2. Skills
        f1_skills = self.skills_calc.calculate_all_skills(f1_data['stats'])
        f2_skills = self.skills_calc.calculate_all_skills(f2_data['stats'])
        
        # 3. Probabilités
        elo_prob = self._elo_prob(f1_elo, f2_elo)
        skills_prob = self._skills_prob(f1_skills, f2_skills)
        context_prob = self._context_prob(f1_data, f2_data, f1_history, f2_history)
        
        # 4. Combinaison : 3 probas fusionnées avec des poids fixes.
        # l'Elo (le niveau) pèse le plus, puis les skills (le matchup technique),
        # puis le contexte (forme + âge). Poids posés à la main, pas optimisés.
        final_prob = 0.40 * elo_prob + 0.35 * skills_prob + 0.25 * context_prob
        
        # 5. Méthode de victoire
        method_pred = self._predict_method(f1_skills, f2_skills)
        
        # 6. Facteurs clés
        factors = self._key_factors(f1_elo, f2_elo, f1_skills, f2_skills, 
                                      f1_data, f2_data)
        
        # 7. Confiance
        confidence = abs(final_prob - 0.5) * 2
        
        return {
            'winner': 'Fighter 1' if final_prob >= 0.5 else 'Fighter 2',
            'fighter1_win_prob': round(final_prob, 4),
            'fighter2_win_prob': round(1 - final_prob, 4),
            'confidence': round(confidence, 3),
            'method': method_pred,
            'key_factors': factors,
            'breakdown': {
                'elo': round(elo_prob, 4),
                'skills': round(skills_prob, 4),
                'context': round(context_prob, 4)
            },
            'fighter1_elo': f1_elo,
            'fighter2_elo': f2_elo,
            'fighter1_skills': f1_skills.to_dict(),
            'fighter2_skills': f2_skills.to_dict()
        }
    
    def _elo_prob(self, elo1: float, elo2: float) -> float:
        return 1 / (1 + 10 ** ((elo2 - elo1) / 400))
    
    def _skills_prob(self, s1: SkillsProfile, s2: SkillsProfile) -> float:
        style1 = self._detect_style(s1)
        style2 = self._detect_style(s2)
        coeffs = self.STYLE_ADVANTAGES.get((style1, style2), {})
        
        total = 0
        for skill in ['striking', 'grappling', 'ground_game', 'cardio', 'chin']:
            coeff = coeffs.get(skill, 1.0)
            diff = (getattr(s1, skill) - getattr(s2, skill)) * coeff
            total += diff
        
        return self._sigmoid(total / 100)
    
    def _detect_style(self, skills: SkillsProfile) -> str:
        if skills.striking > max(skills.grappling, skills.ground_game) + 15:
            return 'striker'
        elif skills.grappling > max(skills.striking, skills.ground_game) + 15:
            return 'wrestler'
        elif skills.ground_game > max(skills.striking, skills.grappling) + 15:
            return 'bjj'
        return 'balanced'
    
    def _context_prob(self, f1, f2, h1, h2) -> float:
        base = 0.5
        adj = []
        
        # Forme
        f1_form = self._recent_form(h1[-5:])
        f2_form = self._recent_form(h2[-5:])
        adj.append((f1_form - f2_form) * 0.15)
        
        # Âge
        age_diff = f2['age'] - f1['age']
        if age_diff > 5:
            adj.append(0.05)
        elif age_diff < -5:
            adj.append(-0.05)
        
        return max(0.0, min(1.0, base + sum(adj)))
    
    def _recent_form(self, fights: List[Dict]) -> float:
        if not fights:
            return 0.0
        wins = sum(1 for f in fights if f.get('result') == 'W')
        return (wins / len(fights) - 0.5) * 2
    
    def _predict_method(self, s1, s2) -> Dict[str, float]:
        striking_adv = s1.striking - s2.striking
        ko_prob = max(0, min(1, striking_adv / 100 + (100 - s2.chin) / 200))
        
        ground_adv = s1.ground_game - s2.ground_game
        sub_prob = max(0, min(1, ground_adv / 150))
        
        dec_prob = 1 - ko_prob - sub_prob + (s1.cardio + s2.cardio) / 400
        
        total = ko_prob + sub_prob + dec_prob
        return {
            'KO/TKO': round(ko_prob / total, 3),
            'Submission': round(sub_prob / total, 3),
            'Decision': round(dec_prob / total, 3)
        }
    
    def _key_factors(self, elo1, elo2, s1, s2, f1, f2) -> List[str]:
        factors = []
        
        elo_diff = abs(elo1 - elo2)
        if elo_diff > 100:
            winner = "F1" if elo1 > elo2 else "F2"
            factors.append(f"✅ {winner}: Elo supérieur (+{int(elo_diff)})")
        
        for skill in ['striking', 'grappling', 'ground_game']:
            val1 = getattr(s1, skill)
            val2 = getattr(s2, skill)
            diff = val1 - val2
            if abs(diff) > 20:
                winner = "F1" if diff > 0 else "F2"
                skill_name = skill.replace('_', ' ').title()
                factors.append(f"✅ {winner}: {skill_name} dominant (+{abs(int(diff))})")
        
        age_diff = f2['age'] - f1['age']
        if abs(age_diff) > 7:
            younger = "F1" if age_diff > 0 else "F2"
            factors.append(f"✅ {younger}: Plus jeune ({abs(age_diff)} ans)")
        
        return factors[:5]
    
    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1 / (1 + np.exp(-x))
