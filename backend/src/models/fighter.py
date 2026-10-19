"""
Modèle Fighter - Combattant MMA
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import date


@dataclass
class Fighter:
    """Combattant MMA avec caractéristiques complètes"""
    id: int
    name: str
    nickname: Optional[str] = None
    date_of_birth: Optional[date] = None
    nationality: str = "USA"
    weight_class: str = "Welterweight"
    reach_cm: float = 180.0
    height_cm: float = 175.0
    stance: str = "Orthodox"
    record_wins: int = 0
    record_losses: int = 0
    record_draws: int = 0
    base_elo: float = 1500.0
    stats: Dict = field(default_factory=dict)
    
    @property
    def age(self) -> int:
        """Calcule l'âge actuel"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < 
                (self.date_of_birth.month, self.date_of_birth.day)
            )
        return 30
    
    @property
    def record(self) -> str:
        """Format du palmarès"""
        return f"{self.record_wins}-{self.record_losses}-{self.record_draws}"
    
    def display_card(self) -> str:
        """Carte d'identité du combattant"""
        return f"""
╔╗
║  {self.name.upper():^46}  ║
║  "{self.nickname or 'N/A'}"{' ' * (44 - len(self.nickname or 'N/A'))}  ║
╠╣
║  Record: {self.record:20}  Age: {self.age:3}     ║
║  Class:  {self.weight_class:20}  Elo: {self.base_elo:7.1f}║
║  Reach:  {self.reach_cm:6.1f} cm  Height: {self.height_cm:6.1f} cm  ║
║  Stance: {self.stance:36}  ║
╚╝
"""
