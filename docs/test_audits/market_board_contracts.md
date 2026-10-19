# 市場板の約定価格と閲覧契約の検査

## 目的と範囲

`MarketBoard` の3ファイル45宣言を全件読み、名前や説明が約束する動作に入力・検査が届いていない4件を直した。単一追加の重複した準備1件は、同じ公開操作の不変性を検査する試験へ統合した。

製品コードは変更していない。公開の取得メソッド、空の結果、Noneの価格、自動約定しない設計、商人の注文、各更新後の価格保持を残す。ファイル全体を退役させたり、試験専用の製品側機構を追加したりしていない。

基準は main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。試験は678行から703行、宣言は45から44、入力表の展開後は45件から46件。差分は追加43行・削除18行、差引25行増。準備関数58行は試験行数の内数で変わらず、独立した補助ファイルと製品コードの差分は0。

## 修理と移管

1. 期限切れ一覧は、期限16でID1が返る元の検査を残し、元の板が不変で同じ対象を再読できることを加えた。呼出側は一覧取得後、各注文を検索して返却するため、読取で注文が消えると預かり品を戻せない
2. 本人注文の個別一覧は、本人の売り注文1件と他人の売り注文1件という元入力を残した。もう1行だけ本人の同品目の買い注文を加え、2件のIDと売買の側を対応付きで検査する。並び順を追加契約にしない
3. 唯一の注文が約定した後、価格取得メソッドの18Gを残したまま、注文が空でも品目7・直近18G・買値Noneの行が返ることを検査する。未約定22Gの注文を残す別試験では、この履歴だけから行を作る経路を保証できない
4. 同じ手番に2注文を受ける元入力を、全量約定の行として残した。追加した部分約定の行では2件目の数量3から1だけ受け、残数2と最後の単価22Gを確認する。注文の残数や返却された取引記録だけでは、板に保存した直近価格を保証できない
5. 空の板への単一追加は、返却された板がその注文だけを持ち、元の板は空のままであることを一度の操作で検査する。件数だけの宣言を消す前に、その確認を保持先へ移した

## 所有者と保持する境界

- [MarketBoard](../../src/ai_rpg_world/domain/trade/aggregate/market_board.py) が注文一覧、期限一覧、取引記録、閲覧者別集約、直近価格を所有する
- [MarketService](../../src/ai_rpg_world/application/trade/services/market_service.py) は売買・取消・期限返却を通じて板を更新し、取引記録で品と代金を動かす
- [InMemoryMarketBoardStore](../../src/ai_rpg_world/application/trade/services/in_memory_market_board_store.py) と [保存復元](../../src/ai_rpg_world/application/being/world_subsystems/market_board_codec.py) は世界の状態と採番を保持する。板の不変性は巻戻しにも必要
- 表示側は `rows_for` の価格行と本人注文を使う。文面・ツールへの接続試験は、ドメインの個別データ契約とは別に残す
- `orders_visible_to` の製品からの直接呼出しは現ツリーで見つからなかったが、導入時からの公開契約である。本人の生きた注文を返す一方、`rows_for` はその注文を取れる価格から除くため、同じ結果の重複とは扱わない
- `MarketOrder` が残数や期限を判定していても、板が注文を残すか、記録を保存するかは別の契約。内部ヘルパーを共有する4種類の更新後履歴保持も、公開操作ごとの脱落を防ぐため残す

### 導入履歴

