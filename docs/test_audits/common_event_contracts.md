# 集約の診断とイベント時刻の契約を確かめる

## なぜ

共通イベント基盤が所有する2ファイル5宣言を全件確認した。警告の件数を見ていない検査、特定の語の不在だけで無音を判断する検査、件数だけで非消費を判断する検査があり、誤った診断や配送内容の変化を見逃していた。

基準は main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。判断は R1/F3/C1/D0。製品コードの変更は0行。対象の試験は104行から119行へ増え、宣言は5件から4件に整理した。元の入力5ケースを残し、混在する型の入力を1つ加えたため、実行ケースは5件から6件になる。試験内の補助クラスは14行から9行へ減った。独立した補助ファイルはない。

件数の削減より、実際に壊れたときに気づけることを優先する。

## 契約の所有者と導入の意図

- [AggregateRoot](../../src/ai_rpg_world/domain/common/aggregate_root.py) は、未発行イベントの保持と、明示的に呼ぶ診断 `warn_if_pending_events` を所有する
- [PR #600](https://github.com/Motifman/llm-rpg/pull/600) は、場所・型名・件数を WARNING で知らせ、イベントを消費しない公開APIとしてこの診断を導入した。保存時の強制実行は、正常なイベント持越しで警告を増やすため採用していない
- 後続の [PR #601](https://github.com/Motifman/llm-rpg/pull/601) と [PR #602](https://github.com/Motifman/llm-rpg/pull/602) は、採取と時間経過の配送経路を修正した。基準の製品コードには診断APIの実呼出がないが、未使用という理由だけで公開契約を削除しない。実適用や廃止は別の設計判断とする
- [BaseDomainEvent](../../src/ai_rpg_world/domain/common/domain_event.py) は、共通の生成APIと `occurred_tick` を所有する。[導入時の変更](https://github.com/Motifman/llm-rpg/commit/c815b29d37cbfa321887bd7613eae878a17485b9) と [設計メモ](../ddd-world-refactor-handoff.md) は、個別イベントの時刻を基底に集約し、観測が遅れても発生時点を表示できる意図を記録している

## 全5宣言の判断と保持先

Rは保持、Fは契約を保って検査を修理、Cは保持先へ先に移して統合する判断。削除を意味するDはない。

ファイル略号:

- W: [test_aggregate_root_warn_pending_events.py](../../tests/domain/common/test_aggregate_root_warn_pending_events.py)
- E: [test_domain_event.py](../../tests/domain/common/test_domain_event.py)

| ID | 判断 | 元の宣言 | 契約と具体的な退行 | 保持先 |
|---|---|---|---|---|
| CE1 | F | W: `TestWarnIfPendingEventsNoWarn.test_no_pending_events_no_warning` | 空なら警告を出さない。元の検査は `pending` / `publish` という語を含まない警告を見逃す | 同じ宣言で対象のログ出力元の WARNING 以上の記録が空であることを検査 |
| CE2 | C | W: `TestWarnIfPendingEventsWithEvents.test_pending_events_emits_warning` | 同型イベント2件で WARNING が出る。警告の削除・INFOへの降格を検出する契約を失わない | CE3の `two-same-type-events` に移管 |
| CE3 | F | W: `TestWarnIfPendingEventsWithEvents.test_warning_includes_context_and_count` | 場所・総数・型別件数が分かる。元の検査は総数を型の種類数へ置換しても通る | 同じ宣言の3入力で WARNING と診断内容を検査 |
| CE4 | F | W: `TestWarnIfPendingEventsNoSideEffect.test_events_remain_after_warn` | 診断後も内容と順序が同じである。元の検査は2件の逆順化や同件数の重複を見逃す | 同じ宣言で不変イベントの順序付き全値を比較 |
| CE5 | R | E: `TestBaseDomainEvent.test_create_accepts_occurred_tick` | 共通生成APIが `WorldTick(42)` を受け取り保持する。個別型にだけ時刻を戻す変更や引数転送の欠落を検出する | 基準と同じ宣言を、ファイルごと無変更で保持 |

### 移管した入力と新しい区別

- CE1の空リストと `MyRepo.save` はそのまま
- CE2の `_FakeEvent` 2件、両方の `aggregate_id="agg-1"`、`MyRepo.save` はそのまま
- CE3の `_FakeEvent` 1件、`aggregate_id="agg-x"`、`SpotAttackOrchestrator.flush` はそのまま
- CE4の `agg-1`、`agg-2` という順序の2件と `ctx` はそのまま
- CE5の `aggregate_id=1`、`aggregate_type="TestAggregate"`、`WorldTick(42)` はそのまま
- 新しい混在ケースは `_FakeEvent` 2件と `BaseDomainEvent` 1件。期待総数3・型別2対1は明示した値であり、製品の集計処理から期待値を作らない

CE2を統合する前に、CE3へ対象のログ出力元と WARNING レベルの確認を移した。警告の記録数を正確に1件へ固定する制約は足していない。

全文や内訳の順序は固定せず、整形された同じ警告に場所・総数・型別件数がそろうことを見る。空時の契約に DEBUG / INFO の禁止を追加しない。不変イベントは順序付きの値で比較し、同値再構築まで禁じる実体の同一性は固定しない。

## 他の層の試験を代替にしない理由

- [腐敗の試験](../../tests/domain/item/aggregate/test_item_spoilage.py) は、実際の腐敗境界から `ItemSpoiledEvent` へ `WorldTick(8)` が載ることを守る
- [マップの試験](../../tests/domain/world/service/test_map_trigger_engine.py) は、入口の `WorldTick(10)` が生成された `GatewayTriggeredEvent` に届くことを守る
- [観測時刻の試験](../../tests/application/observation/services/test_observation_timestamp_resolver.py) は、渡したイベント時刻を現在時刻より優先して表示することを守る。ただしイベントを模擬するため、共通の生成APIは通らない
- [収集の試験](../../tests/application/common/test_command_context_aggregate_event_sink.py) と [採取の試験](../../tests/application/harvest/services/test_harvest_resource_harvested_publish.py) は、それぞれ収集の成功後に消費すること、保存まで原本を残すことを守る。診断APIは実行しないので、その無音・内容・非消費の代替にはならない

共通APIと、それを使う各入口には異なる責務がある。関連試験があることだけを理由に、基盤の小さな公開契約を消していない。退役ファイルと製品側で削除する補助入口はない。

## 変異による対照

8通りの製品の一時変異について、元の診断4ケースと変更後の診断5ケースを同じ変異へ実行した。時刻生成の保持試験はこの変異群の対象外であり、通常の対象実行に含める。旧新の比較は対象領域に限り、リポジトリ全体で初めて検出できたという主張ではない。

| 変異 | 元の診断4ケース | 変更後の診断5ケース | 失敗する検査 |
|---|---|---|---|
| 空の枝で `Aggregate is empty` と警告する | 成功・見逃し | 失敗 | CE1の記録不在 |
| 総数をイベント型の種類数にする | 成功・見逃し | 失敗 | CE3の同型2件と混在3件の総数 |
| 型別の件数を常に1にする | 成功・見逃し | 失敗 | CE3の型別2件 |
| 診断後にイベント列を逆順にする | 成功・見逃し | 失敗 | CE4の順序付き値比較 |
| 2番目のイベントを1番目で置き換える | 成功・見逃し | 失敗 | CE4の内容保持 |
| WARNING を INFO にする | 失敗 | 失敗 | CE2からCE3へ移した警告レベル |
| 呼出場所を `unknown` にする | 失敗 | 失敗 | CE3の場所 |
| 型別内訳の先頭の型だけを残す | 成功・見逃し | 失敗 | CE3の混在ケースの型別内訳 |

すべて意図した検査で失敗し、収集エラーは0件。各変異後に製品を元のバイト列へ戻し、最終ハッシュが基準と一致することを確認した。

## 試験と範囲

隔離した作業木から製品コードを読み込むことを確認し、認証値を除いた環境で外部通信を禁止した。Python 3.10.22 / pytest 8.4.1 を使用。実LLMを呼ぶ試験は実行していない。

- 基準: 対象5件成功、関連94件成功
- 候補と変異復元後: 対象6件成功、関連95件成功
- 対象2ファイルの `ruff check` 0.16.8と `git diff --check`: 成功
- 関連には対象が含まれるため、単独の成功件数を加算しない
- 全リポジトリ試験は未実行。公開する場合はCIで確認する

関連の範囲は `tests/domain/common` と、腐敗、マップのトリガー、観測時刻、コマンド単位の収集、採取・攻撃の配送の7ファイル。

対象試験の差分は追加71行・削除56行。監査記録と近接した所有規則は試験行数とは別に数える。製品2ファイルと時刻生成の試験ファイルは基準から不変。

## 近接作業と残る確認

記憶の撤去方針 [#1631](https://github.com/Motifman/llm-rpg/issues/1631) と、基準時点の [#1693](https://github.com/Motifman/llm-rpg/pull/1693) / [#1694](https://github.com/Motifman/llm-rpg/pull/1694) の変更パス・内容を確認した。共通の診断・イベント生成APIや今回の保持先に直接の変更はない。古い記憶の保存形式や再解釈の部品へ試験を移さない。

公開前に固定差分、全5宣言の保持先、旧新の変異対照、復元、公開説明を独立に照合する。確認された製品不具合はなく、製品修正と外部Issue作成は含めない。マージは別の判断とする。
