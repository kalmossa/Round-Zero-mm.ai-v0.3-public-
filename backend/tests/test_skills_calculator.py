"""
Tests pour SkillsCalculator
"""

import pytest
from src.ml.skills_calculator import SkillsCalculator, SkillsProfile


class TestSkillsCalculator:
    """Tests du calculateur de compétences"""
    
    def setup_method(self):
        self.calc = SkillsCalculator()
    
    def test_calculate_striking(self):
        """Test calcul striking"""
        stats = {
            'sig_str_per_min': 5.0,
            'striking_accuracy': 50.0,
            'striking_defense': 60.0,
            'ko_percentage': 30.0
        }
        striking = self.calc.calculate_striking(stats)
        assert 0 <= striking <= 100
    
    def test_calculate_grappling(self):
        """Test calcul grappling"""
        stats = {
            'td_avg': 3.0,
            'td_accuracy': 50.0,
            'td_defense': 80.0
        }
        grappling = self.calc.calculate_grappling(stats)
        assert 0 <= grappling <= 100
    
    def test_skills_profile_overall(self):
        """Test calcul overall pondéré"""
        profile = SkillsProfile(
            striking=80.0,
            grappling=70.0,
            ground_game=60.0,
            cardio=75.0,
            chin=85.0,
            fight_iq=70.0,
            physicality=65.0
        )
        overall = profile.overall
        assert 0 <= overall <= 100
        assert isinstance(overall, float)
    
    def test_calculate_all_skills(self):
        """Test calcul de tous les skills"""
        stats = {
            'sig_str_per_min': 5.0, 'striking_accuracy': 50.0,
            'striking_defense': 60.0, 'ko_percentage': 30.0,
            'td_avg': 2.0, 'td_accuracy': 40.0, 'td_defense': 70.0,
            'sub_avg': 0.5, 'avg_control_time': 120, 'sub_loss_rate': 0.1,
            'pace_rounds_3_5': 4.0, 'pace_rounds_1_2': 4.5,
            'late_finish_rate': 0.2, 'ko_losses': 1, 'total_fights': 20,
            'sig_str_absorbed_per_min': 3.0, 'decision_wins': 5,
            'total_wins': 15, 'comeback_wins': 2,
            'finish_method_variety': 2,
            'reach_cm': 185.0, 'height_cm': 180.0
        }
        
        profile = self.calc.calculate_all_skills(stats)
        
        assert isinstance(profile, SkillsProfile)
        assert 0 <= profile.striking <= 100
        assert 0 <= profile.grappling <= 100
        assert 0 <= profile.ground_game <= 100
        assert 0 <= profile.cardio <= 100
        assert 0 <= profile.chin <= 100
        assert 0 <= profile.fight_iq <= 100
        assert 0 <= profile.physicality <= 100
        assert 0 <= profile.overall <= 100
