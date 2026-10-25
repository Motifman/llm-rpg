# 世界の現在の構成

2026-10-25、Issue #1862の削除PR #1864〜#1885を取り込んだmainの案内。
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
| 戦闘と技能 | HitBox集約・衝突判定と専用保存先、タイルの技能実行 | 本番の攻撃、状態異常・能力補正、スキルの定義・装備・進行。装備の定義が使う形・速度・効果の値も残る |
| モンスターと追跡 | タイル専用の行動調整・受け手 | `MonsterAggregate`、スポットでの行動・生存・追跡、`domain/pursuit` と追跡のスナップショット |
| 採取と会話 | 物理マップ上の採集実行、NPC会話の木と専用保存先 | スポットの作用による採取、発言・囁き・音の伝播 |
| 経済・社会 | タイル由来のクエスト購読、ショップ・クエストの物理マップ依存 | SNS・取引・市場・ギルド・クエスト・ショップ。保持していることと、全機能が実験に接続済みであることは別 |
| 保存 | 物理マップ・HitBox・NPC会話の専用保存先と接続 | SQLiteの過去migrationと表、他領域の保存先、Beingの記憶とスナップショット |

`SpotWeatherChangedEvent` は削除対象ではなく、現在も登録・配信・整形する。
`Coordinate` が残っていても、タイルマップの本体が残っていることを意味しない。
モンスター撃破時の報酬の扱いは [Issue #1863](https://github.com/Motifman/llm-rpg/issues/1863) の範囲。

現在状態DTOの旧タイル用項目と専用型、利用側のない接続・天候・モンスター設定の補助型、
モンスター集約の旧タイル用メソッドは、#1882〜#1884で整理済み。
#1885までを取り込んだ時点では、ゲート由来の未使用の通行条件と保存先、
当たり判定専用の例外が残る。これらは別作業であり、この案内では削除済みと扱わない。
Beingの記憶・イベント基盤の設計変更やSQLiteの過去の表の削除も、この整理の対象外。

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
