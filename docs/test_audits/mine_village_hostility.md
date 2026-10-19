# 山村の敵対行為: 準備の反復を減らす監査

## 目的と範囲

基準は `0b51eb28d4692635a932dcf4063ab9b231768bf0`。対象は `tests/demos/test_mine_village_attack_and_steal.py` の全33宣言・35実行ケース。削除数を目標にせず、契約を保持したまま繰り返す前提作成だけを短くする。本番コード、シナリオ、既存テストの主張は変更しない。

## 変更前後の境界

変更前の `_knock_down` は10回攻撃し、毎回3tick進める。7試験がこの準備を使う。変更後は最初の実攻撃と3tickを残し、入室観測を通じて互いの存在を知る。その後、対象が立っていることを確かめ、通常の `PlayerStatusAggregate.apply_damage` でHP10にして保存し、最後の実攻撃と3tickを保つ。身体、蘇生猶予、通知を手で作らない。

- 準備開始をtとすると、以前はt+27にダウンしてt+30に返る。変更後はt+3にダウンしてt+6に返る
- 両者とも倒れて3tick経過した状態。攻撃者、対象、場所、籠の状態、持ち物は維持する
- 正のHPが残る `apply_damage` はダウンイベントを発しない。最後の実攻撃が `PlayerDownedEvent` を生成し、対人操作の確定前処理が身体と猶予を記録、確定後処理が観測を届ける
- 7回の準備全体で56回の攻撃と168tickを減らす。累積ダメージそのものの主担当 `test_ten_strikes_knock_someone_down` は変更しない

### 保持を主張しないもの

絶対時刻、間の8回分の非致死攻撃の通知履歴、空腹、日夜、無関係なガスの乱数列、怪物の状態は同一にならない。特に `lift_landing` は深部の音の人数条件に含まれ、従来の10回攻撃は怪物の起床・睡眠を伴う。対象の7試験はこれらを検証しておらず、音/怪物の専用試験を引き続き残す。実際の比較でも、昇降機の試験は旧準備の返却時には獣が眠り、新準備の返却時には深部の獣が起きていた。この獣の宣言は徘徊を指定しておらず、既定の `idle_wander_chance=0` で出現場所に留まる。攻撃対象の選択も同じ場所の生存者だけなので、乗り場にいる対象者への検証を妨げない。ガスの旗にも無関係な差を記録した。このヘルパーを時間経過や怪物との相互作用を検証する試験へ流用しない。

### 単発案を採らなかった理由

HP10への調整後に攻撃1回だけ行う案も35ケースは通った。しかし比較すると、加害者が受ける最後のダウン通知が「ハルが〈外見〉を倒した」から「ハルが誰かを倒した」へ変わった。`_place` が積んだ入室イベントは最初の対人操作後に配られ、`PlayerAcquaintances.on_observation` が互いの存在を記録する。最初から致死攻撃だと、その記録より先にダウン通知が出るためである。

そこで最初の実攻撃と3tickも残した。出会いを直接登録する補助処理を作らず、元の順序を通す。単発案の速度値は採用版の性能結果へ混ぜない。

## 層と保持先

- 攻撃量・待ち時間・10回目のダウン: 同ファイルの `TestStrikingSomeone`
- 3区画の音・別区画に2人いる場合の既知の限界・記録: 同ファイルの `TestStrikingIsLoud` / `TestStrikingLeavesATrace`
- 蘇生、死亡未確定、籠の定員と出発、奪取、明暗の匿名化: 同ファイルの各利用者視点の宣言
- 秘密を漏らさない文章、追加される全前提条件の失敗説明: 同ファイルの静的な2宣言
- 怪物の3音閾値・20tick睡眠・再起床・攻撃: `test_mine_village_noise_and_lift.py`
- 身体の記録地点・奪取の授受・蘇生・事後通知: `test_take_from_fallen_player_e2e.py`
- 死亡通知と猶予の別シナリオ: `test_scenario_death_semantics.py`
- ダウン後の予約移動抑止: `test_downed_player_cancels_reserved_travel.py`

山村の個別宣言を汎用エンジンの試験へ移管しない。削除ファイル、削除宣言、不要になった本番の公開口はない。

## 全宣言の台帳

Rは契約を保持、Fは主張修理、Cは統合、Dは削除。全33宣言がR、F/C/Dは0。区画の3行もそれぞれR。行番号は変更前。全て対象ファイル内の宣言。

