# Review Standard

`flow-review` では、以下を最低ラインとして確認する。

## 実装

- DDD の責務境界が崩れていない
- 継承や interface 利用が既存パターンと整合している
- 例外処理が十分で、握りつぶしや曖昧な失敗がない
- temporary implementation や placeholder がない
- TODO や「あとで対応」が実質的な未実装になっていない

## テスト

- 正常系だけでなく、異常系と境界ケースも見る
- 対応する実装変更に対して十分なテストがある
- 既存の厳しいテスト群と比べて明らかに甘くなっていない
- 例外ケースや validation failure を取りこぼしていない

## 出力

- findings を先に出す
- 問題がなければその旨を明言する
- 残留リスクや testing gap があれば併記する
