# LLM Wiring Phase 2 実装のための調査と明確化事項

## 1. 事前確認: リファクタリングプランについて

**重要**: `docs/refactoring/llm-wiring-refactoring-plan.md` はリポジトリ内に**存在しません**。

現存する refactoring 関連ドキュメント:
- `docs/refactoring/tool_command_mapper_refactoring_plan.md` — ToolCommandMapper 用（Phase 2 は TodoToolExecutor 抽出で**実施済み**）
- `docs/world_query_status_and_llm_context_design.md` — 観測配信の Phase 1〜4（Phase 2 は「配信先の決定（同じスポット）」）
- `docs/llm_agent_prompt_and_memory_implementation_plan.md` — LLM エージェント用（Phase 1〜3 は**実施済み**）

**明確化が必要**: Phase 2 の対象を特定するため、以下のいずれかを決める必要があります。

- **A**: 新規に `llm-wiring-refactoring-plan.md` を作成し、その中の Phase 2 を実装する  
- **B**: 既存ドキュメント内の Phase 2 のいずれかを参照する（後述の解釈候補）  
- **C**: 別途 GitHub Issue 等で定義されている Phase 2 仕様がある  

---

## 2. Phase 2 の解釈候補

### 2.1 解釈 A: world_query_status Phase 2（配信先の決定・同じスポット）

**参照**: `docs/world_query_status_and_llm_context_design.md` Phase 2

**内容**: PlayerLocationChangedEvent を購読し、`new_spot_id` にいる他プレイヤーを列挙して配信先を決定する。

**現状**: **すでに実装済み**。`DefaultRecipientStrategy._resolve_player_location_changed` が同ロジックを実装している。

```python
# default_recipient_strategy.py:158-164
def _resolve_player_location_changed(self, event: PlayerLocationChangedEvent, add) -> None:
    add(event.aggregate_id)
    for pid in self._players_at_spot(event.new_spot_id):
        add(pid)
```

**結論**: この解釈の場合、Phase 2 の実装は完了しており、追加実装は不要。

---

### 2.2 解釈 B: create_llm_agent_wiring のリファクタリング（推奨解釈）

**内容**: `create_llm_agent_wiring` が約 350 行・60 超パラメータの巨大関数になっているため、Phase 2 で構成を分割・簡素化する。

**現状の構成（wiring/__init__.py）**:
- 必須引数: 6 個（player_status_repository, physical_map_repository, world_query_service, movement_service, player_profile_repository, unit_of_work_factory）
- オプション引数: 40 個以上
- 組み立てるコンポーネント: buffer, formatters, memory stores, game_tool_registry, tool_command_mapper, prompt_builder, orchestrator, turn_runner, observation_resolver, observation_handler, observation_registry

**Phase 1 が何か**: 明確なプランが存在しないため推測になるが、例えば以下のような切り出しが Phase 1 と解釈され得る:
- `_llm_client_factory.py` への LLM クライアント生成の分離（既存）
- 環境変数経由の memory_db_path / view_distance の扱いの整理

**Phase 2 の想定内容（解釈 B）**:
- サブアセンブリの抽出（例: メモリ組み立て、ツール組み立て、観測組み立てなど）
- パラメータのグループ化（例: `LlmWiringConfig` などの DTO や Builder パターン）

---

### 2.3 解釈 C: ToolCommandMapper の Phase 4（wiring への波及）

**参照**: `docs/refactoring/tool_command_mapper_refactoring_plan.md` Phase 4

**内容**: ToolCommandMapper をファサード化し、wiring での注入を「各 Executor に必要なサービスだけ渡す」形に簡素化する。

**現状**: Phase 4 は未着手。Phase 3 の Guild（3h）も未実施。

**結論**: この解釈の場合、Phase 3h（Guild）完了後に Phase 4 に着手する前提となる。

---

## 3. コードベースの調査結果（wiring まわり）

### 3.1 wiring のエントリポイント

| モジュール | 役割 |
|-----------|------|
| `wiring/__init__.py` | `create_llm_agent_wiring()` — メインの組み立て関数 |
| `wiring/_llm_client_factory.py` | `create_llm_client_from_env()`, `create_subagent_invoke_text()` |
| `bootstrap.py` | `compose_llm_runtime()` — wiring + Composition + Service の上位窓口 |

### 3.2 create_llm_agent_wiring の依存フロー（簡略）

```
必須: player_status_repository, physical_map_repository, world_query_service,
      movement_service, player_profile_repository, unit_of_work_factory

オプション多数 → register_default_tools(), ToolCommandMapper(), PromptBuilder(),
              ObservationFormatter(), create_observation_recipient_resolver(), ...
```

### 3.3 観測パイプラインとの接続

