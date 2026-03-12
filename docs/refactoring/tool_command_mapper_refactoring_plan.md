# ToolCommandMapper リファクタリング計画

## 背景

`ToolCommandMapper` は多数のサービスを直接注入しており、約905行・23個以上の依存・35個の実行メソッドを持つ巨大クラスになりつつある。将来の拡張性と保守性のため、ファサード・振る舞い別サブマッパーへの分割を段階的に進める。

## 方針

- **段階的リファクタリング**: 一括変更を避け、小さく安全に進める
- **後方互換性**: 公開 API（`execute(player_id, tool_name, arguments)`）は維持
- **競合回避**: 別エージェントが実装中のギルド関連ツールには一切触れない

## フェーズ一覧

### Phase 1: 共通ヘルパーの抽出（先行実施）

**目的**: 重複している `_unknown_tool` / `_exception_result` を共通化し、サブマッパーでの再利用を可能にする。

**成果物**:
- `tool_executor_helpers.py`: `unknown_tool(message)`, `exception_result(e)` をモジュール関数として提供

**変更箇所**:
- 新規: `src/ai_rpg_world/application/llm/services/tool_executor_helpers.py`
- 修正: `tool_command_mapper.py` がヘルパーを import して利用

---

### Phase 2: パイロットとして TodoToolExecutor を抽出

**目的**: サブマッパー分離のパターンを確立する。Todo はギルドと無関係で、3ツールのみで影響範囲が小さい。

**成果物**:
- `executors/todo_executor.py`: `TodoToolExecutor` クラス
  - `get_handlers() -> Dict[str, Callable]` でツール名→ハンドラの辞書を返す
  - `_execute_todo_add`, `_execute_todo_list`, `_execute_todo_complete` を保有

**変更箇所**:
- 新規: `src/ai_rpg_world/application/llm/services/executors/todo_executor.py`
- 修正: `tool_command_mapper.py` が `TodoToolExecutor` を組み込み、`_executor_map` にマージ

---

### Phase 3: その他のサブマッパー抽出（将来）

ギルド以外のグループを順次抽出。**ギルドは最後**（他エージェントの作業完了を待つ）。

| 優先度 | グループ | 対象ツール | 依存 |
|--------|----------|------------|------|
| 3a | Memory | memory_query, subagent, working_memory_append | memory_query_executor, subagent_runner, working_memory_store |
| 3b | Speech | whisper, say | speech_service |
| 3c | Quest | accept, cancel, approve | quest_service |
| 3d | Shop | purchase, list_item, unlist_item | shop_service |
| 3e | Trade | offer, accept, cancel | trade_service |
| 3f | Movement | to_destination, pursuit_start, pursuit_cancel | movement_service, pursuit_service |
| 3g | World | inspect_item, inspect_target, interact, place, destroy, drop, chest, change_attention, conversation, combat | 複数サービス・リポジトリ |
| 3h | Guild | create, add_member, change_role, disband, leave, deposit_bank, withdraw_bank | guild_service ← **最後** |

---

### Phase 4: ファサード化（将来検討）

`ToolCommandMapper` を薄いファサードにし、`executors/` 配下のサブマッパーをまとめるだけの役割にする。wiring での注入は「各 Executor に必要なサービスだけ渡す」形に簡素化できる。

---

## 競合回避の注意

- **ギルド関連**: `_execute_guild_*`, `guild_service`, `TOOL_NAME_GUILD_*` に一切触れない
- 計画・実装ともに Guild を Phase 3h（最後）に据え、他エージェントの作業完了後に実施

---

## 進捗

| Phase | 状態 | 備考 |
|-------|------|------|
| 1 | ✅ 実施済み | tool_executor_helpers 追加 |
| 2 | ✅ 実施済み | TodoToolExecutor 抽出・統合 |
| 3 | ✅ ほぼ実施 | 3a〜3g 実施済み（Memory, Speech, Quest, Shop, Trade, Movement, World）。3h Guild は未着手（他エージェント作業待ち）。executors: memory_executor, movement_executor, quest_executor, shop_executor, speech_executor, trade_executor, world_executor |
| 4 | 未着手 | ファサード化 |
