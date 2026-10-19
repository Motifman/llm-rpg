# 島の救助経路を保った試験整理

## 結論

島シナリオの実行試験4ファイルを整理し、**15ケース・894行から10ケース・836行**にした。断言を主試験へ移して重複起動を5回減らし、救助時刻・漂流締切・実際の材料消費・拒否理由の検査不足を補った。本番コード、シナリオ、共有補助の最終変更はない。

変更後10件は初回と変異復元後2反復、関連51件は変更前後とも全成功。12組の所有者変異と旧版対照により、移管した5契約の保存と、旧試験が見逃した7種の誤りの検出を確認した。製品の基準失敗はなかった。

今回の成果は保守性と検出精度の改善。実時間は変更前245.92〜260.42秒、復元後242.38〜246.08秒と重なり、未固定乱数の2反復なので、確定的な速度改善率は主張しない。

対象上流: `0b51eb28d4692635a932dcf4063ab9b231768bf0`。同内容の再構成基点: `6dc7e3435582e5efd7ece01b2dbda8347c1db599`。ローカル検証まで完了。公開・PR作成・マージは行っていない。

## 範囲と変更量

| ファイル（`tests/e2e/`以下） | ケース 変更前→後 | 行数 変更前→後 |
|---|---:|---:|
| `test_survival_island_v2_rescue_e2e.py` | 5→1 | 313→212 |
| `test_survival_island_v3_coop_sign_e2e.py` | 3→2 | 163→154 |
| `test_survival_island_v3_coop_rescue_e2e.py` | 3→3 | 232→284 |
| `test_survival_island_v4_signal_deposit_e2e.py` | 4→4 | 186→186 |
| 合計 | 15→10 | 894→836 |

全15宣言にパラメーター展開はない。最終差分は147行追加・205行削除、純減58行。補助関数を含む試験側の数値。本番・シナリオ・共有補助は各0行変更、廃止ファイルなし。

## 本番の所有者と残す層

1. **セッション入口**: `GameRuntimeManager.create_session` は本番アプリから呼ばれ、シナリオを読んで `create_world_runtime` とLLM配線を作る。v2/v3の入口は維持した
2. **実ツール経路**: 対象ラベルを実プロンプトから取得し、`StubLlmClient` → `run_turn` → `SpotGraphToolExecutor._interact` → `WorldRuntime.do_interact` → `SpotInteractionApplicationService.execute_interaction` を通す。単に内部サービスを模倣した結果ではない
3. **実保存と条件**: 同アプリケーションサービスはグラフの人数と位置、実在庫、書き手名をドメインへ渡す。効果適用後の旗・物体・在庫を確定し観測を配る。山頂所属と必要品の前提は保存先から読み直す
4. **時計と結果**: `advance_tick` → `SpotGraphSimulationApplicationService` → `PlayerOutcomeRuleStageService`。最初の救助と漂流締切の直前/当日を同じ連続した時計で観測する。途中の待機手番も残す
5. **看板**: `WRITE_PLAYER_TEXT` / `SHOW_PLAYER_TEXT` の本番保存・署名解決と実配置を通す。拠点と山麓は別の宣言接続なので両方残す
6. **v4預入**: `deposit_removal_details` と効果ハンドラーの削除予約が、アプリケーション所有者で実在庫の減算と物体状態へ反映されるまで確認する。下位の辞書・削除予約だけの試験は代替にならない

v2完走を初期配置・山頂所属・必要品・点火の主所有試験にし、v3は二つの拒否と二人完走を保持。看板は拠点の未記入→不在者への伝言と山麓往復を保持。v4は4ケースすべて保持した。本番削除や試験専用の公開機構の新設はない。

## 全15宣言の最終台帳

R=保持、F=契約を保ち断言/説明を修復、C=主試験へ先に移管して統合、D=削除。**R5 / F5 / C5 / D0**。以下の行番号は変更前。

### v2: `TestSurvivalIslandV2RescueE2E`

| 元宣言 | 判定 | 残る主張・実施内容・具体的な回帰 |
|---|---|---|
| `test_step1_ada_shipwreck_beach_spawn` (143–153) | C | 浜辺の初期4人を完走冒頭へ移管。登場位置の誤設定を検出。人数3へ変える所有者変異を旧新版で検出 |
| `test_step2_ada_summit_teleport` (155–167) | C | 配置後の山頂所属を保存済みグラフから確認。グラフ保存で所属が消える変異を旧新版で検出。移動経路探索の証明とは扱わない |
| `test_step3_item_three_ada` (169–191) | C | 必要3品を保存済み実在庫から確認。公開の `iter_occupied_slots` を使い私有スロット辞書への依存を外した。実在庫保存で流木が欠ける変異を旧新版で検出 |
| `test_step4_llm_stub_via_light_signal_line` (193–225) | C | 実 `run_turn` の成功と旗成立を完走へ移管。副作用は成功したのにツール結果だけ失敗する変異を旧新版で検出 |
| `test_step5_tick_168_ada_rescued_outcome` (227–313) | F | `test_signal_rescues_ada_at_192_and_ends_at_384` へ改名。191未確定→192救助、383で残員未確定→384全員確定と終了を検査。最初の救助/締切が遅れると新版のみ失敗 |

