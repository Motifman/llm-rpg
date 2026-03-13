# LLM Wiring リファクタリング計画

`create_llm_agent_wiring` および関連モジュールの段階的リファクタリング計画。
親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md)

---

## 1. フェーズの整理

本計画では LLM wiring 関連の作業を次のように区切る。

| フェーズ | 内容 | 状態 |
|----------|------|------|
| **Phase 1** | メモリストア選択の composition root 外だし | ✅ 完了 |
| **Phase 2** | composition root の factory 関数分割 | 🔲 未着手 |
| **Phase 3** | ToolCommandMapper の handler map を wiring へ移行 | 🔲 未着手 |
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

## 3. 今後やるべきこと: Phase 2 以降

### 3.1 Phase 2: composition root の factory 関数分割（最優先）

**目的**: `create_llm_agent_wiring` を薄い composition root に縮小し、責務ごとの factory 関数に分割する。

**方針**: 同一ファイル (`wiring/__init__.py`) 内に `_build_*` プライベート関数を追加。  
別モジュールや deps オブジェクトは使わず、1 つずつ切り出す。

**着手順序**（影響範囲が小さい順）:

| 順 | 関数名 | 責務 | 依存 | リスク |
|----|--------|------|------|--------|
| 1 | `_build_memory_stack()` | episode / long_term / reflection / working / todo / handle の構築 | memory_db_path, 各種 store 引数 | 低（既にファクトリ利用済み） |
| 2 | `_build_reflection_stack()` | reflection_service, reflection_runner の構築 | memory stack, world_time_config, player_status, llm_player_resolver | 低 |
| 3 | `_build_prompt_stack()` | predictive_retriever, prompt_builder の構築 | buffer, sliding_window, available_tools_provider 等 | 低 |
| 4 | `_build_tool_stack()` | register_default_tools, available_tools_provider, tool_command_mapper, tool_argument_resolver | 多数の service（約 25 個） | 中 |
| 5 | `_build_observation_stack()` | observation_resolver, formatter, handler, registry | llm_turn_trigger（後段で構築）等 | 中 |

**各ステップの進め方**:
1. 対象ブロックを `_build_*` に切り出す
2. テスト実行（`pytest tests/application/llm/test_llm_wiring*.py -v`）
3. 問題なければコミット
4. 次の関数へ

---

### 3.2 Phase 3: ToolCommandMapper の handler map を wiring へ移行

**目的**: ToolCommandMapper を「tool_name → handler の辞書を受け取り実行するだけ」にし、handler map の組み立てを wiring 側に移す。

**既存計画**: `docs/refactoring/tool_command_mapper_refactoring_plan.md` を参照。

**Phase 2 との関係**: Phase 2 の `_build_tool_stack()` 実装時に、handler map の組み立てを wiring 側で行う形に寄せることで、Phase 3 と統合することも可能。  
あるいは Phase 2 完了後に別コミットで実施。

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
