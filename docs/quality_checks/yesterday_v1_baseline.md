# yesterday_v1 — baseline 所感

## このシナリオが見るもの

「カイトに『昨日何してた?』と聞かれたリンが自然に答えられるか」を、prompt
構造の側から見るシナリオ。LLM は呼ばず、prompt の中身そのものを点検する。

詳細とテストコード: `tests/quality/test_yesterday_v1.py`、README:
`docs/quality_checks/README.md`。

## 初回 baseline (= PR #530 直後 / 主観時間も能動想起も未実装の状態)

dump: [`yesterday_v1_in_window.prompt.txt`](./yesterday_v1_in_window.prompt.txt)
[`yesterday_v1_out_of_window.prompt.txt`](./yesterday_v1_out_of_window.prompt.txt)

### in_window 版 — 「素材は揃っているのに時系列ラベルが無い」

「直近の出来事」section に **3 件が並列** に並ぶ:

```
- 閲覧室で見習い司書の覚書を読んだ
- 書架 A で『水』の断片語を見つけた
- カイトの声: 「リン、昨日何してた?」
```

問題:

- **時系列のラベルが無い**。最初の 2 つは "昨日" のはずだが prompt の上では
  「いま起きたばかり」と区別できない
- LLM 側からは「直前にやったこと」と「昨日のこと」が **同列のリストに
  見える** ため、カイトの質問に「いま閲覧室で覚書を読んだ」と答えてしまう
  可能性が高い (= 時間軸が崩壊している)
- 主観時間語彙 (「昨日の昼」「夕方」など) が一切登場していない

「素材は揃っているのに、語彙が無いせいで narrative に組み立てられない」状態。

### out_of_window 版 — 「現在地が同じ場所だけ引けている」

「【関連する記憶】」section に **1 件だけ** 出る:

```
QUALITY_MARKER_NOON: 昨日の昼、閲覧室で見習い司書の覚書を読んだ。
```

書架 A の episode (= 「書架Aで『水』の断片語を見つけた」) は **拾えていない**。

何が起きているかの推定 (= trace で要確認だが、構造から):

1. リンの現在地が「閲覧室」→ runtime context cue として `place_spot:閲覧室_id` が立つ
2. 過去 episode の片方は `place_spot:閲覧室_id` を持つ → cue マッチ ✅
3. もう片方は `place_spot:書架A_id` を持つ → 現在地と一致しない ❌
4. カイトの発話「リン、昨日何してた?」には固有名詞が含まれない → noun_matcher (PR7 R4) でも entity/place cue が立たない
5. 「昨日」という時間表現は cue 化されない (= R5 で encounter cue は入ったが時間 cue は未対応)

結果として:
- **現在地と一致する過去だけが偶然引ける**
- **「思い出そう」という意図駆動の recall は存在しない**
- 場所違いの episode は永遠に呼び戻されない

## 浮かび上がった構造的問題 (Issue #526 との対応)

| 観察 | 対応する Issue #526 の不在 |
|---|---|
| 「昨日」が cue にならない | 1. 時間軸の不在 |
| カイトの質問が recall trigger にならない | 2. agent-driven 想起の不在 |
| 「直近の出来事」に時系列ラベルが無い | 1. 時間軸の不在 (prompt 露出側) |
| 場所違いの過去 episode が永遠に拾われない | 2. agent-driven 想起の不在 |

特に **out_of_window 版で書架 A の episode が出ない** ことは、Issue #526 の
仮説 1+2 が実際に prompt 構造として刺さっていることを具体的に示している。
「2. agent-driven 想起の不在」が「思い出してみる」経路の不在として顕在化
していて、これが無いと「現状況の cue マッチで偶然引ける範囲」しか過去に
アクセスできない。

## 次に試したい変更 (探索メモ、決定ではない)

