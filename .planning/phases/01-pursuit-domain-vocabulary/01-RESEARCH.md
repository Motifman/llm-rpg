# Phase 1: Pursuit Domain Vocabulary - Research

**Researched:** 2026-03-11
**Domain:** Python domain modeling for pursuit state and lifecycle events in the existing DDD-style aggregate/event architecture
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- v1 の pursuit は単一で中立な概念として定義する。
- `follow` / `chase` のようなニュアンス差は Phase 1 の語彙には入れず、後続フェーズまたは上位文脈で表現する。
- 味方追従と敵対追跡の違いも、Phase 1 では domain vocabulary に持ち込まない。
- 追跡中に対象を別主体へ切り替える場合は、既存 pursuit の更新ではなく「終了して新しい pursuit を開始する」扱いにする。
- `last_known` は補助情報ではなく pursuit state の中核情報として扱う。
- 対象そのものが消滅・退場・無効化されて追跡不能になったケースは、v1 では `target_missing` に統一する。
- 明示停止だけを `cancelled` として扱う。
- 別行動への切替や他原因の停止は、将来別理由や別イベントへ拡張できる余地を残す。
- 視界喪失後に最後の既知位置まで到達しても再捕捉できなかったケースは、`vision_lost_at_last_known` を独立した終了理由として維持する。
- 経路が引けない場合は、その時点で `path_unreachable` の即失敗として終了する。
- Phase 1 では pursuit の開始・更新・失敗・中断イベントを用意する。
- 開始イベントには actor / target だけでなく、開始時点の target 座標または last-known 情報も含める。
- 更新イベントは毎 tick ではなく、追跡判断に意味のある変化があった時だけ発行する。
- 失敗イベントには `failure_reason` に加えて、対象と最後の既知情報を含める。
- `cancelled` は failure の一種として吸収せず、失敗イベントとは明確に分ける。

### Claude's Discretion
- 開始イベントと更新イベントで使うフィールド名の具体形
- 「意味のある変化」の厳密な発火条件
- event class 名と enum/value object の最終命名

### Deferred Ideas (OUT OF SCOPE)
- `follow` / `chase` の mode 分化
- hostile / friendly など関係ラベルの導入
- 別行動への切替理由を `cancelled` 以外で細分化すること
- 高頻度の進行イベントや tick 単位の追跡テレメトリ
</user_constraints>

<research_summary>
## Summary

This phase should be planned as a pure domain-language phase, not a runtime-integration phase. The existing codebase already has two strong patterns to reuse: `PlayerStatusAggregate` stores mutable player movement state directly on the aggregate, and monster behavior emits explicit lifecycle events through small frozen dataclass event types. The planner should combine those two patterns: add pursuit state as a separate aggregate-held state object on player status, define structured pursuit outcome/value types, and define pursuit lifecycle events as standalone domain events.

The most important planning constraint is separation. Static movement today is encoded by `current_destination`, `planned_path`, and `goal_*` on `PlayerStatusAggregate`, and multiple services assume that shape. Pursuit state must not be folded into those fields in Phase 1. Instead, Phase 1 should introduce a separate pursuit vocabulary that later phases can map onto movement commands and tick updates.

The safest implementation direction is:
- add new pursuit value objects/enums/events under the domain layer
- attach pursuit state to `PlayerStatusAggregate` with defaulted optional fields
- avoid new repositories, services, or observation wiring in this phase
- write regression tests around state separation and event payload shape

**Primary recommendation:** Plan this phase around one aggregate extension plus a new pursuit event/value-object module, while keeping all new constructor fields optional and all runtime integration deferred.
</research_summary>

<standard_stack>
## Standard Stack

This phase does not need new third-party libraries. The standard stack is the repository’s existing domain modeling style.

### Core
| Library/Pattern | Current Use | Purpose | Why Standard Here |
|---------|---------|---------|--------------|
| Python `dataclass(frozen=True)` events | Widespread in `domain/*/event/*.py` | Immutable domain event payloads | Matches current event publisher and test patterns |
| Aggregate-held mutable state | `PlayerStatusAggregate`, `MonsterAggregate` | Persist domain state on aggregate instances | Reuses repository/UoW cloning behavior already in place |
| Small value objects / enums | `SpotId`, `WorldObjectId`, `BehaviorStateEnum` | Structured domain vocabulary | Keeps outcomes and target metadata explicit |
| `add_event(...)` on aggregate roots | `AggregateRoot` and all aggregates | Event emission | Existing UoW/event publishing flow depends on this |

