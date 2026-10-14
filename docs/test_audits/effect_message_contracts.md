# 看板の本文と秘匿状態の監査

## 範囲と結論

基準はmain `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。効果処理の看板・部屋人数要求の全17宣言を、製品所有者・呼出元・導入履歴・既存の保持先まで読んだ。独立第二読の判定は保持10・修理4・統合3・削除0。状態効果38宣言とは別単位で、関連試験と表の行を17宣言の監査数へ足していない。

試験は17→14宣言、実行ケースは17→22、対象2ファイルは496→478行。変更したのは看板の1試験ファイルで、追加70・削除88行。製品・共有補助の変更と廃止ファイルは0。削除数や速度改善を目的にしていない。

## 見逃しを直した境界

- 本文拒否: 元の欠落・空文字・数値12345、空の看板、手番1、アリスを残し、以前の本文・作者・手番・公開値がある行も通す。例外と案内文に加え、元オブジェクトの全stateを比較する。返却のない例外経路で外部保存の原子性まで証明したとは扱わない
- 文字数上限: 実装から輸入した上限定数を期待値に使わず、導入時の200字仕様を独立した値で検査する。元の「あ」250字を残し、異なる末尾を持つ行を加え、先頭200字と切り詰め通知を確認する
- 既定名: 真と評価されるだけの確認を「名無し」との完全一致へ直す。SHOW_PLAYER_TEXT側の表示や本文上書きの別試験は保持する
- 二回書込み: 元の空stateと二人の書込みを残し、独自秘匿キーと無関係な公開値を持つ行を加える。両回で全state、秘匿キーの和集合、公開stateを確認する。書込み担当が全stateを消す、既存の秘匿を落とす、公開値まで隠す誤りを区別して検査する

## 主担当と統合

空文字・非文字列の2宣言を、不正本文の表へ元入力ごと移した。既定公開区分の件数だけを見る1宣言は、既に同じ件数と作者・行為・秘匿差分を確認する`test_state_delta_text_tick_not_included`へ移し、元の「メモ」入力も表の行として保った。3つの統合元を残した保持先先行25件が成功した後に、元宣言だけを削除した。

単独の`visible_state()`否定試験は保持した。汎用の公開状態が空になる故障は既存の`tests/domain/world_graph/entity/test_spot_object_visible_state.py::TestVisibleState::test_excludes_hidden_keys`が検出するため、その同じ故障を新しい修理理由にしない。今回の追加対照は、WRITE_PLAYER_TEXT自身による過剰秘匿である。公開値保持は二回書込みの主担当にだけ追加した。

人数表示の要求生成も保持した。`SHOW_ROOM_OCCUPANCY`が静的な本文を作らず要求を一件だけ返し、アプリ側で表示時点の人数へ解決する設計を守る。人数要求の生成を実人数表示の完了とは扱わない。

## 履歴と互換性

- [看板の導入](https://github.com/Motifman/llm-rpg/commit/54a6b3bed1c79bee047437510faaec588b319cb2): 本文・作者・手番の保存、200字上限と切り詰め通知を明示
- [二経路の漏えい修理](https://github.com/Motifman/llm-rpg/commit/358ba772989ec9d7b6d994635c207954bc10b575): visible_stateとstate_deltaは別経路。書込み行為は公開し内容は読む本人へだけ返す。片方の否定が似ていることだけで削除しない
- [欠落本文の静かな失敗を修理](https://github.com/Motifman/llm-rpg/commit/d4f1af5180b7801f44e707edbb1e4d7b591ceec8): 欠落を成功扱いしない例外契約を保つ
- [表示時人数の要求](https://github.com/Motifman/llm-rpg/commit/3f35f1de76cc7003a09b14916d4923e9de637d59): その時点の状態はアプリ側で解決し、効果は要求を運ぶ
- [効果処理の分割](https://github.com/Motifman/llm-rpg/pull/1169): 公開入口と看板定数の再export維持を明示。試験が実装定数を輸入しなくなっても、公開互換APIを削除する理由にしない

## 全17宣言の台帳

|元の宣言|判定|守る契約・判断|
|---|---|---|
|`test_show_room_occupancy_effect.py::test_effect_carries_one_runtime_occupancy_request_without_static_text`|R|表示時点で集計する要求を一件だけ運び静的本文を作らない|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_writing_sign_saves_text_author_and_tick_to_state`|R|看板に本文・作者・手番を保存する|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_two_one_removed`|R|二人目の書込みは三値を全て上書きする|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_text_missing_interaction_not_allowed_exception_state`|F|不正本文を失敗として返し元の看板全状態を保持する|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_empty_string_text_interaction_not_allowed_exception_state`|C|空文字本文は拒否し状態を保持する。保持先: test_text_missing_interaction_not_allowed_exception_state|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_text_non_string_interaction_not_allowed_exception_state`|C|非文字列本文は拒否し状態を保持する。保持先: test_text_missing_interaction_not_allowed_exception_state|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_exceeds`|F|200文字を超えた本文の先頭200文字を保存し切詰めを本人へ通知する|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_display_name_unspecified_default_fallback_saved`|F|表示名未提供時は定義済みの名無しを保存する|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_public_observable_effect_observation_included`|C|書く行為の既定区分は公開観測。保持先: test_state_delta_text_tick_not_included|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_after_3key_hidden_state_keys`|R|書込み自身が秘匿3キーを自動付与する|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_after_visible_state_text_tick_not_included`|R|書込み後の公開状態は看板の本文・作者・手番を伏せる|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_after_hidden_state_keys_preserved`|F|再書込みでも既存の秘匿キーを失わず看板内容を隠す|
|`test_sign_object_effects.py::TestWritePlayerTextEffect::test_state_delta_text_tick_not_included`|R|書く行為と作者は見せ、本文/作者key/手番keyの差分は見せない|
|`test_sign_object_effects.py::TestShowPlayerTextEffect::test_text_message`|R|読むと本文と作者を所定の私的メッセージで返す|
|`test_sign_object_effects.py::TestShowPlayerTextEffect::test_displayed`|R|未記入なら何も書かれていないと表示する|
|`test_sign_object_effects.py::TestShowPlayerTextEffect::test_line_state_observation_effect`|R|読むだけでは状態も第三者/非表示要約も変更しない|
|`test_sign_object_effects.py::TestSpotInteractionServicePropagatesSignParams::test_write_action_via_text_state`|R|公開操作入口から本文・作者・時刻が効果へ届く|