- [ebb5e9e](https://github.com/Motifman/llm-rpg/commit/ebb5e9ec4596726611a04aa6731f5e157201eebc)：数量・単価を持つ不変の板、取引の当事者、引き取り待ちの公開一覧
- [932b4ed](https://github.com/Motifman/llm-rpg/commit/932b4ed775296855bd6b91969948a41ada096398)：閲覧者別の集約行と本人注文の個別一覧、世界状態の保存復元
- [0774e4c](https://github.com/Motifman/llm-rpg/commit/0774e4cac7b24bfbb164ed5f15ccda5afa1c461d)：見る人が払う価格と受け取る価格、不在を表すNone
- [948f062](https://github.com/Motifman/llm-rpg/commit/948f0623226910ab64a91047966ebb22ea6d9ad1)：`taken` が価格を記録し、平均を作らず品目ごとに最後の成立単価を保持
- [32fc35b](https://github.com/Motifman/llm-rpg/commit/32fc35b35c110afd93a45ff0957d920d6dd13d1a)：自動約定しない理由を「引き金に人が居るか」へ訂正。手番外の他人による取引は禁止していない

## 原45宣言の判断

Rは保持、Fは契約を保持して検査を修理、Cは保持先へ移管後に統合。R40/F4/C1/D0。

ファイル略号：

- A：[test_market_board.py](../../tests/domain/trade/aggregate/test_market_board.py)
- B：[test_market_board_rows.py](../../tests/domain/trade/aggregate/test_market_board_rows.py)
- H：[test_the_board_remembers_what_it_last_sold.py](../../tests/domain/trade/aggregate/test_the_board_remembers_what_it_last_sold.py)

保持先は原則として同じ宣言。MB-01だけをMB-07へ移す。Fの元入力は失っておらず、MB-32とMB-41は元入力行と追加行を持つ。R40件のうちMB-07は移管先として検査を追加し、残る39宣言は構文木が元のまま。

| ID | 判定 | 原宣言 | 守る契約 | 検出する退行 |
|---|---|---|---|---|
| MB-01 | C | A: `TestOrdersGoOntoTheBoard.test_placing_an_order_puts_one_row_on_the_board` | 空の板に注文を1件置くと、その注文が新しい板に1件だけある | with_order が注文を追加しない、または同じ注文を2件追加する |
| MB-02 | R | A: `TestOrdersGoOntoTheBoard.test_two_orders_for_the_same_item_stay_as_two_rows` | 同品目でも異なる注文は別々の単価を保つ | 品目で注文を潰す、または先の注文を上書きする |
| MB-03 | R | A: `TestOrdersGoOntoTheBoard.test_the_same_order_id_cannot_be_placed_twice` | 同じ注文IDを二重に登録できない | 重複ID判定を取り除く |
| MB-04 | R | A: `TestOrdersGoOntoTheBoard.test_cancelling_removes_the_row` | 持ち主が取り下げた唯一の注文は板から消える | cancelled が対象注文を残す |
| MB-05 | R | A: `TestOrdersGoOntoTheBoard.test_someone_elses_order_cannot_be_cancelled` | 他人は注文を取り下げられない | 所有者照合を削る、または逆向きに判定する |
| MB-06 | R | A: `TestOrdersGoOntoTheBoard.test_cancelling_an_absent_order_is_refused` | 存在しない注文の取り下げを断る | 存在検査をなくして空の板を成功として返す |
| MB-07 | R | A: `TestOrdersGoOntoTheBoard.test_placing_an_order_leaves_the_previous_board_untouched` | 注文追加は元の板を変えず、注文がある新しい板を返す | 元の板を直接書き換える |
| MB-08 | R | A: `TestTheBoardNeverMatchesOnItsOwn.test_a_crossing_pair_stays_on_the_board` | 値が交差した売り注文と買い注文は自動約定せず残る | with_order で自動突き合わせを導入する |
| MB-09 | R | A: `TestOnlySomeoneElseCanTakeAnOrder.test_taking_an_order_reduces_it_and_reports_the_trade` | 部分約定では残数を減らし、実際に受けた数量と単価の記録を返す | 板の差し替えを省く、取引数量に残数を記録する |
| MB-10 | R | A: `TestOnlySomeoneElseCanTakeAnOrder.test_a_fully_taken_order_leaves_the_board` | 全量約定した注文は検索結果から消える | 残数0の注文を板に残す |
| MB-11 | R | A: `TestOnlySomeoneElseCanTakeAnOrder.test_your_own_order_cannot_be_taken_by_yourself` | 自分の注文を自分で受けることを禁止する | 自己約定判定を削り価格履歴を作れてしまう |
| MB-12 | R | A: `TestOnlySomeoneElseCanTakeAnOrder.test_taking_an_absent_order_is_refused` | 存在しない注文の約定は断る | 不在注文を偽の取引として受理する |
| MB-13 | R | A: `TestTheTradeRecordCarriesWhoMovedThePrice.test_taking_a_sell_order_records_the_seller_as_the_resting_side` | 売り注文を受けた記録では売り手が掲示側、買い手が受け手になる | seller/buyer を逆にする、taker_side を掲示側にする |
| MB-14 | R | A: `TestTheTradeRecordCarriesWhoMovedThePrice.test_taking_a_buy_order_records_the_buyer_as_the_resting_side` | 買い注文を受けた記録では買い手が掲示側、売り手が受け手になる | SELL用の割当をBUYにも流用する |
| MB-15 | R | A: `TestTheTradeRecordCarriesWhoMovedThePrice.test_the_trade_keeps_the_tick_and_the_order_it_came_from` | 取引記録は手番・注文ID・品目と実取引総額を保つ | 手番や注文IDを落とす、総額に元注文の全数量を使う |
| MB-16 | F | A: `TestExpiryIsReadWithoutChangingTheBoard.test_orders_past_their_expiry_are_listed` | 期限後の注文を返す参照は、元の板を変更しない | 期限切れを取り出すとき、返す対象を板から除去または引き取り待ちにしてしまう |
| MB-17 | R | A: `TestExpiryIsReadWithoutChangingTheBoard.test_live_orders_are_not_listed` | 期限ちょうどの注文はまだ期限切れ一覧へ入らない | 期限比較を > から >= に変える、または全注文を返す |
| MB-18 | R | A: `TestExpiryIsReadWithoutChangingTheBoard.test_an_order_awaiting_collection_is_not_listed_again` | 引き取り待ちへ移した注文を期限切れとして繰り返し返さない | awaiting_collection の除外を削る |
| MB-19 | R | A: `TestWhatEachViewerSeesOnTheBoard.test_a_live_order_is_visible_to_everyone` | 生きている注文一覧は持ち主にも他人にも見える | 持ち主を一覧から一律除外する、または持ち主以外を一律除外する |
| MB-20 | R | A: `TestWhatEachViewerSeesOnTheBoard.test_an_order_awaiting_collection_is_hidden_from_others` | 引き取り待ち注文は他人の公開注文一覧から隠れる | 待ち状態の判定を削る |
| MB-21 | R | A: `TestWhatEachViewerSeesOnTheBoard.test_an_order_awaiting_collection_is_still_visible_to_its_owner` | 引き取り待ち注文は持ち主の公開注文一覧に状態付きで残る | 待ち注文を持ち主からも隠す |
| MB-22 | R | A: `TestWhatEachViewerSeesOnTheBoard.test_a_merchant_order_is_visible_like_any_other` | 商人の生きた注文も個別注文一覧に見える | orders_visible_to が PLAYER 注文だけを返す |
| MB-23 | R | B: `TestTheRowsSummariseEachItem.test_one_item_becomes_one_row` | 同じ品目の複数注文は集約表示で1行になる | 注文ごとに行を返す、または品目IDを取り違える |
| MB-24 | R | B: `TestTheRowsSummariseEachItem.test_different_items_become_different_rows` | 異なる品目は異なる表示行になる | 全注文を一つの共通行に集約する |
| MB-25 | R | B: `TestTheRowsSummariseEachItem.test_the_row_counts_the_listings_and_the_goods` | 出品件数と買える総数量を別々に集計する | 数量を件数として数える、または総数量を1件分だけにする |
| MB-26 | R | B: `TestTheRowsSummariseEachItem.test_the_row_shows_what_you_pay_and_what_you_receive` | 閲覧者が払う値は売り最安、受け取る値は買い最高になる | 売買の側を反転する、min/maxを逆にする |
| MB-27 | R | B: `TestTheRowsSummariseEachItem.test_a_move_you_cannot_make_has_no_price` | 買い注文がないと売れる単価はNone、買い注文件数は0になる | 空側の価格既定値を0にする、反対側の件数を流用する |
| MB-28 | R | B: `TestTheRowsSummariseEachItem.test_an_empty_board_has_no_rows` | 未使用の空の板は表示行も空になる | 空の板にダミー品目を出す |
| MB-29 | R | B: `TestThePricesShownAreThePricesYouCanTake.test_your_own_order_is_not_counted_as_a_price_you_can_take` | 自分の安い出品を自分が買える価格へ含めない | owner==viewer の除外を削る |
| MB-30 | R | B: `TestThePricesShownAreThePricesYouCanTake.test_someone_else_can_still_buy_at_that_price` | 持ち主が変われば、他人の安い出品を買える値として読める | 除外対象を閲覧者ではなく最安の注文に固定する |
| MB-31 | R | B: `TestThePricesShownAreThePricesYouCanTake.test_a_row_of_only_your_own_orders_has_no_takeable_price` | 自分の注文しかない品目にも行があり、取れる価格・件数はない | 自分だけの品目行を消す、または自分を需給に数える |
| MB-32 | F | B: `TestYourOwnOrdersAreListedOneByOne.test_your_orders_are_returned_individually` | 自分の複数注文は品目や売買の側で一つに潰さず、他人の注文を除いて個別に返す | own_orders を最初の1件や品目ごと1件に切り詰める |
| MB-33 | R | B: `TestYourOwnOrdersAreListedOneByOne.test_other_peoples_orders_are_not_yours` | 本人注文がない場合、own_ordersは空になる | 最初の他人注文を代わりに返す |
| MB-34 | R | B: `TestYourOwnOrdersAreListedOneByOne.test_an_order_awaiting_collection_is_listed_for_its_owner` | 引き取り待ちでも本人のown_ordersへ状態付きで返す | 表示用の本人注文一覧から待ち注文を除外する |
| MB-35 | R | B: `TestYourOwnOrdersAreListedOneByOne.test_an_order_awaiting_collection_is_not_offered_to_others` | 他人の引き取り待ち注文を売買可能な集約行にしない | rows_for が待ち注文を需給へ含める |
| MB-36 | F | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_a_settled_order_leaves_its_unit_price_on_the_row` | 唯一の注文が全量約定しても、その品目の直近価格を取得でき、表示行も残る | rows_for が生きた注文のない品目の約定価格行を作らない |
| MB-37 | R | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_an_item_that_never_traded_has_no_price` | まだ約定していない品目の価格取得結果はNoneになる | 未約定を0G扱いにする、注文単価を実績価格として返す |
| MB-38 | R | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_the_row_carries_the_last_traded_price` | 未約定注文の値と直近成立値は同じ行の別欄として読める | last_trade_price_goldへ現在の最安値を流用する |
| MB-39 | R | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_a_later_trade_replaces_the_earlier_one` | 同品目の後の手番の約定が直近価格を更新する | 最初の取引のみ保存する、古い同品目を先に参照する |
| MB-40 | R | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_each_item_keeps_its_own_price` | 他品目の約定でそれまでの品目の直近価格を失わない | last_tradesを全品目共通の1件に置き換える |
| MB-41 | F | H: `TestTheBoardRecordsThePriceThatActuallyCleared.test_a_partial_fill_across_two_orders_keeps_the_last_one` | 同じ手番に2注文をまたいで受け、最後の注文が部分約定でも最後の単価を直近価格とする | 全量約定したときだけ価格履歴を保存する、同じtickの2件目を無視する |
| MB-42 | R | H: `TestThePriceSurvivesEveryOtherChangeToTheBoard.test_placing_another_order_keeps_it` | 新しい注文の追加で既に成立した価格を落とさない | with_order が orders だけ指定して新しいMarketBoardを作る |
| MB-43 | R | H: `TestThePriceSurvivesEveryOtherChangeToTheBoard.test_cancelling_an_order_keeps_it` | 注文取消で既に成立した価格を落とさない | _without が orders だけ指定して新しいMarketBoardを作る |
| MB-44 | R | H: `TestThePriceSurvivesEveryOtherChangeToTheBoard.test_repricing_an_order_keeps_it` | 値の付け直しで既に成立した価格を落とさない | with_repriced/_replace_order が履歴を落とす |
| MB-45 | R | H: `TestThePriceSurvivesEveryOtherChangeToTheBoard.test_moving_an_order_to_awaiting_collection_keeps_it` | 引き取り待ちへの移行で既に成立した価格を落とさない | awaiting_collection/_replace_order が履歴を落とす |

## 故障を入れた検出力確認

4種類の故障は、元の対象45件が全部通り、修理後46件では狙った1件だけが失敗した。統合1件は、旧削除対象と新保持先が同じ無追加を検出した。故障時の失敗を通常試験の失敗と混同しない。

| 意図的に入れた故障 | 旧試験 | 修理後 | 確認した失敗箇所 |
|---|---|---|---|
| 期限一覧の読取で対象を板から除去 | 対象45件成功 | 46件中1件失敗 | 元の注文が板に残る確認 |
| 本人注文を先頭1件に制限 | 対象45件成功 | 46件中1件失敗 | `both_sides` の2件確認 |
| 履歴だけの品目行を作らない | 対象45件成功 | 46件中1件失敗 | 空の注文板から価格行を取得する確認 |
| 全量約定時だけ履歴を更新 | 対象45件成功 | 46件中1件失敗 | `partial_fill` の直近価格。18Gが残り、期待22Gと食い違う |
| 注文追加が元の板を返すだけ | 旧2件中、削除対象1件が失敗 | 新保持先1件が失敗 | 返却板へ注文が実際に追加された確認 |

計5種類・旧新10実行。本体と候補試験をバイト単位で完全復元した後、下記の最終600件を実行した。本体のSHA-256は `98b77e049dc49819aa06b129b81581f4894018e501dafbe6c4dcedbfd13812f4`。

## 通常の検証結果

外向き通信を遮断し、認証用の環境変数を渡さず、実LLMを使わない固定Python 3.10.22 / pytest 8.4.1環境で実行した。各実行で、この作業ツリーの `src` を読み込んでいることを確認した。CI規定の `uv run --frozen pytest` をそのまま実行したという意味ではなく、既存の固定依存環境から `python -m pytest` と通信遮断・計測プラグインを使った結果である。

- 基準：対象3ファイル45件成功。対象を含む関連範囲599件成功
- 修理後：対象は44宣言・46実行件。元入力を残した2行追加と1宣言統合による違い
- 最終：同じ関連範囲600件成功、失敗・エラー・除外・重複した実行識別子はいずれも0。内訳は対象46件とその他554件。対象だけの結果を再加算しない
- 変更した3ファイルの `ruff check` と `git diff --check` は成功
- `ruff format --check` は基準と候補の両方で既存2ファイルが未整形。新しく触れた部分は書式を合わせ、無関係な全面整形は含めていない

最終の実行範囲は `tests/domain/trade`、`tests/application/trade`、`tests/application/being/test_market_board_codec.py`、`tests/demos/test_paying_a_turn_to_read_the_board.py`、`tests/demos/test_which_order_gets_taken_first.py`、`tests/demos/test_the_board_shows_what_you_can_do.py`。

これらは通常収集対象なので、CIのファイル登録変更は不要。リポジトリ全件、品質指定、実API試験は実行していない。確認済みの製品不具合はなく、この修理はテストだけに閉じる。

## 今後の試験を置くときの判断

「部分約定」なら残数のある注文を実際に通す。「行に残る」なら価格取得メソッドだけで済ませず行を読む。「1件ずつ」なら本人の複数注文を混在させる。取得結果だけでなく、非破壊参照が必要な場面では元の状態を確認する。統合先が無操作で通るまま元の正の対照を消さない。
