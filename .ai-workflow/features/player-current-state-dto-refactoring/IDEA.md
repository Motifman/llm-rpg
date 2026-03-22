---
id: feature-player-current-state-dto-refactoring
title: PlayerCurrentStateDto の段階分割と互換維持リファクタリング
slug: player-current-state-dto-refactoring
status: idea
created_at: 2026-03-23
updated_at: 2026-03-23
source: flow-idea
branch: null
related_idea_file: null
---

# Goal

- `PlayerCurrentStateDto` の肥大化を抑え、**責務ごとの小さな read model** に分割できる形へ寄せる。
- ただし一気に置き換えるのではなく、**LLM 向け既存契約を壊さず**に段階移行できるリファクタリング方針を定める。
- 将来 SNS / Trade / 他アプリ状態が増えても、`PlayerCurrentStateDto` に属性を足し続けなくてよい構造を目指す。

# Success Signals

- `availability_resolvers`、`ui_context_builder`、formatter 群の既存利用を大きく壊さず、**内側の責務分割**を始められる。
- `PlayerCurrentStateBuilder` の組み立て責務が、**world state / runtime context / app session state** などの単位に分けて説明できる。
- SNS / Trade のような追加コンテキストを、`PlayerCurrentStateDto` のトップレベル属性を増やす代わりに、**専用サブ DTO または専用コンテキスト**として扱う方針が定義される。
- plan 時に、**互換レイヤをどこに置くか**と**段階的削除の順序**が決められる。

# Non-Goals

- `PlayerCurrentStateDto` をこの段階で即廃止すること。
- `availability_resolvers`、prompt formatter、各種テストを**一括で全面書き換え**ること。
- SNS / Trade のモード仕様そのものを再設計すること。

# Problem

1. `PlayerCurrentStateDto` が、位置・天候・地形・視界・移動候補・所持品・会話・クエスト・ギルド・ショップ・取引・SNS/Trade 画面状態まで持っており、**単一 DTO の責務が広すぎる**。
2. `PlayerCurrentStateBuilder` もそれに引きずられ、**world state の組み立て**と**runtime UI/LLM 用コンテキストの組み立て**と**アプリ画面セッションの吸い上げ**を 1 つの返却 DTO に集約している。
3. `availability_resolvers` と `ui_context_builder` が `PlayerCurrentStateDto` のトップレベル属性へ直接依存しており、DTO の肥大化が**利用側の結合**も強めている。
4. 最近の SNS / Trade 追加でも `active_game_app`、`sns_virtual_page_kind`、`trade_current_page_snapshot_json` などが同 DTO に積み増されており、今後も同じ増え方をすると**DTO がモード管理の受け皿**になり続ける。

# Constraints

- **互換優先**: ユーザー合意として、まず重視するのは **LLM 向け互換維持**。既存 formatter / resolver 契約を急に壊さない。
- **既存コードの依存先が多い**: `availability_resolvers.py`、`ui_context_builder.py`、`current_state_formatter` 系、`world_query_service` テスト群などで直接参照が多い。
- **builder は既に部分分離の芽がある**: `PlayerRuntimeContextBuilder` があり、inventory / quest / guild / trade / skill などは別 facade へ一部退避されている。全面再設計より、**この延長で分割を進める**のが自然。
- **モード状態は増えやすい**: SNS / Trade の page snapshot 類は今後も派生しやすいため、トップレベル属性のままでは拡張コストが高い。

# Code Context

| 領域 | モジュール・観測 |
|------|------------------|
| 肥大化した DTO 本体 | `src/ai_rpg_world/application/world/contracts/dtos.py` の `PlayerCurrentStateDto` |
| DTO 組み立て | `src/ai_rpg_world/application/world/services/player_current_state_builder.py` |
| runtime context の部分分離 | `src/ai_rpg_world/application/world/services/player_runtime_context_builder.py` |
| 利用可否判定の直接依存 | `src/ai_rpg_world/application/llm/services/availability_resolvers.py` |
| UI ラベル・ref 文脈の直接依存 | `src/ai_rpg_world/application/llm/services/ui_context_builder.py` |
| 既存テストの依存 | `tests/application/world/services/test_world_query_service.py`、`tests/application/llm/test_availability_resolvers.py`、`tests/application/llm/test_ui_context_builder.py` ほか |

**調査メモ**:

- `PlayerCurrentStateDto` は現在、少なくとも以下の塊を同居させている。
  - **World state**: current spot, coordinates, weather, terrain, visible objects, moves
  - **Runtime context**: inventory, chest, conversation, harvest, skills, quests, guild, shop, trade summaries
  - **App session state**: `active_game_app`, SNS page 状態、Trade page 状態
- `PlayerRuntimeContextBuilder` は既に supplemental builder への facade であり、**runtime context の外出し先として使える足場**になっている。
- 一方で `availability_resolvers` は `context.inventory_items` や `context.available_trades`、`context.sns_virtual_page_kind` を直接見るため、**分割するなら adapter/compat property が必要**になる。
