# MM.AI v0.3 — MMA analytics & fight prediction (early showcase)

> **⚠️ This is the first version of the project, published as a showcase for curious people.**
> The predictions, ratings (Elo, Scouter) and matchmaking logic in this repository are
> **simplified early versions — they are NOT the real algorithms.**
> The real engine lives in the final product, **RoundZero** (the site and the app), and is not open source.

MM.AI was my final-year project: a platform that rates MMA fighters and estimates the outcome of a
fight from their full career record, across UFC, PFL, Bellator, ONE and regional promotions.
It later became **RoundZero**. This repo freezes the original MM.AI, *Dragon Ball Z* references included.

<p align="center">
  <img src="docs/screenshots/site_accueil.png" width="48%" alt="Home page">
  <img src="docs/screenshots/site_fiche.png" width="48%" alt="Fighter page">
</p>

## What's in it

- **Rankings, fighters, divisions, events** pages with filters, search and a full fighter profile
- **Elo rating** replayed from each fighter's fight history (v0.3 engine)
- **Scouter rating (0–100)** — a single score for a fighter's current level, revealed in the
  matchmaking page with a *Dragon Ball Z "power level"* scouter animation 🟣
- **Compare** two fighters and **Matchmaking**: win probability, tale of the tape, factor breakdown
- Optional **LLM-written analysis** of a matchup with a reliability score (Gemini / OpenRouter / Groq, with a no-AI fallback)
- Accounts (JWT, email verification, favorites), admin panel with 2FA, 8 languages, dark/light theme

## Stack

PostgreSQL · Python (Flask API serving a vanilla HTML/CSS/JS frontend) · FastAPI sandbox (Swagger) · no frontend framework.

```
api/        Flask API + static file server (entry point: api/app.py)
backend/    FastAPI sandbox + ML code (elo, scouter, skills, matchup predictor)
database/   PostgreSQL schema, migrations, batch scripts
frontend/   HTML / CSS / JS pages
docs/       screenshots
```

## About the data

**This repository contains no fighter data.** The original database was filled by scraping public
sources and lived on Supabase; that data is not mine to redistribute, so it is not included.
The site is therefore **empty if you run it as is**: you would need your own PostgreSQL database
and your own data. The screenshots above show what it looked like with data.

What you *can* run without any data is the FastAPI sandbox, which falls back to 3 built-in sample fighters.

## Running it

**FastAPI sandbox (no database needed, sample data):**

```bash
cd backend
pip install fastapi uvicorn numpy psycopg2-binary python-dotenv
PYTHONPATH=src uvicorn api.app:app --reload     # Windows PowerShell: $env:PYTHONPATH="src"
# → http://localhost:8000/docs
```

**Full site (needs your own PostgreSQL + data):**

```bash
pip install -r api/requirements.txt
cp .env.example .env                             # fill in your database settings
# create the tables: run database/schema_mmai.sql, then database/migrations/*.sql in order
python api/app.py                                # → http://localhost:5000
```

Every page shows a banner reminding visitors that this is the v0.3 showcase, and the prediction
endpoints return a `demo_notice` field saying the same.

## Credits & disclaimers

- Not affiliated with the UFC or any promotion. Fighter names and photos belong to their owners.
- The *Dragon Ball Z* GIFs and images are fan references; they belong to their respective rights holders.
- Author: [Elias Lallouet](https://github.com/kalmossa)