1. `TestStrikingSomeone.test_one_strike_takes_ten_hp` (L147)
   - 契約: 1回でHP10減少
   - 検出する故障: 宣言された攻撃量の変更、対象へのダメージ適用漏れ
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

2. `TestStrikingSomeone.test_a_second_strike_needs_a_pause` (L158)
   - 契約: 直後/2tickは拒否、3tickで再攻撃可能。拒否文にtickなし
   - 検出する故障: 待ち時間の境界ずれ、内部単位の漏出
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

3. `TestStrikingSomeone.test_ten_strikes_knock_someone_down` (L173)
   - 契約: HP100の9回後は立ち、10回目に倒れる
   - 検出する故障: 累積ダメージまたは倒れる閾値の不具合
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

4. `TestStrikingSomeone.test_someone_elsewhere_cannot_be_struck` (L187)
   - 契約: 別地点の相手へ攻撃不可、HP100不変
   - 検出する故障: 同席検証の欠落、拒否後の効果適用
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

5. `TestStrikingSomeone.test_someone_already_down_cannot_be_struck_again` (L198)
   - 契約: 倒れた相手への再攻撃を倒れた旨で拒否
   - 検出する故障: 対象状態の検証抜け
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

6. `TestStrikingIsLoud.test_a_strike_in_the_mine_adds_noise_to_that_sector_only` (L215)
   - 契約: deep/north/south各行で当該区画だけ音1、2tick後も1
   - 検出する故障: 区画取り違え、フラグ未消去による二重計上
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

7. `TestStrikingIsLoud.test_someone_standing_alone_in_another_sector_does_not_carry_the_noise` (L227)
   - 契約: 別区画に1人だけなら音は伝播しない
   - 検出する故障: 人数条件の過緩和
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

8. `TestStrikingIsLoud.test_two_standing_together_elsewhere_also_hear_it` (L238)
   - 契約: 別区画に2人いるとその区画にも音が積もる現行制約
   - 検出する故障: 代替実装の挙動を説明なしで変更
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

9. `TestStrikingIsLoud.test_a_strike_in_the_village_makes_no_mine_noise` (L255)
   - 契約: 坑道が空なら村の攻撃で坑道の音なし
   - 検出する故障: scuffle_noiseの無条件全区画伝播
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

10. `TestStrikingIsLoud.test_no_strike_no_noise_even_when_two_stand_together` (L265)
   - 契約: 攻撃なしなら坑道に2人いても音なし
   - 検出する故障: scuffle_noise条件漏れ
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

11. `TestStrikingLeavesATrace.test_who_struck_and_which_sector_heard_it_are_recorded` (L293)
   - 契約: 音の記録に攻撃者・発生源・区画が正確に残る
   - 検出する故障: 記録配線漏れ、別区画の余計な記録
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

12. `TestTendingTheDowned.test_a_teammate_can_bring_them_back` (L337)
   - 契約: 同席者が実ツールで手当てすると行動可能かつHP正
   - 検出する故障: ツール露出/対象解決/蘇生配線の故障
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

13. `TestTendingTheDowned.test_being_down_is_not_death` (L350)
   - 契約: 倒れて3tick後でもUNRESOLVED
   - 検出する故障: ダウンを即時死亡にする退行
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

14. `TestBoardingTheLift.test_only_those_aboard_escape` (L391)
   - 契約: 乗船者2人はRESCUED、同じ乗り場の未乗船者はSTRANDED
   - 検出する故障: 位置だけで救出とする退行
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

15. `TestBoardingTheLift.test_the_cage_is_full_with_three` (L404)
   - 契約: 定員3、4人目はいっぱいと拒否
   - 検出する故障: 席消費または定員条件の欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

16. `TestBoardingTheLift.test_boarding_twice_does_not_take_a_second_seat` (L414)
   - 契約: 再乗船を専用文で拒否し残り2席は使える
   - 検出する故障: 再乗船で二重消費
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

17. `TestBoardingTheLift.test_the_lift_cannot_be_started_from_outside_the_cage` (L424)
   - 契約: 準備済みでも未乗船者の始動を拒否、出発旗なし
   - 検出する故障: 操作盤の位置条件欠落、拒否後に出発
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

18. `TestBoardingTheLift.test_leaving_the_cage_frees_the_seat` (L434)
   - 契約: 降りると席アイテム喪失、別人が乗れ、降りた人から奪える
   - 検出する故障: 席返却またはaboard解除漏れ
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

