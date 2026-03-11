# Feature Research

**Domain:** Actor pursuit/follow behavior in an LLM-driven RPG world
**Researched:** 2026-03-11
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Start pursuit/follow for players and monsters | Core action the feature exists to provide | MEDIUM | Must target moving actors, not static destinations only |
| Explicit stop/cancel pursuit | Pursuit without cancellation is operationally unsafe | LOW | Should clear pursuit state separately from raw path state |
| Last-known-position handling after visibility loss | Natural expectation for chasing a moving target | MEDIUM | Continue to last known position, then stop with structured reason |
| Structured failure reasons | Needed for LLM replanning and debugging | MEDIUM | At minimum: `target_missing`, `path_unreachable`, `vision_lost_at_last_known`, `cancelled` |
| Event-driven pursuit lifecycle | Fits current app model and user expectation for AI reaction | MEDIUM | Start / update / fail / cancel should all be eventable |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Follow mode vs chase mode semantics | Lets ally follow and hostile pursuit share a base model | MEDIUM | Good candidate for v1 vocabulary, not full behavior richness |
| Reacquisition heuristics beyond last known position | Makes pursuit feel smarter | HIGH | Defer until base pursuit works cleanly |
| Group/formation following | Better party feel | HIGH | Not needed to validate core pursuit loop |
| Predictive interception / speed matching | More realistic chase behavior | HIGH | Overkill for equal-speed v1 actors |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Guaranteed catch-up | Sounds like “successful pursuit” | Breaks under equal-speed actors and hides useful state | Treat continuous pursuit as valid, not failure |
| Generic support for every entity/NPC type | Feels future-proof | Blurs scope and requires extra modeling with weak payoff | Limit v1 to players and monsters |
| LLM manually issuing follow every turn | Seems flexible | Bypasses existing movement persistence and creates prompt brittleness | Use domain state plus events |
| Continuous steering/physics follow | Feels game-like | Conflicts with current tick/path-based movement model | Reuse path-based stepping |

## Feature Dependencies

```
Pursuit Start/Stop
    └──requires──> Pursuit State Model
                           └──requires──> Failure Reason Vocabulary

Pursuit Continuation
    └──requires──> Existing Movement Tick Flow
                           └──requires──> Last-Known-Position Refresh

Pursuit Failure Events
    └──requires──> Observation / LLM Trigger Wiring
```

### Dependency Notes

- **Pursuit commands require pursuit state:** without explicit state, moving-target behavior collapses into stale paths
- **Continuation requires tick integration:** follow/chase should be advanced by the world loop, not ad hoc background logic
- **Failure events require observation wiring:** otherwise LLM agents cannot react to pursuit outcomes consistently

## MVP Definition

### Launch With (v1)

- [ ] Start pursuit for player or monster against a moving actor
- [ ] Continue moving toward the target’s latest known position using existing movement/path rules
- [ ] On visibility loss, continue only to last known position
- [ ] Stop with a structured reason when the target is missing, unreachable, lost at last known position, or explicitly cancelled
- [ ] Emit pursuit lifecycle events usable by the observation/LLM loop

### Add After Validation (v1.x)

- [ ] Mode-specific interruption policy (`pause`, `resume`, `stop`) — once real pursuit behavior is observed
- [ ] Better reacquisition/search logic — once simple last-known-position pursuit proves insufficient
- [ ] Unify monster and player reason vocabularies further — once both paths are implemented

### Future Consideration (v2+)

- [ ] Formation following / party spacing — defer until single-target pursuit is stable
- [ ] Predictive interception — defer until speed and terrain modeling demand it
- [ ] NPC-generalized pursuit — defer until NPC concepts are clearer in the domain

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Pursuit start/stop | HIGH | MEDIUM | P1 |
| Last-known-position continuation | HIGH | MEDIUM | P1 |
| Structured failure reasons | HIGH | MEDIUM | P1 |
| Observation/LLM event wiring | HIGH | MEDIUM | P1 |
| Rich search heuristics | MEDIUM | HIGH | P2 |
| Formation/predictive chase | LOW | HIGH | P3 |

## Competitor Feature Analysis

| Feature | Competitor A | Competitor B | Our Approach |
|---------|--------------|--------------|--------------|
| Follow behavior | Party-follow systems keep state until cancelled | Enemy AI chases until loss/aggro reset | Use persistent pursuit state and explicit cancellation |
| Lost-target handling | Last seen position is common | Hard reset to idle is common | Go to last known position, then emit reasoned stop |
| Failure semantics | Often implicit or UI-only | Often buried in AI state | Promote reasons to domain events for LLM consumption |

## Sources

- `.planning/PROJECT.md`
- `src/ai_rpg_world/application/world/services/movement_service.py`
- `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py`
- `src/ai_rpg_world/domain/world/service/behavior_service.py`
- `src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py`
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py`
- `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py`

---
*Feature research for: actor pursuit/follow*
*Researched: 2026-03-11*
