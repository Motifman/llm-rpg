# LLM Wiring リファクタリング計画

`create_llm_agent_wiring` および関連モジュールの段階的リファクタリング計画。
親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md)

---

## 1. フェーズの整理

本計画では LLM wiring 関連の作業を次のように区切る。

| フェーズ | 内容 | 状態 |
|----------|------|------|
| **Phase 1** | メモリストア選択の composition root 外だし | ✅ 完了 |
| **Phase 2** | composition root の factory 関数分割 | ✅ 完了 |
| **Phase 3** | ToolCommandMapper の handler map を wiring へ移行 | ✅ 完了 |
| **Phase 4** | ToolArgumentResolver のツール別分割 | ✅ 完了 |
| **Phase 5** | ToolDefinitions のカテゴリ別分割 | ✅ 完了 |
| **Phase 6** | UiContextBuilder のラベル生成と描画分離 | ✅ 完了（2026-03-14） |

---

## 2. 完了済み: Phase 1

- **実施日**: 2026-03-13
- **対象**: `create_llm_agent_wiring` のメモリストア選択ロジック
- **成果物**:
  - `infrastructure/llm/_memory_store_factory.py` を新規追加
  - `create_episode_memory_store()`, `create_long_term_memory_store()`, `create_reflection_state_port()` を提供
  - wiring から Sqlite* の直接 import を削除し、ファクトリ経由に変更
- **テスト**: `tests/infrastructure/llm/test_memory_store_factory.py` で 18 件の正常・境界・例外ケースをカバー

---

## 3. 今後やるべきこと: Phase 3 以降

### 3.1 完了済み: Phase 2（composition root の factory 関数分割）

- **実施日**: 2026-03-13
- **目的**: `create_llm_agent_wiring` を薄い composition root に縮小し、責務ごとの factory 関数に分割する。
- **成果物**:
  - `_build_memory_stack()` - episode / long_term / reflection / working / todo / handle の構築
  - `_build_reflection_stack()` - reflection_service, reflection_runner の構築
  - `_build_prompt_stack()` - predictive_retriever, prompt_builder の構築
  - `_build_tool_stack()` - register_default_tools, available_tools_provider, tool_command_mapper, tool_argument_resolver
  - `_build_observation_stack()` - observation_resolver, formatter, handler, registry
- **テスト**: `tests/application/llm/wiring/test_build_*.py`（memory, reflection, prompt, tool, observation）で各スタックの戻り値と統合を検証

---

### 3.2 完了済み: Phase 3（ToolCommandMapper の handler map を wiring へ移行）

- **実施日**: 2026-03-14
- **目的**: ToolCommandMapper を「tool_name → handler の辞書を受け取り実行するだけ」にし、handler map の組み立てを wiring 側に移す。
- **成果物**:
  - `_build_tool_handler_map()` - Executor 群を組み立て、tool_name → handler の辞書を返す（wiring 内）
  - `ToolCommandMapper(handler_map)` - handler_map のみを受け取り、execute のみを担当
  - `tests/application/llm/conftest.py` - テスト用 `_create_tool_command_mapper` ヘルパー
- **変更箇所**:
  - `src/ai_rpg_world/application/llm/services/tool_command_mapper.py` - コンストラクタを handler_map のみに変更
  - `src/ai_rpg_world/application/llm/wiring/__init__.py` - `_build_tool_handler_map` 追加、`_build_tool_stack` で handler map を構築して渡す
  - `tests/application/llm/test_tool_command_mapper.py` - `_create_tool_command_mapper` 経由に変更
  - `tests/application/llm/test_agent_orchestrator.py`, `test_llm_turn_trigger.py`, `test_llm_agent_turn_runner.py`, `test_memory_tools_integration.py` - 同様にヘルパー使用

---

### 3.3 完了済み: Phase 4（ToolArgumentResolver のツール別分割）

- **実施日**: 2026-03-14
- **親ロードマップ**: 2.1
- **目的**: `DefaultToolArgumentResolver` を movement / world / combat / quest / guild_shop_trade の小さな resolver に分割し、`DefaultToolArgumentResolver` は tool_name → resolver の委譲に留める。
- **成果物**:
  - `_resolver_helpers.py` - `require_target`, `require_target_type`, `safe_int`, `resolve_direction_from_context` を純関数として提供。`ToolArgumentResolutionException` を定義
  - `quest_objective_target_resolver.py` - クエスト目標の target_name → target_id 解決を担当
  - `_argument_resolvers/` パッケージ - MovementArgumentResolver, WorldArgumentResolver, CombatSkillArgumentResolver, QuestArgumentResolver, GuildShopTradeArgumentResolver
  - `DefaultToolArgumentResolver` は各サブリゾルバを順に試し、最初に返された結果を使用