- `create_observation_recipient_resolver()`: wiring 内で呼ばれ、複数の IRecipientResolutionStrategy を登録
- `ObservationFormatter`: spot_repository, player_profile_repository, item_spec_repository 等を注入
- `ObservationEventHandler`: resolver, formatter, buffer, turn_trigger, llm_player_resolver 等を受け取る

### 3.4 テスト

- `tests/application/llm/test_llm_wiring.py` — 単体・境界・例外
- `tests/application/llm/test_llm_wiring_integration.py` — 統合・bootstrap・pursuit 等

---

## 4. 明確にすべき事項一覧

### 4.1 スコープ・対象の明確化

| # | 事項 | 選択肢 | おすすめ |
|---|------|--------|----------|
| 1 | Phase 2 の対象 | A: world_query Phase 2 / B: wiring リファクタ / C: ToolCommandMapper Phase 4 | **B**（wiring リファクタ。世界観・影響範囲が最も大きい） |
| 2 | 公式プラン文書 | 新規作成 / 既存ドキュメント参照 / Issue 参照 | 新規に `llm-wiring-refactoring-plan.md` を作成し、Phase 定義を固定する |

### 4.2 解釈 B を採用する場合の設計判断

| # | 事項 | 選択肢 | おすすめ |
|---|------|--------|----------|
| 3 | パラメータのグループ化 | 現状維持 / Dataclass でグループ化 / Builder パターン | **Dataclass でグループ化**（例: `MemoryWiringConfig`, `ToolWiringConfig` など）。段階的に導入可能 |
| 4 | サブアセンブリの粒度 | 1 関数で全組み立て / 責務別に 3〜5 関数に分割 / 完全な Builder クラス | **責務別に 3〜5 関数に分割**（例: `_build_memory_components`, `_build_tool_components`, `_build_observation_components`） |
| 5 | 後方互換性 | create_llm_agent_wiring のシグネチャは維持 / 新しい API を追加して旧 API を deprecated | **シグネチャは維持**。内部実装だけ分割し、既存呼び出しを壊さない |
| 6 | テスト戦略 | 既存テストのみで担保 / 分割した各関数にユニットテスト追加 | **既存テストで担保**。大規模変更時のみ分割関数のユニットテストを追加 |

### 4.3 解釈 A（world_query Phase 2）を採用する場合

| # | 事項 | 選択肢 | おすすめ |
|---|------|--------|----------|
| 7 | 既存実装との関係 | そのまま完了とみなす / 仕様の厳密な検証を追加 | **そのまま完了とみなす**。必要なら仕様検証用のテストを追加 |

### 4.4 解釈 C（ToolCommandMapper Phase 4）を採用する場合

| # | 事項 | 選択肢 | おすすめ |
|---|------|--------|----------|
| 8 | Phase 3h（Guild）の扱い | 先に実施 / wiring 変更は 3h と並行 / 3h 完了を待つ | **3h 完了を待つ**。計画上の方針に従う |
| 9 | wiring 変更の範囲 | ツール注入のみ / 観測・プロンプト等も含めた全体 | **ツール注入のみ**。影響範囲を限定 |

### 4.5 横断事項

| # | 事項 | 選択肢 | おすすめ |
|---|------|--------|----------|
| 10 | 競合する作業 | Guild 関連に触れない / 他の Phase と調整する | **Guild 関連には触れない**（tool_command_mapper_refactoring_plan の方針） |
| 11 | 環境変数・設定 | 現状維持 / 設定オブジェクトに集約 | **現状維持**。将来的な集約は別フェーズで検討 |

---

## 5. 推奨アクション

1. **Phase 2 の対象を確定する**: 解釈 A/B/C のどれを採用するか決定する。
2. **公式プランを作る**: `llm-wiring-refactoring-plan.md` を新規作成し、Phase 1（実施済み）と Phase 2（これから）の内容を明文化する。
3. **解釈 B 採用時**:
   - `_build_memory_components(**kwargs) -> tuple`
   - `_build_tool_components(**kwargs) -> tuple`
   - `_build_observation_components(**kwargs) -> tuple`
   のような内部関数に分割し、`create_llm_agent_wiring` から呼び出す形で進める。
4. **解釈 A 採用時**: Phase 2 は完了として扱い、必要に応じて DefaultRecipientStrategy の仕様検証テストを追加する。
5. **解釈 C 採用時**: Phase 3h 完了後、ToolCommandMapper のファサード化と wiring のツール注入簡素化を実施する。

---

## 6. 次のステップ

1. 上記 4.1〜4.5 の事項について、チーム内で決定する。
2. 採用した解釈に基づき、`llm-wiring-refactoring-plan.md` を作成または更新する。
3. その内容に沿って Phase 2 の実装を進める。

---

*本ドキュメントは、LLM Wiring Phase 2 の調査結果と明確化が必要な事項をまとめたものです。*