### Supporting
| Existing Module | Purpose | When to Use |
|---------|---------|-------------|
| `src/ai_rpg_world/domain/player/event/status_events.py` | Style reference for player-side events | Use as naming and payload baseline |
| `src/ai_rpg_world/domain/monster/event/monster_events.py` | Style reference for lifecycle/behavior events | Use for pursuit started/updated/failed/cancelled event shape |
| `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py` | Natural home for player pursuit state | Extend here with optional/defaulted fields |
| `src/ai_rpg_world/application/world/services/movement_service.py` | Shows current static-movement contract | Use to protect separation boundaries, not to modify heavily in Phase 1 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend `PlayerStatusAggregate` | Create separate pursuit aggregate/repository | Over-architected for Phase 1 and adds unnecessary persistence/wiring work |
| Separate pursuit event module | Reuse monster `TargetSpottedEvent`/`TargetLostEvent` | Too monster-specific and misses required cancelled/failed vocabulary |
| Structured pursuit outcome enum/value object | Raw strings/messages | Violates OUTC-01 and weakens later LLM/observation consumers |
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/domain/
├── pursuit/
│   ├── enum/ or value_object/   # failure/cancel reasons and pursuit state vocabulary
│   └── event/                   # pursuit lifecycle events
├── player/aggregate/            # attach player-side pursuit state here
└── monster/                     # unchanged in Phase 1, but existing behavior events are the model
```

### Pattern 1: Aggregate-owned state, event-defined lifecycle
**What:** Keep durable state on the aggregate, and express lifecycle milestones through immutable domain events.
**When to use:** When the phase introduces a new domain concept that later application services will consume.
**Use here:** `PlayerStatusAggregate` should own pursuit state; lifecycle changes should emit pursuit events.

### Pattern 2: Optional constructor growth on hot aggregates
**What:** Add new aggregate fields with safe defaults so existing tests, fixtures, and repositories remain stable.
**When to use:** When a heavily-instantiated aggregate gains new domain fields.
**Use here:** `PlayerStatusAggregate` is constructed in about 50 places across `src/` and `tests/`; new pursuit fields must be optional.

### Pattern 3: Explicit payloads for future consumers
**What:** Events should carry enough context that later handlers do not need to re-query basic facts.
**When to use:** When later phases will feed observation or LLM replanning.
**Use here:** started/updated/failed/cancelled events should include actor, target, and last-known snapshot data.

### Anti-Patterns to Avoid
- **Overloading static movement fields:** Do not reinterpret `current_destination`, `planned_path`, or `goal_*` as pursuit state. Those fields already drive destination movement semantics.
- **Modeling `cancelled` as a failure reason:** User context explicitly separates cancelled from failure.
- **Premature runtime wiring:** Do not plan event handler registry changes, observation formatter work, or tick-driven pursuit logic into this phase.
- **Adding required constructor arguments:** This will create broad fixture churn for little planning value.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Event infrastructure | New publisher/registry mechanics | Existing `BaseDomainEvent` + `AggregateRoot.add_event(...)` | The repo already has a working event publication path |
| Aggregate persistence model | Separate persistence DTOs or custom serializers | Existing in-memory repository clone/save flow | Current repositories deep-clone aggregates and already persist added fields |
| Free-form pursuit outcomes | Ad hoc strings | Enum/value object for structured reasons | Future observation and LLM phases need stable machine-readable outcomes |
| Monster chase vocabulary reuse | Generic wrapper around monster chase/search state | New pursuit vocabulary module | Monster behavior semantics are related but not equivalent to required pursuit outcomes |

**Key insight:** The codebase already has the right building blocks. Planning should reuse them, not introduce new infrastructure.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Conflating pursuit with destination movement
**What goes wrong:** Pursuit gets stored in `planned_path`/`goal_*`, so a later movement interruption implicitly destroys pursuit state.
**Why it happens:** Static movement is currently the only player movement model, so it is tempting to extend it in place.
**How to avoid:** Introduce a distinct pursuit state object/field on the aggregate and test that clearing movement path does not equal clearing pursuit state.
**Warning signs:** New pursuit code only touches `set_destination`, `clear_path`, or `advance_path`, with no separate pursuit fields.

### Pitfall 2: Under-specifying event payloads
**What goes wrong:** Failed/cancelled events only carry a reason string or target id, forcing later phases to re-query basic context.
**Why it happens:** Existing monster events like `TargetSpottedEvent` are minimal and observation wiring is deferred.
**How to avoid:** Define a shared last-known snapshot or explicit fields that started/updated/failed events can all carry.
**Warning signs:** Event names exist but payloads do not include actor, target, and last-known state together.

### Pitfall 3: Constructor and fixture breakage
**What goes wrong:** Adding required pursuit args to `PlayerStatusAggregate` forces widespread updates across tests and unrelated services.
**Why it happens:** `PlayerStatusAggregate` is widely instantiated directly.
**How to avoid:** Use optional/defaulted fields and helper methods for pursuit lifecycle changes.
**Warning signs:** The plan includes changing every test fixture before any domain behavior exists.

### Pitfall 4: Naming that blocks later monster integration
**What goes wrong:** Pursuit types are named too player-specific or too tied to friendly/enemy semantics.
**Why it happens:** Immediate implementation pressure from the player use case.
**How to avoid:** Keep the Phase 1 vocabulary neutral: actor, target, last-known, failure reason, cancelled.
**Warning signs:** Type names or enum members mention `follow`, `enemy`, `ally`, or `monster-only` semantics.

### Pitfall 5: Pulling Phase 4 work into Phase 1
**What goes wrong:** The planner starts adding observation recipients, formatter prose, or LLM re-drive logic now.
**Why it happens:** OUTC-02 mentions events, and the repo already has observation registries.
**How to avoid:** Limit the phase to domain event definitions and aggregate emission capability; wiring remains deferred.
**Warning signs:** Plan tasks touch `observation_formatter.py`, recipient strategies, or event handler registries.
</common_pitfalls>

<code_examples>
## Code Examples

### Pattern: Player aggregate stores movement state separately from location state
Source: `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py`

```python
def set_destination(
    self,
    destination: Coordinate,
    path: List[Coordinate],
    goal_destination_type: Optional[Literal["spot", "location", "object"]] = None,
    goal_spot_id: Optional[SpotId] = None,
    goal_location_area_id: Optional[LocationAreaId] = None,
    goal_world_object_id: Optional[WorldObjectId] = None,
) -> None:
    self._current_destination = destination
    self._planned_path = path
    self._goal_destination_type = goal_destination_type
    self._goal_spot_id = goal_spot_id
    self._goal_location_area_id = goal_location_area_id
    self._goal_world_object_id = goal_world_object_id
