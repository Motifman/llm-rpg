# AI RPG World

## What This Is

LLMエージェントがプレイヤーとして行動するテキストRPGワールド管理システムです。v1.0 では pursuit 基盤を完成させ、v1.1 ではその上にスキル管理と戦闘判断を進めるための LLM ツール群を拡張しました。

## Core Value

LLMエージェントが、ワールド状態とイベント駆動の文脈を踏まえて、自律的に次の行動を安全に選べること。

## Current State

- Shipped milestones:
  - v1.0 Pursuit Foundation
  - v1.1 LLM Skill Tooling
- Current status:
  - LLM は `skill_equip`、`skill_accept_proposal`、`skill_reject_proposal`、`skill_activate_awakened_mode` を既存 runtime 文脈上で安全に実行できる
  - skill 系ツールの runtime labels、canonical argument resolution、availability gating、default wiring、observation/runtime proof まで閉じている
  - v1.1 milestone audit は `passed` で、planning artifacts は archive 済み

## Next Milestone Goals

- 次に狙う価値を定義し、`$gsd-new-milestone` で fresh requirements を作る
- 候補としては pursuit 拡張、group control、または skill/awakened 周辺の richer behavior がある
- 既知の横断的負債として async event failure visibility の改善余地を意識する

## Requirements

### Validated

- ✓ pursuit domain vocabulary, continuation, observation delivery, live runtime closure — v1.0
- ✓ skill runtime context, label-driven skill tools, equip/proposal execution, awakened runtime proof — v1.1

### Out of Scope Candidates

- pursuit の follow/chase 差分拡張
- 隊列追従や複数主体制御
- 覚醒モードの細かい数値調整を LLM に委ねる設計

## Constraints

- **Tech stack**: 既存の Python レイヤード/DDD 風構成を維持する — skill 系ユースケースも既存 service / repository / event の流れに乗せる
- **Architecture**: ドメインイベント駆動を維持する — tool 実行結果は既存 observation pipeline に接続する
- **Safety**: LLM には生の内部パラメータを極力渡さない — label 解決とサーバ側デフォルトで誤操作を減らす
- **Scope**: v1.1 は skill tooling に集中する — pursuit 拡張や隊列制御は後続へ送る
- **Quality**: runtime path と verification artifact まで含めて閉じる — tool 定義だけで終わらせない

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| pursuit 基盤は v1.0 でいったん閉じる | 次の価値は skill 意思決定の自動化にあるため | ✓ Good |
| skill ツールは人間向けラベルから canonical id へ解決する | LLM に raw id や slot index の判断を強制しないため | ✓ Good |
| 覚醒モードは LLM が発動判断のみを行う | コストや持続時間はゲームルールとして一貫させるため | ✓ Good |
| proposal / loadout / awakened availability は runtime context で明示する | 無効な skill 操作を prompt で避けるだけにしないため | ✓ Good |

## Archived Context

<details>
<summary>v1.0 summary</summary>

v1.0 では、プレイヤー/モンスター両方が共有できる pursuit vocabulary、プレイヤー追跡開始/中断、world tick での継続追跡、observation/LLM delivery、monster alignment、live runtime assembly、audit evidence backfill までを 7 phases / 19 plans で完了した。

</details>

<details>
<summary>v1.1 summary</summary>

v1.1 では、Phase 8-10 の 3 phases / 10 plans で skill runtime labels、tool contracts、equip/proposal execution、awakened activation、hidden-first availability、default wiring proof、observation/runtime confirmation を完成させた。

</details>

---
*Last updated: 2026-03-13 after archiving milestone v1.1*
