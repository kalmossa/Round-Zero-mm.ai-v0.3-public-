# ============================================================================
# NOTE - MM.AI v0.3 (public showcase)
# This is the FIRST, simplified version of the prediction logic, published for
# curious people only. It is NOT the algorithm used in RoundZero, the final
# product (the real Elo / Scouter / prediction engine lives there, not here).
# ============================================================================
"""
mm.ai - le calcul des skills (compétences)
7 dimensions + comparaison à la moyenne UFC + conseils tactiques
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


# Moyennes UFC pour comparaison (basées sur stats réelles)
UFC_AVERAGES = {
    'striking': 50.0,
    'grappling': 50.0,
    'ground_game': 50.0,
    'cardio': 50.0,
    'chin': 55.0,  # Légèrement au-dessus (biais survivant)
    'fight_iq': 50.0,
    'physicality': 50.0
}

# Seuils pour classification
ELITE_THRESHOLD = 80.0
STRONG_THRESHOLD = 70.0
GOOD_THRESHOLD = 60.0
AVERAGE_THRESHOLD = 50.0
WEAK_THRESHOLD = 40.0


@dataclass
class SkillsProfile:
    """le profil de compétences d'un fighter (7 dimensions, 0-100)."""
    striking: float = 0.0
    grappling: float = 0.0
    ground_game: float = 0.0
    cardio: float = 0.0
    chin: float = 0.0
    fight_iq: float = 0.0
    physicality: float = 0.0
    
    @property
    def overall(self) -> float:
        """Score global pondéré"""
        weights = {
            'striking': 0.20, 'grappling': 0.15, 'ground_game': 0.15,
            'cardio': 0.15, 'chin': 0.10, 'fight_iq': 0.15, 'physicality': 0.10
        }
        total = sum(getattr(self, k) * v for k, v in weights.items())
        return round(total, 2)
    
    @property
    def offensive_rating(self) -> float:
        """Score offensif : striking + grappling + ground_game"""
        return round((self.striking * 0.4 + self.grappling * 0.3 + self.ground_game * 0.3), 2)
    
    @property
    def defensive_rating(self) -> float:
        """Score défensif : chin + fight_iq + cardio"""
        return round((self.chin * 0.4 + self.fight_iq * 0.3 + self.cardio * 0.3), 2)
    
    @property
    def finish_potential(self) -> float:
        """Potentiel de finish : striking + ground_game - cardio penalty"""
        finish = (self.striking + self.ground_game) / 2
        cardio_bonus = (self.cardio - 50) / 100  # Bonus/malus selon cardio
        return round(finish + cardio_bonus * 10, 2)
    
    @property
    def consistency_score(self) -> float:
        """Cohérence : variance faible = combattant complet"""
        skills_list = [self.striking, self.grappling, self.ground_game, 
                       self.cardio, self.chin, self.fight_iq, self.physicality]
        avg = sum(skills_list) / len(skills_list)
        variance = sum((s - avg) ** 2 for s in skills_list) / len(skills_list)
        # Score inversé : faible variance = haute consistance
        return round(max(0, 100 - variance / 2), 2)
    
    def get_elite_skills(self) -> List[str]:
        """Skills élites (80+)"""
        elite = []
        for skill in ['striking', 'grappling', 'ground_game', 'cardio', 'chin', 'fight_iq', 'physicality']:
            if getattr(self, skill) >= ELITE_THRESHOLD:
                elite.append(skill.replace('_', ' ').title())
        return elite
    
    def get_weak_skills(self) -> List[str]:
        """Skills faibles (< 40)"""
        weak = []
        for skill in ['striking', 'grappling', 'ground_game', 'cardio', 'chin']:
            if getattr(self, skill) < WEAK_THRESHOLD:
                weak.append(skill.replace('_', ' ').title())
        return weak
    
    def get_style_archetype(self) -> str:
        """Détermine l'archétype de style"""
        if self.striking > 75 and self.grappling < 50:
            return "🥊 Pure Striker"
        elif self.grappling > 75 and self.striking < 50:
            return "🤼 Pure Wrestler"
        elif self.ground_game > 75:
            return "🥋 Submission Specialist"
        elif self.striking > 65 and self.grappling > 65:
            return "⚔️ Hybrid Fighter"
        elif self.consistency_score > 75:
            return "⚖️ Complete Mixed Martial Artist"
        elif self.cardio > 80:
            return "🏃 Cardio Machine / Pressure Fighter"
        elif self.chin > 80 and self.striking > 60:
            return "🗿 Tough Brawler"
        else:
            return "🎯 Tactician / Game Planner"
    
    def compare_to_ufc_average(self) -> Dict[str, Dict]:
        """Compare chaque skill à la moyenne UFC"""
        comparison = {}
        for skill, ufc_avg in UFC_AVERAGES.items():
            my_value = getattr(self, skill)
            diff = my_value - ufc_avg
            
            if diff > 20:
                rating = "⭐⭐⭐ Très supérieur"
            elif diff > 10:
                rating = "⭐⭐ Supérieur"
            elif diff > -10:
                rating = "⭐ Dans la moyenne"
            elif diff > -20:
                rating = "⚠️ En dessous"
            else:
                rating = "❌ Bien en dessous"
            
            comparison[skill] = {
                'value': my_value,
                'ufc_avg': ufc_avg,
                'diff': round(diff, 1),
                'rating': rating
            }
        
        return comparison
    
    def get_tactical_recommendations(self) -> List[str]:
        """Recommandations tactiques basées sur le profil"""
        recs = []
        
        # Recommandations offensives
        if self.striking > self.grappling + 20:
            recs.append("💡 Gardez le combat debout - avantage striking clair")
        elif self.grappling > self.striking + 20:
            recs.append("💡 Cherchez le takedown tôt - imposez votre lutte")
        
        if self.ground_game > 75:
            recs.append("💡 N'hésitez pas à aller au sol - jeu de soumission dangereux")
        
        # Recommandations défensives
        if self.chin < 50:
            recs.append("⚠️ Chin fragile - évitez les échanges, privilégiez mouvement")
        
        if self.cardio < 60:
            recs.append("⚠️ Cardio limité - cherchez le finish tôt ou gérez le rythme")
        elif self.cardio > 80:
            recs.append("💡 Cardio exceptionnel - augmentez la pression au fil des rounds")
        
        # Recommandations stratégiques
        if self.fight_iq > 75:
            recs.append("💡 Fight IQ élevé - adaptez votre game plan en temps réel")
        
        if self.physicality > 75:
            recs.append("💡 Avantage physique - utilisez reach/force pour contrôler distance")
        
        if not recs:
            recs.append("💡 Profil équilibré - adaptez-vous à l'adversaire")
        
        return recs[:4]  # Max 4 recommandations
    
    def to_dict(self) -> Dict[str, float]:
        """Dictionnaire complet avec métriques avancées"""
        return {
            'striking': round(self.striking, 2),
            'grappling': round(self.grappling, 2),
            'ground_game': round(self.ground_game, 2),
            'cardio': round(self.cardio, 2),
            'chin': round(self.chin, 2),
            'fight_iq': round(self.fight_iq, 2),
            'physicality': round(self.physicality, 2),
            'overall': self.overall,
            'offensive_rating': self.offensive_rating,
            'defensive_rating': self.defensive_rating,
            'finish_potential': self.finish_potential,
            'consistency_score': self.consistency_score
        }
    
    def display_radar(self) -> str:
        """affiche le radar ASCII avec les barres de progression et les badges."""
        skills = [
            ('Striking', self.striking),
            ('Grappling', self.grappling),
            ('Ground Game', self.ground_game),
            ('Cardio', self.cardio),
            ('Chin', self.chin),
            ('Fight IQ', self.fight_iq),
            ('Physicality', self.physicality)
        ]
        
        output = "\n" + "" * 70 + "\n"
        output += "  PROFIL DE COMPÉTENCES UFC\n"
        output += "" * 70 + "\n\n"
        
        for name, value in skills:
            # Barre visuelle
            bar_length = int(value / 2)
            bar = "█" * bar_length + "░" * (50 - bar_length)
            
            # Badge de niveau
            if value >= ELITE_THRESHOLD:
                badge = "⭐ELITE"
            elif value >= STRONG_THRESHOLD:
                badge = "💪FORT"
            elif value >= GOOD_THRESHOLD:
                badge = "✓ BON"
            elif value >= AVERAGE_THRESHOLD:
                badge = "→ MOY"
            else:
                badge = "⚠ FAIB"
            
            output += f"  {name:14} [{bar}] {value:5.1f} {badge}\n"
        
        output += "\n" + "" * 70 + "\n"
        output += f"  {'OVERALL':14} {' ' * 25} {self.overall:5.1f}/100\n"
        output += "" * 70 + "\n\n"
        
        # Métriques avancées
        output += "  MÉTRIQUES AVANCÉES\n"
        output += " " + "" * 68 + "\n"
        output += f"  🗡️  Offensif      : {self.offensive_rating:5.1f}  "
        output += f"🛡️  Défensif      : {self.defensive_rating:5.1f}\n"
        output += f"  💥 Finish Pot.  : {self.finish_potential:5.1f}  "
        output += f"⚖️  Consistance  : {self.consistency_score:5.1f}\n"
        output += "" * 70 + "\n"
        
        return output


