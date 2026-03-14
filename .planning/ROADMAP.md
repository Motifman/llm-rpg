# Roadmap: AI RPG World

## Overview

現在の active milestone は `v1.2 World Simulation Service Refactoring` です。`WorldSimulationService` の巨大な tick 処理を、既存の順序保証と wiring 契約を壊さずに責務分割します。

## Phases

- [x] **Phase 11: Tick Facade Extraction** - `WorldSimulationService` を薄い facade に寄せ、主要な tick stage の委譲境界と順序契約を固定する
- [ ] **Phase 12: Monster Policy Separation** - monster lifecycle / behavior と飢餓移住ルールを読みやすい協調オブジェクトへ分離する
- [ ] **Phase 13: Simulation Regression Harness** - 分割後の world simulation を順序保証と小さな回帰テストの両面から守る

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 11. Tick Facade Extraction | 2/2 | Complete | 2026-03-14 |
| 12. Monster Policy Separation | 0/2 | Planned | - |
| 13. Simulation Regression Harness | 0/0 | Not started | - |

## Phase Details

### Phase 11: Tick Facade Extraction
**Goal**: `WorldSimulationService` が tick 全体の facade として残りつつ、主要な world progression stage を明確な委譲境界で実行できる
**Depends on**: Nothing
**Requirements**: WSIM-01, WSIM-02
**Success Criteria** (what must be TRUE):
1. `WorldSimulationService` の tick entry point から、環境処理・継続移動・採取完了・モンスター lifecycle・モンスター behavior・HitBox 更新が個別 stage service に委譲される
2. tick の実行順序が既存挙動と同じ契約で維持され、world progression の流れが分割前と同じ順番で進む
3. observation と LLM / reflection scheduling を含む副作用の発火タイミングが既存 runtime path と両立する
4. stage service の wiring 契約が明示され、並行進行中の `ToolArgumentResolver` 分割に依存せず world simulation だけで閉じて差し替えられる
**Plans**: 2 plans

Plans:
- [ ] 11-01-PLAN.md - facade の前半 stage composition を導入し、environment / movement / harvest を安全に委譲する
- [ ] 11-02-PLAN.md - active spot 以降の stage と post-tick wiring を抽出し、6-stage facade を完成させる

### Phase 12: Monster Policy Separation
**Goal**: monster lifecycle / behavior 周辺の業務ルールが、`WorldSimulationService` 本体から独立した policy / 協調オブジェクトとして読める
**Depends on**: Phase 11
**Requirements**: WSPOL-01, WSPOL-02
**Success Criteria** (what must be TRUE):
1. 飢餓移住の「1 tick に 1 体、最も飢餓が高い個体を移住させる」判定が repository 非依存の policy として単独で評価できる
2. monster lifecycle と monster behavior の業務ルールが、小さな協調オブジェクトを通して実行され、`WorldSimulationService` 本体から直接追わなくてよい
3. monster 関連の責務境界がコード上で判別でき、どのオブジェクトが spawn / respawn / hunger / behavior を扱うか利用者が読み取れる
4. 既存の monster tick 挙動が facade 経由で継続し、分割によって world simulation の外部契約が変わらない
**Plans**: 2 plans

Plans:
- [ ] 12-01-PLAN.md - pure hunger migration policy と monster behavior coordinator/rule を先に抽出する
- [ ] 12-02-PLAN.md - lifecycle survival 境界と hunger migration apply orchestration を facade 契約維持のまま整理する

### Phase 13: Simulation Regression Harness
**Goal**: world simulation の責務分割後も、順序保証と主要副作用を継続的に検証できる回帰テスト基盤を持つ
**Depends on**: Phase 12
**Requirements**: WSTEST-01, WSTEST-02
**Success Criteria** (what must be TRUE):
1. 既存の `WorldSimulationService` 統合テストが、分割後も主要な tick 順序と副作用を失わずに検証し続けられる
2. stage service / policy ごとの回帰テストを、巨大 fixture への過度な依存なしに追加できる
3. tick 順序保証と wiring 契約に関する退行点が、統合テストと小さな単位テストの両方で検知できる
4. 今後の world simulation 分割作業で、どこを壊したかを phase 完了時点で追跡できるテスト境界が揃う
**Plans**: TBD

## Coverage

| Requirement | Phase |
|-------------|-------|
| WSIM-01 | Phase 11 |
| WSIM-02 | Phase 11 |
| WSPOL-01 | Phase 12 |
| WSPOL-02 | Phase 12 |
| WSTEST-01 | Phase 13 |
| WSTEST-02 | Phase 13 |

**Coverage:** 6 / 6 requirements mapped

## Next Step

- `$gsd-execute-phase 12` - monster policy separation を wave 順で実装する

---
*Last updated: 2026-03-14 for milestone v1.2 World Simulation Service Refactoring*
