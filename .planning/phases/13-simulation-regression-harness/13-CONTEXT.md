# Phase 13: Simulation Regression Harness - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 11/12 で分割した `WorldSimulationApplicationService` と各 stage / policy / coordinator について、今後のリファクタでも壊れた箇所を継続的に検知できる回帰テスト基盤を整える。ここで決めるのは「何を最優先の回帰契約として守るか」「大きい統合テストをどこまで残し、どこから小さいテストへ分けるか」「失敗時にどの契約が壊れたか分かる構造をどう作るか」であり、新しい world simulation capability の追加や tick 順序そのものの再設計は扱わない。

</domain>

<decisions>
## Implementation Decisions

### Regression priority
- Phase 13 で最優先に守る回帰契約は、`WorldSimulationApplicationService.tick()` の全体 stage 順序と post-tick hook を含む順序保証とする。
- 具体的には `environment -> movement -> harvest -> lifecycle -> behavior -> hit box -> post-tick hook` の大きな流れを、代表的な統合ケースで固定する。
- 順序契約に付随する副作用のうち、最初に強く守る対象は `llm_turn_trigger` / `reflection_runner` を含む post-tick hook 契約とする。
- Phase 13 では細かい枝分かれの網羅より、代表経路で「tick coordinator の約束が壊れていない」ことを優先する。

### Integration test shape
- 大きな統合テストは残すが、今の巨大ファイルへ寄せ続けるのではなく、中くらいの網として契約ごとに役割を分ける。
- 統合テストの中心は「プレイヤー1体 + pursuit / movement + モンスター1体」が同居する代表ケースとし、world simulation 本流のつながりを 1 本のゴールデンパスとして守る。
- 追加の統合テストは、順序契約、active spot / save 契約、post-tick hook 契約など、守る約束ごとに目的を分離して持つ。
- `test_world_simulation_service.py` は薄くしてよく、責務の近い統合テストは service / 契約単位へ整理する。

### Fixture and builder strategy
- 現在の大きい `setup_service` fixture を唯一の入口にせず、必要な依存だけを組み立てられる薄い builder / helper 群へ分ける。
- 新しい回帰ケースでは、「どんな world 状態を作っているか」が helper 名から分かることを重視する。
- 既存の重い fixture は移行期間の足場として残してよいが、Phase 13 の新規追加テストは軽い builder を優先する。
- fixture / builder の目的はテストコード短縮だけでなく、失敗時に前提 world 状態を読み取りやすくすることとする。

### Small regression boundaries
- Phase 13 の小粒テストは stage 単位を主軸とし、特に `movement`・`monster lifecycle`・`monster behavior` stage を優先する。
- 小粒テストで最初に守るのは、正常系の巨大シナリオではなく、skip / guard / support 有無による collaborator 呼び出し契約である。
- `active spot ではない`, `busy actor`, `support が未注入`, `skip 対象 actor` などの条件で、何が呼ばれるか / 呼ばれないかを直接検証する。
- 既に存在する `HungerMigrationPolicy` や `MonsterBehaviorCoordinator` などの小粒テストは核として活かし、足りない stage service の境界だけを追加していく。

### Failure diagnostics
- テストが落ちたとき、最初に「どの契約が壊れたか」が分かることを強く重視する。
- 命名は service 名先行ではなく契約ベースを基本とし、`stage order`, `active spot save`, `post-tick hook` のように守りたい約束がテスト名から読める形を優先する。
- 1 テスト 1 契約を原則とし、近い契約をまとめすぎない。
- 補助手段として、fixture / builder 名でも前提 world 状態を説明できるようにし、失敗時にケースの意図を追いやすくする。

### Claude's Discretion
- builder / helper の具体的な API 形状と配置先
- 統合テストを契約別ファイルへどう分けるかの最終ファイル構成
- stage service テストのうち、どの guard 条件を Phase 13 で先に拾い、どれを後続へ回すかの優先順位

</decisions>

<specifics>
## Specific Ideas

- world simulation 全体の安心感は少数の代表的な統合ケースで残し、増やしやすさは stage 単位テストで担保する。
- 代表ケースでは「tick の大きな流れ」と「tick 本体の後で hook が走ること」を一緒に守る。
- 小粒テストは stage service が collaborator をどう呼ぶかに集中し、重い map / monster / loadout 構築がなくても意味のある回帰点を増やせる形を目指す。
- テストの読み口は「どのクラスを叩くか」より「どの約束を守るか」を前面に出す。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/application/world/services/test_world_simulation_service.py`: 既存の順序契約、active spot、hit box、pursuit continuation、monster lifecycle / behavior、LLM hook の広い回帰網が集まっており、Phase 13 の統合テスト再編の起点になる。
- `tests/application/world/services/test_hunger_migration_policy.py`: pure policy を小粒で守る既存パターンとして再利用できる。
- `tests/application/world/services/test_monster_behavior_coordinator.py`: coordinator の内部順序と保存契約をモック中心に確認する既存パターンとして使える。
- `tests/application/world/services/test_hunger_migration.py`: world simulation 本体経由と補助ロジック経由の両方が混ざっており、Phase 13 での境界整理対象として示唆がある。

### Established Patterns
- Phase 11/12 で `WorldSimulationApplicationService` は facade / order coordinator として残し、詳細処理は stage / coordinator / policy へ分かれている。
- `WorldSimulationMonsterLifecycleStageService` と `WorldSimulationMonsterBehaviorStageService` は薄い orchestration になっており、guard 条件や collaborator 呼び出し契約を直接テストしやすい。
- 既に pure policy と coordinator の小粒テスト文化は存在するため、Phase 13 はそれを world simulation stage 群へ広げる方向が自然である。

### Integration Points
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`: tick 全体の順序保証、active spot の導出、post-tick hook 契約を持つため、統合テストで守るべき中心境界になる。
- `src/ai_rpg_world/application/world/services/world_simulation_movement_stage_service.py`: pursuit continuation と movement 実行の結線・スキップ条件を直接守る候補。
- `src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py`: spawn/respawn 分岐と survival coordinator 呼び出し条件を直接守る候補。
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py`: active spot / busy / active time / skipped actor の guard 契約を直接守る候補。
- `tests/application/llm/test_llm_wiring_integration.py`: world simulation への `llm_turn_trigger` / pursuit continuation wiring 契約を別系統で押さえており、Phase 13 では post-tick hook 回帰と重複しすぎない整理が必要。

</code_context>

<deferred>
## Deferred Ideas

- world simulation の新 capability 追加や tick 順序そのものの変更
- hit box / combat 系の細かい枝分かれを全面的に整理し直すこと
- monster 個別ルールごとの詳細な網羅を Phase 13 の主眼に据えること
- fixture / builder 基盤を world simulation 以外のテスト全体へ一気に横展開すること

</deferred>

---

*Phase: 13-simulation-regression-harness*
*Context gathered: 2026-03-14*
