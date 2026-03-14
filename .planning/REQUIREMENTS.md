# Requirements: AI RPG World

**Defined:** 2026-03-14
**Core Value:** LLMエージェントが、ワールド状態とイベント駆動の文脈を踏まえて、自律的に次の行動を安全に選べること

## v1.2 Requirements

### Tick Orchestration

- [x] **WSIM-01**: `WorldSimulationService` は tick 全体の facade として残り、環境処理、継続移動、採取完了、モンスター lifecycle、モンスター behavior、HitBox 更新を専用の stage service に委譲できる
- [x] **WSIM-02**: tick の実行順序と副作用は既存挙動と両立し、world progression・observation・LLM / reflection scheduling の回帰を起こさない

### Domain Policy Extraction

- [x] **WSPOL-01**: 飢餓移住の「1 tick に 1 体、最も飢餓が高い個体を移住させる」判定を repository 非依存の policy として抽出できる
- [x] **WSPOL-02**: モンスター lifecycle / behavior 周辺の業務ルールは、`WorldSimulationService` 本体から読める責務境界を持つ小さな協調オブジェクトへ移せる

### Regression Harness

- [x] **WSTEST-01**: `WorldSimulationService` の既存統合テストは責務分割後も主要な tick 順序と副作用を検証し続けられる
- [x] **WSTEST-02**: 分離した stage service / policy 単位で、巨大 fixture に依存しすぎない回帰テストを追加できる

## vNext Requirements

### Adjacent Refactors

- **MOVE-01**: `MovementService` の目的地解決・継続移動・到着判定を独立した service / policy に分割する
- **TARG-01**: `ToolArgumentResolver` を tool family ごとの小さな resolver 群へ分割する
- **MAP-01**: `PhysicalMapAggregate` の trigger / interaction / harvest 責務を分離する

## Out of Scope

| Feature | Reason |
|---------|--------|
| ToolArgumentResolver の分割 | 別ブランチで並行進行中のため、本 milestone に含めると衝突リスクが高い |
| MovementService の責務分割 | World simulation と隣接するが、同一 milestone に入れると完了条件が広がりすぎる |
| pursuit / group control の新機能追加 | 今回は新機能ではなく既存ワールド進行の内部構造改善に集中する |
| LLM skill / awakened 系の追加改善 | v1.1 で shipped 済みの領域であり、今回の最優先リファクタリング対象ではない |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| WSIM-01 | Phase 11 | Satisfied |
| WSIM-02 | Phase 11 | Satisfied |
| WSPOL-01 | Phase 12 | Satisfied |
| WSPOL-02 | Phase 12 | Satisfied |
| WSTEST-01 | Phase 13 | Satisfied |
| WSTEST-02 | Phase 13 | Satisfied |

**Coverage:**
- v1.2 requirements: 6 total
- Mapped to phases: 6
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 after v1.2 milestone audit*
