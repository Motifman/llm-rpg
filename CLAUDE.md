# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install
pip install -e .          # or: make install / make dev-install

# Test
pytest                                           # full suite
pytest tests/domain/guild -v                     # focused slice
pytest --cov=src --cov-report=term-missing       # with coverage
make test-cov                                    # same via Make
make test-html                                   # HTML report → htmlcov/index.html

# Markers: -m unit | integration | slow | asyncio

# Backend servers
python -m ai_rpg_world.presentation.spot_graph_game.server   # game server (port 8080)
AI_RPG_WORLD_GAME_DB=var/game/ai_rpg_world.db \
  uv run python -m ai_rpg_world.presentation.web.server      # web viewer (port 8000)

# Web viewer DB setup
make web-demo-db          # create demo SQLite DB
make web-demo-db-reset    # recreate from scratch

# Frontend (React + Phaser)
cd frontend && npm install --cache .npm-cache && npm run dev

# Asset pipeline (separate uv project)
make asset-pipeline-sync
make asset-pipeline CMD="split sheet.png -r 2 -c 2 -o ./out"
```

## Architecture

DDD layered architecture under `src/ai_rpg_world/`:

```
presentation/   ← FastAPI servers, WebSocket, REST endpoints
application/    ← Use cases, DTOs, LLM orchestration, observation pipeline
domain/         ← Aggregates, entities, value objects, repository interfaces
infrastructure/ ← Repository implementations (in-memory + SQLite), LLM adapters
```

### Bounded Contexts (domain/)

16 contexts: `world_graph` (spot graph navigation), `world` (physical map/weather), `player` (profile, status, inventory), `item`, `monster`, `combat`, `skill`, `shop`, `trade`, `quest`, `guild`, `sns` (in-world social network), `conversation`, `pursuit`, `common`.

Each context owns its aggregates, value objects, exceptions, and repository interfaces. Infrastructure provides both `InMemory*Repository` and `Sqlite*Repository` implementations.

### LLM Agent Turn Flow

1. Agent scheduled for turn → gather current state + recent events
2. `prompt_builder.py` constructs system prompt (persona) + user prompt (situation)
3. `litellm` client calls LLM with tool_use mode
4. Tool calls parsed and executed (move, attack, trade, recall memory, etc.)
5. Domain events emitted → converted to observations → fed into episodic memory
6. WebSocket broadcasts scene updates

Key files: `application/llm/llm_agent_turn_runner.py`, `application/llm/prompt_builder.py`, `application/llm/tool_catalog/`.

### Episodic Memory System

Active development area. Domain events become structured observations, chunked into episodes, reinterpreted for subjective significance, and recalled passively as context cues for future turns.

Key dirs: `application/llm/chunk_boundary/`, `application/llm/contracts/`, `application/observation/`.

## Conventions

- Python 3.10+, 4-space indent, `snake_case` functions/modules, `PascalCase` classes
- Type hints required on public APIs
- Tests mirror package structure under `tests/` (e.g., `tests/domain/shop/value_object/test_shop_id.py`)
- Conventional Commits: `feat:`, `fix:`, `refactor:`, etc.
- Secrets in `.env` only (copy from `.env.example`), never committed
- LLM client via `litellm` abstraction (supports OpenAI, Anthropic, etc.)

## PR Workflow

- PRs are mandatory before merge (`gh pr create`)
- 1 PR = 1 purpose; keep changes ~200-400 lines
- Include test evidence in PR description
- Feature branches use git worktrees for parallel work per `docs/memory_system/memory_feature_workflow.md`

## Parallel Branch Note

`feature/observation-trace-runtime-context` (observation trace / `application/llm/wiring`) と `LlmJsonEpisodeEncoder` を同時に触る場合、`wiring/__init__.py` の競合を避けるため観測trace側を先にマージすること。
