# Roadmap: AI RPG World

## Overview

現在のロードマップは進行中マイルストーン v1.1 のみを保持し、完了済みマイルストーンの詳細はアーカイブへ置きます。

## Archived Milestones

- [x] **v1.0: Pursuit Foundation** - shipped 2026-03-12, 7 phases / 19 plans / 58 tasks, archive: `.planning/milestones/v1.0-ROADMAP.md`

## Current Milestone

### Milestone v1.1: LLM Skill Tooling

**Goal:** LLM が skill loadout・進化提案・覚醒モードを既存 runtime 文脈の中で安全に操作できるようにする
**Status:** In progress
**Phases:** 8-10

### Phase 8: Skill Runtime Context And Tool Contracts

**Goal**: skill 系ツールを LLM に安全に見せるための runtime target・tool definition・argument resolution を整える
**Depends on**: v1.0 runtime and observation foundation
**Requirements**: `SKRT-01`, `SKTL-02`
**Status:** Complete (2026-03-12)
**Plans:** 4 plans
Plans:
- [x] `08-00-PLAN.md` — Nyquist Wave 0 として不足しているテストアンカーを追加する
- [x] `08-01-PLAN.md` — skill runtime read models と typed runtime target DTO を整える
- [x] `08-02-PLAN.md` — UI label 表示と label-to-canonical argument resolution を追加する
- [x] `08-03-PLAN.md` — public tool names / schemas / availability / available-tools coverage を閉じる
**Success criteria:**
1. proposal・装備候補・slot・awakened action に対応する runtime labels が UI context で表現される
2. `skill_equip` などの新規ツール定義が label-driven contract を持つ
3. invalid label や不整合な target kind が tool argument resolution で拒否される

### Phase 9: Skill Equip And Proposal Decision Tools

**Goal**: LLM が装備変更と進化提案の受諾/却下を行えるようにする
**Depends on**: Phase 8
**Requirements**: `SKTL-01`, `SKPR-01`, `SKPR-02`
**Status:** Planned
**Plans:** 3 plans
Plans:
- [ ] `09-01-PLAN.md` — skill equip / proposal decision の facade と world executor 実行経路を接続する
- [ ] `09-02-PLAN.md` — proposal target の slot-aware display 情報と Phase 9 成功文面を確定する
- [ ] `09-03-PLAN.md` — mapper / wiring / runtime path 回帰で Phase 9 ツール群の統合を証明する
**Success criteria:**
1. LLM が `skill_equip` で候補スキルを指定 slot に装備できる
2. LLM が pending proposal を受諾でき、必要な loadout 反映まで完了する
3. LLM が pending proposal を却下でき、進化提案状態が正しく更新される
4. 成功/失敗結果が既存 tool 実行結果と整合する

### Phase 10: Awakened Mode Tooling And Runtime Proof

**Goal**: 覚醒モード発動を LLM tool として公開し、runtime path で安全性と観測結果を確認する
**Depends on**: Phase 9
**Requirements**: `SKAW-01`, `SKAW-02`, `SKAW-03`, `SKRT-02`
**Success criteria:**
1. `skill_activate_awakened_mode` が内部パラメータを LLM に要求せず発動できる
2. リソース不足・既に覚醒中・loadout 不整合などの条件では tool が非表示または失敗理由付きで拒否される
3. 覚醒発動結果が observation / runtime flow 上で確認できる
4. LLM wiring を通る統合テストで skill 系ツール群が共存する

## Next Step

- `$gsd-discuss-phase 9` — skill equip / proposal execution の context を固める
- `$gsd-plan-phase 9` — Phase 9 の実装計画を作る

---
*Last updated: 2026-03-12 after creating milestone v1.1 roadmap*