## 故障対照と復元

同じ基準製品のWRITE_PLAYER_TEXTへ一箇所ずつ故障を入れ、元17件と候補22件を比較した。10種類20実行を直列で行った。7種類は元17件が全成功し、候補では狙ったassertが失敗した。残る3種類は空文字拒否・数値拒否・公開件数の統合保存で、元と候補の失敗箇所を確認した。全リポジトリが故障を見逃すという主張ではない。

|故障|元17件|候補22件|
|---|---|---|
|拒否の直前に元オブジェクトの辞書を消す|0失敗|3失敗|
|仕様200を199に変える。旧試験は同じ実装定数を期待値へ輸入する|0失敗|2失敗|
|先頭でなく末尾200字を残す。同一文字の旧入力では区別不能|0失敗|1失敗|
|空でない別名へ既定名が変わる|0失敗|1失敗|
|今回書いた3キーだけを秘匿し、元からある秘匿キーを落とす|0失敗|1失敗|
|書込み先の全キーを秘匿し、公開すべき既存値まで隠す|0失敗|1失敗|
|既存stateを引き継がず、書く3キーだけを作る|0失敗|1失敗|
|統合した空文字拒否の原入力と例外assertが残る|1失敗|2失敗|
|統合した数値拒否の原入力と例外assertが残る|1失敗|2失敗|
|統合した既定公開summary件数assertが元メモ入力で残る|2失敗|2失敗|

故障後は毎回、変更製品を元のバイト列へ戻した。旧作業木のsrc/tests全3176ファイル、候補の製品1601ファイル、および変更1試験以外のsrc/tests3175ファイルを基準SHA-256と照合した。保持10宣言のうち公開件数を受け入れた1宣言を除く9宣言は構文木不変。

## 試験と限界

- Python3.10.22 / pytest8.4.1。資格情報を除去し外部接続を遮断した固定対象の実行
- 未編集基準: 対象17＋関連15＝32件成功（全55群の基準112件のうち、この単位が所有する範囲）
- 保持先先行25件、統合後22件成功
- 全復元後の最終: 所有22＋関連15＝37件成功、失敗・収集エラー・skipなし
- 変更1試験のRuff0.16.8、git diff --check成功

関連15件は看板の公開操作6件、人数表示が未配線の場合の明示失敗1件、欠落本文の失敗観測抑止と通常の前提条件拒否観測3件、位置表示盤の実行時人数・匿名性・遺体と幽霊の区別・役割・目撃文5件。元の空入力・上書き・未記入表示・公開操作の伝達・読むだけの非変更を残した。全リポジトリ試験・実LLM・有料API・性能比較は未実施。公開後の正確な先端に対するCI結果はこの37件に含めない。

## 競合と所有規則

状態効果38と共通効果35は別の主担当である。#1684の備蓄再生、#1688のOBJECT_STOCK_AT_LEASTの対象選択、保留中のアイテム効果・状態へ変更を広げない。世界グラフの共有AGENTS.mdは未統合の#1735が追加しているため、重複して新規作成しない。

本文と書込み時の状態保持は効果入口、読む本人への文面はSHOW_PLAYER_TEXT、汎用の公開キー選別はSpotObject、観測・保存・配送・管理画面はそれぞれのアプリ側に主担当を置く。複数の経路で秘匿する設計を、見た目の類似だけで一経路へ減らさない。
