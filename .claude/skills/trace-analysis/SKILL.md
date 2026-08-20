---
name: trace-analysis
description: llm-rpg の実験 run (var/runs/.../trace.jsonl + report.md) を 6 軸 (効率 / 物語 / per-agent / 記憶 / 失敗 / システム) で多角分析し、人間が読める analysis.html を生成する。`/trace-analysis <run_dir>` で起動。baseline run を比較対象として渡すと差分も出す。
---

# 使い方

```
/trace-analysis var/runs/island_recall_layer/Y_after_issue621
# または baseline 付き
/trace-analysis var/runs/island_recall_layer/Y_after_issue621 var/runs/island_recall_layer/Y_after_all_fixes
```

引数:
- `run_dir` (必須): 解析対象の run dir。`trace.jsonl` と `report.md` を含む
- `baseline_dir` (任意): 前回 baseline。指定すると比較表を出す

## 処理フロー

### Step 1: 共通指標を抽出

```bash
PYTHONPATH=. python .claude/skills/trace-analysis/extract_metrics.py <run_dir> [baseline_dir] > /tmp/trace_metrics.json
```

これで以下が JSON で得られる:
- summary (LLM call / latency p50/p90/p99 / token / cost / cache hit / 失敗率)
- per-player counts と tool histogram
- per-tool 成功/失敗 + error_code breakdown
- 時系列 cache hit 推移 (20 tick 毎)
- 時系列 per-tick wall time
- observation category 内訳
- summary 生成回数 (L4/L5/episodic_chunk)
- loop_guard_warning 詳細
- baseline 比較 (baseline_dir 指定時)
- 協調指標 (PR-A, survival_island_v3_coop 系向け): ペア別 / 全員同スポット
  共在 tick 数、hearsay (伝聞) evidence の話者別件数、pending_prediction の
  kind 別件数 (created/resolved/expired + 未知 suffix) と resolved の
  verdict 内訳、give_item 実行件数

`extract_metrics.py --help` で詳細。

### Step 2: 並列サブエージェント 2 体を起動

両方同時に launch (= 1 メッセージで Agent を 2 つ叩く)。**プロンプトはこの SKILL の `prompts/` 配下のテンプレートを読み込んで作る** (中身は run_dir の trace path に置換)。

- **Agent 1 (narrative + per-agent)**: `prompts/narrative_per_agent.md` をベースに、対象 trace へのパスを差し込む。B-09〜B-16 と C-17〜C-24 を担当。
- **Agent 2 (memory + failures)**: `prompts/memory_failures.md` をベースに、対象 trace へのパスを差し込む。D-25〜D-32 と E-33〜E-36 を担当。

両 Agent ともに 5000 字程度の Markdown レポートを返す契約。

### Step 3: 自分で A + F 軸を書く

Step 1 の metrics JSON を読んで効率セクション (A-1〜A-8) と Issue #621 / システム検証セクション (F-37〜F-40) を作る。

### Step 4: 統合 HTML viewer を生成

`.claude/skills/trace-analysis/viewer_template.html` を元に、6 軸のセクションを差し込む。出力は `<run_dir>/analysis.html`。

### Step 5: gist に publish

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/publish_experiment_gist.py \
  --description "<run_dir のベース名> 多軸分析レポート" \
  --no-build-viewer \
  <run_dir>
