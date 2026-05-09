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

### ドメイン層では組み込み例外ではなくドメイン例外を投げる

`domain/` 配下のバリデーション・不変条件違反では、`ValueError` 等の組み込み例外ではなく、
そのバウンデッドコンテキストのドメイン例外を投げる。

- 各コンテキストの `domain/<context>/exception/<context>_exception.py` に集約された例外群を使う
- 既存パターン: `<Context>DomainException` を基底に `ValidationException` / `BusinessRuleException` /
  `NotFoundException` などのカテゴリと多重継承し、`error_code` 属性を持たせる（例:
  `WORLD_GRAPH.AMBIENT_SOUND_DEF_VALIDATION`）
- 新しいエラーケースを追加する場合は、まず既存ファイルに新しい例外クラスを追加してから値オブジェクト・
  集約側で使用する
- `application/` 層・`infrastructure/` 層では `ValueError` / `TypeError` 等の組み込み例外も許容する
  （引数チェックなど）

参考: `src/ai_rpg_world/domain/world_graph/exception/spot_graph_exception.py`

### テストには日本語のドックストリングを付ける

テストクラスとテストメソッドには、何を保証するテストか一目で分かる 1 行の日本語ドックストリングを付ける。

- クラスドックストリング: 対象クラス・対象機能の挙動の概要（例: `"""SpotDarknessQueryService.is_dark の合成判定挙動。"""`）
- メソッドドックストリング: そのテストが保証する具体的な振る舞いを「〜する／〜される／〜が返る／〜を投げる」形式で記述
  （例: `"""ticks_per_day が 0 以下なら ValidationException を投げる。"""`）
- 既存のテストファイル全体の文体（です・ます調 vs 体言止め）に合わせる。新規ファイルは体言止め推奨

## PR Workflow

- PRs are mandatory before merge (`gh pr create`)
- 1 PR = 1 purpose; keep changes ~200-400 lines
- Include test evidence in PR description
- Feature branches use git worktrees for parallel work per `docs/memory_system/memory_feature_workflow.md`

### PR タイトル・本文の書き方

PR タイトルと本文は、コードを読まずに「何が enable されるか」「なぜ要るか」が一読で分かることを最優先にする。レビュアーや将来の自分が PR ハンドルだけ眺めて把握できる粒度を保つ。

**タイトル**:
- 「**何ができるようになるか**」を素直な日本語で書く。`feat: <日本語の主旨>` の形式を推奨
- 専門用語の英語をそのまま並べない（NG: `feat: cross-instance interaction の domain primitive`）
- 一読で分からない英語概念は日本語に置き換える（例: `cross-instance interaction` → 「物Aを物Bに使う相互作用」、`primitive` → 「基盤機能」、`reactive binding` → 「条件連動の状態書き換え」）

**本文**:
- 概念説明・設計判断・効果は日本語ベースで書く
- セクション構成は #93 形式: 「なぜ」「何を」「設計判断」「試験」「Test plan」「マージ後の予定」
- 「なぜ」は「現状で書けないこと」「先送りすると何が困るか」を具体例で示す
- **コード識別子・API 名・enum 値・既存技術用語はコード上の実名（英語）のまま残す**
  （例: `CHANGE_TARGET_ITEM_INSTANCE_STATE`, `apply_effects`, `Mapping[ItemSpecId, int]`）。
  翻訳すると grep やコード参照との対応関係が崩れて検索性が下がる
- 「acting / target」など複数の PR で繰り返し使う概念には日本語の訳語を一貫させる
  （例: 「使う側 / 使われる側」）
- 「primitive / interaction / wiring / silent failure」のような英語の業界用語は、
  初出で日本語の説明を添える（例: 「primitive（基盤機能）」「silent failure（黙って失敗）」）

**訳語マッピング例**:

| 英語表現 | 日本語訳 |
|---|---|
| primitive | 基盤機能 |
| cross-instance interaction | 二者間の相互作用 / 物Aを物Bに使う相互作用 |
| reactive binding | 条件連動の状態書き換え |
| acting / target | 使う側 / 使われる側 |
| wiring | 配線 / 接続 |
| silent failure | 黙って失敗 / 静かに無視 |
| boundary | 入口 / 境界 |
| guard | ガード |

## Parallel Branch Note

`feature/observation-trace-runtime-context` (observation trace / `application/llm/wiring`) と `LlmJsonEpisodeEncoder` を同時に触る場合、`wiring/__init__.py` の競合を避けるため観測trace側を先にマージすること。