class SkillsCalculator:
    """calcule chaque skill à partir des stats UFC stats."""
    
    @staticmethod
    def calculate_striking(stats: Dict) -> float:
        """
        le striking : volume + précision + défense + KO rate + variété

        la formule :
        - Volume (25%) : Pression offensive
        - Précision (25%) : Efficacité technique
        - Défense (20%) : Head movement / esquives
        - KO Rate (25%) : Puissance pure
        - Variety (5%) : Mix coups de poing/pied/coude/genou
        """
        # Volume (normalisé sur 7 sig strikes/min = 100%)
        volume = min(stats.get('sig_str_per_min', 0) / 7.0, 1.0) * 25
        
        # Précision (50% accuracy = moyenne UFC)
        accuracy_raw = stats.get('striking_accuracy', 0)
        accuracy = (accuracy_raw / 100) * 25
        
        # Défense (65% = moyenne UFC)
        defense_raw = stats.get('striking_defense', 0)
        defense = (defense_raw / 100) * 20
        
        # KO Rate (bonus si > 30%)
        ko_pct = stats.get('ko_percentage', 0)
        ko_score = (ko_pct / 100) * 25
        if ko_pct > 30:
            ko_score *= 1.1  # Bonus power puncher
        
        # Variety bonus (si utilise plusieurs techniques)
        variety_bonus = 0
        if stats.get('head_kick_attempts', 0) > 0:
            variety_bonus += 2
        if stats.get('body_kicks', 0) > 0:
            variety_bonus += 1.5
        if stats.get('leg_kicks', 0) > 0:
            variety_bonus += 1.5
        
        total = volume + accuracy + defense + ko_score + variety_bonus
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_striking_detailed(stats: Dict) -> Dict[str, float]:
        """Breakdown détaillé du striking"""
        return {
            'volume': min(stats.get('sig_str_per_min', 0) / 7.0 * 100, 100),
            'accuracy': stats.get('striking_accuracy', 0),
            'defense': stats.get('striking_defense', 0),
            'power': stats.get('ko_percentage', 0),
            'pressure': min(stats.get('sig_str_per_min', 0) / 5.0 * 100, 100)
        }
    
    @staticmethod
    def calculate_grappling(stats: Dict) -> float:
        """
        le grappling : TD avg + précision + défense + contrôle clinch

        la formule :
        - TD Average (35%) : Volume de takedowns
        - TD Accuracy (30%) : Efficacité des tentatives
        - TD Defense (30%) : Résistance aux projections
        - Clinch Control (5%) : Domination au clinch
        """
        # TD Average (3+ TD/fight = excellent)
        td_avg = stats.get('td_avg', 0)
        td_avg_score = min(td_avg / 5.0, 1.0) * 35
        
        # Bonus pour wrestlers élites (4+ TD/fight)
        if td_avg > 4.0:
            td_avg_score *= 1.1
        
        # TD accuracy
        td_acc = (stats.get('td_accuracy', 0) / 100) * 30
        
        # TD Defense (85%+ = elite)
        td_def = (stats.get('td_defense', 0) / 100) * 30
        
        # Clinch control (inféré depuis control time)
        control_time = stats.get('avg_control_time', 0)
        clinch_score = min(control_time / 200, 1.0) * 5
        
        total = td_avg_score + td_acc + td_def + clinch_score
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_ground_game(stats: Dict) -> float:
        """
        le ground game : soumissions + contrôle + positions + défense

        la formule :
        - Submission Rate (35%) : Dangerosité au sol
        - Control Time (30%) : Domination positionnelle
        - Sub Defense (20%) : Résistance soumissions
        - Transitions (10%) : Fluidité changements position
        - Scrambles (5%) : Capacité à se relever
        """
        # Submission Average (1+ sub/fight = elite)
        sub_avg = stats.get('sub_avg', 0)
        sub_score = min(sub_avg / 3.0, 1.0) * 35
        
        # Bonus pour submission specialists (1.5+ sub/fight)
        if sub_avg > 1.5:
            sub_score *= 1.15
        
        # Control Time (5min+ = excellent)
        control = stats.get('avg_control_time', 0)
        control_score = min(control / 300, 1.0) * 30
        
        # Submission Defense
        sub_loss_rate = stats.get('sub_loss_rate', 0)
        sub_def = (1 - sub_loss_rate) * 20
        
        # Transitions (inféré depuis reversals)
        reversals = stats.get('reversals', 0)
        transition_score = min(reversals / 2.0, 1.0) * 10
        
        # Scramble ability (get back up rate)
        scramble_score = 5  # Base score
        if stats.get('td_defense', 0) > 75:
            scramble_score *= 1.2
        
        total = sub_score + control_score + sub_def + transition_score + scramble_score
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_cardio(stats: Dict) -> float:
        """
        le cardio : pace ratio + finishes tardifs + constance du rythme

        la formule :
        - Pace Ratio tardif/précoce (50%) : Maintien du rythme
        - Late Round Finishes (25%) : Finish en rounds 4-5
        - Pace Consistency (15%) : Variance faible = bon cardio
        - Recovery (10%) : Capacité à récupérer entre rounds
        """
        # Pace Ratio
        late_pace = stats.get('pace_rounds_3_5', 0)
        early_pace = stats.get('pace_rounds_1_2', 1)
        
        if early_pace > 0:
            ratio = late_pace / early_pace
            # Ratio > 0.9 = excellent cardio
            if ratio > 0.9:
                pace_score = 50
            elif ratio > 0.8:
                pace_score = 40
            elif ratio > 0.7:
                pace_score = 30
            else:
                pace_score = 20
        else:
            pace_score = 25
        
        # les finishes tardifs (rounds 4-5)
        late_finish_rate = stats.get('late_finish_rate', 0)
        late_finish_score = late_finish_rate * 25
        
        # la constance du rythme (faible variance = bon cardio)
        consistency_score = 15  # Base
        if abs(late_pace - early_pace) < 0.5:
            consistency_score *= 1.2
        
        # Recovery (inféré depuis defense stats late rounds)
        recovery_score = 10  # Base
        
        total = pace_score + late_finish_score + consistency_score + recovery_score
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_chin(stats: Dict) -> float:
        """
        le menton : résistance aux KO + absorption + résistance knockdowns

        la formule :
        - KO Loss Rate (40%) : Nombre de KO subis
        - Absorption (30%) : Frappes encaissées/min
        - Knockdown Resistance (20%) : Résistance aux knockdowns
        - Recovery (10%) : Capacité à récupérer après un gros coup
        """
        total_fights = max(stats.get('total_fights', 1), 1)
        ko_losses = stats.get('ko_losses', 0)
        
        # KO Loss Rate (0% KO loss = 40 points)
        ko_loss_rate = ko_losses / total_fights
        chin_base = (1 - ko_loss_rate) * 40
        
        # Bonus si jamais KO
        if ko_losses == 0 and total_fights > 10:
            chin_base *= 1.15
        
        # Absorption (moins de strikes absorbés = meilleur chin)
        absorbed = stats.get('sig_str_absorbed_per_min', 5)
        # 2.5 sig str/min = excellent defense
        # 5.0 sig str/min = moyenne
        # 7.0+ sig str/min = beaucoup de dégâts
        if absorbed < 2.5:
            absorption_score = 30
        elif absorbed < 4.0:
            absorption_score = 25
        elif absorbed < 5.5:
            absorption_score = 20
        else:
            absorption_score = 10
        
        # Knockdown Resistance
        knockdowns_suffered = stats.get('knockdowns_suffered', 0)
        if knockdowns_suffered == 0 and total_fights > 5:
            kd_resistance = 20
        elif knockdowns_suffered < 2:
            kd_resistance = 15
        else:
            kd_resistance = 10
        
        # Recovery ability (inféré depuis comebacks)
        comeback_wins = stats.get('comeback_wins', 0)
        recovery_score = min(comeback_wins * 3, 10)
        
        total = chin_base + absorption_score + kd_resistance + recovery_score
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_fight_iq(stats: Dict) -> float:
        """
        le fight IQ : décisions + comebacks + versatilité + adaptabilité

        la formule :
        - Decision Rate (30%) : Capacité à gagner aux points
        - Comeback Wins (25%) : Résilience mentale
        - Method Variety (20%) : Versatilité finish
        - Game Planning (15%) : Exécution stratégie
        - Adaptability (10%) : Ajustements en combat
        """
        total_wins = max(stats.get('total_wins', 1), 1)
        decision_wins = stats.get('decision_wins', 0)
        
        # le ratio de decisions gagnées (>50% = fighter intelligent)
        decision_rate = (decision_wins / total_wins)
        if decision_rate > 0.5:
            decision_score = 30
        elif decision_rate > 0.3:
            decision_score = 23
        else:
            decision_score = 15
        
        # les comebacks (la solidité mentale)
        comeback_wins = stats.get('comeback_wins', 0)
        comeback_score = min(comeback_wins * 8, 25)
        
        # method variety (KO + SUB + DEC wins)
        variety = stats.get('finish_method_variety', 0)
        variety_score = min(variety * 7, 20)
        
        # Game Planning (exécution tactique)
        # Inféré depuis striking accuracy + TD accuracy
        strike_acc = stats.get('striking_accuracy', 50)
        td_acc = stats.get('td_accuracy', 40)
        avg_acc = (strike_acc + td_acc) / 2
        if avg_acc > 50:
            planning_score = 15
        elif avg_acc > 40:
            planning_score = 10
        else:
            planning_score = 5
        
        # Adaptability (inféré depuis décisions gagnées + comebacks)
        adaptability_score = 10  # Base
        if decision_wins > 5 and comeback_wins > 2:
            adaptability_score *= 1.2
        
        total = decision_score + comeback_score + variety_score + planning_score + adaptability_score
        return round(min(total, 100), 2)
    
    @staticmethod
    def calculate_physicality(stats: Dict) -> float:
        """
        la physicalité : allonge + taille + force + explosivité + endurance

        la formule :
        - Reach (35%) : Avantage allonge
        - Height (25%) : Avantage taille
        - Strength (20%) : Force pure (TD success)
        - Explosiveness (15%) : Burst power (KO rate proxy)
        - Muscular Endurance (5%) : Maintien force
        """
        # Reach (normalisé par catégorie)
        reach = stats.get('reach_cm', 180)
        # 150cm = very short, 210cm = very long
        reach_normalized = (reach - 150) / 60  # 0-1 scale
        reach_score = min(max(reach_normalized, 0), 1.0) * 35
        
        # Height
        height = stats.get('height_cm', 175)
        height_normalized = (height - 160) / 40  # 0-1 scale
        height_score = min(max(height_normalized, 0), 1.0) * 25
        
        # Strength (TD accuracy comme proxy)
        strength_proxy = (stats.get('td_accuracy', 50) / 100) * 20
        
        # Explosiveness (KO rate comme proxy)
        explosiveness = (stats.get('ko_percentage', 0) / 100) * 15
        
        # Muscular Endurance
        endurance = 5  # Base score
        if stats.get('pace_rounds_3_5', 0) > stats.get('pace_rounds_1_2', 0):
            endurance *= 1.2
        
        total = reach_score + height_score + strength_proxy + explosiveness + endurance
        return round(min(total, 100), 2)
    
    @classmethod
    def calculate_all_skills(cls, stats: Dict) -> SkillsProfile:
        """Calcule TOUS les skills avec formules améliorées"""
        return SkillsProfile(
            striking=cls.calculate_striking(stats),
            grappling=cls.calculate_grappling(stats),
            ground_game=cls.calculate_ground_game(stats),
            cardio=cls.calculate_cardio(stats),
            chin=cls.calculate_chin(stats),
            fight_iq=cls.calculate_fight_iq(stats),
            physicality=cls.calculate_physicality(stats)
        )
    
    @classmethod
    def get_skill_breakdown(cls, stats: Dict) -> Dict[str, Dict]:
        """Analyse détaillée de chaque skill avec sous-composantes"""
        return {
            'striking': cls.calculate_striking_detailed(stats),
            'overall_skills': cls.calculate_all_skills(stats).to_dict()
        }

