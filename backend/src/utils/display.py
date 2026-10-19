"""
Utilitaires d'affichage console
"""

import os
import platform

def clear_screen():
    """Efface l'écran"""
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def print_header(text: str):
    """Affiche un titre stylisé"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def print_separator():
    """Ligne de séparation"""
    print("-" * 60)
