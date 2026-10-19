# 会議開始・投票集計・同期定義の監査

## 範囲と結果

基準mainは `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。会議開始4・投票集計11・同期定義6の全21宣言を読み、独立第二読を経て、保持17・修理3・統合1・単純削除0とした。

試験3ファイルは298→323行。変更はそのうち2ファイルの追加40・削除15行で、宣言数は21→20、表を展開した実行件数は21→25。製品・共通試験支援は変更0、廃止ファイルは0。削減数や速度改善を成果とはしない。

## 修理と統合

- 勝者の元の2対1を残し、2対1対1と2対1対1対1を追加。過半数や半数を条件にしてしまう退行を検出する
- 同期操作数の元の1件を残して0件を追加。窓の元の0を残して-1を追加し、説明にある下限を実際に通す
- 重複していた「棄権2対指名1」の元2入力を、同じ集計所有者の表へ先にまとめる。旧宣言を残した26件の成功を確認してから1宣言を統合した

## 仕様根拠と既存文書の食い違い

最多票の補強は、現実装の式だけから仕様を作ったものではない。

[設計導入ac4fdaf](https://github.com/Motifman/llm-rpg/commit/ac4fdaf1ad2478c26cfd33b7e0f1d7535d4c150f) は単純多数を選ぶ一方、設計本文に過半数不足という説明も含んでいた。設計書の最終変更は2026-07-26 09:38:49 UTC。その後の同日10:39:09 UTCの[集計API導入f91776b](https://github.com/Motifman/llm-rpg/commit/f91776b646bef3b3eff9332a52f9bf3b2fa50501) は、ユーザーの選択に沿って過半数を要しない単純多数を採ると、変更理由と新規モジュールの説明の両方に明記している。

ただし、基準の `docs/memory_system/meeting_and_voting_design.md` の51・263・280行には古い過半数不足の説明が残っている。f91776bは文例を直したと述べるが、差分に設計書は含まれない。その主張を検証済みとはしない。また、旧集計実装からの変更でもなく、新規API導入時の判断である。

独立第二読では、設計の曖昧な記述を意識した後発の明示選択を根拠として、半数以下の最多者の補強を承認した。既存設計書・製品は今回変更せず、この記載の食い違いを別の課題として残す。

会議理由の保持は[fff93ab](https://github.com/Motifman/llm-rpg/commit/fff93abf204c140dad03b7aeaee107a767546ec8) と設計判断40、許可集合の正本参照は[1bc77ed](https://github.com/Motifman/llm-rpg/commit/1bc77edbd7106952a9f51853d3ff2d262a894691) が導入根拠。単独会議効果は[40f56bf](https://github.com/Motifman/llm-rpg/commit/40f56bf7eb08b432b0170e6e5a9b0d6e48fcd1e4) の専用処理への分離が理由である。

同期定義の正値・操作数制約は[31281b9](https://github.com/Motifman/llm-rpg/commit/31281b95080f16740f87117cc6b3634dc9a8a989) に明記される。[abc2a12](https://github.com/Motifman/llm-rpg/commit/abc2a12c17866aa449f7f7700cca37c4576b806c) の名前到達性の修理は読込側の別契約として残す。

## 主担当と残す別の入口

| 契約 | 主担当 | 代替できない別の責任 |
|---|---|---|
| 会議効果の理由保持・不正値拒否・単独制約 | `test_call_meeting_effect.py`、`WorldGraphEffectService`、`InteractionDef` | 読込時のJSON検査、実行時の理由転送、会議状態への記録、専用処理の確定 |
| 最多・棄権・同点・空票・自己票、結果の票数と投票者別記録 | `test_vote_tally.py`、`resolve_vote` | `MeetingCommandService`の追放反映・観測配送、最終票での閉会、時間切れ、失敗時の復元 |
| 同期定義の正常構築と異常入力拒否 | `test_synchronized_action_group.py`、`SynchronizedActionGroup` | 操作名の到達可能性、異なる参加者、時間窓の実解決、完了/時間切れ効果、準備解除と配送 |

許可集合を差し替える会議試験は、結果そのものを模擬していない。正本集合に第二の値を入れ、宣言値を固定値へ縮退させない独立した退行を検査するため保持した。小さい正常構築も正の対照として保持する。投票記録の比較は実入力を集計した返値の比較であり自己比較ではない。一方、入力との非共有までは保証すると主張しない。

会議集合で移動経路を畳むこと、救命と会議のタイマーの関係、結果配送はこの21宣言の所有契約ではない。関連の主試験を残し、元宣言の監査件数へ重ねて加算しない。

## 全21宣言の台帳

行番号は基準版。Rは保持、Fは契約を保持して補強、Cは先に保持先へ移して統合、Dは単純削除。Dはない。

### `tests/domain/world_graph/test_call_meeting_effect.py`

| 番号・基準行・宣言 | 判定 | 検出する契約と判断 |
|---|---|---|
| 1・42 `TestCallMeetingEffect.test_preserves_the_declared_trigger` | R | 許可集合に含まれる第二の招集理由を効果結果まで保持する。固定emergency_buttonへの置換を検出。 許可集合は実製品とloaderが共有する正本であり、観測結果を偽造していない。設計判断40とfff93ab/1bc77edにより保持。 |
| 2・54 `TestCallMeetingEffect.test_rejects_a_missing_trigger` | R | 直接構築したCALL_MEETINGのtrigger欠落を所定domain例外で拒否する。暗黙補完を検出。 loaderのJSON検査は別入口で、直接構築を代替しない。 |
| 3・59 `TestCallMeetingEffect.test_rejects_an_unknown_trigger` | R | 未知triggerを実適用入口で拒否し、その値を診断へ残す。検証削除・黙殺を検出。 missingとは別の値集合検査。 |
| 4・64 `TestCallMeetingEffect.test_rejects_mixing_a_meeting_call_with_normal_effects` | R | InteractionDefへ会議と通常効果を混在させる構築を拒否する。会議の確定区間へ通常効果を混ぜる退行を検出。 40f56bfの会議command分離が導入理由。純粋な構築であっても公開入力契約。 |

### `tests/domain/world_graph/test_vote_tally.py`

| 番号・基準行・宣言 | 判定 | 検出する契約と判断 |
|---|---|---|
| 5・34 `TestPlurality.test_clear_winner_is_ejected` | F | 最多票の一人を追放する集計規則。元の2対1だけでは過半数必須へ変えても通る。 元2対1を保持し、半数と半数未満の行を同じ宣言へ追加した。仕様根拠は上記の導入履歴と独立判断。 |
| 6・39 `TestPlurality.test_a_lone_vote_loses_to_the_skips` | R | 指名1票より棄権2票を優先して追放しない。棄権を無視する退行を検出。 統合元のA→棄権/B→棄権/C→Bも別行として先に保持した。 |
| 7・51 `TestPlurality.test_a_lone_vote_wins_when_it_outnumbers_the_skips` | R | 指名2票が棄権1票を上回ると追放する。棄権が一つでもあれば拒否する退行を検出。 skip優勢の負例とは別の正の対照。 |
| 8・60 `TestTiesEjectNobody.test_two_way_tie` | R | 名指し同点では誰も追放しない。先着・ID順で勝者を選ぶ退行を検出。 投票が存在する同点を空票の否定と混同しない。 |
| 9・65 `TestTiesEjectNobody.test_tie_with_skip` | R | 指名と棄権が同数なら追放しない。top >= skip_countへの境界変更を検出。 名指し同士の同点とは別条件。 |
| 10・73 `TestTiesEjectNobody.test_skip_alone_ejects_nobody` | C | 棄権2対指名1で追放しない。既存のtest_a_lone_vote_loses_to_the_skipsと同じ公開契約。 元入力をTestPlurality.test_a_lone_vote_loses_to_the_skipsへ先行移管。26件成功後にこの1宣言を統合した。 |
| 11・82 `TestEmptyVote.test_no_votes_ejects_nobody` | R | 空票で例外を出さず追放なしを返す。空Counterへのmax実行を検出。 会議時間切れの無投票から本番利用される下限。 |
| 12・95 `TestTallyIsReportable.test_counts_per_target` | R | 名指し票ごとの実数を返す。勝者だけ残す・票数を1へ丸める退行を検出。 ejected_player_idだけの検査では代替できない結果報告契約。 |
| 13・100 `TestTallyIsReportable.test_skip_count_is_separate` | R | 棄権数を独立して返す。スキップ票計数や結果転送の欠落を検出。 追放結果の陰性と異なる公開値。 |
| 14・105 `TestTallyIsReportable.test_who_voted_for_whom_is_kept` | R | 投票者ごとの相手と棄権をballotsへ保持する。集計だけ返す・棄権行欠落を検出。 実入力に対する返値比較であり自己比較ではない。入力との非共有の追加保証までは既存の主張に含めない。 |
| 15・118 `TestSelfVote.test_self_vote_counts` | R | 自分への票を数えて追放先を決める。自己票除外を検出。 他者への指名票と別の公開受付規則。 |

### `tests/domain/world_graph/value_object/test_synchronized_action_group.py`

| 番号・基準行・宣言 | 判定 | 検出する契約と判断 |
|---|---|---|
| 16・31 `TestSynchronizedActionGroupValidation.test_minimal_valid_group` | R | 二操作・窓2・完了効果を持つ最小定義が受理され、指定窓2を返す。正当構築の過剰拒否や窓の改変を検出。 単純構築という見た目で削除しない。全フィールドや時限解決を証明するとは主張しない。 |
| 17・41 `TestSynchronizedActionGroupValidation.test_empty_group_id_rejected` | R | 空group_idを所定domain例外で拒否する。無名グループ受付を検出。 loaderのid必須判定とは直接構築の別入口。 |
| 18・51 `TestSynchronizedActionGroupValidation.test_required_actions_must_be_at_least_two` | F | required_action_namesが1件以下なら拒否する。1件しか渡さず0件許可へ変わる故障を見逃す。 元の1件を保持し、空tupleを追加した。 |
| 19・61 `TestSynchronizedActionGroupValidation.test_required_actions_must_be_unique` | R | 重複操作名を拒否する。一人の操作で複数枠を満たせる定義を受付ける退行を検出。 二要素を渡すため個数ガードには阻まれず狙ったuniqueガードに到達する。 |
| 20・71 `TestSynchronizedActionGroupValidation.test_window_ticks_must_be_positive` | F | window_ticksが0以下なら拒否する。0だけなので負値許可へ変わる故障を見逃す。 元の0を保持し、-1を追加した。 |
| 21・81 `TestSynchronizedActionGroupValidation.test_on_complete_must_have_at_least_one_effect` | R | on_completeが空の定義を所定domain例外で拒否する。効果なし同期の受付を検出。 他の入力は正常なので完了効果ガードへ到達する。 |

## 故障比較と保持確認

各行は製品に一つの故意変更を入れ、旧21件と新25件をそれぞれ新しいキャッシュで実行した結果。故障は毎回元のバイト列へ戻した。

| 故意変更 | 旧21件 | 新25件 | 判定 |
|---|---|---|---|
| 勝者に過半数を要求 | 全成功 | 半数・半数未満の2行で追放先の判定が失敗 | 修理による新規検出 |
| 勝者に半数以上を要求 | 全成功 | 半数未満の1行で追放先の判定が失敗 | 修理による新規検出 |
| 同期操作数の拒否を1件だけに限定 | 全成功 | 空tupleの行で所定例外が出ず失敗 | 修理による新規検出 |
| 窓の拒否を0だけに限定 | 全成功 | -1の行で所定例外が出ず失敗 | 修理による新規検出 |
| 棄権数を追放判定から外す | 元の保持先・統合元・棄権同点の3件で失敗 | 保持先の元2入力・棄権同点の3件で失敗 | 統合前後の検出を保存 |

5種類・旧新10実行。新規検出4種類について、旧の対応1宣言だけでなく旧所有21件全体が成功してしまうことを確認した。統合対象は元の両入力が保持先自身で失敗する。違う入口の失敗を代わりの証拠にしていない。

各作業木の追跡済み `src` / `tests` 全3176ファイルを照合した。製品1601ファイルは全て基準と一致し、旧作業木の差分は0、新作業木の差分は承認した2試験だけ。表を拡張した保持先1宣言を除くR16宣言は構文木が不変だった。

## 基準と最終確認

Python 3.10.22 / pytest 8.4.1。資格情報を除去し外部TCP接続を遮断した固定対象の環境で直列実行した。

- 未編集基準: 所有21＋関連62＝83件成功
- 統合元を残した保持先先行: 所有26件成功
- 統合後: 所有25件成功
- 5種類10実行の故障比較後、全製品を復元
- 最終: 所有25＋関連62＝87件成功、失敗・収集エラー・skipは0
- Ruff 0.16.8で変更2試験を検査し成功。`git diff --check`も成功

関連62件は以下の実際の入口を通す。反復回数や関連件数を21宣言の成果へ加算しない。

- 緊急ボタンの実操作5件
- 同期解決の完了・未完了・時間切れ・参加者限定の配送12件
- 会議処理の確定・失敗時復元・移動状態・票と追放の順序14件
- 投票結果の追放と結果配送6件
- 会議の沈黙・時間上限・時間切れ時集計9件
- 集合後の移動継続2件
- 同期名の到達可能性と旧キー拒否7件
- runtimeの会議入口接続2件
- 会議宣言の有効性・理由・単独効果の読込拒否5件

全リポジトリ試験・実LLM・有料API・ネットワーク試験・性能比較はローカルで実施していない。公開する正確な先端のCIは別途確認する。

## 併行変更と限界

2026-10-14 10:57 UTCの照合ではmainは不変、未統合78件の先端と変更パスを確認した。対象3試験と宣言所有者の直接重複はない。

- #1670の実interactによる二役拒否は、同期定義の入力検査とは別責任で保持
- #1688の物体備蓄条件は対象選択の2行だけで、会議理由の転送・投票・同期構築は不変
- #1737の経路選択と会議集合後の移動状態、#1742/#1743の他効果と会議効果は別の保証
- 記憶・SNSの進行中変更、製品修理、Issue作成、統合操作は対象外

製品・共通支援の削除を解放する変更はない。今回の責任分担はこの記録に残し、同時に変更中の共通規則を重ねて編集しない。
