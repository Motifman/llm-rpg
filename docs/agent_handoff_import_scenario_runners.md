# 他エージェントへの依頼: シナリオ実行関連一式の取り込み

このドキュメントは、**Gemma ホスト (vLLM 実行 PC) 上で動いている別エージェント**に対する依頼書です。
こちら側 (メイン開発機) の `llm-rpg` リポジトリには、シナリオ実行用のランナー / Makefile / .env / レポートテンプレが揃っていません。Gemma ホスト側にそれらの正本があるはずなので、PR として持ってきてもらうことで実行方法を一本化します。

## 背景

- メイン開発機 (このリポジトリ) は実装と単体テストの場所。`pytest` は走るが、長尺シナリオの実 LLM 実行ができない
- Gemma ホストは Gemma 4 31B を vLLM で serve しており、`make` や bash スクリプトで G1 (relay_puzzle 等) を回している
- 第 7〜10 回実験はすべて Gemma ホスト側で走っており、結果だけが Gist / Issue コメントとしてこちらに届いている状態
- これでは **実行コードがメインリポジトリにバージョン管理されておらず、他人 (および将来の自分) が再現できない**

## ゴール

Gemma ホスト側で実際に使われているシナリオ実行関連ファイルをすべて llm-rpg リポジトリに取り込み、`git clone && make ...` だけで同じ実験を走らせられる状態にする。

## 取り込み対象 (例)

Gemma ホスト側の作業ディレクトリ (おそらく `~/ghq/github.com/Motifman/llm-rpg/` または近い場所) から、以下に該当するものをすべて見つけて PR に含める:

### 必須

- [ ] `Makefile` ターゲット (例: `make relay-r1`, `make relay-r2`, `make escape-game`, `make experiment-g1` など、シナリオを走らせる系すべて)
- [ ] `scripts/` 配下のシナリオランナー (例: `scripts/run_relay_puzzle.py`, `scripts/experiment_g1.sh`, `scripts/issue154_runner.py` 等)
- [ ] `.env.example` の追記 (vLLM / LiteLLM 接続情報 — `OPENAI_API_BASE`, `OPENAI_API_KEY`, `LLM_CLIENT`, `LLM_MODEL`, etc.)
- [ ] `var/` 配下の **テンプレ** だけ (実レポート本体は除外 — `var/issue188_experiment10_report.md` のような確定済みは別途扱う)

### 推奨

- [ ] レポート整形用テンプレ (`var/report_template.md` 等があれば)
- [ ] 既知の Gist と対応する run 設定の対応表 (どの環境変数で第 X 回が再現できるか)
- [ ] README / docs にシナリオ実行手順を追記 (例: `docs/running_scenarios.md`)

### 取り込まない

- 機密情報を含む `.env` 本体
- Gemma の重み / vLLM サーバ設定 (本リポジトリのスコープ外)
- 一時的なログファイル (`var/runs/*.jsonl` の具体的なファイル, etc.)
- `__pycache__` / `.venv` 等の生成物

## PR を作る手順

1. Gemma ホスト側で **最新の `main`** から `feat/import-scenario-runners` ブランチを切る
2. 上記対象ファイルを `git add` する
3. **このリポジトリにも既に存在するファイル** (例: `scripts/demo_llm_prompt_inspection.py` のように両方にあるもの) は **差分を取って統合**。Gemma 側にだけある変更が捨てられないように注意
4. `.env` 本体 / 秘密鍵 / 個人ホームパス (`/Users/<your-name>/...`) が混入していないか確認
5. `pytest -q` を走らせて全部緑のまま (新しいスクリプトが既存テストを壊さない)
6. PR タイトル: `feat: Gemma ホスト側のシナリオ実行関連 (Makefile / script / .env / docs) を取り込む`
7. PR 本文に以下を含める:
   - **取り込んだファイルの一覧** (find . -newer などで確認)
   - **各スクリプトの簡単な説明** (どのコマンドが第何回相当か)
   - **手動で merge した箇所** (両方に存在していたファイルの差分整理)
   - **環境変数の一覧** (何を設定すれば走るか)

## こちら側との整合性

メインリポジトリで既に PR #197 (memo system) / #198 (fuzzy hint) / #199 (trace 基盤) が動いています。**PR #199 の `JsonlTraceRecorder` を取り込んだランナーに inject すれば、即座に第 11 回以降の実験で trace.jsonl を残せます。** 余力があれば、ランナーに trace recorder を `--trace-out` オプションで挿せるようにしてもらえると助かります (任意)。

## やりとり

質問があれば issue #188 にコメントしてください。こちら側で先回りで確認できる事は確認します。
