# Phase 11: Tick Facade Extraction - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

`WorldSimulationService` を world tick 全体の facade として残しつつ、既存の順序保証と runtime wiring 契約を壊さない形で stage 委譲境界を明確化する。Phase 11 では tick coordinator の薄型化と stage service の導入方針を固めるのであり、飢餓移住 policy の本格抽出や stage 単位テストの厚み付けは後続 phase に委ねる。

</domain>

<decisions>
## Implementation Decisions

### Stage boundary
- Phase 11 の目標粒度は 6-stage split とし、環境処理、継続移動、採取完了、monster lifecycle、monster behavior、HitBox 更新を個別 stage として扱う。
- ただし Phase 11 の実装は一気に完全分離するのではなく、既存 private method と既存順序を活かした incremental 移行で進める。
- stage service 導入は将来の細分化余地を残しつつ、まず facade から責務の束を読み取れる状態を優先する。

### Facade responsibility
- `WorldSimulationService` は Phase 11 で order coordinator として寄せ、tick entry point、unit of work 境界、順序制御、エラー変換を主責務として残す。
- active spot 集約や tick 中の各 stage 呼び出し順は facade に残してよいが、個別の業務処理本体は stage 側へ委譲する前提で整理する。
- facade は world simulation 全体の公開契約を維持し、既存 wiring から見た差し替え先として残す。

### Migration style
- 導入方針は behavior-safe incremental を優先し、既存の private method や helper を足場にして段階的に stage service へ移す。
- 新しい stage API に一気に寄せる clean cut refactor は Phase 11 の目的にしない。
- wrapper 的な橋渡しは許容するが、最終的に「どこが coordinator で、どこが stage 本体か」が読める構造まで持っていく。

### Regression focus
- Phase 11 の最優先回帰契約は `pursuit continuation -> movement` の順序、observation の発火タイミング、LLM / reflection scheduling を含む wiring 契約とする。
- monster behavior や HitBox の広範な再整理は Phase 11 の主眼ではなく、順序と facade 契約を守るために必要な範囲で扱う。
- Phase 11 の検証は「分割後も tick coordinator の外部挙動が変わらない」ことを示す観点を優先する。

### Placement and packaging
- 新しい stage service 群は Phase 11 では `application/world/services/` 直下に置く。
- `simulation/` のような subpackage への再編は、分割対象の輪郭が安定してから後続 phase で再検討する。

### Claude's Discretion
- 各 stage service の具体的な命名 (`EnvironmentTickService` など) と constructor shape
- 既存 private helper をそのまま移設するか、薄い orchestrator helper を挟むか
- active spot 集約や map 再取得処理を facade に残すか、補助 coordinator に分けるかの細部

</decisions>

<specifics>
## Specific Ideas

- 「6-stage split を最終形の目印にしつつ、Phase 11 は安全な incremental step にする」という進め方を優先する。
- `WorldSimulationService` は薄い facade に寄せたいが、順序制御と公開契約は維持したい。
- stage service の配置は最初から大きく reorganize せず、既存 `application/world/services/` の流儀に合わせたい。
- Phase 11 では policy 抽出や test deepening を広げすぎず、まず tick coordinator の輪郭を安定させる。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`: 既存 private method 群 (`_advance_pending_player_movements`, `_complete_due_harvests`, `_process_spawn_and_respawn_by_slots`, `_update_hit_boxes`) が incremental な stage 抽出の足場になる。
- `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py`: Phase 3 で world tick 前段に統合した順序契約を守るうえで、player movement 前処理の既存 seam として再利用できる。
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py`: monster behavior stage の責務境界を考える際の既存 integration point になる。

### Established Patterns
- application service は `application/world/services/` 直下に置かれており、既存の命名・配置規約に合わせる方がこの phase では自然。
- world tick にはすでに「weather sync → pending player movement → actor behaviors」の順序前提があり、Phase 3 の pursuit 継続判定もその前後関係に依存している。
- aggregate / domain service / application service の分担は既存 DDD 風構成に沿う必要があり、Facade は orchestration に寄せるのが全体方針と整合する。

### Integration Points
- `WorldSimulationService` の constructor で受けている `movement_service`, `pursuit_continuation_service`, `llm_turn_trigger`, `reflection_runner` は順序契約と wiring 契約の重要接点。
- `tests/application/world/services/test_world_simulation_service.py` の順序系テストと `tests/application/llm/test_llm_wiring_integration.py` の wiring 前提が、Phase 11 の回帰 guard になる。
- monster lifecycle / behavior や hunger migration は将来的にさらに分かれるが、Phase 11 では facade から見える stage 境界として先に整理する。

</code_context>

<deferred>
## Deferred Ideas

- 飢餓移住 policy の repository 非依存な本格抽出
- stage service / policy 単位のテスト厚み付け
- `application/world/services/simulation/` のような subpackage への再編
- monster lifecycle / behavior のより深い責務分離

</deferred>

---

*Phase: 11-tick-facade-extraction*
*Context gathered: 2026-03-14*
