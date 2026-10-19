# シナリオ実 LLM 実行ガイド

シナリオを実 LLM で回すときの補足。実験の入口と profile の決まりは CLAUDE.md の「実験の進め方」にある。

2 体の協調を観察する relay_puzzle の実験 (`make experiment-relay*`、`scripts/run_relay_puzzle_experiment.py`、`data/scenarios/relay_puzzle_demo.json`) は、#1631 で退役させた。当時の記録は [docs/experiments/relay_puzzle_run_history.md](experiments/relay_puzzle_run_history.md) に残す。

---

## 新シナリオを試す (汎用 `make experiment` — Issue #188 Phase 1d)

任意の scenario JSON で実 LLM を回し、**trace.jsonl + Markdown レポート + Mermaid HTML** を出力する汎用フロー。
新しいシナリオを試すのに最も手早い経路。

```bash
make experiment SCENARIO=data/scenarios/forbidden_library_demo.json \
                LLM_MODEL=openai/gpt-5-mini

# 既定の出力先:
#   var/runs/<scenario-stem>-<UTC timestamp>/
#     ├── trace.jsonl     ← Issue #188 Phase 1d 形式 (docs/trace_format.md)
#     ├── report.md       ← outcome / tick / 行動数 / memo 数の汎用集計
#     └── trace.html      ← ブラウザで開ける Mermaid タイムライン
```

オプション:

| 変数 | 例 | 説明 |
|------|----|------|
| `SCENARIO` | `data/scenarios/foo.json` | 必須。シナリオ JSON のパス |
| `MAX_WORLD_TICKS` | `50` | `world_tick` がこの値に達したら停止 (既定 30、旧名 `MAX_TICKS`) |
| `OUT` | `var/runs/foo-001` | 出力ディレクトリ (省略時 timestamp 付き自動) |

スクリプト直接実行も可能:

```bash
python scripts/run_scenario_experiment.py \
    --scenario data/scenarios/forbidden_library_demo.json \
    --max-world-ticks 30 \
    --out var/runs/library-foo
```

**新シナリオ追加手順**:

1. `data/scenarios/your_scenario.json` を作る (既存シナリオを参考に)
2. `make experiment SCENARIO=data/scenarios/your_scenario.json`
3. 出力された `trace.html` をブラウザで開く

### `survival_island_v3_coop`（協力シナリオ）を回すとき: `--max-world-ticks 240` を使う

`data/scenarios/survival_island_v3_coop.json` は「協調に失敗すると漂流確定 (stranded) になる」シナリオで、
`stranded_at_tick: 240`（`estimated_ticks` も 240）で設計されている。**`--max-world-ticks` にこれより小さい値を渡すと
stranded 判定が発火する前に実験が打ち切られ、協調が破綻したかどうかを一度も観測できない**（M7 実走で
`--max-world-ticks 200` を指定してしまい、この失敗が起きた）。

```bash
make experiment-survival-coop OUT=var/runs/m7_coop_r1
# 等価 (make experiment 直接):
make experiment SCENARIO=data/scenarios/survival_island_v3_coop.json \
                MAX_WORLD_TICKS=240 OUT=var/runs/m7_coop_r1
```

`make experiment-survival-coop` は `MAX_WORLD_TICKS=240` / `PUBLISH=1` を既定に固定したショートカット
（`make experiment-survival` の v2 版に相当）。他シナリオ (`survival_island_v2` など) の既定値には影響しない。

### Gist 自動 publish (リモート実験を依頼者と共有)

実行終了時に成果物 (trace.jsonl + report.md + trace.html + scenario.json + **viewer.html**) を **secret gist に一括アップロード**し、`htmlpreview.github.io` 経由のプレビュー URL も同時表示します。

```bash
# make 経由 (推奨)
make experiment-publish SCENARIO=data/scenarios/forbidden_library_demo.json

# 等価
make experiment SCENARIO=... PUBLISH=1

# スクリプト直接
python scripts/run_scenario_experiment.py \
    --scenario data/scenarios/forbidden_library_demo.json \
    --publish-gist
```

実行終了時に出力されるログ:

```
[gist] https://gist.github.com/<user>/<id>
[viewer] https://htmlpreview.github.io/?https://gist.githubusercontent.com/<user>/<id>/raw/06_viewer.html
[legacy-html] https://htmlpreview.github.io/?https://gist.githubusercontent.com/<user>/<id>/raw/03_trace.html
```

`[viewer]` URL を開くと **playback 再生 + 空間マップ + memo パネル付き** の Cytoscape インタラクティブ viewer (PR #213 系) が表示されます。`[legacy-html]` は旧 Mermaid シーケンス図 viewer (jq/grep 派向け)。

オプション:

| flag | 説明 |
|------|------|
| `--publish-gist-public` | secret ではなく public gist にする (既定 secret) |
| `--publish-gist-desc "..."` | gist の説明文を上書き |

#### viewer.html の自動生成

`publish_experiment_gist.py` は publish 直前に `viewer.html` を build します (既に存在すれば skip)。`trace.jsonl` と `scenario.json` (任意) から自動的に Cytoscape inline viewer を生成。

Cytoscape の取得 (初回のみネット越し、以降キャッシュ) が失敗した場合は警告のみで publish は続行します (旧 trace.html はあるので可視化手段はゼロにならない)。

`--no-build-viewer` で viewer 自動生成を抑止できます。

#### 後追い publish (実験はすでに済んでいるが、後から gist 化したい)

```bash
python scripts/publish_experiment_gist.py var/runs/forbidden_library_demo-20260524-xxx
# viewer.html が無ければ自動で build される
```

#### 前提

- `gh` CLI がインストール済み (`gh --version`)
- `gh auth status` で認証済み
- gist 作成権限 (`gist` scope)
- viewer 自動生成のため初回のみ Cytoscape の download (~400KB)。以降は `~/.cache/llm-rpg-viewer/` から読む

---

## はまりどころ（必読）

### 1. `.env` の `OPENAI_API_BASE` がクラウド実行を壊す

`.env` に `OPENAI_API_BASE` が残っていると、シェルで `LLM_MODEL` だけ変えても **そちらのエンドポイントに向く**。
クラウド実験時は **`OPENAI_API_BASE=` をコマンド先頭で明示的に空**にする。

### 2. Pydantic serializer warning

実行中に `CompletionTokensDetails` の UserWarning が出ることがある。**実行は継続可能**。

### 3. `var/` は git 管理外

レポート・ログはローカル `var/` に出力。共有は **Gist** または Issue コメント（`gh gist create`）。

### 4. 非決定性

同一条件でも LLM サンプリングで WIN/LOSE が変わる。比較は **同一 commit + 同一モデル + 複数回** を推奨。

---

## サーバ UI での実行（別経路）

FastAPI サーバ + ブラウザで tick loop を回す手順は `docs/demos/two_agent_world_issue.md`。

---

## テスト

```bash
pytest tests/infrastructure/llm/test_litellm_client.py -q
```

実 LLM を呼ばない。`OPENAI_API_BASE` 経路のみ検証。