移管後は全行が最後の1ケースへ集約される。元の `invoke` 回数spyは `>=1` しか要求せず、正確な回数契約ではなかった。実呼出しを残し、結果と世界状態で接続を保証する。呼出形の固定を独立契約とは扱わない。

### v3看板

| 元宣言 | 判定 | 残る主張・実施内容・具体的な回帰 |
|---|---|---|
| `TestCampNoticeBoardCarriesMessageAcrossAbsence::test_noah_reads_message_ada_wrote_while_absent` (80–111) | R | 実拠点の板切れにAdaが書き、後からNoahが本文と署名を読める。読込・物体保存・名前解決の切断を検出 |
| 同クラス `test_unwritten_board_shows_nothing_written` (113–130) | C | 上の試験の書込前へ移管。Noahが未記入を読んだ後に浜辺へ戻り、Adaの書込時には不在であることを明示確認。誤った未記入文を旧新版で検出 |
| `TestTrailCairnAtFoothillsForksTowardMountain::test_write_then_read_round_trip_at_foothills` (136–163) | R | 別配置・別操作名・リオの署名を通す。山麓側だけの宣言接続破損を拾うため保持 |

### v3救助

| 元宣言 | 判定 | 残る主張・実施内容・具体的な回帰 |
|---|---|---|
| `TestSoloCannotLight::test_solo_light_signal_is_rejected` (135–152) | F | 材料が揃っていても単独では拒否、旗なし、実在庫不変、もう一人必要という公開拒否理由を確認。無関係な理由の誤表示を新版のみ検出 |
| `TestInsufficientMaterials::test_single_driftwood_is_rejected` (158–176) | F | 二人いても流木1では拒否。実在庫不変と流木不足の公開理由を確認。人数不足への誤表示を新版のみ検出 |
| `TestDuoLightsAndSummitOnlyRescue::test_duo_light_succeeds_and_rescue_resolves_at_144` (182–232) | F | 実在庫から流木3/枯れ葉2だけが消え他品が残ることを確認。143未確定→144山頂2人救助、239麓2人未確定→240漂流と終了。消費欠落・救助/漂流遅延を新版のみ検出 |

### v4: `TestDistributedSignalDeposit`

| 元宣言 | 判定 | 残る主張・実施内容・具体的な回帰 |
|---|---|---|
| `test_two_players_deposit_materials_then_light_signal` (81–109) | R | 二人の分担材料を実在庫から消して台へ蓄積し点火。削除予約だけで保存しない退行を拾うため保持 |
| `test_direct_light_with_personal_materials_fails_before_deposit` (111–134) | R | 個人が全材料を持っていても台が空なら正しい理由で拒否し在庫を守る。旧個人所持条件へ戻る退行を検出 |
| `test_deposit_wakes_co_located_witness_with_declared_message` (136–154) | F | `test_deposit_delivers_turn_scheduling_observation_to_witness` へ改名。宣言文と人物名が実観測として届き起動対象属性を持つ契約に説明を合わせた。実スケジューラーの起動予約まで証明したとは扱わない |
| `test_fixed_three_with_two_owned_keeps_inventory_and_state_in_sync` (156–186) | R | 要求3/所持2の固定数量分岐で実在庫0・台2を検査。下位の削除予約一致やquantity='all'だけでは代替できないので保持 |

### 否定条件と証明範囲の限界

集約により、複数の故障が同時にある場合の独立した診断は減る。先行する断言が失敗すると、後続の断言は実行されない。ただし、初期人数・保存済み位置・必要品・点火成功の段階別の断言は時計進行前に置き、各単独故障の早期検出を維持する。

山頂所属・必要品の存在・点火成功は、「山頂以外では救助不可」「不足材料なら拒否」の否定条件全般の代替ではない。元step2/3もそこは検査していなかった。主試験へ移したことを理由に保証範囲を広く述べない。

拒否理由の変異は**公開拒否文の誤表示**を検出したもので、「異なる内部条件で拒否されたことを全て検出した」とは言わない。実際の人数/材料不足の入力は各独立ケースに残す。

## 期待値を現在JSONの写しにしない根拠

