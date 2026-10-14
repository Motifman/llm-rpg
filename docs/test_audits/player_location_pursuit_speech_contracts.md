# プレイヤーの位置・追跡・発話の通知と拒否後保持

## 範囲と依存

元21宣言を R11/F10/C0/D0 として監査した。位置・経路2、追跡12、発話7が対象。削除・統合は行わず、元の65assertに34個の観測を加えた。試験ファイルは1322行から1369行（+59/-12）。製品コードと共通準備は変更していない。

この変更は [#1727](https://github.com/Motifman/llm-rpg/pull/1727) に依存する。基準ブランチは `codex/test-audit-player-resource-growth-20261014`、公開基準先端は `337d93b4fa1743f9175403412e35835f84ea4d02`。先行する資源・成長39、注意/効果6、対象外の合成戦闘2を保持し、今回の21件へ重複計上しない。

## なぜ変えたか

- 位置/追跡の一部は通知の存在しか見ず、話者や対象の誤転記、重複を見逃していた
- 残経路は長さ2だけで、同じ長さの誤った座標を集約へ保存しても通っていた
- 追跡の対象不一致は例外だけが正しくても、元の追跡値や既存通知を壊す処理を見逃した
- SHOUTの元入力はplayer2/spot2/(1,1,0)だが、話者・場所・座標の転記を確認していなかった
- 発話拒否は例外を確認する一方、拒否前に通知を積んでしまう処理を検出しなかった

## 主担当と残す契約

位置・経路の計算は `PlayerNavigationState`、追跡値の遷移は `PlayerPursuitState` が所有する。集約はそれらの新状態を保持し、公開操作の拒否と未発行イベントを作る。値型の試験は集約が結果を誤保存する故障を検出できない。

移動サービスはマップ更新と保存・到着判断、追跡サービスは探索・切替・再計画・保存を所有する。発話サービスは検索・例外変換・発行後の排出・発行失敗を所有し、観測側は配信先と表示を所有する。観測側が自分で作ったイベントを受け取る試験は、集約が正しいイベントを作った証拠ではない。

追跡の同値更新2件は保持した。開始コマンドは `last_known` を省略し、継続サービスは同値を明示する。後者は [a0620bc](https://github.com/Motifman/llm-rpg/commit/a0620bc9f691b1f3dd6c38322f7d314c85951159) で追加された退行試験であり、短い別入力を削減目的で結合しない。

静的移動と追跡の非干渉は、非空の静的経路を持つ失敗/清掃の逆方向2件で守る。開始・中断の元入力は静的経路が空なので、その2件から非空経路の保持まで保証したとはしない。

## 実利用者と履歴

- `application/world/services/movement_step_executor.py` が位置更新を呼び、`movement_service.py` が経路設定・前進・清掃を利用する
- `pursuit_command_service.py` が開始・更新・切替・中断を、`pursuit_continuation_service.py` が明示の位置情報更新と失敗を呼ぶ
- `application/speech/services/player_speech_service.py` が通常の集約発話を呼ぶ。`world_runtime.py`、発話/スポットグラフのツール実行器がそのサービスを利用する
- [98328af](https://github.com/Motifman/llm-rpg/commit/98328af87cf2fe8d7694d1364ea78b159ea6e40c) が位置・経路2件を導入し、[f038f40](https://github.com/Motifman/llm-rpg/commit/f038f40d44d3e69eff766c86848932ee552db8b8) が値型へ抽出した
- [6cb30f4](https://github.com/Motifman/llm-rpg/commit/6cb30f4775760cd7e2bd7b7277c0e02bfa600f02) が追跡を静的経路から分離し、[6c0d681](https://github.com/Motifman/llm-rpg/commit/6c0d681eacd0289e4edb7beac4b6c67982b59427) が公開API互換を保って値型へ抽出した
- [0a82dea](https://github.com/Motifman/llm-rpg/commit/0a82dea0d61da38ad8241611fbad66eb00ec1077) が追跡の専用ドメイン例外と元6負例を追加した
- [8dc037b](https://github.com/Motifman/llm-rpg/commit/8dc037bcc1870714dfc97726781cf8d9cf75884b) が発話7件とサービス・観測を別の境界として導入した

## 元21件の台帳

全件の保持先は元の `tests/domain/player/aggregate/test_player_status_aggregate.py`。名前は元のまま。R11の本文、元65assert、全入力、元7準備関数、対象外47宣言を保持した。中断試験のsnapshotだけは、同じ準備呼出しをローカル変数へ置いて同じ開始操作へ渡している。

| 元の試験名 | 判定 | 検査する契約と保持・修理の理由 |
|---|---|---|
| `test_location_updates` | F | 位置イベントを1件、識別子・旧位置None・新位置・時刻Noneで確認。元3点経路・戻り値・長さ2・清掃を保持し、残経路を[coord1,dest]と独立比較。誤った「進んだ先が残る」コメントを訂正。 |
| `test_advance_path_exhaustion` | R | 下位値型は遷移結果を返すだけ。集約が戻り値を返し新状態を保持する接続を別に検査する。2点経路と目的地消去は非空→空の実遷移であり既定値試験ではない。 |
| `test_start_pursuit_stores_separate_state_and_emits_started_event` | R | 集約が実PursuitStateと開始イベントを作る唯一の短い主試験。静的経路は最初から空で、非空経路の保持まで保証するとは記述しない。 |
| `test_update_pursuit_emits_only_for_meaningful_changes` | F | 元の省略last_known無更新→(4,4,0)更新の順と全assertを保持。更新イベントの件数1、aggregate_id/type、actor_id、target_idを確認。 |
| `test_update_pursuit_is_noop_when_snapshot_and_last_known_are_unchanged` | R | a0620bcで追加された継続処理の退行。継続処理はlast_knownを明示し、開始コマンドは省略するため入力契約が異なる。短い独立試験を保持し、削減目的で先行無更新との逐次試験へ結合しない。 |
| `test_fail_pursuit_clears_only_pursuit_state_and_emits_failed_event` | R | 非空静的経路と追跡が共存する入力から追跡だけを消す、意味のある非干渉契約。下位PlayerPursuitStateは静的経路を持たないので代替できない。 |
| `test_clear_path_does_not_cancel_active_pursuit` | R | 上記とは逆方向の非干渉。非空経路の清掃後も実追跡が残り、イベントも出ない。移動アプリの試験は保存/到着処理の接続という別の責務。 |
| `test_cancel_pursuit_emits_cancelled_event_and_clears_state` | F | 元対象99、静的経路なし、中断後stateNoneを保持。中断イベント1件のaggregate/actor/target、snapshot、last_knownを元の入力と比較。 |
| `test_update_pursuit_when_no_active_pursuit_raises_no_active_pursuit_exception` | R | 集約公開updateの専用ドメイン例外を固定する。値型の同名ガードと別入口で、アプリは同条件を無操作へ変換し得るため代替できない。 |
| `test_fail_pursuit_when_no_active_pursuit_raises_no_active_pursuit_exception` | R | 公開failのNoActivePursuitExceptionを守る短い独立負例。cancel/updateのガードが残ってもこの入口だけ壊れる故障は存在する。 |
| `test_cancel_pursuit_when_no_active_pursuit_raises_no_active_pursuit_exception` | R | 公開cancelのNoActivePursuitException契約。アプリcancelは無追跡時に成功no_opを返すため、その試験を集約拒否の代替にしない。 |
| `test_start_pursuit_with_different_target_while_active_raises_cannot_switch` | F | 99→88と専用例外/文言、元target99assertを保持。拒否前後の公開pursuit_state全体と既存未発行イベント一覧を比較。 |
| `test_update_pursuit_with_different_target_snapshot_raises_pursuit_target_mismatch` | F | 元snapshot88+last_known99と専用例外/文言を保持。公開pursuit_stateと既存未発行イベントを前後比較。 |
| `test_start_pursuit_with_last_known_target_id_mismatch_raises_pursuit_last_known_mismatch` | F | snapshot99とlast_known88/spot1/(0,0,0)/observedNoneを保持。拒否後も無追跡かつ未発行イベントなしを確認。 |
| `test_speak_say_success` | R | 話者/本文/チャンネル/場所/座標/宛先Noneを実イベント1件から観測する、集約の入力受理の主試験。アプリは検索/発行/排出、観測戦略は配信範囲という別契約。 |
| `test_speak_shout_success` | F | 元player2/spot2/(1,1,0)/「助けて！」/SHOUTを維持し、通知の話者・場所・座標・対象Noneを追加確認。 |
| `test_speak_whisper_success` | R | 有効な宛先99を伴うWHISPERの成功と転記。宛先欠落拒否とは別の正例で、宛先を無視する故障を直接検出する。 |
| `test_speak_whisper_without_target_raises` | F | 有効内容「こんにちは」・非ダウン・WHISPER・明示targetNone・専用例外/文言を維持し、拒否後のget_events()==[]を確認。 |
| `test_speak_empty_content_raises` | F | 空文字と空白3文字を両方そのまま維持。各raises直後にget_events()==[]を確認し、片方だけの不発をもう片方で代替しない。 |
| `test_speak_when_downed_raises` | F | 元is_down=True/「助けて」/SAY/spot1/(0,0,0)と専用例外・文言を維持し、拒否後のget_events()==[]を確認。 |
| `test_speak_strips_content` | R | 空白付きの有効本文をhelloへ正規化して1イベントにする独立成功境界。空白のみ拒否は有効本文の正規化を検出しない。 |

## 基準・候補・故障対照

- #1722相当の発見基準で構文木と47件の収集を確認後、未編集の対象21＋関連26が成功
- #1727基準へ揃え、元21本文/構文木、元7準備、製品1601ファイル、関連6ファイルの同一性を確認。専用作業ツリーで同じ47件が成功
- 候補の47件も成功。対象は引き続き21宣言、追加後は99assert
- 改善34組は、それぞれ旧21件が全成功し、新21件では対応する追加assertだけが失敗。34個の追加assertの全行に、それぞれ独立の故障対照が対応する
- 保持11組は旧新とも対応するRの元の確認で失敗。意味を保った位置比較式の変更1組は旧新とも全21件成功
- 計46組92実行はすべて直列。準備・収集・後始末の失敗、skipは0。各実行後に両方の製品1601ファイルと試験一式を完全復元した

改善対照の内訳:

| 操作 | 故障の種類 | 組数 |
|---|---|---:|
| 位置通知 | 集約ID/種別、旧spot/座標、新spot/座標、tickの誤転記、通知重複 | 8 |
| 経路前進 | 値型と戻り値/長さを保ったまま、集約だけが残経路の先頭を通過点へ誤保存 | 1 |
| 追跡更新通知 | 集約ID/種別、actor/targetの誤転記、通知重複 | 5 |
| 追跡中断通知 | 集約ID/種別、actor、snapshot/last_knownの誤転記、通知重複 | 6 |
| 追跡対象不一致3入力 | 各入力で公開追跡値の変更と未発行通知の変更を別々に検査 | 6 |
| SHOUT | 話者/場所/座標の既定値化、不要な宛先の追加 | 4 |
| 発話拒否 | ダウン、宛先なし、空文字、空白3文字それぞれの拒否前通知 | 4 |

保持11組は、経路終了、開始actor、明示同値更新、非干渉2方向、未追跡のupdate/fail/cancel専用例外、SAY種別、WHISPER宛先、有効本文の空白除去を検査した。旧新のいずれも対象の元確認で故障を捉えた。

残経路の値型の算術は既存の値型試験でも守られている。今回の改善対照は集約だけの誤保存を使い、その層固有の検出力を示した。発話の宛先欠落はアプリが集約より先に拒否するため、アプリの負例を集約の残留通知の代替にしていない。

## 最終確認と限界

復元後の最終は全ファイル69実行＋関連26＝一意95件が全成功し、失敗・エラー・skipは0。全ファイルは68宣言だが、先行#1727の経験値加算1宣言が2行のため実行数は69になる。対象21の宣言/実行数には変更がない。Ruff0.16.8と差分検査も成功。独立保存審査も合格し、元入力・assert・対象外の保持、全故障対照の失敗位置、製品の完全復元、最終95件を確認した。Python3.10.22 / pytest8.4.1、対象作業ツリー自身のsrc、資格情報除去、通信遮断で実行した。実LLM・外部APIは呼んでいない。

この監査が確かめるのは集約の公開値と未発行通知までで、観測が相手へ実配送されたことや記憶へ届いたことを主張しない。無関係な全状態の原子性、指定tickや非空静的経路の新規網羅、Monster追跡、変更中のmemory/SNSを対象へ加えない。製品不具合の修理、Issue作成、マージは含めない。

変更中の #1693/#1694 は、共有 `world_runtime.py` の発話呼出しを変更しないことを差分で確認した。通常CIはPython3.10で通常pytest、Ruff、mypy、秘密情報走査、品質資料の5経路を持つ。手元では全リポジトリ試験を実行しておらず、公開した正確な先端のCIは別に確認する。

## この21件の所有ルール

この規則は `test_player_status_aggregate.py` の位置・経路2件、追跡12件、発話7件だけに適用する。他の資源・成長・状態効果の所有範囲は変更しない。

- 位置・経路と追跡の値型は状態遷移を、集約は新状態の保持・公開拒否・未発行通知を所有する。値型が通るだけで集約の保存結果を代替しない
- 発話の入力検証・正規化・通知値は集約で確認する。サービスの発行・排出や、観測側の配信範囲・表示とは分ける。自作イベントを受け取る試験で生成元の転記を代替しない
- 拒否後に守るものを具体的に確認する。追跡対象不一致では元の公開追跡値と既存通知、発話拒否では新規通知がないことを見る。無関係な全状態の原子性へ広げない
- 通知は型の存在だけでなく、件数とその操作が所有する業務値を確認する。UUID・実時刻・内部実体の同一性は固定しない
- 追跡更新の `last_known` 省略と同値の明示は、開始コマンドと継続処理で別の実入力。空文字と空白だけの発話も別入力として維持する
- 空の静的経路から非空経路の保持を保証したと記述しない。静的移動と追跡の相互非干渉は、非空経路を持つ失敗・清掃の試験が守る
- 残経路を説明するときは、現在地も残る仕様と整合させる。件数だけで経路内容を代替しない

`tests/domain/player/aggregate/AGENTS.md` は #1699、親階層の `tests/domain/player/AGENTS.md` は #1725 が新設中のため、このPRでは同名ファイルを追加しない。両PRの統合後、既存ルールとこの21件の適用範囲を照合し、必要な内容を既存AGENTSへ追記する。
