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
| **Phase 4** | ToolArgumentResolver のツール別分割 | 🔲 未着手（ロードマップ 2.1） |
| **Phase 5** | ToolDefinitions のカテゴリ別分割 | 🔲 未着手（ロードマップ 3.7） |
| **Phase 6** | UiContextBuilder のラベル生成と描画分離 | 🔲 未着手（ロードマップ 3.8） |

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

### 3.3 Phase 4: ToolArgumentResolver のツール別分割

**親ロードマップ**: 2.1

**目的**: `DefaultToolArgumentResolver` を movement / world / combat / quest 等の小さな resolver に分割し、`DefaultToolArgumentResolver` は tool_name → resolver の委譲に留める。

**wiring との関係**: wiring は `DefaultToolArgumentResolver` をそのまま利用。分割後もインターフェースが変わらなければ wiring 変更は不要。

---

### 3.4 Phase 5: ToolDefinitions のカテゴリ別分割

**親ロードマップ**: 3.7

**目的**: `tool_definitions.py` を `tool_catalog/movement.py`, `world.py`, `social.py`, `memory.py` 等に分割。

**wiring との関係**: `register_default_tools()` の呼び出し箇所は wiring。分割後は「spec 群を集めて登録」の形になり、呼び出し側の変更は軽微な想定。

---

### 3.5 Phase 6: UiContextBuilder のラベル生成と描画分離

**親ロードマップ**: 3.8

**目的**: `LabelAllocator`, `RuntimeTargetCollector`, `SectionRenderer` に責務を分離。

**wiring との関係**: wiring は `DefaultLlmUiContextBuilder` を PromptBuilder 経由で利用。インターフェースが維持されれば wiring の変更は不要。

---

## 4. 参照

- [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md) - 全体のロードマップ
- [tool_command_mapper_refactoring_plan.md](./tool_command_mapper_refactoring_plan.md) - ToolCommandMapper の既存計画
