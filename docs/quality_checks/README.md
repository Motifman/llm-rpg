# Quality Check Scenarios

## 何のためのフォルダか

このフォルダは Issue #526 で議論した「人間らしさのギャップ」を
**振る舞いの質感** として点検するための場所です。

通常のユニット / 統合テストは「コードが期待通り動くか」を見ますが、
ここに置くのは **「人間として読んで違和感が減ったか」** を見るための
material:

- 質感シナリオ (= `tests/quality/test_*.py`) は、特定の状況を再現する
  pytest テスト。LLM は呼ばず prompt の中身だけダンプする
- baseline ドキュメント (= ここに置く `.md` ファイル) は、その prompt
  を読んで「何が拾えていて何が拾えていないか」を 1 段落で記録する

CI には乗せません (= pytest mark `quality` で分離)。改善 PR ごとに
1 回回して、所感を該当ドキュメントに追記する運用です。

## シナリオ一覧

| ID | テスト | doc | 目的 |
|---|---|---|---|
| `yesterday_v1` | `tests/quality/test_yesterday_v1.py` | `yesterday_v1_baseline.md` | 「昨日何してた?」に答えられるか (= 自伝的時系列 / 能動想起) |

## 使い方

```bash
# シナリオを 1 つ走らせて prompt dump を生成
uv run pytest tests/quality/test_yesterday_v1.py -m quality

# 結果は docs/quality_checks/yesterday_v1_<variant>.prompt.txt に
# 上書き保存される。git diff で「前回 PR から prompt がどう変わったか」
# が確認できる
```

dump の中身を読んで、対応する baseline `.md` の末尾に短い所感を追記
してください。書く内容は:

- 変化があったか (前回 PR の trace と diff)
- 良い方向か中立か悪化か
- 次に何を試したいか

## 設計の根拠

詳細は Issue #526 と PR #530 後の議論を参照。要旨:

- 「ここまで足したのに振る舞いの質感はあまり変わってない」を見落とすと
  シリーズ全体が "機能の集合" に終わる
- 数値テストでは検出できない振る舞いの差を、PR 作者 1 人が trace を
  読むことで早期に気付く場として用意する
- 軽さを担保するため、フォーマット厳密化 / レビュー必須 / CI 必須は
  しない
