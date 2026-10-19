"""
Modèle Fight - Combat MMA
"""

from dataclasses import dataclass
from typing import Optional
from datetime import date


@dataclass
class Fight:
    """Combat entre deux combattants"""
    id: int
    fighter1_id: int
    fighter2_id: int
    date: date
    winner_id: Optional[int] = None
    method: str = "Decision"
    method_detail: str = ""
    round: int = 3
    event_name: str = ""
    weight_class: str = "Welterweight"
    title_bout: bool = False
    
    @property
    def result_fighter1(self) -> str:
        if self.winner_id == self.fighter1_id:
            return 'W'
        elif self.winner_id == self.fighter2_id:
            return 'L'
        return 'D'
    
    @property
    def result_fighter2(self) -> str:
        if self.winner_id == self.fighter2_id:
            return 'W'
        elif self.winner_id == self.fighter1_id:
            return 'L'
        return 'D'