19. `TestBoardingTheLift.test_a_seat_left_outside_the_landing_does_not_escape` (L446)
   - 契約: 席を持っていても乗り場を離れればSTRANDED
   - 検出する故障: 席だけで救出とする退行
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

20. `TestBoardingTheLift.test_the_downed_get_no_turn_and_are_left_behind` (L457)
   - 契約: ダウン者の手番不可、出発後STRANDED
   - 検出する故障: 倒れた人を手番または救出対象に含める
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

21. `TestTakingThings.test_take_a_named_item_from_someone_standing` (L475)
   - 契約: 名指しの燃料が対象から消えて行為者へ移る
   - 検出する故障: 品名解決、授受、対象側削除の欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

22. `TestTakingThings.test_cannot_take_what_they_do_not_have` (L486)
   - 契約: 対象の持たない品は固有文で拒否し行為者も得ない
   - 検出する故障: 持ち物条件漏れ/無からの生成
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

23. `TestTakingThings.test_taking_again_needs_a_pause` (L497)
   - 契約: 立位相手から奪う直後は拒否、3tick後は成功
   - 検出する故障: pickpocket待ち時間欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

24. `TestTakingThings.test_take_from_someone_who_is_down` (L509)
   - 契約: ダウン者から燃料を取得できる
   - 検出する故障: 身体位置/ダウン対象の授受配線抜け
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

25. `TestTakingThings.test_taking_from_the_downed_also_needs_a_pause` (L521)
   - 契約: ダウン者から奪う直後は拒否、3tick後は成功
   - 検出する故障: loot_from_downed待ち時間欠落
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

26. `TestTakingThings.test_cannot_take_from_someone_in_the_cage` (L534)
   - 契約: 籠の立位相手から燃料を奪えず対象は保持
   - 検出する故障: aboard制約欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

27. `TestTakingThings.test_cannot_take_from_someone_knocked_down_in_the_cage` (L545)
   - 契約: 籠内で倒れた相手の席を奪えず行為者に席なし
   - 検出する故障: ダウン経路だけでaboard制約を迂回
   - 保持先: 同宣言。準備のみ短縮。分類: R（契約を保持）

28. `TestTakingThings.test_in_the_light_the_onlooker_sees_who_took_it` (L557)
   - 契約: 明所の目撃者に既知ゲンの名前/未知ハルの見た目が届く
   - 検出する故障: 知らない名前の漏出、目撃通知欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

29. `TestTakingThings.test_in_the_dark_no_one_sees_who_took_it` (L569)
   - 契約: 暗所の被害者・目撃者に荷の通知は届きゲンの名前はない
   - 検出する故障: 暗所匿名化または通知配線欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

30. `TestTakingThings.test_in_the_dark_no_one_sees_who_struck` (L583)
   - 契約: 暗所の目撃者に攻撃音の通知は届きゲンの名前はない
   - 検出する故障: 攻撃経路固有の匿名化/通知欠落
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

31. `TestHostileActsStayHidden.test_hostile_acts_are_offered_only_on_someone_here` (L603)
   - 契約: 同席の未知人物の外見行に攻撃が出て、別地点なら消える
   - 検出する故障: 秘匿された人/遠隔対象の露出
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

32. `TestHostileActsStayHidden.test_hostile_act_texts_mention_no_beast_or_sector` (L617)
   - 契約: 宣言文に獣・目覚め・眠り・区画・呼ぶの秘密を含めない
   - 検出する故障: シナリオ説明文から仕掛けが漏れる
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）

33. `TestHostileActsStayHidden.test_every_precondition_has_its_own_failure_message` (L623)
   - 契約: 全対人/籠操作の全前提条件に失敗文がある
   - 検出する故障: 追加条件で説明のない拒否が混入
   - 保持先: 同宣言。既存の試験を維持。分類: R（契約を保持）


## 試験と比較

基準と候補を同じPython 3.10.22・uv.lockに対応する依存環境で直列実行した。ネットワーク通信を禁止し、認証用環境変数を除去し、対象作業ツリーのsrcを読み込んでいることを開始時に確認した。外部API・有料LLM・quality/live_apiは実行していない。

| 範囲 | 基準 | 採用した2攻撃案 |
|---|---:|---:|
| 対象ファイル | 35成功 × 2回 | 35成功 × 2回 |
| 関連4ファイル | 82成功 | 82成功 |
| 一時的な準備比較 | 8成功 | 8成功 |
| 対象35件の経過秒数1 | 43.626 | 26.104 |
| 対象35件の経過秒数2 | 48.665 | 26.194 |
| 経過秒数の中央値 | 46.146 | 26.149 |

