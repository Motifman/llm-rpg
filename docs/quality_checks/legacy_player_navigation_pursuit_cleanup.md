# 旧タイル移動・追跡状態の削除 (#1893)

基準: f86d9fcde0ba4ada9d1e3124c13452dfa3b3aae2。

## テストリスト

- [x] 旧移動・追跡の型、import、専用操作が残らない。
- [x] 古い世界snapshotの追跡キーだけを捨て、件数をtraceに残す。
- [x] 未知キーと現役キー欠落はstrict読込で拒否する。
- [x] スポット移動途中の状態、active_effects、attentionを復元する。
- [x] 旧SQLiteと旧プレイヤーJSONを読み、新規保存も成功する。
- [x] 新旧両方の現在地項目が欠けたJSONは拒否し、明示的なnullは復元する。
- [x] 本番CHASE、発言、shop/questの場所判定を維持する。
- [x] smoke_stubと山村・避難訓練のseed 0〜2・40tickが前後で成功し、記録種別・観測種別・行動件数が一致する。

## 削除前の依存

ASTとrgで実装・型import・再公開を点検した。旧移動・追跡の読者は専用操作、SQLite、世界snapshot、観測登録である。現行CHASEはMonsterBehaviorStateとAttackerRefを使う。
`current_spot_id`には発言・shop/quest・観測の読者が残るため、このSpotIdだけをプレイヤーに保持する。スポット移動の実装とPlayerSpotNavigationStateは変更しない。

旧タイルの位置変更イベントPlayerLocationChangedEventはupdate_locationだけが発行していたため、発行元と同時に退役した。観測の名前解決・注意水準の試験はEntityEnteredSpotEvent、複数配信の試験はPlayerDownedEventで残した。旧追跡の配信・文面・値オブジェクト・集約操作の専用試験だけを削除した。

## 振る舞いの比較

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| スポットを移動・CHASEで追跡する | グラフの位置と行動状態を使う | 同じ状態・イベント・装備を使う |
| 旧追跡キーのある世界snapshotを読む | 旧追跡を復元する | そのキーだけ捨て、件数をtraceに残す |
| 未知キー・現役キー欠落がある | strict読込で停止する | 停止を維持する |
| 古いSQLite・プレイヤーJSONを読む | 旧経路・追跡も復元する | 現役のHP・現在地・CHASE等だけを復元する |

## 検証条件

比較はsmoke_stub、mine_village_v1 / station_drillの各seed 0〜2・40tick。独立した.venvを使い、PYTHONPATHでこのworktreeのsrcを固定した。一時sitecustomizeでdotenv.load_dotenvを無効化し、実LLM・.env・手動quality/live_api試験は使っていない。出力先は `/tmp/llm-rpg-1893-a/`。

## 質感

本番の移動とCHASEの表現を変える変更ではない。スタブの観測・行動件数と種類で回帰を確認し、人間らしさの改善を主張しない。旧タイル移動・追跡だけの通知は実行経路に発行元がなく、退役後もスポット上の移動・追跡通知は残る。

## 確認結果

- 変更前に不在検査2件と旧snapshot strict読込1件が失敗することを確認し、変更後は成功した。
- 独立レビューのMEDIUM 1件（JSONの現在地項目欠落を許す回帰）をRed→Greenで修正した。
- 関連試験1,859件、互換・実験再開34件、移動・snapshot131件が成功。位置更新イベント退役後の観測811件、trace配線最終版のsnapshot49件も成功した。
- 前後のsmoke_stub成功。解決済み設定のprofile・シナリオ・2tick・基準commitを確認した。smokeは観測/行動0件で配線確認に限り、行動比較は下記fuzzを使った。
- 山村と避難訓練の各3seed・40tickは前後とも検出0件。全記録種別ごと・観測種別ごとの件数と行動件数が一致した。計1,990観測・1,205行動。詳細は `/tmp/llm-rpg-1893-a/comparison.json`。

## 残る検索一致

実行時・型・再公開・動的参照をsrc/tests/scriptsで調べ、旧型へのimport・生成・呼出は0件。文字列として残すのは、世界snapshotの削除キー判定、旧JSONの現在地回収、SQLite旧表の掃除、不在検査と互換試験である。

履歴として保持する文書は `docs/pursuit/phase1_integration_strategy.md`、`docs/test_audits/{monster_pursuit_contracts,player_location_pursuit_speech_contracts}.md`、`docs/refactoring/{phase2-3-refactoring-plan,llm-agent-refactoring-roadmap,observation-formatter-refactoring-plan}.md`、`docs/{world_query_status_and_llm_context_design,domain_events_observation_spec,llm_agent_prompt_and_memory_implementation_plan}.md`、`docs/game/spot_graph_world_implementation_plan.md`、`docs/quality_checks/legacy_monster_tile_actions_cleanup.md`、設計判断D1862-6 / D1862-7 / D1862-20。これらの当時の保持判断はD1893で上書きする。共有 `docs/game/world_architecture.md` の現行説明は親の文書PRで更新する。
