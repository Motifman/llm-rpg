# AI RPG World

## What This Is

LLMエージェントがプレイヤーとして行動するテキストRPGワールド管理システムです。v1.0 では pursuit 基盤を完成させ、v1.1 ではその上にスキル管理と戦闘判断を進めるための LLM ツール群を拡張します。

## Core Value

LLMエージェントが、ワールド状態とイベント駆動の文脈を踏まえて、自律的に次の行動を安全に選べること。

## Requirements

### Validated

- ✓ pursuit domain vocabulary, continuation, observation delivery, live runtime closure — v1.0

### Active

- [ ] LLM がスキル装備・進化提案の意思決定・覚醒発動をツール経由で行える
- [ ] skill 系ツールがラベル解決と availability 判定により安全に提供される
- [ ] 覚醒モード発動は LLM が「発動するか」を決め、コストや持続時間はサーバ側設定で確定する

### Out of Scope

- pursuit の follow/chase 差分拡張 — v1.1 は skill tooling に集中するため
- 隊列追従や複数主体制御 — skill 系ツールの導線を先に固めるため
- 覚醒モードの細かい数値調整を LLM に委ねる設計 — 実行時の安全性と一貫性を優先するため

## Current Milestone: v1.1 LLM Skill Tooling

**Goal:** LLM が skill loadout・進化提案・覚醒モードを既存 runtime 文脈の中で安全に操作できるようにする。

**Target features:**
- `skill_equip` で習得済みスキルを loadout slot に装備できる
- `skill_accept_proposal` / `skill_reject_proposal` で進化提案の意思決定を行える
- `skill_activate_awakened_mode` で覚醒発動を判断できる
- skill 系ツール用の runtime targets / argument resolution / availability を整える

## Context

- v1.0 で pursuit foundation は完了し、LLM runtime wiring・observation delivery・verification artifact まで閉じている
- `SkillCommandService` には `equip_player_skill(...)`、`accept_skill_proposal(...)`、`reject_skill_proposal(...)`、`activate_player_awakened_mode(...)` が既に存在する
- 既存 LLM ツール基盤は `tool_definitions.py`、`tool_argument_resolver.py`、`world_executor.py`、`ui_context_builder.py` でカテゴリ別に拡張する構造になっている
- 現状は `combat_use_skill` だけが skill 系ツールとして露出しており、proposal や loadout slot を表す runtime target は未整備
- 覚醒モード command は内部実行パラメータを受け取れるが、v1.1 では LLM に発動判断のみを委ね、数値はサーバ側で決める

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

---
*Last updated: 2026-03-12 after starting milestone v1.1 LLM Skill Tooling*