- **テスト**:
  - `tests/application/llm/test_tool_argument_resolver.py` - 71 件（統合テスト、既存パターン維持）
  - `tests/application/llm/services/test_resolver_helpers.py` - 26 件（正常・例外ケース網羅）
  - `tests/application/llm/services/test_quest_objective_target_resolver.py` - 17 件（正常・例外ケース網羅）
- **wiring との関係**: wiring は `DefaultToolArgumentResolver` をそのまま利用。インターフェース変更なしのため wiring 変更不要。

---

### 3.4 完了済み: Phase 5（ToolDefinitions のカテゴリ別分割）

- **実施日**: 2026-03-14
- **親ロードマップ**: 3.7
- **目的**: `tool_definitions.py` をカテゴリ別 `tool_catalog/` パッケージに分割。
- **成果物**:
  - `tool_catalog/movement.py` - no_op, move_to_destination, move_one_step, cancel_movement
  - `tool_catalog/pursuit.py` - pursuit_start, pursuit_cancel
  - `tool_catalog/speech.py` - whisper, say
  - `tool_catalog/world.py` - interact, harvest, inspect, attention, conversation, place, drop, chest（flag 別に条件登録）
  - `tool_catalog/combat.py` - combat_use_skill, skill_equip, skill_accept/reject_proposal, skill_activate_awakened
  - `tool_catalog/quest.py` - quest_accept, cancel, approve, issue
  - `tool_catalog/guild.py` - guild_* 7種
  - `tool_catalog/shop.py` - shop_purchase, shop_list_item, shop_unlist_item
  - `tool_catalog/trade.py` - trade_offer, accept, cancel, decline
  - `tool_catalog/sns.py` - sns_* 10種（SnsToolAvailabilityResolver 共有）
  - `tool_catalog/memory.py` - memory_query, subagent, todo_add, todo_list, todo_complete, working_memory_append
  - `tool_catalog/__init__.py` - `register_default_tools()` を実装し、各 get_*_specs() を集約
- **削除**: `tool_definitions.py`（後方互換なし、参照元を tool_catalog に変更）
- **更新**: `services/__init__.py`, `wiring/__init__.py`, `test_tool_definitions.py`, `test_available_tools_provider.py`, `test_prompt_builder.py`, `scripts/demo_llm_*.py`
- **テスト**: `tests/application/llm/test_tool_definitions.py` - 定義内容・register_default_tools の正常・例外ケースを検証。pytest tests/application/llm/ で 977 件 PASSED

---

### 3.5 完了済み: Phase 6（UiContextBuilder のラベル生成と描画分離）

- **実施日**: 2026-03-14
- **親ロードマップ**: 3.8
- **目的**: `LabelAllocator`, `RuntimeTargetCollector` に責務を分離し、ロケーションとショップ出品の prefix を分離。
- **成果物**:
  - `_label_allocator.py` - `LabelAllocator`, `SectionBuildResult`, `DEFAULT_LABEL_PREFIXES`
  - `_runtime_target_collector.py` - `RuntimeTargetCollector`
  - `DefaultLlmUiContextBuilder` を `LabelAllocator` と `RuntimeTargetCollector` でリファクタリング
  - ロケーション（同一スポット内エリア）の prefix を `L` から `LA` に変更（ショップ出品 `L` と衝突解消）
- **テスト**:
  - `test_label_allocator.py` - SectionBuildResult / LabelAllocator の正常・例外ケース
  - `test_runtime_target_collector.py` - RuntimeTargetCollector の正常・例外ケース
  - `test_ui_context_builder.py` - 入力検証（TypeError）テストを追加
- **wiring との関係**: `ILlmUiContextBuilder` インターフェースは維持のため wiring 変更不要。`system_prompt_builder` と `movement` ツールの説明を LA 対応に更新。

---

## 4. 参照

- [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md) - 全体のロードマップ
- [tool_command_mapper_refactoring_plan.md](./tool_command_mapper_refactoring_plan.md) - ToolCommandMapper の既存計画
