# 通路状態と動的接続の試験監査

## 対象と結果

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。以下の5ファイル44宣言を全件読み、R36（保持）・F5（契約を保持して修復）・C3（確認を保持先へ移して統合）・D0（削除のみ）とした。

| 対象 | 元宣言 | 元行数 |
| --- | ---: | ---: |
| `tests/domain/world_graph/aggregate/test_set_connection_passage.py` | 7 | 140 |
| `tests/domain/world_graph/entity/test_spot_connection.py` | 4 | 63 |
| `tests/domain/world_graph/test_dynamic_connections.py` | 10 | 194 |
| `tests/domain/world_graph/value_object/test_passage.py` | 19 | 206 |
| `tests/domain/world_graph/value_object/test_reactive_passage_binding.py` | 4 | 63 |

- 所有試験は44→41宣言、48→50ケース、666→693行。試験差分は追加83・削除56で27行増。削除数や速度改善を目的にしていない
- 廃止ファイル0。製品・共有準備・専用支援の差分0。試験専用の製品入口は新設・削除とも0
- 未編集基準71件、保持先を先に作って元3宣言を残した段階76件、統合後の所有50件、全変異復元後の最終73件が成功。最終は所有50＋関連23で、関連の宣言を今回の44へ加えない
- [配置監査の固定候補](https://github.com/Motifman/llm-rpg/pull/1735)（`037b2b17f182c97a174e0bca6a05b8015087a9bc`、併用した試験2ファイルと規約のblob一致を確認）と別の作業木で併用し、配置65＋通路50＋関連16の一意131件が成功。73件と重なるので合算しない
- 12種類の意図的誤変更を元48件と候補50件で比較し、各回を元のバイト列へ復元。原本・候補・併用の3作業木で製品1601ファイルのハッシュが基準と一致

## 所有者・呼出元・層の分担

1. `Passage` は形態ごとの既定値、明示上書き、状態検証、状態別宣言の往復を所有する。`value_object/test_passage.py` が主担当で、期待値を実装の表から生成しない。呼出元は `parse_map.parse_connections`、`sqlite_world_graph_state_codec._passage_from_dict`、`apply_create_connection`、`SpotGraphAggregate.set_connection_passage_state`
2. `SpotConnection` は移動時間の構築時制約と、passage未指定時のOPEN既定を所有する。`entity/test_spot_connection.py` に残す。シナリオ解析、SQLite復元、相互作用・シナリオイベントによる動的生成が構築APIを使う
3. `SpotGraphAggregate` は接続に値を反映すること、通行可否に応じた未配信通知、正逆の接続本体と出方向索引を所有する。`aggregate/test_set_connection_passage.py` と `test_dynamic_connections.py` が担当。値オブジェクトの数値計算とは別契約なので、その試験を理由に集約の入口検査を消さない
4. `WorldGraphEffectService.apply_effects` は登録済ハンドラを通して `CreateConnectionSpec` / `DestroyConnectionSpec` を返す。相互作用とシナリオイベントのサービスがその結果をグラフへ適用する。4宣言は生成計画の値・受理条件を保証し、実グラフへの適用、保存、確定後配送までの証明とは呼ばない
5. `ReactivePassageBinding` は真偽別の状態宣言を構築時に検証する。パーサーは一部を先に別例外で拒否し、ステージは有効な宣言を使うため、直接構築の成功対照・専用例外3件を代替しない。`ReactivePassageBindingStageService` の条件評価・保存・通知収集は別層の関連試験に残す

`set_connection_passage_state` の本番呼出元には `SpotInteractionApplicationService`、`SpotGraphScenarioEventStageService`、`SynchronizedActionResolverStageService`、`ReactivePassageBindingStageService` がある。state、通行上書き、音上書きを渡す入口を修復し、実装を変えずに欠落を検出する。

SQLiteの非活性状態上書き復元は、開扉中に保存・復元して再施錠する変換契約。値オブジェクトの往復試験とは別に保持した。音の伝播・経路探索は `passage.sound_permeability` / `passage.traversable` の利用側であり、この監査で全体を完了扱いにしていない。

## 統合した3宣言と元の入力

| 元の試験 | 保持先 | 保存した入力・確認 |
| --- | --- | --- |
| `TestSpotConnectionPassage.test_wall_intact_passage_makes_connection_impassable` | `TestPassageFactories.test_wall_state_default_table` と実集約の置換・通行変化通知 | `Passage.wall(INTACT)` のFalse/0.1。明示通路をOPENへ戻す構築故障は実集約で検出 |
| `TestSpotConnectionPassage.test_door_open_passage_makes_connection_passable_with_full_sound` | `TestPassageFactories.test_door_state_default_table` | `Passage.door(OPEN)` のTrue/1.0を新しいOPEN行へ先に移管 |
| `TestPassageFactories.test_door_closed_is_not_traversable_by_default` | 同じ扉表のCLOSED行 | `Passage.door(CLOSED)` のFalse。元LOCKEDのFalseも表の別行に保持 |

元の接続fixtureはID1、両端10/20、名称、移動時間1、双方向Trueを渡していたが、その値や逆方向生成は検査していない。`SpotConnection` の構築はこれらでpassageを計算・分岐せず、渡された値を格納する。したがってこの数値を値オブジェクトの定数表へ機械的に移してはいない。構築時の明示通路の尊重は実集約で検査することを、独立した第二読と意図的誤変更で確認した。

この判断は「短い取得試験は不要」だからではない。旧実装は接続上の `is_passable` / `sound_permeability` へ同期しており、その所有者だった。同期を廃止した後に、渡したPassageの属性を再読する形だけが残っていた。未指定のOPEN既定と負の移動時間拒否は現在も独立した構築API契約なので保持する。

## 修復した5宣言

- 置換試験は元WALL.BROKEN行を残し、DOOR.OPENへの別形態置換を追加。kind/state/通行可True/音1.0を検査する
- 通行可否不変のINTACT→CRACKEDでは、実状態CRACKED・通行不可・音0.4を確認してから無通知を検査する。操作を省いただけで成功する形をやめた
- 上書き試験は元CRACKED/音0.55/通行引数省略を残す。CRACKED/TrueとBROKEN/Falseも入力し、遷移後state・通行可否・音を検査する。Falseを未指定扱いする誤りにも届く
- 双方向の正ID10からの削除と、逆ID11からの削除は各宣言を残す。元の両ID参照が `UnknownConnectionException` となる確認を保ち、両端1/2の出方向一覧も空とする

## 導入履歴と残した回帰

- [通路抽象の導入](https://github.com/Motifman/llm-rpg/commit/d554cb52451e7f5c181ce00d0323642c5351375e) は形態と状態から通行・遮音を決める設計を導入した
- [状態変更の効果と集約入口](https://github.com/Motifman/llm-rpg/commit/7a202e047caa7ffd478f3b32c51bbfabbdb81352) は通行可否が変わるときだけ通知する方針を導入した
- [旧同期フィールドの廃止](https://github.com/Motifman/llm-rpg/commit/268780b0ef90f91d4c6d4f004ac35ac6f1f3f0c6) でSpotConnectionの同期処理が消え、読み手をpassageへ一本化した。今回の層の整理はこの履歴に基づく
- [動的接続の生成・破壊](https://github.com/Motifman/llm-rpg/commit/d3046a602134479a4c10a82594accdb5485e50cb) は本体除去、通知、アプリケーションでの計画消費を追加した。生成計画だけを実適用の証明と取り違えない
- [反応的な通路宣言の導入](https://github.com/Motifman/llm-rpg/commit/a8969098daaa44504bba67d93e837911ef87c143) が空・同一状態の拒否を定めた
- [状態別上書きの消失修復](https://github.com/Motifman/llm-rpg/commit/fa8d85656be6a937b31fa2663912a238c0e23b1d) と[直接構築入口の回帰](https://github.com/Motifman/llm-rpg/commit/a68bc9b9f7d43377f205244f85d7bf24936f4a5f) に由来する4宣言は原文のまま保持した

R36のうち扉表へ改名・拡張した1件を除く35件は構文木が原本と一致し、そのうち32件は関数原文も一致する。残る3件の原文差は整形による改行のみ。共通準備にも整形差はあるが、引数や分岐を変えていない。「全Rの原文が不変」とは主張しない。

## 意図的な誤変更の比較

各行で元48件・候補50件を別々に実行した。元48件が成功し候補が失敗した誤変更は5種類。失敗数は試験ケース数で、収集・準備エラーやスキップは0。各実行後に変更ファイルを元バイトへ戻した。

| 意図的誤変更 | 元の失敗数 | 候補の失敗数 | 確認の意味 |
| --- | ---: | ---: | --- |
| 別形態のOPEN扉をOPEN開口へ誤正規化 | 0 | 1 | 新しいDOOR行のkind確認が失敗。妥当なPassage.open()へ誤正規化し、型とstateの不整合例外では赤くしていない |
| 通行可否不変なら実状態更新も省略 | 1 | 3 | 元の音上書き試験も失敗。候補では無通知試験自身が実状態を検出する。全体で初めて検出した故障とは数えない |
| 集約の明示通行上書きを捨てる | 0 | 2 | CRACKED/TrueとBROKEN/Falseの両行が検出 |
| 明示Falseを未指定として扱う | 0 | 1 | BROKEN/Falseの行が検出 |
| 逆方向の出方向索引だけを残す | 0 | 2 | 正逆削除の両宣言が公開一覧問い合わせ中のKeyErrorで失敗。assert比較前だが準備エラーではない |
| 壁INTACTの音既定を誤る | 2 | 1 | 元の接続再読と値オブジェクト表から、値オブジェクト表へ確認を集約 |
| 開扉の音既定を誤る | 3 | 4 | 元の接続再読を除去後も、移管したOPEN表行が検出 |
| 閉扉の既定を通行可にする | 1 | 1 | 元CLOSED宣言と移管先CLOSED行が同じ誤変更を検出 |
| 構築時に明示通路をOPEN既定へ戻す | 5 | 8 | 元の接続再読を除去後も、実集約の通行変化通知などが検出 |
| 状態遷移で他state用の宣言表を失う | 4 | 4 | 過去の4回帰が元と候補で同じ4失敗となる |
| 施錠扉の既定を通行可にする | 1 | 1 | 元LOCKED宣言と移管先LOCKED行が同じ誤変更を検出 |
| 音の上書きがある経路で元状態を誤って再使用 | 0 | 3 | 第二読で追加したstate確認が3行とも検出 |

6組目の実行後、結果照合スクリプトがpytestの列挙名 `WallStateEnum.INTACT` を短い `INTACT` と期待して停止した。試験実行と元バイトへの復元は終わっていた。期待名を実際のXMLへ合わせ、既存の生結果を上書き・再実行せず再読して確認を続けた。この訂正を製品不具合や追加の試験失敗には数えない。

## 検証の範囲

Python 3.10.22 / pytest 8.4.1。秘密情報を除去し外部接続を遮断した環境で、作業木自身のsrcと毎回別のPython・pytestキャッシュを使用した。実LLM・有料API・実ネットワーク試験なし。

関連23ケースは次のとおり。

- `test_spot_graph_aggregate.py::TestConnectionState` 3件と `::TestConnectionStateChangedActor` 4件
- `test_cross_domain_effects.py::TestChangePassageStateEffect` 3件
- `tests/application/world_graph/test_reactive_passage_binding_stage.py` 11件
- `tests/infrastructure/repository/test_sqlite_spot_graph_roundtrip.py::test_sqlite_roundtrip_preserves_override_for_an_inactive_passage_state` と `::test_sqlite_roundtrip_preserves_passage_field` 各1件

変更した4試験ファイルにRuff 0.16.8の静的検査・整形確認と差分の空白検査が成功。リポジトリCIは `.github/workflows/ci.yml` の `uv run --frozen pytest -n auto` と独立した静的検査を使う。通常試験はquality/live_apiを除外する。このローカル記録を全リポジトリ試験や公開後CI成功の代わりにはしない。

## 競合と残り

09:27UTCにmainと未統合70PRの先端を再確認し、対象試験5・製品所有者5の直接変更重複は0。配置監査とは `spot_graph_aggregate.py` を共有するが双方とも製品差分0で、試験の変更パスも異なる。配置側のstate API通知・actor既定None統合は今回の差分へ含めず、固定候補との併用試験だけを行った。

今回の所有規則を以下へ記す。

- 形態ごとの既定・上書き計算はPassageの表、未指定値・構築拒否はSpotConnection、実値反映・通知・削除索引は集約で守る
- 無通知だけを検査するときも、予定した状態遷移が実際に起きたことを確認する
- boolの上書きは未指定・True・Falseを区別し、状態更新と一緒に検査する
- 双方向接続の削除は両ID参照に加えて両端の公開出方向一覧を確認する
- 生成された効果計画を、実グラフ適用・保存・配送の成功と表現しない

製品の修理・課題票作成・マージはこの監査に含めない。基準での製品不具合は発見していない。別層の全体監査、公開後の正確な先端のCI確認、配置規約との統合は別の作業として扱う。

## 全44宣言の台帳

位置は編集前の基準。表のR/F/C/Dは元の宣言に対する判断で、新しく増えた表の行を別の監査完了宣言として足さない。

| 番号 | 元の宣言 | 判断 | 契約と検出対象 |
| ---: | --- | :---: | --- |
| 1 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:62` `TestSetConnectionPassage::test_replaces_passage` | F | 置換した形態・状態・通行可否・遮音値を公開参照へ反映。同じWALLだけではkindの置換漏れを見逃す。元BROKENに加えDOOR.OPEN行で別形態を入力し、kindを独立期待値で検査 |
| 2 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:71` `TestSetConnectionPassage::test_emits_state_changed_event_when_passability_flips` | R | 通行不可から通行可への変更を1件通知。通知欠落・多重発火・通行可否逆転を検出。配置監査側のstate API通知とは直接置換APIの入口が異なる |
| 3 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:81` `TestSetConnectionPassage::test_no_event_when_passability_unchanged` | F | 通行可否不変でも状態を更新し通知しない。現行は操作丸ごと省略でも成功。CRACKEDと0.4とFalseを公開参照してから無通知を検査 |
| 4 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:94` `TestSetConnectionPassageState::test_transitions_state_keeping_kind` | R | state APIがWALL形態を維持してBROKENへ移す。状態のみの操作が別形態へ置き換わる退行を検出 |
| 5 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:102` `TestSetConnectionPassageState::test_overrides_apply_to_transitioned_passage` | F | state APIが通行可否・遮音の明示上書きを届ける。元CRACKED/音0.55/通行引数省略を保持し、CRACKED/TrueとBROKEN/False行を追加。stateも独立期待値で検査し、転送漏れ・False省略・上書き時の状態遷移欠落を検出 |
| 6 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:113` `TestSetConnectionPassageState::test_rejects_state_of_different_kind` | R | 既存形態に不適合なLOCKEDを専用例外で拒否。集約のstate APIが値オブジェクトの検証を迂回する退行を検出 |
| 7 | `tests/domain/world_graph/aggregate/test_set_connection_passage.py:119` `TestSetConnectionPassageState::test_door_locked_to_open_transition` | R | LOCKED扉をOPENへ更新して通行可能にする。扉の状態遷移がグラフの公開参照へ反映されない退行を検出 |
| 8 | `tests/domain/world_graph/entity/test_spot_connection.py:37` `TestSpotConnectionValidation::test_negative_travel_ticks_rejected` | R | 負のtravel_ticksを専用例外・文言で拒否。不正な移動時間を構築時に受け付ける退行を検出 |
| 9 | `tests/domain/world_graph/entity/test_spot_connection.py:46` `TestSpotConnectionPassage::test_default_passage_is_open` | R | passage未指定の接続はOPEN・通行可・音1.0。既定値の変更を検出。短い既定値試験でも構築APIの独立契約なので残す |
| 10 | `tests/domain/world_graph/entity/test_spot_connection.py:53` `TestSpotConnectionPassage::test_wall_intact_passage_makes_connection_impassable` | C | 明示WALL.INTACTの通行不可・音0.1。旧同期フィールド削除後は渡したPassageをそのまま読むだけ。定数はPassage壁表、接続への適用は実集約の置換/通知試験が担当 |
| 11 | `tests/domain/world_graph/entity/test_spot_connection.py:59` `TestSpotConnectionPassage::test_door_open_passage_makes_connection_passable_with_full_sound` | C | 明示DOOR.OPENの通行可・音1.0。旧同期フィールド削除後は渡したPassageの再読。OPEN扉の数値をPassage扉表へ先に移し、閉扉からの実集約遷移を保持 |
| 12 | `tests/domain/world_graph/test_dynamic_connections.py:61` `TestRemoveConnectionUnidirectional::test_remove_deletes_from_graph` | R | 単方向削除後get_connectionが専用例外。ID本体の残存を検出。移動/索引/通知とは別の公開契約 |
| 13 | `tests/domain/world_graph/test_dynamic_connections.py:68` `TestRemoveConnectionUnidirectional::test_remove_emits_event` | R | 単方向削除の通知件数・対象ID。通知欠落・多重通知・別IDを検出。未配信集約通知の証明に限定 |
| 14 | `tests/domain/world_graph/test_dynamic_connections.py:76` `TestRemoveConnectionUnidirectional::test_remove_makes_movement_impossible` | R | 削除された接続で移動できない。配置済み実体のmove_entityが削除済みIDを受け付ける退行を検出 |
| 15 | `tests/domain/world_graph/test_dynamic_connections.py:85` `TestRemoveConnectionUnidirectional::test_outgoing_list_updated` | R | 単方向削除後の出方向一覧が空。本体削除だけで索引を残す退行を検出 |
| 16 | `tests/domain/world_graph/test_dynamic_connections.py:96` `TestRemoveConnectionBidirectional::test_remove_deletes_both_directions` | F | 正方向から削除すると双方向本体と出方向索引が消える。元の10/11のUnknownConnectionExceptionを保持し、両端の公開出方向一覧も空と検査。逆索引消去漏れを検出 |
| 17 | `tests/domain/world_graph/test_dynamic_connections.py:105` `TestRemoveConnectionBidirectional::test_remove_reverse_also_deletes_forward` | F | 逆方向から削除しても両方向本体と出方向索引が消える。元の逆ID11入力・10/11の例外を保持し、両端一覧も空と検査。正逆非対称を検出 |
| 18 | `tests/domain/world_graph/test_dynamic_connections.py:118` `TestEffectServiceCreateConnection::test_create_connection_spec_generated` | R | CREATE_CONNECTIONの指定値を効果結果へ変換。from/to/name/bidir/ticksの取り違え・未登録ハンドラを検出。実グラフ追加/保存の証明とはしない |
| 19 | `tests/domain/world_graph/test_dynamic_connections.py:146` `TestEffectServiceCreateConnection::test_create_connection_requires_name` | R | 名前が空の接続作成を生成しない。他のfrom/toは有効なので名前条件が実際に到達する |
| 20 | `tests/domain/world_graph/test_dynamic_connections.py:165` `TestEffectServiceDestroyConnection::test_destroy_connection_spec_generated` | R | DESTROY_CONNECTIONの正ID42を結果へ変換。破壊効果の未登録・ID取り違えを検出。実グラフ削除との別契約 |
| 21 | `tests/domain/world_graph/test_dynamic_connections.py:181` `TestEffectServiceDestroyConnection::test_destroy_connection_zero_id_ignored` | R | 破壊対象ID0なら生成しない。正ID条件の欠落を検出。外部API/LLMなし |
| 22 | `tests/domain/world_graph/value_object/test_passage.py:22` `TestPassageFactories::test_open_default_is_traversable_and_full_sound` | R | OPENの形態・通行可・音1.0既定。シナリオ意味上の公開既定。定数の誤変更を検出 |
| 23 | `tests/domain/world_graph/value_object/test_passage.py:29` `TestPassageFactories::test_open_can_override_sound_permeability` | R | OPENの音0.7上書き。factoryが引数を捨てる退行を検出 |
| 24 | `tests/domain/world_graph/value_object/test_passage.py:42` `TestPassageFactories::test_wall_state_default_table` | R | WALLのINTACT/CRACKED/BROKEN各既定とstate。3行すべて保持。状態表の誤変更を検出 |
| 25 | `tests/domain/world_graph/value_object/test_passage.py:51` `TestPassageFactories::test_wall_overrides_apply` | R | WALL.INTACTの通行True・音0.95上書き。factory引数の脱落を検出 |
| 26 | `tests/domain/world_graph/value_object/test_passage.py:59` `TestPassageFactories::test_door_locked_is_not_traversable` | R | DOORのLOCKED/CLOSED/OPEN既定を表で保護。元LOCKED=Falseを維持しCのCLOSED=FalseとDOOR.OPEN=True/1.0を表へ先に移す。新しいsound既定の追加は不要 |
| 27 | `tests/domain/world_graph/value_object/test_passage.py:64` `TestPassageFactories::test_door_closed_is_not_traversable_by_default` | C | DOOR.CLOSEDの既定通行不可。同じdoor factoryの状態表へ統合。CLOSED入力とFalse確認を保持 |
| 28 | `tests/domain/world_graph/value_object/test_passage.py:69` `TestPassageFactories::test_door_closed_can_be_overridden_to_traversable` | R | DOOR.CLOSEDの通行True上書き。閉扉を素通り可にする明示例外を許容する既定とは別契約 |
| 29 | `tests/domain/world_graph/value_object/test_passage.py:74` `TestPassageFactories::test_open_traversable_can_be_overridden` | R | OPENの通行False上書き。意味的には非推奨だが公開factoryが許容する互換契約。削除しない |
| 30 | `tests/domain/world_graph/value_object/test_passage.py:79` `TestPassageFactories::test_barrier_active_is_not_traversable` | R | BARRIER.ACTIVEは通行不可。障壁の公開既定。単純値だから削除しない |
| 31 | `tests/domain/world_graph/value_object/test_passage.py:84` `TestPassageFactories::test_barrier_inactive_is_traversable` | R | BARRIER.INACTIVEは通行可。障壁解除の公開既定 |
| 32 | `tests/domain/world_graph/value_object/test_passage.py:93` `TestPassageValidation::test_invalid_state_for_kind_rejected` | R | WALLとLOCKEDの不整合を専用例外で拒否。直接構築の検証迂回を検出 |
| 33 | `tests/domain/world_graph/value_object/test_passage.py:104` `TestPassageValidation::test_sound_permeability_out_of_range_rejected` | R | 音透過率-0.01/1.01/2.0を拒否。既存3行と文言を保持。範囲ガード欠落を検出 |
| 34 | `tests/domain/world_graph/value_object/test_passage.py:118` `TestPassageWithState::test_wall_intact_to_broken_uses_default_table` | R | 壁の状態変更はkind維持・state・通行・音を再計算。同じ値保持や旧既定流用を検出。factoryとは状態変更入口が異なる |
| 35 | `tests/domain/world_graph/value_object/test_passage.py:127` `TestPassageWithState::test_with_state_rejects_state_of_other_kind` | R | with_stateは別形態の状態を拒否。状態変更入口の検証迂回を検出 |
| 36 | `tests/domain/world_graph/value_object/test_passage.py:133` `TestPassageWithState::test_with_state_overrides_apply` | R | with_stateの音0.55上書きと通行既定False。明示値と未指定既定の混同を検出。集約引数転送とは別の計算所有者 |
| 37 | `tests/domain/world_graph/value_object/test_passage.py:143` `TestPassageWithState::test_declared_sound_override_returns_with_its_state` | R | LOCKED音0.3はOPEN中1.0、再施錠で0.3。過去#1007の状態別上書き消失を防ぐ。保存層とは別の状態遷移契約 |
| 38 | `tests/domain/world_graph/value_object/test_passage.py:156` `TestPassageWithState::test_declared_traversable_override_returns_with_its_state` | R | CLOSED通行TrueはOPEN往復後もTrue。過去#1007の通行上書き消失を防ぐ |
| 39 | `tests/domain/world_graph/value_object/test_passage.py:169` `TestPassageWithState::test_state_specific_override_table_applies_only_to_each_state` | R | from_dict状態別音0.3/0.9は相互汚染しない。解析入口が複数stateの宣言を取り違える退行を検出 |
| 40 | `tests/domain/world_graph/value_object/test_passage.py:189` `TestPassageWithState::test_direct_constructor_preserves_non_default_values_across_state_roundtrip` | R | 直接構築の非既定True/0.3は状態往復で戻る。過去a68bc9bの独立入口。factoryや保存の試験では代替しない |
| 41 | `tests/domain/world_graph/value_object/test_reactive_passage_binding.py:24` `TestReactivePassageBindingValidation::test_valid_binding_constructs` | R | 有効な真偽別状態の宣言を構築できる。過剰拒否・状態の取り違えを検出。短い構築APIの成功対照を残す |
| 42 | `tests/domain/world_graph/value_object/test_reactive_passage_binding.py:35` `TestReactivePassageBindingValidation::test_empty_on_true_state_rejected` | R | 空のon_true_stateを専用例外で拒否。on_falseは有効なので独立に到達する |
| 43 | `tests/domain/world_graph/value_object/test_reactive_passage_binding.py:45` `TestReactivePassageBindingValidation::test_empty_on_false_state_rejected` | R | 空のon_false_stateを専用例外で拒否。on_trueは有効なので独立に到達する |
| 44 | `tests/domain/world_graph/value_object/test_reactive_passage_binding.py:55` `TestReactivePassageBindingValidation::test_same_states_rejected` | R | 同一真偽状態の宣言を拒否。値オブジェクトの非退化制約。ステージ実行での同stateスキップとは別契約 |
