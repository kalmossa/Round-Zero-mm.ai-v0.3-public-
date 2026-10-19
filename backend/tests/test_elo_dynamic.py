"""
Tests pour DynamicEloCalculator
"""

import pytest
from datetime import datetime, timedelta
from src.ml.elo_dynamic import DynamicEloCalculator


class TestDynamicEloCalculator:
    """Tests du calculateur Elo Dynamique"""
    
    def setup_method(self):
        self.calc = DynamicEloCalculator()
    
    def test_age_factor_peak(self):
        """Test facteur âge au peak (28-32 ans)"""
        assert self.calc._get_age_factor(30) == 1.05
        assert self.calc._get_age_factor(28) == 1.05
        assert self.calc._get_age_factor(32) == 1.05
    
    def test_age_factor_young(self):
        """Test facteur âge jeune (20-24 ans)"""
        assert self.calc._get_age_factor(22) == 0.95
    
    def test_age_factor_old(self):
        """Test facteur âge vieux (39+ ans)"""
        assert self.calc._get_age_factor(40) == 0.85
        assert self.calc._get_age_factor(45) == 0.80
    
    def test_form_factor_winning_streak(self):
        """Test facteur forme avec streak de victoires"""
        fights = [
            {'result': 'W', 'method': 'KO'},
            {'result': 'W', 'method': 'Submission'},
            {'result': 'W', 'method': 'Decision'}
        ]
        factor = self.calc._calculate_form_factor(fights)
        assert factor > 1.0
    
    def test_form_factor_losing_streak(self):
        """Test facteur forme avec streak de défaites"""
        fights = [
            {'result': 'L', 'method': 'KO'},
            {'result': 'L', 'method': 'Decision'},
            {'result': 'L', 'method': 'Submission'}
        ]
        factor = self.calc._calculate_form_factor(fights)
        assert factor < 1.0
    
    def test_opponent_quality_top10(self):
        """Test qualité opposition top 10"""
        ratings = [1750, 1720, 1710]
        factor = self.calc._calculate_opponent_quality(ratings)
        assert factor == 1.10
    
    def test_inactivity_penalty_recent(self):
        """Test pénalité inactivité (combat récent)"""
        fights = [{'date': datetime.now() - timedelta(days=180)}]
        factor = self.calc._calculate_inactivity_penalty(fights)
        assert factor == 1.0
    
    def test_inactivity_penalty_layoff(self):
        """Test pénalité inactivité (2 ans)"""
        fights = [{'date': datetime.now() - timedelta(days=800)}]
        factor = self.calc._calculate_inactivity_penalty(fights)
        assert factor < 1.0
    
    def test_calculate_dynamic_elo_complete(self):
        """Test calcul Elo complet"""
        fights = [
            {'result': 'W', 'method': 'KO', 'date': datetime.now() - timedelta(days=90)},
            {'result': 'W', 'method': 'Decision', 'date': datetime.now() - timedelta(days=200)}
        ]
        
        elo = self.calc.calculate_dynamic_elo(
            fighter_id=1,
            base_elo=1600,
            age=30,
            recent_fights=fights,
            opponent_ratings=[1580, 1550]
        )
        
        assert isinstance(elo, float)
        assert 1000 < elo < 2500
    
    def test_predict_outcome(self):
        """Test prédiction de probabilités"""
        prob1, prob2 = self.calc.predict_outcome(1600, 1500)
        assert 0 < prob1 < 1
        assert 0 < prob2 < 1
        assert abs(prob1 + prob2 - 1.0) < 0.0001
        assert prob1 > prob2  # Fighter 1 devrait être favori
