# 備蓄の消費前再生と端数持越しを守る

## なぜ

備蓄の旧試験は「0個から24手番で3個再生し、3個消費して0個残る」を
調べていた。しかし再生を無視し、記録済みの0個から3個を引いて下限0へ
丸めても同じ結果になる。純粋な再生関数の試験が通っても、消費する側が
計算結果を使わない退行は見つからなかった。

また、再生関数が返す端数を保持した基準手番を、効果側が現在手番に
置き換えて保存しても旧試験は通った。次の採取までの待ち時間が伸びる
誤りであり、純粋関数と消費・保存の接続で確かめる必要がある。

## 対象と固定点

- 基準・旧新変異比較のmain: `37bae48104b50ec2f0f73d1fd6cf493ffffdb1f1`
- 公開前に追随したmain: `7719ee62deef29c85533da70311b9291c95c495f`
- 主要対象: `tests/domain/world_graph/test_object_stock_pool.py` と
  `tests/domain/world_graph/test_stock_pool_regen.py` の旧16宣言・248行
- 製品所有者: `effect_application/handlers/object_state.py` の
  `apply_consume_object_stock`、`stock_pool_regen.py` の `compute_stock_regen`、
  `SpotInteractionService.execute_interaction`
- 読取時に関連する数量・記録手番の試験も確認したが、今回は編集しない

備蓄機構を導入した `12eeda6b1f3b510548f3380d05f6e96ae5bc5c3d` は、
満杯未満で端数を保存し、次回へ進捗を持ち越す契約を明記している。
`c01ad0770f2cbe09dc24f3cf73b55b2cc494b34b` は実行入口から現在手番が
渡らず永久枯渇する事故を直している。計算単体と実行入口は別々に守る。

## 変更と残す契約

1. `test_consume_credits_regen_first` を2行の表へする
   - 元の24手番・3個消費 → 残量0、基準手番24をそのまま残す
   - 20手番・1個消費 → 残量1、基準手番16を加える
   - 期待値は再生関数を呼んで作らず、独立した数値を使う
2. `test_next_harvest_keeps_partial_regen_progress` を加える
   - 実 `execute_interaction` で20手番に2個採取する
   - 返された室内状態を次の操作へそのまま渡す
   - 31手番はまだ1個しか戻らず拒否され、状態も変わらない
   - 32手番で2個が戻り、再び全量採取して0個になる

準備側で初回実行後の在庫や基準手番を作り直さない。評価器や消費処理の
模倣も置かない。拒否には備蓄以外の前提条件を混ぜない。

### 旧宣言の保存台帳

|旧宣言|判定|保存する契約|
|---|---|---|
|`test_consume_decrements_stock`|保持|時間経過なしの消費|
|`test_consume_credits_regen_first`|検査修復|再生後の全量消費と正の残量|
|`test_consume_writes_canonical_tick`|保持|満杯からの消費は現在手番へ基準を戻す|
|`test_enough_stock_allows`|保持|備蓄が十分なら許可|
|`test_insufficient_stock_blocks_with_message`|保持|不足拒否と理由|
|`test_regen_restores_availability`|保持|条件側も現在手番から再生を計算|
|`test_stock_pool_keys_not_in_visible_state`|保持|4種の内部状態名を公開しない|
|`test_stock_key_hidden_generically_other_state_visible`|保持|通常の状態は公開したまま|
|`test_no_elapsed_returns_stock_unchanged`|保持|同手番では変わらない|
|`test_regen_by_whole_intervals`|保持|完了した間隔だけ再生|
|`test_capacity_is_capped`|保持|容量を超えない|
|`test_remainder_is_preserved`|保持|純粋計算が端数を保持|
|`test_at_capacity_resets_tick_to_now`|保持|満杯では古い進捗を貯めない|
|`test_zero_refill_interval_means_no_regen`|保持|間隔0は静的資源|
|`test_clock_going_back_does_not_lose_stock`|保持|時計逆行で在庫を失わない|
|`test_input_stock_clamped_to_capacity`|保持|破損在庫を容量へ抑える|

短い境界試験を削除する理由はない。消費、条件、公開状態、計算の所有範囲は
混ぜず、今回の削除は0。試験専用の製品APIや互換層も増やさない。

## 変異による比較

製品を一箇所ずつ一時的に変え、同じ主要2ファイルを旧試験・修復試験で
比較した。各実行後、製品を元のバイト列へ復元した。

|意図的な退行|旧16件|修復18件での失敗|
|---|---|---|
|消費時に再生結果を使わず、記録済みstockから引く|全件成功し見逃し|正の残量を調べる行が `0 != 1` で失敗|
|効果が保存するstock_tickをcanonical_tickからnowへ変える|全件成功し見逃し|2件が初回の保存値 `20 != 16` で失敗|
|execute_interactionが条件評価へ渡すcurrent_tickだけをNoneへ変える|全件成功し見逃し|連続採取の初回20手番が誤拒否され、その1件だけ失敗|

最後の変異では、新しい数値表も通る。連続採取試験が直接の効果・条件試験と
異なり、実行入口から条件評価への手番受渡しを守ることが確認できた。
保存手番の変異は初回保存値で失敗しており、32手番の呼出しまで進んだ
という結果ではない。

## 検証

資格情報を除いた環境で、外部通信を遮断する共有実行器を使用した。
毎回、読み込む `ai_rpg_world` が検証対象の作業木にあることを確かめた。
Python3.10.22 / pytest8.4.1。実APIは呼んでいない。

関連範囲は次の5ファイルである。

- `tests/domain/world_graph/test_object_stock_pool.py`
- `tests/domain/world_graph/test_stock_pool_regen.py`
- `tests/domain/world_graph/test_item_quantity_semantics.py`
- `tests/domain/world_graph/test_record_object_state_tick_effect.py`
- `tests/application/world_runtime/test_do_interact_passes_current_tick.py`

旧版は40件を2回成功。修復後は42件を2回成功し、最後の追加変異から
復元後も同じ42件を再確認した。変更試験のRuffと `git diff --check` は成功。
全リポジトリ試験はこの検証では実行していない。

公開前にmainの進行を取り込み、関連42件を再度成功した。今回の所有者・
試験・依存ロックに変更は無かったが、`world_runtime.py` は別機能の
引数削除で変わっていたため、現在手番の受渡しを含む関連範囲を再確認した。
旧新の変異対照は37bae上、新main確認は7719ee上の結果として区別する。

独立した保存レビューは、元の入力・期待値の脱落、準備側が望む動作を
供給していないか、拒否が別条件に依存しないかを確認し、必須修正なし。

主要試験は16宣言16件から17宣言18件、248行から308行へ増える。
試験差分は +67/-7 行、製品・共通補助の差分は0。この変更の目的は
速度や削除数ではなく、実際に見逃した3つの退行を止めることである。
