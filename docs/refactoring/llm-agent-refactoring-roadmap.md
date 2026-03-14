# LLM エージェント・コードベース リファクタリングロードマップ

LLMツールが出揃った時点での区切りとして、リファクタリングすべき箇所を優先度順に整理した文書です。小分けにした単位で取り組み、完了したらチェックを付けてください。

**調査日**: 2026-03-13  
**対象**: application/llm, application/observation, application/world, domain の巨大モジュール群

---

## 目次

1. [最優先（Phase 1）](#1-最優先phase-1)
2. [優先度高（Phase 2）](#2-優先度高phase-2)
3. [次点だが効果大（Phase 3）](#3-次点だが効果大phase-3)
4. [着手順序の推奨](#4-着手順序の推奨)
5. [追記・変更履歴](#5-追記変更履歴)

---

## 1. 最優先（Phase 1）

### 1.1 WorldSimulationService の tick 責務分割

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- **テスト**: `tests/application/world/services/test_world_simulation_service.py` (約3508行)

**問題点**:
- `_tick_impl()` が天候同期、継続移動、採取完了、環境効果、スポーン/リスポーン、飢餓移住、モンスターAI、HitBox更新、LLM/Reflection起動まで一括で担当
- コンストラクタに 27 個以上の依存があり、変更の波及先が広い
- `_process_hunger_migration_for_spot()` では「飢餓が最も高い1体を1tickに1体だけ移住させる」という業務ルールがアプリ層に存在

**分割案**:
- `WorldSimulationApplicationService` は facade として残す
- 以下に責務を分離:
  - `EnvironmentTickService`（天候・環境効果）
  - `PlayerMovementTickService`（継続移動）
  - `HarvestAutoCompletionService`（採取完了）
  - `MonsterLifecycleTickService`（スポーン/リスポーン、飢餓・寿命）
  - `MonsterBehaviorTickService`（モンスターAI）
  - `HitBoxTickService`（HitBox更新）
- 飢餓移住判定はリポジトリ非依存の `MonsterMigrationPolicy` に寄せる

**関連行番号**: 167–303行（tick本体）, 509–593行（飢餓移住）, 731–882行（アクター行動）, 1081–1149行（HitBox更新）

---

### 1.2 LLM Wiring の composition root 分割

- [x] **Phase 1 実施済み**（メモリストア選択の composition root 外だし）
- **対象**: `src/ai_rpg_world/application/llm/wiring/__init__.py`

**問題点**:
- `create_llm_agent_wiring()` が入力検証、環境変数読取、メモリストア選択（SQLite/InMemory）、ツール登録、ToolCommandMapper構築、プロンプト構築、観測ハンドラ構築、Reflection構築まで1関数で担当
- `SqliteEpisodeMemoryStore` / `SqliteLongTermMemoryStore` / `SqliteReflectionStatePort` を application 層から直接参照しており、依存方向が重い
- ツール追加や永続化切替のたびにこの関数へ変更が集中

**分割案**:
- `create_llm_agent_wiring()` 自体は薄い composition root に縮小
- 以下の factory 関数に分割:
  - `_build_memory_stack()`
  - `_build_tool_stack()`
  - `_build_prompt_stack()`
  - `_build_observation_stack()`
  - `_build_reflection_stack()`
- SQLite / InMemory の選択は application 外の bootstrap 層か infrastructure 側 factory に寄せる

**関連行番号**: 173–511行

---

### 1.3 ObservationFormatter の実質モノリス解消

- [x] **Phase 1–5 実施済み**（2026-03-14 マージ）
- **対象**: `src/ai_rpg_world/application/observation/services/observation_formatter.py`（約150行に縮小）
- **テスト**: `tests/application/observation/`, `tests/application/observation/formatters/`

**実施内容**:
- 各 sub-formatter（Conversation, Quest, Shop, Trade, Sns, Guild, Harvest, Monster, Combat, Skill, World, Player, Pursuit）にイベント判定・整形ロジックを移行
- `ObservationFormatter` を formatter registry を回すだけのオーケストレータに縮小
- `ObservationFormatterContext` + `ObservationNameResolver` による共通基盤を整備
- 関連修正: `domain_event.py` の uuid 修正、`name_resolver.py` の例外処理の具体化、Trade/Sns formatter の単体テスト追加

**元の問題点（解消済み）**:
- 12個の sub-formatter が親の `_format_*_event()` を単純委譲しているだけ
- 実体は単一クラス集中で、`_format_*` が100件以上
- イベント追加時に中央ファイルの import・dispatcher・個別整形を毎回同時変更する構造

**分割案**:
- 各 sub-formatter（Conversation, Quest, Shop, Trade, Sns, Guild, Harvest, Monster, Combat, Skill, World, Player）に、親委譲ではなく実際のイベント判定と整形ロジックを移す
- `ObservationFormatter` は formatter registry を回すだけのオーケストレータに縮小
- イベント群ごとに依存を閉じ込める

**補足**: `formatters/` 配下の12ファイルは同型で、いずれも `return self._parent._format_*_event(...)` の薄い委譲だけ

**関連箇所**: 181–240行（format本体）, 259–522行（各種_format_*_event）, 538–1683行

**段階的リファクタリング計画**: [observation-formatter-refactoring-plan.md](./observation-formatter-refactoring-plan.md)

---

## 2. 優先度高（Phase 2）

### 2.1 ToolArgumentResolver のツール別分割

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py` (約1360行)
- **テスト**: `tests/application/llm/test_tool_argument_resolver.py`

**問題点**:
- `DefaultToolArgumentResolver` が1クラスで、ツール名ディスパッチ、ラベル解決、数値変換、各ツールの canonical args 変換、クエスト目標の `target_name -> id` 解決まで担当
- `resolve()` の長い `if` 連鎖（117–219行）
- `_resolve_quest_issue()` は878–1017行でリポジトリを使った名前解決ロジックを抱えている
- 新ラベル系ツール追加のたびにこのクラスと巨大テストを同時更新する構造

**分割案**:
- `movement` / `world` / `combat` / `quest` / `guild_shop_trade` などの小さな resolver 群へ分割
- `DefaultToolArgumentResolver` は `tool_name -> resolver` の委譲に留める
- `_resolve_quest_issue()` 内の `target_name` 解決は `QuestObjectiveTargetResolver` のような専用サービスに切り出す

---

### 2.2 ToolCommandMapper の handler map 組み立てを wiring へ移行

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/llm/services/tool_command_mapper.py`
- **テスト**: `tests/application/llm/test_tool_command_mapper.py`
- **既存計画**: `docs/refactoring/tool_command_mapper_refactoring_plan.md` を参照

**問題点**:
- executor 分割は進んでいるが、`ToolCommandMapper` が依然として多量の raw service / repository を受け取り、内部で全 executor を組み立てている（68–156行）
- `WorldToolExecutor` 側には `inspect_item` / `inspect_target` の read-side repository 操作も残り、command 実行と query 実行が混在

**分割案**:
- `ToolCommandMapper` は「`tool_name` から handler を引いて実行するだけ」にする
- handler map の組み立ては `wiring` 側へ移す
- `WorldToolExecutor` から inspect 系を `InspectionToolExecutor` へ分離し、query は application service 経由に寄せる

---

### 2.3 PhysicalMapAggregate の責務分離

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/domain/world/aggregate/physical_map_aggregate.py` (約1006行)
- **テスト**: `tests/domain/world/aggregate/test_physical_map_aggregate.py`, `test_physical_map_harvest.py`, `test_physical_map_aggregate_location_gateway.py` 等

**問題点**:
- 1 aggregate が空間整合性、移動コスト、視界計算、エリア/ロケーション/ゲートウェイ発火、インタラクション、チェスト入出庫、採取開始/完了/中断まで持っている
- `move_object()`, `_check_area_triggers()`, `interact_with()`, `start/finish/cancel_resource_harvest()` は別々の関心事

**分割案**:
- aggregate root は「タイル・オブジェクト配置整合性」とイベント発行に絞る
- 以下に切り出す:
  - `MapTriggerEngine`（トリガー判定）
  - `MapInteractionPolicy`（相互作用）
  - `HarvestSessionDomainService`（採取セッション）
  - `ChestInteractionPolicy`（チェスト操作）

**関連行番号**: 359–528行（move_object + area_triggers）, 597–702行, 793–994行

---

### 2.4 MovementService の責務分割

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/world/services/movement_service.py` (約810行)
- **テスト**: `tests/application/world/services/test_movement_service.py` (約1709行)

**問題点**:
- 目的地解決、オブジェクト隣接マス探索、継続移動、到着判定、ゲートウェイ条件評価、スタミナ消費計算、DTO組み立てが1サービスに集中
- `_tick_movement_core()` の spot/location/object ごとの到着判定や、対象消失時の経路消去は業務ルールが濃い

**分割案**:
- 以下に分離:
  - `SetDestinationService`
  - `MovementStepExecutor`
  - `ArrivalPolicy`
  - `MoveResultAssembler`
- `_find_passable_adjacent_to_object()` と到着判定はリポジトリ非依存のポリシーとして切り出す

**関連行番号**: 201–349行（_set_destination_impl）, 498–564行, 566–668行, 669–733行

---

## 3. 次点だが効果大（Phase 3）

### 3.1 観測対象イベント定義の分散解消

- [ ] **未着手**
- **対象**: `application/observation/services/` の formatter と recipient strategy

**問題点**:
- 「観測対象イベントかどうか」の定義が formatter 側と recipient strategy 側に分散
- モンスター系・戦闘系などで `supports()` は多く持つが、formatter 側では複数イベントが `return None`（no-op）
- 新イベント追加時に「受信者解決」「整形」「通知しない判断」を別々の場所で同期させる必要がある

**分割案**:
- 「観測するイベント定義」を一箇所に寄せる
- 各イベント群 formatter が `supports + format` を完結して持ち、recipient strategy はそのイベント群のうち本当に観測対象のものだけに限定する
- または `ObservedEventPolicy` のような判定レイヤを挟み、resolver/formatter の両方がそれを参照する形

**関連箇所**: `monster_recipient_strategy.py` 53–126行, `observation_formatter.py` 1379–1437行, `combat_recipient_strategy.py` 32–65行

---

### 3.2 受信者解決の「同一スポットプレイヤー取得」重複解消

- [ ] **未着手**
- **対象**: `application/observation/services/recipient_strategies/*`

**問題点**:
- `_players_at_spot()` が4戦略以上に重複実装
- `player_status_repository.find_all()` を直接なめる処理が6箇所以上
- スポット判定ルール変更時に複数戦略を同時修正する必要がある

**分割案**:
- `PlayerAudienceQueryService` あるいは `PlayersAtSpotResolver` のような application service / query port を作成
- `players_at_spot(spot_id)`, `all_known_players()`, `players_within_range(...)` を集約
- 各 strategy はそのクエリを呼ぶだけにする

**対象戦略**: default_recipient_strategy, shop_recipient_strategy, guild_recipient_strategy, monster_recipient_strategy, speech_recipient_strategy, quest_recipient_strategy

---

### 3.3 ObservationEventHandler の副作用分離

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py`

**問題点**:
- 1クラスで別トランザクション実行、例外ラップ、attention level 取得、ゲーム内時刻付与、buffer append、移動キャンセル、LLM turn scheduling を担当
- コンストラクタ引数が9個、`_handle_impl()` の後段で3種類の副作用分岐

**分割案**:
- `ObservationPipeline` を中心に、以下に副作用を分ける:
  - `ObservationAppender`
  - `MovementInterruptionService`
  - `ObservationTurnScheduler`
  - `ObservationTimestampResolver`
- handler 自体は「別UoWで pipeline を起動する」だけに縮小

**関連行番号**: 42–205行

---

### 3.4 WorldQueryService と PlayerCurrentStateBuilder の read-model 分割

- [ ] **未着手**
- **対象**: `world_query_service.py` (約439行), `player_current_state_builder.py` (約444行)
- **テスト**: `test_world_query_service.py` (約1058行), `test_player_current_state_builder.py`

**問題点**:
- プレイヤー位置、スポット文脈、利用可能移動先、視界、インベントリ、会話、クエスト、ギルド、ショップ、取引、スキルまで1 DTO 構築系に集約
- `find_all()` で同スポット人数を数える処理が複数箇所に重複
- クエリ1項目追加のたびに依存と fixture が増える構造

**分割案**:
- 以下に分離:
  - `PlayerLocationQueryService`
  - `SpotContextQueryService`
  - `AvailableMovesQueryService`
  - `VisibleContextQueryService`
  - `PlayerRuntimeContextBuilder`
- `WorldQueryService` は薄い facade に留める

**関連行番号**: world_query_service 72–132行, 161–204行, 215–270行, 322–395行 / player_current_state_builder 94–148行, 179–392行

---

### 3.5 MonsterAggregate の状態機械分離

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py` (約1103行)
- **テスト**: `tests/domain/monster/aggregate/test_monster_aggregate.py` (約1871行)

**問題点**:
- 1 aggregate が HP/MP・生死、成長段階、飢餓、餌場記憶、追跡状態、行動状態遷移、攻撃された時の反応、テリトリー復帰、意思決定イベント記録まで持っている
- `apply_behavior_transition()` は ENRAGE/FLEE/CHASE/SEARCH/RETURN をまとめて更新し、複数イベントを直接発行。分岐が重い

**分割案**:
- aggregate root は維持しつつ、内部を以下に分ける:
  - `MonsterLifecycleState`
  - `MonsterPursuitState`
  - `MonsterBehaviorStateMachine`
  - `FeedMemory`
- `record_attacked_by()` と `apply_behavior_transition()` の状態変更規則を同じ state machine に集約

**関連行番号**: 611–657行, 808–845行, 846–986行, 987–1022行

---

### 3.6 PlayerStatusAggregate の内部状態分離

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py` (約801行)
- **テスト**: `tests/domain/player/aggregate/test_player_status_aggregate.py` (約1139行)

**問題点**:
- 1 aggregate が基礎ステータス/成長/資源、位置/経路/目的地、追跡状態、会話、注意レベルをまとめて保持
- `set_destination()`・`advance_path()`・`update_location()` と `start/update/fail/cancel_pursuit()` が同居し、移動系と戦闘/会話系の関心が混ざっている

**分割案**:
- aggregate root は維持しつつ、内部状態を以下に分ける:
  - `PlayerNavigationState`
  - `PlayerPursuitState`
  - `PlayerResources`
- `PlayerStatusAggregate` は不変条件の調停役に寄せる

**関連行番号**: 229–431行, 456–756行, 757–794行

---

### 3.7 ToolDefinitions のカテゴリ別分割（中優先）

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/llm/services/tool_definitions.py` (約1145行)

**問題点**:
- 1ファイルにツール定義の JSON Schema 定数群と `register_default_tools()` の登録条件分岐が集約
- 可用性 resolver の import も全カテゴリ分をまとめて抱えている

**分割案**:
- `tool_catalog/movement.py`, `tool_catalog/world.py`, `tool_catalog/social.py`, `tool_catalog/memory.py` のようにカテゴリ別へ分割
- 各モジュールが `ToolSpec` の配列を返す形にする
- `register_default_tools()` は spec 群を集めて登録するだけにすると定義と登録の重複を減らせる

**関連行番号**: 117–1023行（定義群）, 1026–1145行（登録）

---

### 3.8 UiContextBuilder のラベル生成と描画分離（中優先）

- [ ] **未着手**
- **対象**: `src/ai_rpg_world/application/llm/services/ui_context_builder.py` (約831行)

**問題点**:
- `build()` が全セクションの組み立て、ラベル採番、`runtime_targets` への DTO 格納、最終テキスト整形を一括で行っている
- 各 section builder が「表示文言生成」と「ToolRuntimeTargetDto 生成」の2役を持っている
- ラベル prefix は手作業で共有されており、`L` がロケーション移動先にもショップ listing にも使われている

**分割案**:
- `LabelAllocator`, `RuntimeTargetCollector`, `SectionRenderer` を分ける
- 各 section は `SectionBuildResult(lines, targets)` を返す形にする
- ロケーションと shop listing の prefix を分離し、LLM に見せるラベル契約を読みやすくする

**関連行番号**: 86–281行（build本体）, 283–831行（各 _build_*_lines）

---

## 4. 着手順序の推奨

以下の順で着手すると、変更波及を抑えつつ効果が大きいです。

| 順 | 項目 | 理由 |
|----|------|------|
| 1 | LLM wiring の薄型化 | ツール追加のボトルネックを先に解除 |
| 2 | ToolArgumentResolver のカテゴリ分割 | 新ツール追加時の修正先を分散 |
| 3 | ObservationFormatter の strategy 化 | 観測イベント追加を容易にする |
| 4 | WorldSimulationService の tick 分割 | 世界更新の変更波及を抑える |
| 5 | PhysicalMapAggregate と MovementService | ドメイン境界を明確化 |

---

## 5. 追記・変更履歴

このセクションには、着手時に判明した前提・制約、後から追加した項目、他ドキュメントとの関連を記録してください。

### 追記テンプレート（コピーして使用）

```markdown
### YYYY-MM-DD: [タイトル]

- **内容**: 
- **関連項目**: （上記の番号を参照）
- **備考**: 
```

### 既知の関連ドキュメント

- `docs/refactoring/observation-formatter-refactoring-plan.md` - ObservationFormatter のモノリス解消計画（Phase 1–5 段階的移行）
- `docs/refactoring/llm-wiring-refactoring-plan.md` - LLM wiring の段階的リファクタリング計画（実施済み・未着手・着手順の詳細）
- `docs/refactoring/tool_command_mapper_refactoring_plan.md` - ToolCommandMapper の段階的分割計画（Phase 1–3 が既に定義済み）
- `docs/observation_implementation_plans.md` - 観測機構の仕様・実装計画
- `docs/domain_events_observation_spec.md` - 観測対象イベントの仕様

### 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-03-13 | 初版作成。LLMツール出揃い時点でのリファクタリング候補を優先度順に整理 |
| 2026-03-13 | 1.2 Phase 1 実施。infrastructure/llm/_memory_store_factory.py を追加し、メモリストア選択をファクトリへ委譲。Phase 2（factory 関数分割）は依存関係が複雑なため一旦見送り。将来は同一ファイル内の `_build_*` から段階的に抽出を推奨 |
