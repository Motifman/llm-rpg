# 実験設定管理

この文書は、LLM 実験の起動条件を再現可能に保つための仕様書です。
判断の背景は [docs/design_decisions.md](./design_decisions.md) の「28. 実験に意味を持つ設定は profile/config だけから入れる」を参照してください。

## 目的

実 LLM を使う実験は時間と費用がかかるため、あとから「何を変えた run だったのか」を復元できなければ比較が壊れます。このリポジトリでは、実験に意味を持つ設定を profile/config に集約し、run 成果物へ入力値と解決済み値を保存します。

## 原則

1. 実験挙動を変える値は `data/experiment_profiles/*.json` または `--experiment-config` の `runtime_config` だけから入れる。
2. `LLM_*`、`SEMANTIC_*`、`BELIEF_*`、`GOAL_*` などの実験設定を環境変数から読む経路は作らない。
3. 環境変数で許すのは、`OPENAI_API_KEY` などの秘密情報と、サーバのホスト/ポート、ローカル DB パスのような実行基盤の値だけに限る。
4. 起動時に `ResolvedLlmRuntimeConfig` を 1 度だけ作り、以後はその解決済み設定を引数で渡す。
5. 新しい実験設定を足す PR は、設定 DTO、profile、成果物、配線テストを同時に更新する。

## 入力形式

標準 profile は `data/experiment_profiles/*.json` に置きます。

```json
{
  "profile": "smoke_stub",
  "description": "実 LLM を呼ばずに profile / fail-fast / manifest 配線を確認する低コスト smoke run。",
  "scenario": "data/scenarios/survival_island_v3_coop.json",
  "max_world_ticks": 2,
  "snapshot_save": false,
  "runtime_config": {
    "LLM_CLIENT": "stub",
    "LLM_EPISODIC_ENABLED": false,
    "SHORT_TERM_MEMORY_KIND": "sliding_window"
  }
}
```

`runtime_config` のキーは、`ResolvedLlmRuntimeConfig` が受け付けるキーだけです。未知のキーや秘密値の混入は起動時に失敗させます。

任意の一時設定は `--experiment-config path/to/config.json` で渡します。`--profile` と `--experiment-config` は同時に使えません。

## 起動方法

普段使いの本命 run:

```bash
make experiment EXPERIMENT_PROFILE=belief_goal_full OUT=var/runs/example_001
```

低コストの配線確認:

```bash
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-smoke
```

比較用の差分 run:

```bash
make experiment EXPERIMENT_PROFILE=ablation_base OUT=var/runs/example_ablation_001
```

`SCENARIO`、`MAX_WORLD_TICKS`、`OUT`、`SNAPSHOT_LOAD_DIR`、`SNAPSHOT_SAVE_DIR` は実験 driver の起動条件として上書きできます。上書き結果は成果物へ保存されます。

## 成果物

`scripts/run_scenario_experiment.py` は run ディレクトリに次を保存します。

- `experiment.config.source.json`: profile/config の入力 JSON。秘密値は伏せる。
- `experiment.config.resolved.json`: 解決済みの実験条件。scenario、tick 数、snapshot 入出力、git 情報、`ResolvedLlmRuntimeConfig.to_trace_dict()` の値を含む。
- `trace.jsonl`: 先頭の `run_start` に解決済み設定と `experiment_manifest_sha256` を書く。
- `report.md`: 実験の要約。
- `trace.html`: 解析用 HTML。`--no-html` のときは作らない。
- `progress.jsonl`: 進捗ログ。`--no-progress-jsonl` のときは作らない。

git 情報には commit、branch、dirty 状態、dirty file 一覧、dirty diff の sha256 を残します。dirty diff 本文は保存していないため、完全再現を最優先する run は clean tree で始めてください。

## 標準 profile

- `belief_goal_full`: 普段の本命観察 run。episodic / semantic / belief / prediction / goal / stagnation を有効にする。
- `ablation_base`: `belief_goal_full` から `STAGNATION_REASONING_ENABLED` だけを落とした比較土台。
- `smoke_stub`: 実 LLM を呼ばず、設定解決・成果物・配線だけを確認する低コスト run。

標準 profile の追加・変更は、比較の土台を変える行為です。PR では「何を測るための profile か」「どの既存 profile と比較するか」「既定値を変える理由」を本文に書いてください。

## 新しい実験設定を足す手順

1. `ResolvedLlmRuntimeConfig` にフィールド、入力キー、検証、`to_trace_dict()` 出力を足す。
2. profile/config から `ResolvedLlmRuntimeConfig.from_mapping(...)` へ渡ることをテストする。
3. 実 runtime へ `create_world_runtime(..., config=cfg)` または同等の引数で渡し、下位層で環境変数を読ませない。
4. 機能が有効なとき、必要な部品が構築される配線テストを足す。
5. 機能が無効なとき、誘うだけ誘って捨てる状態にならないことをテストする。
6. 効果測定に必要な trace / metrics が出ることをテストする。
7. 必要なら `data/experiment_profiles/*.json` を更新する。

## 禁止事項

- 実験設定のために `os.environ` を直接読む。
- profile/config の値を process env に書き戻して下位層へ渡す。
- 「後方互換」のために環境変数入力を復活させる。
- API キーを profile/config や成果物に平文で保存する。
- 新機能だけを足して、観測 trace と metrics を後回しにする。

## 残っている課題

実験設定の単一入口と成果物保存は入っていますが、実験管理としてはまだ次が残っています。

- 実験計画の台帳: 「どの profile を baseline とし、何を 1 つだけ変えるか」を run 前に記録する仕組み。
- 比較単位の固定: `belief_goal_full` と `ablation_base` のような対を、run group として明示する仕組み。
- trace / metrics の要求表: 機能ごとに「効果測定に必須の trace イベントと metrics」を一覧化し、run 前に欠落を検出する仕組み。
- PR チェックリスト: 新しい実験機能の PR に、設定追加、fail-fast、配線テスト、metrics 配線、profile 更新の確認欄を入れること。
- dirty tree の完全再現: 現状は dirty diff の sha256 だけを残す。必要なら patch 本文も成果物に保存するか、実 LLM run は clean tree 必須にする。
- 実験結果の索引: `var/runs` 配下の manifest を集め、profile、commit、scenario、主要設定、結果を検索できる一覧を作ること。
