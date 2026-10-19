"""
Tests pour MatchupPredictor
"""

import pytest
from datetime import datetime, timedelta
from src.ml.matchup_predictor import MatchupPredictor


class TestMatchupPredictor:
    """Tests du prédicteur de matchup"""
    
    def setup_method(self):
        self.predictor = MatchupPredictor()
    
    def test_predict_fight_basic(self):
        """Test prédiction basique"""
        f1 = {
            'id': 1, 'base_elo': 1700, 'age': 30,
            'stats': self._get_default_stats()
        }
        f2 = {
            'id': 2, 'base_elo': 1600, 'age': 28,
            'stats': self._get_default_stats()
        }
        
        h1 = [{'result': 'W', 'method': 'KO', 'opponent_elo': 1650,
               'date': datetime.now() - timedelta(days=90)}]
        h2 = [{'result': 'L', 'method': 'Decision', 'opponent_elo': 1680,
               'date': datetime.now() - timedelta(days=120)}]
        
        pred = self.predictor.predict_fight(f1, f2, h1, h2)
        
        assert 'winner' in pred
        assert 'fighter1_win_prob' in pred
        assert 'fighter2_win_prob' in pred
        assert 'confidence' in pred
        assert 'method' in pred
        assert 'key_factors' in pred
    
    def test_probabilities_sum_to_one(self):
        """Test que les probabilités = 100%"""
        f1 = {'id': 1, 'base_elo': 1600, 'age': 30,
              'stats': self._get_default_stats()}
        f2 = {'id': 2, 'base_elo': 1600, 'age': 30,
              'stats': self._get_default_stats()}
        
        h1 = h2 = []
        pred = self.predictor.predict_fight(f1, f2, h1, h2)
        
        total = pred['fighter1_win_prob'] + pred['fighter2_win_prob']
        assert abs(total - 1.0) < 0.0001
    
    def test_confidence_calculation(self):
        """Test calcul de confiance"""
        f1 = {'id': 1, 'base_elo': 1800, 'age': 30,
              'stats': self._get_default_stats()}
        f2 = {'id': 2, 'base_elo': 1500, 'age': 35,
              'stats': self._get_default_stats()}
        
        h1 = h2 = []
        pred = self.predictor.predict_fight(f1, f2, h1, h2)
        
        assert 0 <= pred['confidence'] <= 1
    
    def _get_default_stats(self):
        return {
            'sig_str_per_min': 4.0, 'striking_accuracy': 50.0,
            'striking_defense': 60.0, 'ko_percentage': 25.0,
            'td_avg': 2.0, 'td_accuracy': 40.0, 'td_defense': 70.0,
            'sub_avg': 0.5, 'avg_control_time': 120, 'sub_loss_rate': 0.1,
            'pace_rounds_3_5': 4.0, 'pace_rounds_1_2': 4.2,
            'late_finish_rate': 0.15, 'ko_losses': 0, 'total_fights': 20,
            'sig_str_absorbed_per_min': 3.0, 'decision_wins': 8,
            'total_wins': 15, 'comeback_wins': 2,
            'finish_method_variety': 2,
            'reach_cm': 180.0, 'height_cm': 175.0
        }
