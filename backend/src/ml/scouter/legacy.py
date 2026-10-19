"""
FighterScouter - l'analyse complete d'un combattant.
utilise tout ce que le SkillsProfile sait faire.
"""

from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from ..elo import DynamicEloCalculator          # ml.elo (package voisin)
from ..skills_calculator import SkillsCalculator  # ml.skills_calculator


class FighterScouter:
    """le "Scouter" : l'analyse complete d'un combattant."""
    
    # Classification par tiers
    TIER_S = "🏆 S-Tier (Elite)"
    TIER_A = "⭐ A-Tier (Top Contender)"
    TIER_B = "💪 B-Tier (Gatekeeper)"
    TIER_C = "✓ C-Tier (Développement)"
    TIER_D = "⚠️ D-Tier (Difficultés)"
    
    def __init__(self):
        self.elo_calc = DynamicEloCalculator()
        self.skills_calc = SkillsCalculator()
    
    def analyze_fighter(
        self, 
        fighter_data: Dict, 
        fight_history: List[Dict],
        detailed: bool = True
    ) -> Dict:
        """
        l'analyse complete d'un combattant.

        params :
            fighter_data  : les donnees du combattant
            fight_history : l'historique des combats
            detailed      : si True, analyse + poussee

        renvoie un dict avec toute l'analyse.
        """
        base_elo = fighter_data.get('base_elo', 1500)
        age = fighter_data.get('age', 30)
        recent_fights = fight_history[-5:]
        opponent_elos = [f.get('opponent_elo', 1500) for f in recent_fights]
        
        # 1. Elo Dynamique
        dynamic_elo = self.elo_calc.calculate_dynamic_elo(
            fighter_data['id'], base_elo, age, recent_fights, opponent_elos
        )
        
        # 2. Skills complets
        skills = self.skills_calc.calculate_all_skills(fighter_data['stats'])
        
        # 3. Power Level (score fun DBZ-style mais plus précis)
        power_level = self._calculate_power_level(dynamic_elo, skills)
        
        # 4. Tier classification
        tier = self._classify_tier(dynamic_elo, skills.overall)
        
        # 5. Analyse contextuelle
        analysis = self._generate_analysis(
            fighter_data, dynamic_elo, skills, recent_fights
        )
        
        # 6. Prédiction trajectoire
        trajectory = self._predict_career_trajectory(
            age, recent_fights, dynamic_elo, base_elo
        )
        
        # 7. Matchup tendances
        matchup_profile = self._generate_matchup_profile(skills)
        
        result = {
            'scouter_score': dynamic_elo,
            'power_level': power_level,
            'tier': tier,
            'skills': skills.to_dict(),
            'analysis': analysis,
            'trajectory': trajectory,
            'matchup_profile': matchup_profile,
            'metadata': {
                'age': age,
                'record': fighter_data.get('record', '0-0-0'),
                'base_elo': base_elo,
                'weight_class': fighter_data.get('weight_class', 'N/A')
            }
        }
        
        # Analyse détaillée supplémentaire
        if detailed:
            result['detailed_analysis'] = {
                'comparison_to_ufc': skills.compare_to_ufc_average(),
                'style_archetype': skills.get_style_archetype(),
                'tactical_recommendations': skills.get_tactical_recommendations(),
                'elite_skills': skills.get_elite_skills(),
                'weak_skills': skills.get_weak_skills(),
                'offensive_rating': skills.offensive_rating,
                'defensive_rating': skills.defensive_rating,
                'finish_potential': skills.finish_potential,
                'consistency_score': skills.consistency_score
            }
        
        return result
    
    def _calculate_power_level(self, elo: float, skills) -> int:
        """
        Calcule le Power Level (score DBZ amélioré)
        
        Formule : Elo×4 + Overall×15 + Bonus élites
        """
        base = elo * 4 + skills.overall * 15
        
        # Bonus pour skills élites
        elite_count = len(skills.get_elite_skills())
        elite_bonus = elite_count * 100
        
        # Bonus pour consistance
        if skills.consistency_score > 80:
            consistency_bonus = 150
        elif skills.consistency_score > 70:
            consistency_bonus = 75
        else:
            consistency_bonus = 0
        
        total = int(base + elite_bonus + consistency_bonus)
        return total
    
    def _classify_tier(self, elo: float, overall: float) -> str:
        """
        Classifie le combattant par tiers
        
        Basé sur Elo + Overall skill
        """
        combined_score = (elo - 1500) + (overall - 50)
        
        if combined_score > 350 or elo > 1800:
            return self.TIER_S
        elif combined_score > 200 or elo > 1700:
            return self.TIER_A
        elif combined_score > 50 or elo > 1600:
            return self.TIER_B
        elif combined_score > -100:
            return self.TIER_C
        else:
            return self.TIER_D
    
    def _generate_analysis(
        self, 
        fighter: Dict, 
        elo: float, 
        skills, 
        recent: List[Dict]
    ) -> Dict:
        """Génère analyse contextuelle complète"""
        
        # 1. Tendance de forme
        trend = self._analyze_trend(recent)
        
        # 2. Style dominant (utilise nouvelle méthode)
        style = skills.get_style_archetype()
        
        # 3. Phase de carrière
        age = fighter.get('age', 30)
        phase = self._determine_career_phase(age, recent, elo)
        
        # 4. Momentum
        momentum = self._calculate_momentum(recent, elo, fighter.get('base_elo', 1500))
        
        # 5. le niveau d'experience
        total_fights = fighter.get('stats', {}).get('total_fights', 0)
        experience = self._classify_experience(total_fights)
        
        return {
            'trend': trend,
            'style': style,
            'phase': phase,
            'momentum': momentum,
            'experience': experience,
            'strengths': skills.get_elite_skills() or ['Équilibré'],
            'weaknesses': skills.get_weak_skills() or ['Aucune majeure'],
            'signature_move': self._identify_signature_move(fighter['stats'], skills)
        }
    
    def _analyze_trend(self, recent: List[Dict]) -> str:
        """Analyse la tendance de forme récente"""
        if len(recent) < 2:
            return "❓ Données insuffisantes"
        
        results = [f.get('result', 'L') for f in recent[:5]]
        wins = results.count('W')
        losses = results.count('L')
        
        # Analyse des 3 derniers
        last_3 = results[:3]
        
        if all(r == 'W' for r in last_3):
            return "🔥🔥 Sur une lancée (3 victoires)"
        elif all(r == 'L' for r in last_3):
            return "❄️❄️ En crise (3 défaites)"
        elif wins >= 4:
            return "🔥 Très en forme (4+ victoires sur 5)"
        elif losses >= 4:
            return "❄️ Difficultés majeures (4+ défaites sur 5)"
        elif wins > losses:
            return "↗️ En progression"
        elif losses > wins:
            return "↘️ En déclin"
        else:
            return "➡️ Forme mitigée"
    
    def _determine_career_phase(
        self, 
        age: int, 
        recent: List[Dict], 
        current_elo: float
    ) -> str:
        """Détermine la phase de carrière avec plus de précision"""
        
        # Jeune prospect
        if age < 25:
            return "🌱 Jeune Prospect (En développement)"
        
        # l'etoile montante
        elif 25 <= age < 28:
            if current_elo > 1650:
                return "🚀 Rising Star (Ascension rapide)"
            else:
                return "📈 En progression"
        
        # le prime (le pic de carriere)
        elif 28 <= age <= 32:
            if current_elo > 1750:
                return "⭐💎 Dans son PRIME (Elite)"
            elif current_elo > 1650:
                return "⭐ Dans son prime"
            else:
                return "⭐ Peak physique (sous-performant)"
        
        # Vétéran expérimenté
        elif 33 <= age <= 36:
            wins = len([f for f in recent if f.get('result') == 'W'])
            if wins >= 3 and current_elo > 1700:
                return "🦁 Vétéran Elite (toujours dangereux)"
            elif wins >= 2:
                return "🦁 Vétéran expérimenté"
            else:
                return "⏳ Vétéran en déclin"
        
        # Fin de carrière
        else:
            if current_elo > 1700:
                return "🏛️ Légende vivante (exception)"
            else:
                return "🍂 Fin de carrière probable"
    
    def _calculate_momentum(
        self, 
        recent: List[Dict], 
        current_elo: float, 
        base_elo: float
    ) -> str:
        """Calcule le momentum (élan)"""
        
        if not recent:
            return "Neutral"
        
        # Différence Elo actuel vs base
        elo_diff = current_elo - base_elo
        
        # Résultats récents
        wins = len([f for f in recent[:3] if f.get('result') == 'W'])
        
        if elo_diff > 100 and wins >= 2:
            return "🚀🚀 MOMENTUM ÉNORME"
        elif elo_diff > 50 and wins >= 2:
            return "🚀 Fort momentum"
        elif elo_diff > 0:
            return "↗️ Momentum positif"
        elif elo_diff > -50:
            return "→ Stable"
        elif elo_diff > -100:
            return "↘️ Momentum négatif"
        else:
            return "📉 Chute libre"
    
    def _classify_experience(self, total_fights: int) -> str:
        """Classifie le niveau d'expérience"""
        if total_fights < 5:
            return "🆕 Rookie (< 5 combats)"
        elif total_fights < 10:
            return "📚 En apprentissage (5-10 combats)"
        elif total_fights < 20:
            return "✓ Expérimenté (10-20 combats)"
        elif total_fights < 30:
            return "🎓 Vétéran (20-30 combats)"
        else:
            return "🏛️ Légende (30+ combats)"
    
    def _identify_signature_move(self, stats: Dict, skills) -> str:
        """Identifie le coup signature du combattant"""
        
        # le cogneur (gros pourcentage de KO)
        ko_pct = stats.get('ko_percentage', 0)
        if ko_pct > 40:
            return "💥 Heavy Hands (Power Striker)"
        
        # le specialiste de la soumission
        sub_avg = stats.get('sub_avg', 0)
        if sub_avg > 1.0:
            return "🎯 Submission Specialist"
        
        # le lutteur (beaucoup de takedowns)
        td_avg = stats.get('td_avg', 0)
        if td_avg > 3.5:
            return "🤼 Wrestling Domination"
        
        # le gros volume de frappe
        sig_str = stats.get('sig_str_per_min', 0)
        if sig_str > 6.0:
            return "🌪️ High Volume Striking"
        
        # la machine a cardio
        if skills.cardio > 80:
            return "🏃 Cardio Pressure"
        
        # le frappeur technique (precis)
        strike_acc = stats.get('striking_accuracy', 0)
        if strike_acc > 55:
            return "🎯 Technical Precision"
        
        return "⚖️ Well-Rounded Game"
    
    def _predict_career_trajectory(
        self,
        age: int,
        recent: List[Dict],
        current_elo: float,
        base_elo: float
    ) -> Dict:
        """Prédit la trajectoire de carrière"""
        
        # Calcul du momentum
        if recent:
            wins = len([f for f in recent[:5] if f.get('result') == 'W'])
            win_rate = wins / len(recent[:5])
        else:
            win_rate = 0.5
        
        elo_trend = current_elo - base_elo
        
        # Prédiction future
        if age < 27:
            if win_rate > 0.6 and elo_trend > 0:
                prediction = "📈 Trajectoire ascendante - Futur champion potentiel"
                years_left = "8-12 ans de carrière"
            else:
                prediction = "→ En développement - Potentiel à confirmer"
                years_left = "10+ ans de carrière"
        
        elif 27 <= age <= 32:
            if current_elo > 1750:
                prediction = "⭐ Au sommet - Fenêtre de titre ouverte"
                years_left = "3-6 ans au top niveau"
            elif win_rate > 0.5:
                prediction = "💪 Stable dans le top 15"
                years_left = "4-7 ans de carrière"
            else:
                prediction = "⚠️ Lutte pour rester pertinent"
                years_left = "2-4 ans probables"
        
        elif 33 <= age <= 36:
            if current_elo > 1700 and win_rate > 0.6:
                prediction = "🦁 Vétéran encore dangereux"
                years_left = "2-4 ans possibles"
            else:
                prediction = "⏳ Fin de prime - Considérer retraite"
                years_left = "1-3 ans max"
        
        else:
            prediction = "🍂 Carrière en phase finale"
            years_left = "< 2 ans recommandés"
        
        return {
            'prediction': prediction,
            'years_left': years_left,
            'peak_reached': age >= 28 and age <= 33,
            'trending': 'up' if elo_trend > 50 else 'down' if elo_trend < -50 else 'stable'
        }
    
    def _generate_matchup_profile(self, skills) -> Dict:
        """Génère un profil de matchup (favorables/défavorables)"""
        
        favorable = []
        unfavorable = []
        
        # le striker face aux autres styles
        if skills.striking > 70:
            favorable.append("Wrestlers sans striking (keep it standing)")
            if skills.grappling < 50:
                unfavorable.append("Wrestlers élites (TD défense faible)")
        
        # le lutteur face aux autres styles
        if skills.grappling > 70:
            favorable.append("Strikers purs (TD faciles)")
            if skills.striking < 50:
                unfavorable.append("Strikers avec TD defense > 80%")
        
        # le BJJ face aux autres styles
        if skills.ground_game > 75:
            favorable.append("Wrestlers (soumission depuis le dos)")
            unfavorable.append("Strikers avec anti-wrestling")
        
        # l'avantage cardio
        if skills.cardio > 80:
            favorable.append("Fighters avec cardio < 60 (pression)")
        
        # le menton fragile
        if skills.chin < 50:
            unfavorable.append("Power strikers (chin fragile)")
        
        if not favorable:
            favorable = ["Style équilibré - s'adapte"]
        if not unfavorable:
            unfavorable = ["Pas de faiblesse majeure identifiée"]
        
        return {
            'favorable_matchups': favorable,
            'unfavorable_matchups': unfavorable
        }
    
    def generate_fight_report(
        self,
        fighter_data: Dict,
        fight_history: List[Dict]
    ) -> str:
        """Génère un rapport textuel complet"""
        
        analysis = self.analyze_fighter(fighter_data, fight_history, detailed=True)
        
        report = f"""
╔╗
║  RAPPORT D'ANALYSE - {fighter_data['name'].upper():<42}  ║
╚╝

📊 SCORE SCOUTER : {analysis['scouter_score']:.1f}
💪 POWER LEVEL   : {analysis['power_level']}
🏆 TIER          : {analysis['tier']}



📈 ANALYSE CONTEXTUELLE

• Tendance    : {analysis['analysis']['trend']}
• Style       : {analysis['analysis']['style']}
• Phase       : {analysis['analysis']['phase']}
• Momentum    : {analysis['analysis']['momentum']}
• Expérience  : {analysis['analysis']['experience']}
• Signature   : {analysis['analysis']['signature_move']}



🎯 TRAJECTOIRE DE CARRIÈRE

{analysis['trajectory']['prediction']}
⏱️  Temps restant estimé : {analysis['trajectory']['years_left']}



⚔️ PROFIL DE MATCHUP

✅ Matchups Favorables :
"""
        
        for m in analysis['matchup_profile']['favorable_matchups']:
            report += f"   • {m}\n"
        
        report += "\n❌ Matchups Défavorables :\n"
        for m in analysis['matchup_profile']['unfavorable_matchups']:
            report += f"   • {m}\n"
        
        report += f"""


💡 RECOMMANDATIONS TACTIQUES

"""
        for rec in analysis['detailed_analysis']['tactical_recommendations']:
            report += f"  {rec}\n"
        
        report += """

"""
        
        return report