1. **「直近の出来事」section に時系列ラベルを足す**: tick → "昨日" / "今朝" /
   "数分前" のラベリングを観測 entry に付ける (= 主観時間 v0)。これだけで
   in_window 版の「素材を narrative にする」プロンプト側の支援になる
2. **時間表現を cue に変換する経路**: 観測 prose の「昨日」「先週」を検出
   して、「過去 N tick の episode」を recall 対象に追加する (= 時間 cue)
3. **質問が来たことを agent-driven recall の trigger にする**: 観測種別が
   `speech_message` で質問形式 (= "?" を含む) のとき、recall を能動側で
   1 回打つ

これらは別 PR で 1 つずつ試す。次回 baseline 取り直したときに、それぞれの
変更で in_window / out_of_window がどう変わるかを追記する。

## 主観時間 v0 後の所感 (2026-06-19, PR for subjective-time-v0)

dump 更新: `yesterday_v1_in_window.prompt.txt`, `yesterday_v1_out_of_window.prompt.txt`

### in_window — 時系列ラベル付与の効果

「直近の出来事」section が次のように変わった:

```
- [昨日] 閲覧室で見習い司書の覚書を読んだ
- [昨日] 書架 A で『水』の断片語を見つけた
- [たった今] カイトの声: 「リン、昨日何してた?」
```

これは前回 baseline と比べて **大きな改善** :

- 「昨日のこと」と「今のこと」が prompt 上で明示的に区別された
- LLM は narrative 化のとき「昨日 閲覧室と書架Aを巡った」と組み立てやすくなる
- カイトの「昨日何してた?」の「昨日」が、prompt 内の「[昨日]」ラベルと **語彙レベルで一致** したので、対応関係が読み取れる可能性が高まった

### out_of_window — 状況は基本変わらず

```
- [たった今] カイトの声: 「リン、昨日何してた?」
```

passive recall 側 (= 「関連する記憶」section) は変わらず閲覧室の 1 件だけ
拾える状態。**主観時間 v0 は「直近の出来事」section にしか効かない** ため、
recall trigger としての時間 cue は未解決。

これは次のシリーズ (時間 cue / 質問駆動 recall) で対処する。

### 質感判定

- in_window: ✅ 改善 (= 「素材を narrative にする」プロンプト側の支援が成立)
- out_of_window: ⚪ 中立 (= 「直近の出来事」が「カイトの声 / たった今」になって区別はついたが、過去 episode 側は依然として現在地一致頼み)

## memory_recall_episodes e2e 配線後の所感 (2026-06-19)

dump 更新: 両 variant の `=== tools ===` セクション末尾に
`memory_recall_episodes` が出るようになった:

```
=== tools ===
...
- memo_done
- memory_recall_episodes      ← 新規
```

### 質感判定

- **tools 側**: LLM が「思い出そう」と意志して tool を呼べる状態に到達 (= Issue #526 不在 2 への構造的経路が開通)
- **prompt 側**: 「直近の出来事」「関連する記憶」section は変わらず (= 主観時間 v0 + 既存 passive recall のまま)

### 残る穴

実 LLM 呼び出しでは検証していない。次の点が宿題:

- LLM はカイトの「昨日何してた?」を見たとき、`memory_recall_episodes` を **実際に呼ぶか**? それとも passive recall だけで済ませようとするか?
- 呼んだ場合、`about` と `time_range` をどう組み立てるか? (= description の指示が効くか)
- 呼ばないとしたら、prompt の system 指示で誘導する必要があるか?

これは実 LLM 試走 (= LLM_CLIENT=litellm) で検証する別 task。

## 改訂履歴

- **2026-06-19** (PR #531 = quality scenario 導入時): 初回 baseline
- **2026-06-19** (主観時間 v0 PR): in_window に "[昨日]" / "[たった今]" のラベルが乗るようになった
- **2026-06-19** (memory_recall_episodes e2e 配線): tools list に `memory_recall_episodes` が出るようになった (= Issue #526 不在 2 への経路開通)
