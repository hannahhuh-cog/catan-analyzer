# Catan Analyzer

Did you lose to the dice, or to your decisions? A full-stack web app that analyzes Catan games played on [Colonist.io](https://colonist.io).

- **Profile analysis (real data):** enter any Colonist.io username. The backend pulls up to 100 recent games from Colonist's public profile history and reports win rate by placement order, player count, game length and VP target, each compared against (a) seat luck alone and (b) the player's own overall level, so it can call out real strengths and weaknesses ("you win 27% when placing 1st vs. 50% predicted"). It also flags close losses, blowouts, rivals and form over time.
- **Per-game luck vs. strategy (demo):** each game is replayed event by event to compute
  - **luck index** - dice income vs. what the player's buildings should have produced (a z-score, relative to opponents), plus robber blocks and steals;
  - **decision score** - opening placement percentile among open spots, tempo, robber targeting, hand management (7 discards) and awards, compared with the table;
  - a **verdict** (Earned win, Lucky win, Lost to RNG, Strategic loss, ...);
  - a **win-probability timeline** with critical decisions and luck swings marked, the dice distribution, and the final board.
- **Strategy strengths:** win rate by inferred strategy (city rush, expansion, dev cards, balanced) and a luck-vs-decision scatter across all games.

Colonist.io's turn-by-turn replay API requires a logged-in session, so the per-game analysis currently runs on a demo profile of 40 simulated games (`backend/app/catan/sim.py`) that emit the same normalized event format an imported replay would. Adding a replay importer only needs a mapper from Colonist's event log into that format (`backend/app/catan/analyze.py` documents it).

## Layout

```
backend/   FastAPI app (Python 3.10+)
  app/colonist.py       Colonist.io profile-history fetch, normalization, aggregate stats and insights
  app/catan/board.py    Board geometry in Colonist's hex/corner/edge coordinates
  app/catan/sim.py      Heuristic Catan simulator (demo games)
  app/catan/analyze.py  Per-game luck/decision analysis, timeline and critical moments
  app/demo.py           Demo profile + cross-game "deep" stats
  app/main.py           API routes; serves the built frontend
frontend/  Vite + React + TypeScript + Recharts
```

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
cd backend && uvicorn app.main:app --port 8000   # http://localhost:8000
```

For frontend development run `npm run dev` in `frontend/` (proxies `/api` to port 8000).

## Checks

```bash
cd backend && pytest && ruff check app tests
cd frontend && npx tsc -b && npm run lint
```

## API

- `GET /api/profile/{username}` - Colonist.io profile stats (cached 5 minutes)
- `GET /api/demo` - demo profile with deep stats
- `GET /api/demo/games/{id}` - full analysis of one demo game
