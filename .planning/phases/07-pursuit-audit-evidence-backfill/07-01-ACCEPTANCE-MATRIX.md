---
phase: 07-pursuit-audit-evidence-backfill
plan: 01
status: approved
updated: 2026-03-11
requirements:
  - PURS-02
  - OUTC-03
  - RUNT-03
  - OBSV-01
  - PURS-03
  - PURS-04
  - PURS-05
  - RUNT-01
  - OBSV-02
  - OUTC-01
  - OUTC-02
  - RUNT-02
---

# Phase 07 Plan 01 Acceptance Matrix

Phase 7 fixes audit evidence gaps only. This matrix locks the final requirement-to-phase acceptance owner before any `VERIFICATION.md` backfill is written.

## Acceptance Rules

- `accepted_phase` is the phase whose verification artifact should be treated as the final audit acceptance source.
- `implementation_phase` records where the underlying behavior was primarily built when that differs from final acceptance.
- `dependency_note` is mandatory when current-codebase acceptance depends on a later runtime-closure phase.

## Requirement Ownership Matrix

| Requirement | accepted_phase | implementation_phase | acceptance_artifact | Status | dependency_note |
|-------------|----------------|----------------------|---------------------|--------|-----------------|
| PURS-02 | Phase 5 | Phase 5 | `05-monster-pursuit-alignment/VERIFICATION.md` | Accepted in Phase 5 after evidence backfill | Audit gap was verification-only; implementation and validation already existed in Phase 5. |
| OUTC-03 | Phase 4 | Phase 4 | `04-observation-and-llm-delivery/VERIFICATION.md` | Pending until 07-02 | Observation failure payload ownership stays with Phase 4. |
| RUNT-03 | Phase 4 | Phase 4 | `04-observation-and-llm-delivery/VERIFICATION.md` | Pending until 07-02 | Observation semantics for interruption boundaries stay with Phase 4. |
| OBSV-01 | Phase 4 | Phase 4 | `04-observation-and-llm-delivery/VERIFICATION.md` | Pending until 07-02 | Pipeline wiring ownership stays with Phase 4. |
| PURS-03 | Phase 6 | Phase 3 | `06-player-pursuit-runtime-assembly-closure/VERIFICATION.md` | Accepted in Phase 6 | Phase 3 built continuation logic, but current-codebase runtime acceptance requires Phase 6 bootstrap closure. |
| PURS-04 | Phase 6 | Phase 3 | `06-player-pursuit-runtime-assembly-closure/VERIFICATION.md` | Accepted in Phase 6 | Last-known continuation behavior is implemented in Phase 3 and accepted only after Phase 6 runtime closure. |
| PURS-05 | Phase 6 | Phase 2 | `06-player-pursuit-runtime-assembly-closure/VERIFICATION.md` | Accepted in Phase 6 | Explicit cancel entered in Phase 2, but live runtime exposure closed in Phase 6. |
| RUNT-01 | Phase 6 | Phase 3 | `06-player-pursuit-runtime-assembly-closure/VERIFICATION.md` | Accepted in Phase 6 | Integration with the authoritative runtime path is a Phase 6 closure concern. |
| OBSV-02 | Phase 6 | Phase 4 | `06-player-pursuit-runtime-assembly-closure/VERIFICATION.md` | Accepted in Phase 6 | Phase 4 supplies observation wiring; Phase 6 proves live runtime turn resumption. |
| OUTC-01 | Phase 1 | Phase 1 | `01-pursuit-domain-vocabulary` phase artifacts | Accepted in Phase 1 | Structured pursuit failure vocabulary is owned and already completed in Phase 1. |
| OUTC-02 | Phase 1 | Phase 1 | `01-pursuit-domain-vocabulary` phase artifacts | Accepted in Phase 1 | Lifecycle event publication is owned and already completed in Phase 1. |
| RUNT-02 | Phase 1 | Phase 1 | `01-pursuit-domain-vocabulary` phase artifacts | Accepted in Phase 1 | Pursuit state separation from static movement is a Phase 1 domain boundary. |

## Audit Notes

- Phase 3 `VERIFICATION.md` must describe Phase 3 as the implementation owner for continuation-loop behavior while explicitly deferring final current-codebase acceptance of `PURS-03`, `PURS-04`, and `RUNT-01` to Phase 6.
- Phase 5 `VERIFICATION.md` must mark `PURS-02` as passed because the remaining gap was documentation evidence, not incomplete behavior.
- Phase 7 plan `07-02` is responsible for closing the remaining Phase 4 rows in this matrix.
