# Transversal

A VTTRPG where players travel across a multiverse through a common backend application. Rules based on Cortex Prime with a dual-pipeline dice resolution system (simplified + dice pool). The backend manages locations, characters, factions, and assets as entities with traits, razmerit (hyper-dimensional currency), and SFX-driven effects.

## Quick Start

```bash
cd code
docker compose up -d
```

Then open:
- Frontend: http://localhost:3000 (Vue3 PWA)
- API: http://localhost:8085/health
- API docs: http://localhost:8085/docs (OpenAPI)
- GraphQL: http://localhost:8085/api/v1/graphql
- ArangoDB: http://localhost:8531 (root password: `transversal`)

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Vue3 + Vite PWA |
| Backend | FastAPI (Python 3.12) |
| GraphQL | Strawberry (code-first, FastAPI-native) |
| Real-time | SSE (Server-Sent Events) |
| Database | ArangoDB 3.12 (graph + document) |
| Cache | Redis 7 |
| MCP | stdio transport |

## Project Layout

```
code/
├── docker-compose.yaml
├── api/                          # FastAPI backend
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/transversal/
│       ├── main.py               # App entry, startup, seed
│       ├── domain/               # Pydantic models + validation
│       ├── db/                   # ArangoDB client, repository, seed
│       ├── services/             # Entity manager, dice resolver, effects, razmerit, session
│       ├── api/
│       │   ├── graphql/          # Strawberry schema + types
│       │   ├── rest/             # /roll, /effects, /sessions, /players, /locations
│       │   └── sse/              # Event bus + streaming endpoint
│       └── mcp/                  # MCP server (stdio)
├── frontend/                     # Vue3 PWA
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── App.vue               # Root: state, SSE, entity switcher, session
│       ├── main.js
│       └── components/
│           ├── CharacterSheet.vue  # GraphQL-powered, trait toggling, SFX buttons
│           ├── DiceRoller.vue      # Dual-pipeline, phases, die selection, SFX
│           ├── DieIcon.vue         # SVG dice (d4-d12), color-coded
│           ├── LocationViewer.vue   # Full-screen background + label
│           └── LocationNav.vue      # Navigation panel (super/transversal edges)
docs/                             # Obsidian-wiki documentation (10 docs, 2700+ lines)
```

## Running Tests

```bash
cd code/api
pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests/ -v
```

Or inside the container:
```bash
docker compose -f code/docker-compose.yaml exec api python -m pytest tests/ -v
```

## Key Conventions

- **Python**: Pydantic models in `domain/`, business logic in `services/`, API routers in `api/`
- **Vue**: Composition API (`<script setup>`), props down/events up, refs for reactive state
- **Database**: 7 ArangoDB collections (entities, projections, traits, traitsets, traitsettings, sfxs, relationships). Edges for trait settings and relationships.
- **Seed data**: Runs on startup via `@app.on_event("startup")`. Idempotent — guards check for existing records.
- **SSE events**: Published through `EventBus` singleton, scoped to session IDs
- **Dice resolver**: Stateless — pure function, no DB access
- **Documentation**: All in `docs/` as Obsidian-wiki `.md` files with `[[wikilinks]]`

## Documentation

Start with `docs/Transversal Hub.md` — it links to everything. Key docs:
- Game design: `docs/Game Design/`
- Technical: `docs/Technical/`
- Roadmap: `docs/Project Roadmap.md`
