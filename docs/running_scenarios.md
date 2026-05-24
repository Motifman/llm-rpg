# シナリオ実 LLM 実行ガイド

relay_puzzle_demo など **2 体 LLM エージェント**の協調シナリオを、ローカル vLLM または OpenAI クラウドで再現する手順。
Issue #188 の実験（第 4〜10 回）で使ってきた方法を正規化したもの。

**関連 PR**: [#200 依頼書](https://github.com/Motifman/llm-rpg/pull/200)（本ドキュメントで取り込み完了を報告）

---

## 新シナリオを試す (汎用 `make experiment` — Issue #188 Phase 1d)

任意の scenario JSON で実 LLM を回し、**trace.jsonl + Markdown レポート + Mermaid HTML** を出力する汎用フロー。
relay_puzzle 固有集計 (latch tick / kaito-rin marker) は付かないが、新しいシナリオを試すのに最も手早い経路。

```bash
make experiment SCENARIO=data/scenarios/relay_puzzle_demo.json \
                OPENAI_API_BASE=http://127.0.0.1:18001/v1 \
                LLM_MODEL=openai/gemma-4-31b-it-nvfp4

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
| `MAX_TICKS` | `50` | 外側ループ回数 (既定 30) |
| `OUT` | `var/runs/foo-001` | 出力ディレクトリ (省略時 timestamp 付き自動) |

スクリプト直接実行も可能:

```bash
python scripts/run_scenario_experiment.py \
    --scenario data/scenarios/relay_puzzle_demo.json \
    --max-ticks 30 \
    --out var/runs/relay-foo
```

**新シナリオ追加手順**:

1. `data/scenarios/your_scenario.json` を作る (既存シナリオを参考に)
2. `make experiment SCENARIO=data/scenarios/your_scenario.json`
3. 出力された `trace.html` をブラウザで開く

scenario 固有の集計が欲しくなったら、`scripts/issue154_full_tables_experiment.py` を真似て新規 aggregator を書く (relay_puzzle 専用集計はこれ)。

---

## リモート vLLM 接続（推奨: SSH 専用 Host エイリアス）

**ホストの追加は Mac 側の `~/.ssh/config` に数行書くだけ**で、リモートサーバ側の設定変更は不要です。
`LocalForward` は SSH クライアントが「ローカル 18001 への接続をリモートの 8001 に転送する」機能で、エイリアス（別名）のようなものです。

> **セキュリティ上の注意**: 実 FQDN・組織ドメイン・ジャンプホスト名などの **インフラ識別情報を本ドキュメントや本リポジトリに書かないこと**。下記の例はすべてプレースホルダ (`<...>` 形式) で、各自の `~/.ssh/config` (リポジトリ管理外) に実値を書きます。

`~/.ssh/config` の例 (各自の環境に合わせて埋める):

```sshconfig
Host my-vllm
     HostName <vllm-host>                    # 各自のリモートホスト名
     ProxyCommand ssh <jump-host> -W %h:%p   # ジャンプ経由が必要な場合のみ
     LocalForward 18001 127.0.0.1:8001
```

> 本リポジトリのスクリプト (`scripts/ensure_vllm_tunnel.sh` / `make vllm-tunnel`) は `VLLM_SSH_HOST` 環境変数で Host エイリアスを切り替えられます。既定 `v108-vllm` は履歴互換のための **エイリアス名 (任意の文字列)** であり、組織情報は含みません。各自の環境で別名にする場合:
>
> ```bash
> export VLLM_SSH_HOST=my-vllm  # 自分の ~/.ssh/config の Host 名に合わせる
> make vllm-tunnel
> ```

**なぜ 18001 か**: ローカル `8001` は Cursor 等と競合しやすい。18001 に固定すると `.env` を毎回いじらなくてよい。

```bash
make vllm-tunnel    # 未接続なら ssh -N $VLLM_SSH_HOST を起動
make vllm-check     # curl で vLLM 応答確認のみ

# .env（一度設定）
# OPENAI_API_BASE=http://127.0.0.1:18001/v1
# LLM_MODEL=openai/<your-served-model-name>
# OPENAI_API_KEY=

make experiment SCENARIO=data/scenarios/relay_puzzle_demo.json
```

Makefile の `experiment-relay` 等も既定で `18001` を使う（`VLLM_LOCAL_PORT` で変更可）。

---

## クイックスタート（Gemma vLLM / このデバイス）

relay_puzzle 専用の詳細集計付き経路 (第 7〜10 回実験で使ったもの)。

```bash
git clone git@github.com:Motifman/llm-rpg.git
cd llm-rpg
python3 -m venv venv && source venv/bin/activate
pip install -e .

cp .env.example .env
# .env: OPENAI_API_BASE=http://127.0.0.1:18001/v1（v108-vllm トンネル）

make vllm-tunnel
make experiment-relay
```

成功すると `var/experiment_relay_report.md` に G1 サマリー + タイムラインが出力される（`var/` は gitignore）。

---

## 取り込んだファイル一覧

| パス | 役割 |
|------|------|
| `scripts/issue154_full_tables_experiment.py` | **実装本体**。R1/R2/R3 実走、観測フック、Markdown レポート生成 |
| `scripts/run_relay_puzzle_experiment.py` | エントリポイント（上記への薄いラッパ） |
| `scripts/ensure_vllm_tunnel.sh` | v108-vllm トンネル起動・死活確認 |
| `docs/running_scenarios.md` | 本ドキュメント |
| `docs/experiments/relay_puzzle_run_history.md` | 第 4〜10 回と再現条件の対応表 |
| `docs/experiments/templates/relay_puzzle_report_summary.md` | Issue コメント用要約テンプレ |
| `.env.example` | vLLM / クラウド / 実験用環境変数 |
| `src/.../litellm_client.py` | `OPENAI_API_BASE` + 無キー時 `EMPTY` プレースホルダ |
| `tests/infrastructure/llm/test_litellm_client.py` | 上記の単体テスト |
| `tests/scripts/test_issue154_experiment_helpers.py` | 実験スクリプトのヘルパ単体テスト |

---

## Makefile ターゲット

| ターゲット | 内容 |
|------------|------|
| `make experiment-relay` | R1_default + R2_pure（relay_puzzle_demo、既定 max_ticks=30） |
| `make experiment-relay-r1` | R1 のみ |
| `make experiment-relay-r2` | R2 のみ |
| `make experiment-relay-cloud` | OpenAI クラウド（`OPENAI_API_BASE` を空に上書き） |
| `make vllm-tunnel` | `v108-vllm` SSH トンネル起動（port 18001） |
| `make vllm-check` | トンネル + vLLM `/v1/models` 応答確認 |

上書き例:

```bash
make experiment-relay ISSUE154_MAX_TICKS=30 \
  OPENAI_API_BASE=http://127.0.0.1:18001/v1 \
  LLM_MODEL=openai/gemma-4-31b-it-nvfp4 \
  EXPERIMENT_OUTPUT=var/issue188_experiment11_report.md
```

---

## 試行定義（R1 / R2 / R3）

| キー | シナリオ | `LLM_TOOL_MODE` | 用途 |
|------|----------|-----------------|------|
| `R1_default` | `relay_puzzle_demo` | （未設定 = TODO ツール含む） | 協調 + TODO あり |
| `R2_pure` | `relay_puzzle_demo` | `pure_spot_graph` | spot_graph + speech のみ |
| `R3_contention` | `single_relic_contention_demo` | （未設定） | 争奪デモ（relay 以外） |

フィルタ: `ISSUE154_RUNS=R1_default,R2_pure`（カンマ区切り）。

---

## 環境変数

### 共通

| 変数 | 既定 | 説明 |
|------|------|------|
| `LLM_CLIENT` | `litellm`（スクリプトが setdefault） | 実 LLM 必須 |
| `LLM_MODEL` | コード側 `openai/gpt-5-mini` | vLLM では `openai/<served-model-name>` |
| `ISSUE154_MAX_TICKS` | Makefile: `30` / スクリプト単体: `18` | **外側** `advance_tick` 回数の上限 |
| `ISSUE154_RUNS` | 全試行 | 実行する試行キー |
| `EXPERIMENT_OUTPUT` | `var/experiment_relay_report.md` | レポート出力（Make のみ） |
| `SPOT_GRAPH_TICK_LOOP_ENABLED` | `false`（スクリプトが強制） | サーバ tick loop ではなくバッチ駆動 |

### vLLM（Gemma ホスト）

| 変数 | 例 |
|------|-----|
| `OPENAI_API_BASE` | `http://127.0.0.1:18001/v1`（`v108-vllm` トンネル） |
| `OPENAI_API_KEY` | 空で可（クライアントが `EMPTY` を送る） |
| `LLM_MODEL` | `openai/gemma-4-31b-it-nvfp4` |

### OpenAI クラウド（gpt-5-mini / nano 等）

| 変数 | 注意 |
|------|------|
| `OPENAI_API_BASE` | **必ず空**（`.env` に vLLM URL があるとクラウド実行も vLLM に向く） |
| `OPENAI_API_KEY` | 必須 |

実行例:

```bash
OPENAI_API_BASE= LLM_MODEL=openai/gpt-5-mini ISSUE154_MAX_TICKS=30 \
  ISSUE154_RUNS=R1_default,R2_pure \
  python scripts/run_relay_puzzle_experiment.py -o var/gpt5mini_report.md
```

---

## vLLM 向け `.env` 例

```bash
LLM_CLIENT=litellm
OPENAI_API_BASE=http://127.0.0.1:8001/v1
OPENAI_API_KEY=
LLM_MODEL=openai/gemma-4-31b-it-nvfp4
```

接続確認:

```bash
curl -s http://127.0.0.1:18001/v1/models | python3 -m json.tool | head -20
```

---

## スクリプト直接実行

```bash
source venv/bin/activate

# relay_puzzle R1+R2（vLLM）
OPENAI_API_BASE=http://127.0.0.1:8001/v1 \
LLM_MODEL=openai/gemma-4-31b-it-nvfp4 \
OPENAI_API_KEY= \
ISSUE154_MAX_TICKS=30 \
ISSUE154_RUNS=R1_default,R2_pure \
python scripts/run_relay_puzzle_experiment.py \
  -o var/my_report.md 2>&1 | tee var/my_run.log
```

進捗は **stderr**（試行名・駆動 n/max・world_tick・経過秒）。レポートは `-o` で指定した Markdown。

---

## レポートの読み方

自動生成 Markdown の構成:

1. **G1** — WIN/LOSE、終了 tick、所要時間
2. **G2** — LLM invoke 数
3. **G3** — `power_on` / **扉固定スイッチ** tick（PR #195 以降）
4. **G4** — TODO ツール回数
5. **Issue #188** — adjacent 音、リン role 逸脱、`recipient_position`
6. **Issue #190** — 自己三人称、tick=20 プロンプトサンプル
7. **表 A** — 全イベントタイムライン
8. **表 B** — ツール呼び出し集計

Issue 投稿用の要約は `docs/experiments/templates/relay_puzzle_report_summary.md` をコピーして埋める。

---

## はまりどころ（必読）

### 1. `.env` の `OPENAI_API_BASE` がクラウド実行を壊す

`.env` に `OPENAI_API_BASE=http://127.0.0.1:8000/v1` があると、シェルで `LLM_MODEL=openai/gpt-5-mini` だけ変えても **vLLM に向く**。
クラウド実験時は **`OPENAI_API_BASE=` をコマンド先頭で明示的に空**にする。

### 2. vLLM のポート（リモート vs ローカル）

v108 **上**では vLLM は **8001**。Mac **上**では `v108-vllm` トンネル経由で **18001** にマップする。
`.env` の `OPENAI_API_BASE` は **18001** を指す（8001 は Cursor 等と競合しやすい）。

### 3. SSH トンネル

```bash
make vllm-tunnel    # または ssh -N v108-vllm &
make vllm-check
```

トンネルなしで `OPENAI_API_BASE=http://127.0.0.1:18001/v1` だけ設定すると **Connection refused**。

### 4. `ISSUE154_MAX_TICKS` と world tick のズレ

`ISSUE154_MAX_TICKS=30` は外側ループ回数。**表の tick は 50 前後まで進む**ことがある（`do_wait` / 移動ツール内の `advance_tick`）。
LOSE 条件はシナリオの `tick_limit: 50`（relay_puzzle_demo）。

### 5. WIN 前に打ち切り

30 駆動で WIN/LOSE に達しない場合、G1 は「未完了」。第 8 回 gpt-5-mini R1 のように tick 47 で打ち切られた例あり。
協調に時間がかかるモデルは `ISSUE154_MAX_TICKS` を増やすか、ログで途中経過を確認。

### 6. persona 名（PR #192 以降）

プレイヤー名は **カイト / リン**（旧 A/B ラベル廃止）。自己三人称検出も `カイトさん` / `リンさん` ベース。
旧レポートの「A（オペレーター）」表記とは互換のためスクリプト内マーカーに旧名も残している。

### 7. 正規解法（latch / PR #195）

メモに「扉固定スイッチ」の記述あり。期待フロー:

1. カイトが制御室で `power_on`
2. リンが金庫室へ → **扉固定スイッチ press**
3. カイトが合流 → 二人とも金庫室で WIN

第 7 回以前は latch なしのため R1 が早すぎる `power_off` で LOSE しやすかった。

### 8. Pydantic serializer warning

実行中に `CompletionTokensDetails` の UserWarning が出ることがある。**実行は継続可能**（第 8/9 回実験で確認済み）。

### 9. `var/` は git 管理外

レポート・ログはローカル `var/` に出力。共有は **Gist** または Issue コメント（`gh gist create`）。

### 10. 非決定性

同一条件でも LLM サンプリングで WIN/LOSE が変わる。比較は **同一 commit + 同一モデル + 複数回** を推奨。

---

## サーバ UI での実行（別経路）

FastAPI サーバ + ブラウザで tick loop を回す手順は `docs/demos/two_agent_world_issue.md`。
本実験スクリプトは **バッチ駆動**（`GameRuntimeManager` + フック）で、表形式レポート向け。

---

## trace 連携（PR #199 マージ後）

PR #199 の `JsonlTraceRecorder` が main に入ったら、ランナーに `--trace-out var/run.jsonl` を足す予定。
現時点（main @ PR #192/#195 マージ後）では Markdown レポートのみ。

---

## テスト

```bash
pytest tests/scripts/test_issue154_experiment_helpers.py -q
pytest tests/infrastructure/llm/test_litellm_client.py -q
```

実 LLM を呼ばない。ヘルパと `OPENAI_API_BASE` 経路のみ検証。

---

## 実験履歴との対応

詳細は [docs/experiments/relay_puzzle_run_history.md](experiments/relay_puzzle_run_history.md)。

| 回 | 主な条件 | R1 | R2 |
|----|----------|----|----|
| 第 10 回 | カイト/リン + latch, Gemma v108 | WIN (17) | WIN (17) |
| 第 7 回 | A/B, PR #191 | LOSE (52) | WIN (29) |
| 第 8 回 | gpt-5-mini クラウド | 未完了 | LOSE |
| 第 9 回 | gpt-5-nano クラウド | LOSE | LOSE |

Gist 一覧も run history に記載。
