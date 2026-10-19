"""
Données de test - 3 combattants réalistes
"""

from datetime import date, datetime, timedelta

SAMPLE_FIGHTERS = [
    {
        'id': 1,
        'name': 'Jon Jones',
        'nickname': 'Bones',
        'date_of_birth': date(1987, 7, 19),
        'nationality': 'USA',
        'weight_class': 'Heavyweight',
        'reach_cm': 214.0,
        'height_cm': 193.0,
        'stance': 'Orthodox',
        'record_wins': 27,
        'record_losses': 1,
        'record_draws': 0,
        'base_elo': 1820.0,
        'stats': {
            'sig_str_per_min': 4.5, 'striking_accuracy': 52.0,
            'striking_defense': 65.0, 'ko_percentage': 25.0,
            'td_avg': 2.1, 'td_accuracy': 43.0, 'td_defense': 95.0,
            'sub_avg': 0.6, 'avg_control_time': 180, 'sub_loss_rate': 0.0,
            'pace_rounds_3_5': 3.8, 'pace_rounds_1_2': 4.2,
            'late_finish_rate': 0.15, 'ko_losses': 0, 'total_fights': 28,
            'sig_str_absorbed_per_min': 2.1, 'decision_wins': 10,
            'total_wins': 27, 'comeback_wins': 3,
            'finish_method_variety': 3,
            'reach_cm': 214.0, 'height_cm': 193.0
        }
    },
    {
        'id': 2,
        'name': 'Ciryl Gane',
        'nickname': 'Bon Gamin',
        'date_of_birth': date(1990, 4, 12),
        'nationality': 'France',
        'weight_class': 'Heavyweight',
        'reach_cm': 206.0,
        'height_cm': 196.0,
        'stance': 'Switch',
        'record_wins': 11,
        'record_losses': 2,
        'record_draws': 0,
        'base_elo': 1680.0,
        'stats': {
            'sig_str_per_min': 5.2, 'striking_accuracy': 58.0,
            'striking_defense': 62.0, 'ko_percentage': 45.0,
            'td_avg': 1.1, 'td_accuracy': 35.0, 'td_defense': 70.0,
            'sub_avg': 0.2, 'avg_control_time': 90, 'sub_loss_rate': 0.1,
            'pace_rounds_3_5': 4.8, 'pace_rounds_1_2': 5.1,
            'late_finish_rate': 0.25, 'ko_losses': 0, 'total_fights': 13,
            'sig_str_absorbed_per_min': 2.8, 'decision_wins': 4,
            'total_wins': 11, 'comeback_wins': 1,
            'finish_method_variety': 2,
            'reach_cm': 206.0, 'height_cm': 196.0
        }
    },
    {
        'id': 3,
        'name': 'Gilbert Burns',
        'nickname': 'Durinho',
        'date_of_birth': date(1986, 7, 20),
        'nationality': 'Brazil',
        'weight_class': 'Welterweight',
        'reach_cm': 180.0,
        'height_cm': 178.0,
        'stance': 'Orthodox',
        'record_wins': 22,
        'record_losses': 7,
        'record_draws': 0,
        'base_elo': 1650.0,
        'stats': {
            'sig_str_per_min': 4.8, 'striking_accuracy': 48.0,
            'striking_defense': 55.0, 'ko_percentage': 15.0,
            'td_avg': 2.8, 'td_accuracy': 48.0, 'td_defense': 72.0,
            'sub_avg': 1.2, 'avg_control_time': 240, 'sub_loss_rate': 0.05,
            'pace_rounds_3_5': 3.5, 'pace_rounds_1_2': 4.1,
            'late_finish_rate': 0.10, 'ko_losses': 2, 'total_fights': 29,
            'sig_str_absorbed_per_min': 3.5, 'decision_wins': 8,
            'total_wins': 22, 'comeback_wins': 4,
            'finish_method_variety': 3,
            'reach_cm': 180.0, 'height_cm': 178.0
        }
    }
]

SAMPLE_FIGHT_HISTORY = {
    1: [
        {'date': datetime.now() - timedelta(days=90), 'opponent_id': 4,
         'opponent_name': 'Stipe Miocic', 'opponent_elo': 1720.0,
         'result': 'W', 'method': 'TKO'},
        {'date': datetime.now() - timedelta(days=450), 'opponent_id': 2,
         'opponent_name': 'Ciryl Gane', 'opponent_elo': 1680.0,
         'result': 'W', 'method': 'Submission'},
        {'date': datetime.now() - timedelta(days=800), 'opponent_id': 5,
         'opponent_name': 'Dominick Reyes', 'opponent_elo': 1620.0,
         'result': 'W', 'method': 'Decision'}
    ],
    2: [
        {'date': datetime.now() - timedelta(days=180), 'opponent_id': 6,
         'opponent_name': 'Sergey Spivac', 'opponent_elo': 1580.0,
         'result': 'W', 'method': 'KO'},
        {'date': datetime.now() - timedelta(days=450), 'opponent_id': 1,
         'opponent_name': 'Jon Jones', 'opponent_elo': 1820.0,
         'result': 'L', 'method': 'Submission'},
        {'date': datetime.now() - timedelta(days=650), 'opponent_id': 7,
         'opponent_name': 'Tai Tuivasa', 'opponent_elo': 1600.0,
         'result': 'W', 'method': 'KO'}
    ],
    3: [
        {'date': datetime.now() - timedelta(days=120), 'opponent_id': 8,
         'opponent_name': 'Jorge Masvidal', 'opponent_elo': 1580.0,
         'result': 'L', 'method': 'Decision'},
        {'date': datetime.now() - timedelta(days=280), 'opponent_id': 9,
         'opponent_name': 'Neil Magny', 'opponent_elo': 1520.0,
         'result': 'W', 'method': 'Submission'},
        {'date': datetime.now() - timedelta(days=450), 'opponent_id': 10,
         'opponent_name': 'Khamzat Chimaev', 'opponent_elo': 1720.0,
         'result': 'L', 'method': 'Decision'}
    ]
}

def get_fighter_by_id(fighter_id: int):
    for f in SAMPLE_FIGHTERS:
        if f['id'] == fighter_id:
            return f.copy()
    return None

def get_fighter_by_name(name: str):
    name_lower = name.lower()
    for f in SAMPLE_FIGHTERS:
        if name_lower in f['name'].lower():
            return f.copy()
    return None

def get_fight_history(fighter_id: int):
    return SAMPLE_FIGHT_HISTORY.get(fighter_id, []).copy()

def list_all_fighters():
    return [f['name'] for f in SAMPLE_FIGHTERS]