2反復の中央値で約43.3%短縮した。これはプロセス起動を含むこの35件の直列計測であり、並列CI全体の短縮率ではない。初回の基準2回目は終盤に別試験の起動が重なったため速度値を除外し、直列で取り直した。途中で止めた関連試験も成功件数に数えない。単発案の成功・速度値も採用版の表に混ぜていない。

### 準備の比較で確認したこと

恒久的な重複試験を増やさず、一時検証で7利用元の実際のテスト本体を実行し、準備の直前と直後を記録した。

- 7件全てでHP0、行動/手番不可、UNRESOLVED、身体の場所、蘇生猶予の登録、対象のteam/aboard状態が一致
- 身体のダウン時刻と猶予起点はそれぞれ一致し、準備返却時の経過は両方3tick
- 被害者・加害者・同席者・別地点の人へ届く最後のダウン通知の本文と構造化データは全て一致。同席者への最後の攻撃目撃通知も一致
- 6件は開始/ダウン/返却時刻が0/27/30から0/3/6へ、昇降機の1件は8/35/38から8/11/14へ変わる。絶対通知時刻の一致は主張しない
- 被害者への非致死攻撃通知は9件から1件、同席目撃者がいる場合の攻撃通知は10件から2件へ減る。削った8回分の履歴は保存しない
- HP100から10への非致死調整自体はイベント0、身体記録なし、猶予未登録、全員の通知件数不変。したがって準備による余計なダウン通知はない

### 意図的な故障での検出確認

一度に一つだけ本番コードまたはシナリオ宣言を壊し、既存試験が意図した理由で失敗することを確認した。各回の終了時に変更前のバイト列へ戻し、復元後に本番コード/シナリオ差分がないことを確認した。

1. 対人操作の確定前処理から身体登録だけを外す: `test_take_from_someone_who_is_down` が「倒れている相手の身体位置が記録されていません」で失敗。準備が身体を手作りして本番登録漏れを隠していない
2. `PlayerInteractedWithPlayerEvent` の配送を外す: `test_in_the_dark_no_one_sees_who_struck` と `test_in_the_dark_no_one_sees_who_took_it` が通知なしで失敗。匿名化の否定条件だけで空の通知を許していない
3. `loot_from_downed` のaboard=no条件を外す: `test_cannot_take_from_someone_knocked_down_in_the_cage` が奪取成功を検出して失敗。別の拒否条件に偶然阻まれて通る否定試験ではない

これらの故障は変更に含めない。復元後の対象35件は全て成功（22.77秒）。対象ファイルのruff、`git diff --check`も成功し、本番コード/シナリオ差分は0。全33宣言のASTも基準と同一であることを確認した。

## 再実行する範囲とCI

通常のコマンドで確認する場合:

```sh
uv run --frozen pytest tests/demos/test_mine_village_attack_and_steal.py -q --durations=35
uv run --frozen pytest tests/demos/test_mine_village_noise_and_lift.py tests/demos/test_take_from_fallen_player_e2e.py tests/demos/test_scenario_death_semantics.py tests/demos/test_downed_player_cancels_reserved_travel.py -q
uv run --frozen ruff check tests/demos/test_mine_village_attack_and_steal.py
git diff --check
```

CIはPython3.10で `uv run --frozen pytest -n auto` を実行し、対象ファイルは通常のtests収集に残るためCI経路の変更はない。この変更で全リポジトリの試験を実行済みとは主張しない。

## 履歴と差分

- 導入コミット `9e252715c70db3f0a713384c0fb1d394d88a37f6`: 攻撃/奪う/3人籠を導入。別区画の2人にも音が積もる制約を明示的に試験へ残した
- `df0eca74f4b59d94e3d756d7c6a1d1eed98beac7`: 無関係なガス発生が音の記録試験を壊したため、検査を音フラグへ限定した。今回も世界全状態の完全一致を要求しない
- `c14acf66974a61ca8ed04ca5006a4b2d0162bd24`: 初対面で名前を漏らさず、外見で表示する仕様を追加。準備短縮でもこの認知境界を不用意に変えないため2攻撃を残した
- 本番コード/シナリオ: 変更0行
- 既存試験: 637→646行（+14/-5）。33宣言/35ケースは不変。既存の全試験本体と主張は不変
- 追加物: この監査記録のみ。一時採取・比較・変異用のプログラムは通常の試験群へ追加しない

