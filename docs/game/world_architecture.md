# 世界の現在の構成

2026-10-27、Issue #1862・#1893の旧タイル実装の削除を反映した構成案内。
モンスター個体の旧座標・物体IDに関する記述は、[PR #1907](https://github.com/Motifman/llm-rpg/pull/1907)の反映後を対象とする。
[旧実装計画](spot_graph_world_implementation_plan.md)は移行前の検討記録であり、
そこにあるタイルマップとスポットグラフの並存構成は現在の構成ではない。

## 実装をたどる入口

パスはこの文書からの相対リンク。識別子はコード上の名前を使う。

| 確認したいこと | 入口 |
| --- | --- |
| シナリオからの構築と接続 | [`create_world_runtime`](../../src/ai_rpg_world/application/world_runtime/world_runtime.py) |
| スポット・経路・作用・音の世界 | [`domain/world_graph/`](../../src/ai_rpg_world/domain/world_graph/)と[`application/world_graph/`](../../src/ai_rpg_world/application/world_graph/) |
| 現在状態をプロンプトへ渡す | [`WorldRuntimeQueryAdapter`](../../src/ai_rpg_world/application/world_runtime/default_prompt_builder_adapters.py) → ランタイムの `_build_minimal_player_state_dto` |
| 現在地と周囲の表示 | [`SpotGraphCurrentStateFormatter`](../../src/ai_rpg_world/application/llm/services/spot_graph_current_state_formatter.py)と[`SpotGraphUiContextBuilder`](../../src/ai_rpg_world/application/llm/services/spot_graph_ui_context_builder.py) |
| 天候の更新 | [`SpotGraphEnvironmentStageService`](../../src/ai_rpg_world/application/world_graph/spot_graph_environment_stage_service.py) |
| 時刻・昼夜 | [`world_runtime.py`](../../src/ai_rpg_world/application/world_runtime/world_runtime.py)の時刻進行と[`SpotGraphDayNightStageService`](../../src/ai_rpg_world/application/world_graph/spot_graph_day_night_stage_service.py) |
| 攻撃の調整 | [`SpotAttackOrchestrator`](../../src/ai_rpg_world/application/world_graph/spot_attack_orchestrator.py) |
| 観測するイベントの集合 | [`observed_event_registry.py`](../../src/ai_rpg_world/application/observation/services/observed_event_registry.py) |
| 配信先と観測文 | [`recipient_strategies/`](../../src/ai_rpg_world/application/observation/services/recipient_strategies/)と[`formatters/`](../../src/ai_rpg_world/application/observation/services/formatters/) |
| WebSocket・RESTの入口 | [`presentation/spot_graph_game/`](../../src/ai_rpg_world/presentation/spot_graph_game/) |

現在状態はスポットグラフのスナップショットから組み立てる。
旧 `WorldQueryService` やタイル向けの `DefaultCurrentStateFormatter` は削除済み。
新しい観測を追加する際は、過去のイベント一覧を現在の登録表として扱わず、
[trace観測性レビュー](../trace_observability_review.md)に従って発火・配信・表示を確認する。

## 削除した実装と残る領域

| 領域 | 削除済み | 残るもの |
| --- | --- | --- |
| 世界と移動 | 物理マップ集約、タイル・物体・仕掛け、タイル移動・経路探索、旧シミュレーション | スポットグラフの移動・作用、`world` の天候・時刻・施設割当・座標などの共有の値 |
| 戦闘と技能 | HitBox集約・衝突判定と専用保存先、タイルの技能実行、スキル定義の旧形・速度・命中パターン・追加効果 | 本番の攻撃、状態異常・能力補正、スキルの定義・装備・進行・消費 |
| モンスターと追跡 | タイル専用の行動調整・受け手、`domain/pursuit`と旧追跡状態、個体の旧座標・初期座標・世界物体IDとその採番・検索 | `MonsterAggregate`、スポットでの行動・生存・CHASE。`MonsterId`とスポットの位置・追跡相手を使う |
| プレイヤーの移動 | タイルの座標・経路・目的地を持つ`PlayerNavigationState` | スポット移動の`PlayerSpotNavigationState`、現在地の`SpotId`、移動途中の保存と再開 |
| 採取と会話 | 物理マップ上の採集実行、NPC会話の木と専用保存先 | スポットの作用による採取、発言・囁き・音の伝播 |
| 経済・社会 | タイル由来のクエスト購読、ショップ・クエストの物理マップ依存 | SNS・取引・市場・ギルド・クエスト・ショップ。保持していることと、全機能が実験に接続済みであることは別 |
| 保存 | 物理マップ・HitBox・NPC会話の専用保存先と接続 | SQLiteの過去migrationと表、他領域の保存先、Beingの記憶とスナップショット |

天候は`SpotGraphWeatherChangedEvent`の確定後に実行環境が通知する。
発火元のない旧`SpotWeatherChangedEvent`と専用の登録・配信・整形は削除済み。
`Coordinate` が残っていても、タイルマップの本体が残っていることを意味しない。
モンスター個体の座標項目を外しても、餌場の記憶・旧行動状態・出現点などの別用途に使う共有の値は残る。
モンスター撃破時の報酬の扱いは [Issue #1863](https://github.com/Motifman/llm-rpg/issues/1863) の範囲。

現在状態DTOの旧タイル用項目と専用型、利用側のない接続・天候・モンスター設定の補助型、
モンスター集約の旧タイル用メソッドは、#1882〜#1884で整理済み。
ゲート由来の未使用の通行条件と保存先、利用側のない戦闘例外は、
#1886・#1887で整理済み。現在状態の問い合わせも、効果のない移動先取得指定を持たない。
Beingの記憶・イベント基盤の設計変更やSQLiteの過去の表の削除も、この整理の対象外。

## 保存済みデータの読み込み

- 世界snapshotに残る旧`player_pursuit_state`だけを除き、`snapshot_load.removed_world_subsystems`と`world_snapshot_load.removed_subsystems`に捨てたプレイヤー行数を残す。現役のスポット移動とその途中状態は復元する。未知キーと現役キー欠落の厳格な検査は維持する。
- Beingは記憶の種類の所有宣言を持たない。古いsnapshotに残る宣言はどの文字列も読み捨て、`snapshot_load.removed_declared_memory_kinds`にBeingごとの種類別の件数を残す。記憶本文とは別で、本文の`removed_memory_keys`へ混ぜない (D1469-1)。
- スキルの旧形・速度・追加効果は型へ復元しない。過去のSQLiteの表・列は残し、旧`pattern_type`必須列はwriterのSQLだけで空文字を入れる。ドメインに仮の命中パターンは作らない。装備・消費・前提条件・クールダウン等は引き続き保存・復元する。
- モンスター個体の旧ID・座標列はドメインへ復元しない。旧`world_object_id`必須列は保存層で既存行の値を保持し、新規行だけ同じ表の最大値+1で満たす。旧座標列も更新せず、過去の表や列は残す。現役のHP・生死・行動状態等のSQLite保存は維持する。

これらは旧データを今のコードで読むための互換処理であり、新しく保存したデータを旧コードへ戻す互換性は保証しない。各判断は[旧移動・追跡](../design_decisions/D1893.md)、[スキルの旧当たり判定](../design_decisions/D1893-3.md)、[旧天候と未使用型](../design_decisions/D1893-4.md)、[意味記憶の宣言](../design_decisions/D1893-5.md)を参照。

世界snapshotには、モンスター個体のHP・行動状態やグラフ上のモンスター位置を保存・復元するcodecがない。実験再開ではシナリオから実行環境を構築した後にsnapshotを読むため、モンスターは初期構築された状態になる。動的に出現した個体の復元も保証しない。モンスターのSQLite保存先が存在することとは別の制限であり、今回の旧状態の削除で変更するものではない。

## 履歴文書の読み方

旧計画と試験監査は、当時の判断・呼出元・検証件数を残している。
先頭に退役・部分失効の案内がある文書では、本文中の「現在」「本番」やコード例は
記録当時の説明として読む。現在の実装や検証件数を保証するものではない。

削除の根拠・保持する契約は[設計判断の個別ファイル](../design_decisions/)と
[検証記録](../quality_checks/)にある。過去の削除PRの検証記録も、そのPR時点の事実として扱う。
削除後の不在保証は、たとえば[タイルマップ](../../tests/architecture/test_tile_map_elimination.py)、
[物理マップ保存先](../../tests/architecture/test_physical_map_repository_elimination.py)、
[当たり判定](../../tests/architecture/test_hitbox_removal.py)、
[NPC会話](../../tests/architecture/test_npc_dialogue_elimination.py)の構造試験を参照する。
追加の不在保証は[旧移動・追跡](../../tests/architecture/test_legacy_navigation_pursuit_removed.py)、
[スキルの旧当たり判定](../../tests/architecture/test_legacy_skill_hit_values_removed.py)、
[旧天候と未使用型](../../tests/architecture/test_unused_domain_types_weather_event_removed.py)、
[意味記憶の宣言](../../tests/architecture/test_semantic_memory_kind_removed.py)を参照する。