- [PR435](https://github.com/Motifman/llm-rpg/pull/435) と [改定コミットd1154cd](https://github.com/Motifman/llm-rpg/commit/d1154cd0a1f7bf125190af1ad6900ff871d09afb) は、v2の1日24→48tick、救助168/264→192/288/336、漂流336→384を明示する。判断・対話の時間と救助機会を増やす改定。試験名の168は更新漏れだった
- [v3導入PR695](https://github.com/Motifman/llm-rpg/pull/695) の時間圧と机上検算が救助144/192、漂流240を明示する。材料3/2/1、二人条件、最初の機会を逃しても二度目へ学習を持ち越せる意図がある。[PR709](https://github.com/Motifman/llm-rpg/pull/709) は本体と実行試験の再取込みを記録する
- [PR370](https://github.com/Motifman/llm-rpg/pull/370) は実ツールから状態変化までの接続漏れを実験前に検出する狙い。[#471対応](https://github.com/Motifman/llm-rpg/commit/7b872dc9d94dd4b1df949ad685dfc874da125c18) はwait内の入れ子tickを除去した履歴。連続時計・待機手番を省かない理由になる
- [PR714](https://github.com/Motifman/llm-rpg/pull/714) / [PR717](https://github.com/Motifman/llm-rpg/pull/717) は不在者への伝言と2配置の意図。[PR908](https://github.com/Motifman/llm-rpg/pull/908) は分担して運んだ材料の実減算と台への蓄積を同じ数量で保証する意図

初期調査の「実装と過去説明が違えば現在ソース優先」は撤回した。期待値は改定根拠で裏付け、根拠が見つからない不一致は未確定とする。

## 完走を弱めない条件

- v2/v3のManager入口、実ラベル解決、実run_turnを維持
- 時間ジャンプなし。`advance_tick` と待機手番を連続実行
- 指定時刻までの進行は有限range。毎回1tickだけ進むことを確認し、飛越・停止・早期終了は即失敗
- 欲求無効化は既存方式を維持。`hunger_per_tick=0` は公開設定で拒否されるため、同値と確かめず置換しない
- seedや天候の入力を変更しない。嵐による基準失敗は観測していない
- 2本の救助完走、山麓の別配置、v4の実在庫・数量不足・実配送は残す

## 所有者変異と旧版対照

全12組24実行を直列で実施。旧版は同基点のgit blobを使い、試験補助を壊すだけの変異にはしていない。各組で所有者と試験をバイト単位復元した。

| 対象 | 所有者への変異 | 旧版 | 新版 |
|---|---|---|---|
| 初期4人 | Adaの初期位置を拠点にする | 失敗 | 失敗 |
| 山頂所属 | グラフ保存時に山頂所属を消す | 失敗 | 失敗 |
| 必要3品 | 実在庫保存時に流木を欠落させる | 失敗 | 失敗 |
| 点火成功結果 | 実相互作用の副作用後、ツール結果を失敗にする | 失敗 | 失敗 |
| 未記入文 | 効果ハンドラーの既定文を誤文にする | 失敗 | 失敗 |
| 単独拒否理由 | 人数不足を無関係な品物不足と表示 | 成功 | 失敗 |
| 材料拒否理由 | 流木不足を人数不足と表示 | 成功 | 失敗 |
| 流木消費 | 点火時の流木消費効果だけを除く | 成功 | 失敗 |
| v2最初の救助 | 192→193 | 成功 | 失敗 |
| v2漂流締切 | 384→385 | 成功 | 失敗 |
| v3最初の救助 | 144→145 | 成功 | 失敗 |
| v3漂流締切 | 240→241 | 成功 | 失敗 |

全失敗は対象断言によるもので、収集エラー・無関係な例外ではない。意図的な誤りの検出結果であり、実際の製品不具合を12件発見したという意味ではない。v4は独立契約を保持し、変更は1件の名称・説明のみ。

詳細な所有者ファイル、旧新版node ID、失敗行、復元hashは `survival-e2e-mutations-ja.md`。独立保存レビューでも12組と復元hash、固定差分の一致を確認した。

## 実行結果・測定限界

| 実行 | 成功 | 実時間秒 | 利用者CPU秒 | システムCPU秒 |
|---|---:|---:|---:|---:|
| `survival-baseline1` | 15 | 260.415 | 260.074 | 0.278 |
| `survival-baseline2` | 15 | 245.920 | 245.660 | 0.210 |
| `survival-boundaries-baseline` | 51 | 10.452 | 10.212 | 0.234 |
| `survival-focused` | 8 | 7.457 | 7.297 | 0.158 |
| `survival-candidate` | 10 | 243.011 | 242.718 | 0.250 |
| `survival-final1` | 10 | 246.077 | 245.791 | 0.245 |
| `survival-final2` | 10 | 242.379 | 242.078 | 0.271 |
| `survival-boundaries-final` | 51 | 11.208 | 11.017 | 0.173 |

関連51件は看板アプリケーション6、人数配線2、預入ドメイン10、宣言結果動作6、結果配線3、自由入力ツール配線4、島結果宣言20。各所有者の狭い証明と実シナリオの接続証明を区別して保持した。

指定runnerは認証関連環境変数を除去し、外部通信遮断と作業環境自身のsrc確認を通す。Python3.10.22、pytest8.4.1。seed固定用pluginなし。通常・変異・旧版対照をすべて直列実行。正確なargv、終了値、時間は各接頭辞の `.json`、全結果は `.log` / `.xml`、ケース別setup/call/teardownは `-phases.json` に保存した。

- 時間は未固定世界乱数と環境の揺らぎを含む。少数反復で速度改善率を確定しない
- 初回runtime初期化の約4秒は統合後も別ケースへ移り得る。削除した最初のケースの時間をそのまま節約としない
- 主な時間は2本の完走に残る。今回、それを削って速くしていない
- 旧固定点68c96の計時値や複製時間の割合は今回の改善率に使わない
- 全リポジトリ試験・リモートCIは今回未実行。今回の4ファイルと関連51件の証明に限定する

### 復元後の全10ケース時間（本体呼出し秒）

| ケース | final1 | final2 |
|---|---:|---:|
| `tests/e2e/test_survival_island_v2_rescue_e2e.py::TestSurvivalIslandV2RescueE2E::test_signal_rescues_ada_at_192_and_ends_at_384` | 164.030067 | 161.842274 |
| `tests/e2e/test_survival_island_v3_coop_sign_e2e.py::TestCampNoticeBoardCarriesMessageAcrossAbsence::test_noah_reads_message_ada_wrote_while_absent` | 0.061179 | 0.061387 |
| `tests/e2e/test_survival_island_v3_coop_sign_e2e.py::TestTrailCairnAtFoothillsForksTowardMountain::test_write_then_read_round_trip_at_foothills` | 0.047771 | 0.054980 |
| `tests/e2e/test_survival_island_v3_coop_rescue_e2e.py::TestSoloCannotLight::test_solo_light_signal_is_rejected` | 0.056573 | 0.057665 |
| `tests/e2e/test_survival_island_v3_coop_rescue_e2e.py::TestInsufficientMaterials::test_single_driftwood_is_rejected` | 0.056101 | 0.058059 |
| `tests/e2e/test_survival_island_v3_coop_rescue_e2e.py::TestDuoLightsAndSummitOnlyRescue::test_duo_light_succeeds_and_rescue_resolves_at_144` | 77.772127 | 76.333671 |
| `tests/e2e/test_survival_island_v4_signal_deposit_e2e.py::TestDistributedSignalDeposit::test_two_players_deposit_materials_then_light_signal` | 0.087855 | 0.093897 |
| `tests/e2e/test_survival_island_v4_signal_deposit_e2e.py::TestDistributedSignalDeposit::test_direct_light_with_personal_materials_fails_before_deposit` | 0.054478 | 0.057331 |
| `tests/e2e/test_survival_island_v4_signal_deposit_e2e.py::TestDistributedSignalDeposit::test_deposit_delivers_turn_scheduling_observation_to_witness` | 0.041123 | 0.052527 |
| `tests/e2e/test_survival_island_v4_signal_deposit_e2e.py::TestDistributedSignalDeposit::test_fixed_three_with_two_owned_keeps_inventory_and_state_in_sync` | 0.304256 | 0.056082 |

## CIと最終状態

既存CIはPython3.10、`uv sync --locked --extra export`、`uv run --frozen pytest -n auto`。通常収集される4ファイルをすべて維持し、markやルーティング変更なし。

最終ruff検査、`git diff --check` が成功。変更は対象4試験のみで、本番・シナリオの全変異を撤去済み。最終差分とSHA256一覧を保存した。共有補助・新しい本番機構・新しい環境設定は追加していない。

証拠一覧:
- `survival-e2e-discovery-ja.md`: 全15件の詳細な発見台帳、呼出し、来歴、初期判断と訂正
- `survival-e2e-baseline-ja.md`: 変更前の全ケース計時と実行条件
- `survival-e2e-mutations-ja.md`: 全12組の具体的な失敗位置と復元hash
- `survival-final.patch`: 最終4ファイル差分
- `survival-final-manifest.json`: 変更量・ケース数・最終SHA256
- `survival-static-final.log`: 静的検査・差分範囲
- 各実行接頭辞の `.log` / `.xml` / `.json` / `-phases.json`

公開操作は確認待ち。今回のローカル試験整理と証明は完了し、追加領域の監査は開始していない。
