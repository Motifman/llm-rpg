# relay_puzzle 実験 — 実行履歴と再現条件

Issue [#188](https://github.com/Motifman/llm-rpg/issues/188) の LLM 実走記録。
**再現手順の正本**は [running_scenarios.md](../running_scenarios.md)。

---

## 再現コマンド（第 10 回相当 — 現行 main 推奨）

```bash
make experiment-relay \
  OPENAI_API_BASE=http://127.0.0.1:8001/v1 \
  LLM_MODEL=openai/gemma-4-31b-it-nvfp4 \
  ISSUE154_MAX_TICKS=30 \
  EXPERIMENT_OUTPUT=var/experiment10_repro_report.md
```

前提: v108 vLLM が `8001` で listen、`gemma-4-31b-it-nvfp4` が served 名。

---

## 履歴表

| 回 | commit / PR 目安 | モデル | OPENAI_API_BASE | persona | 付記 | R1 | R2 |
|----|------------------|--------|-----------------|---------|------|----|----|
| 4 | Issue #154 系 | Gemma 31B v108 | :8001 | A/B | 初回ベースライン | WIN (37) | LOSE (55) |
| 5 | #182/#186/#187 | 同上 | :8001 | A/B | adjacent 音確認 | LOSE (50) | LOSE (52) |
| 6 | #190 speech suppress | 同上 | :8001 | A/B | 自己三人称激減 | LOSE (52) | LOSE (53) |
| 7 | #191 action_result | 同上 | :8001 | A/B | R2 初 WIN | LOSE (52) | **WIN (29)** |
| 8 | 同上 | **gpt-5-mini** | **空** | A/B | 口頭協調過多 | 未完了 (47) | LOSE (50) |
| 9 | 同上 | **gpt-5-nano** | **空** | A/B | 待機ループ | LOSE (59) | LOSE (54) |
| **10** | **#192/#194/#195** | Gemma 31B v108 | :8001 | **カイト/リン** + latch | 両 WIN 最短 | **WIN (17)** | **WIN (17)** |

---

## Gist / ローカル成果物

| 回 | Gist |
|----|------|
| 5 | https://gist.github.com/Motifman/cd8bfed63a9acec3817e02070da5a5f4 |
| 6 | https://gist.github.com/Motifman/a4ccd1e65455cad6c992ae66d39144e0 |
| 7 | https://gist.github.com/Motifman/c6e9277af35a38547ebc83216d442947 |
| 8 | https://gist.github.com/Motifman/f245c5a24364d3b9a0abe6207cf181ce |
| 9 | https://gist.github.com/Motifman/abefa936b62edfa194922c586fe6c4e6 |
| 10 | https://gist.github.com/Motifman/66aef959f30affdf0a8e4eb8d2c70320 |

ローカルレポート命名例: `var/issue188_experiment{N}_report.md`（gitignore）。

---

## 環境変数セット早見

### Gemma v108（第 5〜7, 10 回）

```bash
export OPENAI_API_BASE=http://127.0.0.1:8001/v1
export OPENAI_API_KEY=
export LLM_MODEL=openai/gemma-4-31b-it-nvfp4
export ISSUE154_MAX_TICKS=30
export ISSUE154_RUNS=R1_default,R2_pure
```

### OpenAI クラウド（第 8〜9 回）

```bash
export OPENAI_API_BASE=   # 空必須
export OPENAI_API_KEY=sk-...
export LLM_MODEL=openai/gpt-5-mini   # または gpt-5-nano
export ISSUE154_MAX_TICKS=30
export ISSUE154_RUNS=R1_default,R2_pure
```

---

## スクリプト改修履歴（Gemma ホスト側）

| 時期 | 内容 |
|------|------|
| Issue #188 第 5 回 | `ISSUE154_RUNS` フィルタ、#188 集計（recipient_position, adjacent 音, role 逸脱） |
| 第 6 回 | #190 自己三人称カウント、tick=20 プロンプトサンプル |
| 第 10 回 | カイト/リン マーカー、扉固定スイッチ tick（G3） |
| PR #200 対応 | リポジトリ取り込み、`make experiment-relay*`、本ドキュメント |
