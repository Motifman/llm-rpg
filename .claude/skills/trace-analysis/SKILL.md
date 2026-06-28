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

# 守るべきこと

- **統計だけで終わらない**: 必ず具体的な台詞 / memo / inner_thought を引用する
- **「だいたい良い」は却下**: 数字と引用で根拠を示す
- **新規発見は最終 viewer の冒頭に「主要発見」として 5 項目以内で要約**
- **次の宿題 (= 改善 PR 候補) を最後に列挙する** (これが分析の ROI)
