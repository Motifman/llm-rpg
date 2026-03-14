# AI RPG World

## What This Is

LLMエージェントがプレイヤーとして行動するテキストRPGワールド管理システムです。v1.0 では pursuit 基盤を完成させ、v1.1 ではその上にスキル管理と戦闘判断を進めるための LLM ツール群を拡張しました。

## Core Value

LLMエージェントが、ワールド状態とイベント駆動の文脈を踏まえて、自律的に次の行動を安全に選べること。

## Current State

- Shipped milestones:
  - v1.0 Pursuit Foundation
  - v1.1 LLM Skill Tooling
  - v1.2 World Simulation Service Refactoring
- Current status:
  - LLM は `skill_equip`、`skill_accept_proposal`、`skill_reject_proposal`、`skill_activate_awakened_mode` を既存 runtime 文脈上で安全に実行できる
  - skill 系ツールの runtime labels、canonical argument resolution、availability gating、default wiring、observation/runtime proof まで閉じている
  - v1.1 milestone audit は `passed` で、planning artifacts は archive 済み
  - `WorldSimulationService` は 6-stage facade・monster policy/coordinator 分離・contract-oriented regression harness を備えた状態で shipped 済み
  - 現在は次 milestone の定義待ちで、fresh な requirements/roadmap はまだ未作成

## Next Milestone Goals

- `MOVE-01`: `MovementService` の目的地解決・継続移動・到着判定を独立した service / policy に分割する
- `TARG-01`: `ToolArgumentResolver` を tool family ごとの小さな resolver 群へ分割する
- `MAP-01`: `PhysicalMapAggregate` の trigger / interaction / harvest 責務を分離する

## Requirements

### Validated

- ✓ pursuit domain vocabulary, continuation, observation delivery, live runtime closure — v1.0
- ✓ skill runtime context, label-driven skill tools, equip/proposal execution, awakened runtime proof — v1.1

### Active

- 次 milestone の requirements は未定義。`$gsd-new-milestone` で fresh な `.planning/REQUIREMENTS.md` を作成する

### Out of Scope Candidates

- ToolArgumentResolver の分割 — 別ブランチで並行進行中のため v1.2 には含めない
- pursuit の follow/chase 差分拡張 — 新機能追加であり、今回の service 分割とは別問題
- 隊列追従や複数主体制御 — world simulation の構造整理後に再評価する
- 覚醒モードの細かい数値調整を LLM に委ねる設計 — v1.1 の shipped scope 外であり本 milestone の目的ではない

## Constraints

- **Tech stack**: 既存の Python レイヤード/DDD 風構成を維持する — skill 系ユースケースも既存 service / repository / event の流れに乗せる
- **Architecture**: ドメインイベント駆動を維持する — tool 実行結果は既存 observation pipeline に接続する
- **Safety**: LLM には生の内部パラメータを極力渡さない — label 解決とサーバ側デフォルトで誤操作を減らす
- **Scope**: v1.2 は `WorldSimulationService` の責務分割に集中する — ToolArgumentResolver や他の大型リファクタリングは別ストリームで扱う
- **Quality**: runtime path と verification artifact まで含めて閉じる — tool 定義だけで終わらせない
- **Compatibility**: tick 順序と副作用の既存挙動を維持する — world progression / monster AI / observation / LLM scheduling の退行を避ける

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| pursuit 基盤は v1.0 でいったん閉じる | 次の価値は skill 意思決定の自動化にあるため | ✓ Good |
| skill ツールは人間向けラベルから canonical id へ解決する | LLM に raw id や slot index の判断を強制しないため | ✓ Good |
| 覚醒モードは LLM が発動判断のみを行う | コストや持続時間はゲームルールとして一貫させるため | ✓ Good |
| proposal / loadout / awakened availability は runtime context で明示する | 無効な skill 操作を prompt で避けるだけにしないため | ✓ Good |
| v1.2 は `WorldSimulationService` 単体の責務分割に絞る | 並列進行中の ToolArgumentResolver リファクタリングと衝突させず、最優先負債へ集中するため | ✓ Complete |

## Archived Context

<details>
<summary>v1.0 summary</summary>

v1.0 では、プレイヤー/モンスター両方が共有できる pursuit vocabulary、プレイヤー追跡開始/中断、world tick での継続追跡、observation/LLM delivery、monster alignment、live runtime assembly、audit evidence backfill までを 7 phases / 19 plans で完了した。

</details>

<details>
<summary>v1.1 summary</summary>

v1.1 では、Phase 8-10 の 3 phases / 10 plans で skill runtime labels、tool contracts、equip/proposal execution、awakened activation、hidden-first availability、default wiring proof、observation/runtime confirmation を完成させた。

</details>

<details>
<summary>v1.2 summary</summary>

v1.2 では、Phase 11-13 の 3 phases / 6 plans で `WorldSimulationService` の 6-stage facade 化、monster policy/coordinator 分離、contract-oriented world simulation regression harness を完成させた。milestone audit は `passed` で、requirements 6/6・integration 3/3・flows 3/3 を満たした。

</details>

---
*Last updated: 2026-03-14 after archiving milestone v1.2*
