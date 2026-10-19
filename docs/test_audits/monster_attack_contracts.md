# モンスターの攻撃間隔・死亡後拒否・環境被害のテスト監査

## 結果

対象２ファイルの全16宣言を監査し、契約と元の入力値を保存したまま、繰り返す準備の統合と検証漏れの補強を行った。本番コードは変更していない。

- テスト行数: 342 → 325（17行減）
- 変更: テスト67行追加・84行削除、本番0行、共通補助コード0行
- 宣言数: 16 → 12。引数展開後の実行件数: 16 → 15
- 基準実行16件成功。候補を含む関連590件成功。変異から復元後の対象15件成功
- 同一の本番変異20種類で旧版と新版を比較。保存対象11種類は両方が検知し、補強対象9種類は旧版が見逃し、新版が検知した
- 基準失敗・製品不具合は見つからなかった。全体CIは未実行で、公開後の確認対象

## 範囲と基準

遠隔mainの ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f と同じ内容を持つ手元の d2a11ae023ad55ff0dc5b0dcf9864cd88e43d2d0 を使用した。内容の識別子は 4807c4c1ce6ceddf5f812a0b0bef0278e528fe07。

全文監査したファイル:

- tests/domain/monster/aggregate/test_monster_aggregate_attack_cooldown.py: 213 → 188行
- tests/domain/monster/aggregate/test_monster_aggregate_environmental_damage.py: 129 → 137行

隣接テストは契約の重複確認と回帰試験に使ったが、全ファイルの監査完了数には含めない。application combat handlersを変更するPR1666とは重複しない。

## 原因と変更

### 攻撃間隔を表へまとめる

攻撃記録tick10の後に攻撃できるかを検証する４つの宣言は、同じ集約構築を繰り返していた。以下の３行へまとめ、元の照会順序とすべての期待値を保存した。

- 間隔3: tick10・11・12は不可、tick13は可
- 間隔1: 記録と同じtick10は不可
- 間隔5: tick14は不可、tick15は可

