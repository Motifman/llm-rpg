# prediction_v1 baseline

「予測が外れた経験が次の予測を変えるか」を prompt 構造で点検するシナリオ
(Issue #526 不在#3、PR0〜PR3 = 予測→学習ループ)。詳細設計は
[../memory_system/prediction_learning_loop_design.md](../memory_system/prediction_learning_loop_design.md)。

テスト: `tests/quality/test_prediction_v1.py` (`-m quality`、CI 非搭載)。
dump: `prediction_v1_immediate.prompt.txt` / `prediction_v1_learned.prompt.txt`。

## variant

| variant | 再現する状況 | 見るもの |
|---|---|---|
| `immediate` | 「ノアに声をかければ聞ける」と予測 → ノアは無視。その直後のターン | `【前回の予測と実際】` が予測と実際の gap を並べるか (PR1 突き合わせ) |
| `learned` | 「ノアは機嫌が悪いと無視する」学びが semantic に既にある状態で、次にノアに会うターン | `【関連する学び】` にその学びが戻り次の予測を変える材料になるか (PR3 ループ閉) |

## 所感

### 2026-06-20 (PR3 #544 直後、シナリオ初版)

**immediate**: `【前回の予測と実際】` が `【直近の出来事】` の直前に出て、予測
(「ノアに声をかければ、今の目的を聞ける」) と実際 (`tool=speech_say /
success=True` + 後続観測「ノアは答えず立ち去った」) が並んだ。注目すべきは
**発話 tool 自体は success=True なのに、世界の応答についての予測 (返事をもらえる)
は外れている**点。これは「構造的失敗ではない意味的な乖離」で、PR2b の決定論
fallback では拾えないが、PR1 の「驚きを文脈内で経験する」設計では gap が prompt に
並ぶので、次ターンの推論で「あれ、無視された」と気づく材料は揃っている。ここは
意図どおり。ただし agent が実際にそれを拾って行動を変えるかは LLM を回さないと
分からない (このシナリオの範囲外)。

**learned**: 予測由来の学び「ノアは機嫌が悪いと無視することがある」が
`【関連する学び】` に戻ることを確認。次にノアに会う場面で、この学びが次の
`expected_result` を変える材料として prompt に乗っている。ループの「学び → 次の
予測」の口が構造的につながっていることが見える。

**発見 (ハーネス)**: escape_game runtime は episodic recall のみ配線し semantic
recall (`【関連する学び】`) を配線していない。learned variant は prompt builder へ
`SemanticPassiveRecallService` を white-box 注入して確認した。**escape_game 上では
学び (semantic) が生成されても prompt に戻らない = ループが escape_game 単体では
閉じ切らない**。これは escape_game の限界であって本番 wiring の問題ではないが、
実験を escape_game で回すと「学びが次の予測に効く」質感は観測できない点に注意。
→ 次の課題候補: escape_game に semantic recall を配線するか、本番 wiring を使う
質感ハーネスを別途用意するか。

**次に試したいこと**:
- LLM を回す軽い run で、immediate の gap を見た agent が次行動を変えるか
- 予測誤差 episode の promotion 優先付け (PR3.5) を入れた場合に learned の学びが
  どれだけ早く立ち上がるか