```

Planning implication: pursuit needs its own analogous state slot, not reuse of these fields.

### Pattern: Monster lifecycle emits explicit behavior events from aggregate methods
Source: `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`

```python
self.add_event(
    TargetSpottedEvent.create(
        aggregate_id=self._world_object_id,
        aggregate_type="Actor",
        actor_id=self._world_object_id,
        target_id=params.target_id,
        coordinate=params.coordinate,
    )
)
```

Planning implication: pursuit lifecycle events should be emitted from aggregate methods in the same style.

### Pattern: Domain events are small frozen dataclasses
Source: `src/ai_rpg_world/domain/player/event/status_events.py`

```python
@dataclass(frozen=True)
class PlayerLocationChangedEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    old_spot_id: Optional[SpotId]
    old_coordinate: Optional[Coordinate]
    new_spot_id: SpotId
    new_coordinate: Coordinate
```

Planning implication: pursuit events should follow the same dataclass convention and keep payloads explicit.
</code_examples>

<sota_updates>
## State of the Art (Project-Local)

This phase is not about an external ecosystem that changed recently. The relevant “current approach” is the codebase’s present internal architecture.

| Older Temptation | Current Best Fit | Impact |
|--------------|------------------|--------|
| Hide pursuit inside existing movement path | Separate pursuit state on aggregate | Preserves RUNT-02 and avoids semantic leakage |
| Express stop/failure as prose strings | Use enum/value object + explicit events | Supports later observation/LLM consumers |
| Model pursuit only from player needs | Keep vocabulary neutral across actor types | Leaves room for monster integration in Phase 5 |
</sota_updates>

<open_questions>
## Open Questions

1. **Where should the new module live?**
   - What we know: `PlayerStatusAggregate` is the natural player integration point, but pursuit is conceptually cross-actor.
   - What's unclear: whether the repo prefers `domain/pursuit/...` or attaching all types under `domain/player/...` first.
   - Recommendation: Plan a short design decision early. Favor `domain/pursuit/...` for neutral vocabulary, then reference it from player/monster code later.

2. **What exact shape should `last_known` take?**
   - What we know: user context says it is core state, not auxiliary data.
   - What's unclear: whether it should be a dedicated value object or repeated `spot_id`/`coordinate`/`seen_tick` fields.
   - Recommendation: Plan a single value object if at least three fields are needed. Otherwise keep explicit fields now and refactor later only if duplication appears.

3. **Should failure reasons and cancellation reasons be separate types?**
   - What we know: `cancelled` must not be absorbed into failure.
   - What's unclear: whether that means two enums/value objects or one failure enum plus a dedicated cancelled event with no reason enum.
   - Recommendation: Keep failure reasons as one enum/value object and use a separate cancelled event. Only introduce a dedicated cancellation-reason enum if planning already identifies multiple cancel causes.

4. **Which aggregate should emit pursuit events first?**
   - What we know: success criteria only require the events to exist in the domain.
   - What's unclear: whether Phase 1 should also add emission helper methods on player status now, or only define event classes and state fields.
   - Recommendation: Plan at least lightweight player-side aggregate methods for start/update/fail/cancel so the vocabulary is exercised by tests, but do not wire services yet.
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- `.planning/phases/01-pursuit-domain-vocabulary/01-CONTEXT.md` - locked user decisions and scope boundaries
- `.planning/REQUIREMENTS.md` - phase requirement mapping for OUTC-01, OUTC-02, RUNT-02
- `.planning/STATE.md` - current blockers and project-level constraints
- `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py` - existing player movement state model
- `src/ai_rpg_world/application/world/services/movement_service.py` - current static movement contract and path clearing behavior
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py` - existing lifecycle-event emission pattern
- `src/ai_rpg_world/domain/monster/event/monster_events.py` - event dataclass conventions for actor lifecycle
- `src/ai_rpg_world/domain/player/event/status_events.py` - player event naming and payload conventions
- `src/ai_rpg_world/domain/common/domain_event.py` and `src/ai_rpg_world/domain/common/aggregate_root.py` - base event and aggregate semantics
- `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py` - evidence that observation wiring is separate and partial today
- `src/ai_rpg_world/application/observation/services/recipient_strategies/monster_recipient_strategy.py` - evidence that some monster events are intentionally unwired for recipients today

### Secondary (HIGH confidence, project scan)
- `rg` scan across `src/` and `tests/` - `PlayerStatusAggregate(...)` appears in about 50 call sites, confirming constructor-change risk

### Project Guidance Check
- `CLAUDE.md`: not present
- `.claude/skills/`: not present
- `.agents/skills/`: not present
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Python domain aggregates, value objects, and events
- Ecosystem: existing repo architecture only
- Patterns: aggregate state separation, event dataclasses, player/monster modeling conventions
- Pitfalls: state conflation, payload under-specification, fixture churn, premature wiring

**Confidence breakdown:**
- Standard stack: HIGH - entirely based on current repository conventions
- Architecture: HIGH - supported by direct aggregate/service/event reads
- Pitfalls: HIGH - directly inferred from current movement/event code and aggregate usage count
- Code examples: HIGH - drawn from repository source files

**Research date:** 2026-03-11
**Valid until:** Until the repository significantly changes its aggregate/event conventions
</metadata>

---
## RESEARCH COMPLETE