間隔0と-1のテンプレート拒否も、値を別々に展開する表に統合した。境界一致を許可する契約と最小間隔でも同時刻の二重攻撃を拒否する契約は、[PR127のレビュー対応](https://github.com/Motifman/llm-rpg/commit/183850a109dd065f2cd6782adeea34671dd5ea25)で追加されたもので、どちらも残している。

初期攻撃記録None、初撃可能、暗視の既定値False、攻撃間隔の既定値1の４宣言は、独立した公開契約としてそのまま残した。サービス側のモックを使う試験では、集約の時間計算や未指定時の設定を証明できない。

### 死亡準備を公開操作へ移す

３件が非公開の_lifecycle_stateへ直接書き込んでいた。公開操作を使い、元と同じHPの死亡状態を作るよう変更した。

- 攻撃可否: 環境ダメージ999をtick5で適用し、HP0の死亡個体にする
- 攻撃記録拒否: tick5でstarveし、HP10の死亡個体にする
- 環境ダメージ拒否: tick1でstarveし、HP20の死亡個体にする

正のHPが残る死亡状態は飢餓死や寿命死で実際に起こる。すべてを致命ダメージへ変更すると、死亡状態の判定をHPだけの判定に誤変更しても通るため、元のHP0・10・20を明示的に確認した。

拒否前に残った死亡イベントを非空のまま保存し、拒否後も同じ内容であることを確認する。例外を出しながら既存イベントを消す誤りや、拒否前に攻撃記録・HPを変更する誤りも検出する。

### 環境被害の通知と正確な死亡遷移を確認する

非致命試験ではHP17に加え、生存状態と被害イベントのcurrent_hp=17を確認する。致命試験では曖昧なstatus!=ALIVEをDEADへ変更し、HP0・死亡tick20・被害イベント１件の内容も確認する。実際にRESPAWNINGという別状態があるため、単に生存していないという断言では死亡を証明できなかった。

環境死のcause=ENVIRONMENTと両方の殺害者情報がNoneである断言は保存した。これは[PR143のレビューで修正された環境死の原因欠落](https://github.com/Motifman/llm-rpg/commit/d2f2652e5fad07c1b99e13d0d3c7407fae3fb49c)を直接防ぐ契約である。

共通の死亡報酬、戦利品、復活予定時刻、座標消去は既存のTestDeathAndRespawnに任せ、今回重ねて検証していない。環境入口から正しくHP更新・死亡遷移・被害通知につながったことだけを補強した。

最新攻撃tick20の公開記録に加え、同tick20・21は不可、tick22は可という実際の攻撃判定も確認する。公開記録だけ更新され、待ち時間計算が初回tick10を参照し続ける変異では、旧版は通り新版だけ失敗した。

## 変異による保存性・補強の実証

それぞれ同じ作業用ディレクトリ、同じ本番変異、同じ選択対象で旧版と新版を実行した。各実行の失敗箇所を確認し、構文エラーや収集エラーを検知件数へ含めていない。

旧新版とも失敗した11種類:

1. 攻撃間隔の境界比較を>=から>へ変更
2. 同tickの再攻撃を許可
3. テンプレートの攻撃間隔を無視して3へ固定
4. ２回目以降の攻撃記録を更新しない
5. 死亡後の攻撃可否ガードを除去
6. 攻撃記録の状態ガードをHPガードへ変更
7. 環境ダメージの状態ガードをHPガードへ変更
8. 間隔0を許可
9. 間隔-1を許可
10. 環境死の原因をNoneへ変更
11. 環境ダメージによるHP減少を捨てる

旧版成功・新版失敗となった９種類:

1. 最新攻撃記録は更新するが、間隔計算は初回攻撃時刻に固定
2. 被害イベントの現在HPを実値より1増やす
3. 環境致命後の状態をRESPAWNINGへ変更
4. 致命時の被害イベントだけ省略
5. 環境死の記録時刻を0へ変更
6. 攻撃記録拒否の前に攻撃時刻を更新
7. 攻撃記録拒否の前に既存イベントを消去
8. 環境ダメージ拒否の前にHPを削る
9. 環境ダメージ拒否の前に既存イベントを消去

本番２ファイルと候補テスト２ファイルの内容が、実行前の保存内容とバイト単位で一致することを確認して復元した。作業差分に本番変更はない。

## 実行した検証

Python3.10の安全な実行器を使用し、認証情報を環境から外し、外部通信を禁止した。品質点検・実API・有料呼出しは実行していない。

- 基準: 対象２ファイル、16件成功（実行器計測0.45秒）
- 候補: tests/domain/monster全体、温度処理、SpotAttackOrchestratorの通常攻撃・対モンスター攻撃・捕食、590件成功（同2.15秒）
- 変異対照: 20種類×旧新版。保存11組、補強9組とも予定どおり
- 復元後: 対象２ファイル、15件成功（同0.44秒）
- Ruff: 変更２ファイルの検査成功
- git diff --check: 成功
- git diff --exit-code -- src: 成功

## 残る確認

独立した保存性レビューと公開文書レビューは合格した。公開後の全体CI確認は別途行う。製品修正、ファイル廃止、テスト専用の本番注入口の追加はない。

## 全16宣言の台帳

記号: Rは独立契約として保持、Fは契約を残して検証を修理、Cは別の表へ統合。契約を捨てるDはない。以下のAは攻撃間隔ファイル、Eは環境被害ファイルを示す。

- A: tests/domain/monster/aggregate/test_monster_aggregate_attack_cooldown.py
- E: tests/domain/monster/aggregate/test_monster_aggregate_environmental_damage.py

| 元の宣言 | 判断 | 残る検証先 |
|---|---|---|
| A: TestInitialState.test_last_attack_tick_initial_value_none | R | 同名を保持 |
| A: TestInitialState.test_can_attack_now_true | R | 同名を保持 |
| A: TestCooldown.test_record_attack_after_false | C | TestCooldown.test_attack_availability_after_recording の間隔3の行へ元の順序で統合 |
| A: TestCooldown.test_record_attack_same_tick_can_attack_now_false | C | 同表の間隔1の行へ統合 |
| A: TestCooldown.test_boundary_value_elapsed_cooldown_equals_true | C | 同表の間隔5の行へ元の順序で統合 |
| A: TestCooldown.test_record_attack_after_cooldown_true | C | 同表の間隔3の行へ境界tick13を統合 |
| A: TestCooldown.test_last_attack_tick_value_updated | F | 同名で最終攻撃tick20を保持し、tick20・21不可、tick22可を追加 |
| A: TestDeadMonster.test_dead_can_attack_now_false | F | 同名でtake_environmental_damage(999, tick5)を使い旧HP0・死亡tick5を保存する |
| A: TestDeadMonster.test_dead_record_attack_raises_exception | F | 同名でstarve(tick5)により旧HP10を保存し、拒否前の記録・イベントを保存する |
| A: TestTemplateValidation.test_zero_or_less_attack_cooldown_ticks_raise_exception | C | TestTemplateValidation.test_nonpositive_attack_cooldown_ticks_raise_exception の0行 |
| A: TestTemplateValidation.test_negative_attack_cooldown_ticks_raise_exception | C | 同表の-1行 |
| A: TestTemplateValidation.test_has_dark_vision_default_false | R | 同名を保持 |
| A: TestTemplateValidation.test_attack_cooldown_ticks_defaults_to_one | R | 同名を保持 |
| E: TestNonLethal.test_hp_event_trigger | F | 同名で全断言を保持し、生存状態と被害イベントのcurrent_hp=17を追加 |
| E: TestLethal.test_hp_cause_environment_dead | F | 同名で死因・殺害者なし・件数を保持し、HP0・DEAD・死亡tick20と被害通知を追加 |
| E: TestAlreadyDead.test_dead_take_environmental_damage_raises_exception | F | 同名でstarve(tick1)により旧HP20を保存し、HP20/死亡tick1/非空の既存イベントを拒否後も確認 |