```

publish 前に `<run_dir>/00_analysis_viewer.html` として analysis.html をコピーして gist の先頭に並ぶようにし、publish 後に local の duplicate は削除。

# 40 軸一覧

軸の名前は固定し、毎回同じ番号で呼ぶ (= 過去 run と比較しやすい)。詳細は
`prompts/narrative_per_agent.md` と `prompts/memory_failures.md` を参照。

**A. 効率・コスト・レイテンシ** (自分で担当)
- A-1 tick latency 分布
- A-2 per-player LLM call 数
- A-3 cache hit 率の時系列
- A-4 並列 worker 利用率 (`extract_metrics.py` で取れる範囲で)
- A-5 tool 成功/失敗 per-tool
- A-6 per-tick wall time 推移
- A-7 idle / wait 比率
- A-8 short/long summary 生成回数

**B. 物語・ドラマ** (Agent 1 担当)
- B-09 シナリオ目標進捗
- B-10 主要転機 tick
- B-11 speech_speak タイムライン
- B-12 協力 / 対立 events
- B-13 感情・トーン推移
- B-14 ペルソナ忠実度
- B-15 memo の内省内容
- B-16 outcome の物語的意味

**C. エージェント別深掘り** (Agent 1 担当)
- C-17 tool 使用 top 5 / 時系列
- C-18 error_code 分布
- C-19 memo lifecycle
- C-20 主な滞在 spot
- C-21 inner_thought の質
- C-22 encounter pattern
- C-23 失敗多発 player の真因
- C-24 speech style 一貫性

**D. 記憶システム** (Agent 2 担当)
- D-25 episodic_recall K 分布と質
- D-26 recall habituation 効果
- D-27 recall slot 動作
- D-28 afterglow / score 構造
- D-29 episodic_chunk_written と subjective_filled の整合
- D-30 short / long summary クオリティ
- D-31 memo 重複と done balance
- D-32 失敗の記憶化

**E. 失敗・loop_guard・異常** (Agent 2 担当)
- E-33 error_code 分布
- E-34 loop_guard_warning 詳細
- E-35 silent failure 兆候
- E-36 INVALID_TARGET / PRECONDITION 具体例

**F. システム検証** (自分で担当)
- F-37 down/revive chain 発火状況 (Issue #621 検証)
- F-38 prompt の tool catalog 露出
- F-39 observation pipeline category
- F-40 baseline 比較

**G. 市場・価格形成** (自分で担当 — `extract_metrics.py` の `market` セクション)

市場のある run (経済統合 Phase 3 以降) でのみ意味を持つ。板が一度も動いていない
run では `market.measurable` が `false` になるので、その場合は G 節ごと落とす。

- G-41 価格の時系列 (品目別・**向き別**。売りと買いを混ぜない)
- G-42 値を動かした主体と、その手番の独白
- G-43 板が仲介した品と、しなかった品 (分母 = 世界に現れた全品目)
- G-44 交差の機会と結果 (分母 = 売りと買いが同時に並んだ手番数)
- G-45 支払能力の窓 (分母 = 板に出ていた全手番) — **所持金の台帳が要る**
- G-46 gold の出入りと滞留 (商人との境界をまたいだ額)
- G-47 経路の選択 (分母 = 板と対面の**両方が選べた**場面)
- G-48 市場ツールの失敗と、**呼ばれなかったツール** (分母 = `llm_call.tool_names`)

# 守るべきこと

- **すべての数字に分母を持たせる** (下の節。これが最優先)
- **統計だけで終わらない**: 必ず具体的な台詞 / memo / inner_thought を引用する
- **「だいたい良い」は却下**: 数字と引用で根拠を示す
- **新規発見は最終 viewer の冒頭に「主要発見」として 5 項目以内で要約**
- **次の宿題 (= 改善 PR 候補) を最後に列挙する** (これが分析の ROI)

## すべての数字に分母を持たせる

**0 件を「起きなかった」と読んではいけない。「起こりえなかった」かもしれない。**

分子だけを見ると、この 2 つは区別がつかない。実際に繰り返し踏んでいる。

| 数えたもの | 読みかけた解釈 | 実際 |
|---|---|---|
| 交差 0 件 (市場 v3) | 誰も裁定に気づかなかった | 売りと買いが同時に板へ並んだ瞬間が無かった |
| recall 0 件 (市場 v1) | 想起が働かなかった | 短期記憶が上限未満で、出番が構造的に無かった |
| `trade_offer` 0 件 (v2) | 取引機構が使われなかった | 相手が品を持って同席した瞬間が無かった |

**どれも「機構が働かなかった」と読みかけて、実際は「機構が試されていなかった」**
だった。前者は機構の問題で、後者はシナリオの問題。**直す場所が正反対になる**ので、
取り違えると次の run が丸ごと無駄になる。

したがって、どの軸でも次を守る。

1. **分子と一緒に分母を出す**。「何回起きたか」ではなく「**起こりうる状況が
   何度あって、そのうち何回起きたか**」
2. **分母が 0 なら「測定不能」と書く**。0 件と並べて書かない
3. **0 回を専用に見る軸を持つ**。失敗していないものは失敗分布に一行も出ない
   (G-48 がこの形。露出していたのに呼ばれなかったツールは、error_code 分布の
   外側にある)
4. **再現器を作ったら、既知の並びで自己点検してから使う**。板の再現器は
   この点検で「売り注文と買い注文の値を混ぜている」バグが見つかった。
   点検を通していなければ、間違った価格の時系列をそのまま報告していた
