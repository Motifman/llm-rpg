# Phase 12: Monster Policy Separation - Research

**Researched:** 2026-03-14
**Domain:** WorldSimulationService monster lifecycle / behavior rule extraction
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### Monster behavior の読み口
- monster behavior は「観測を作る → 状態を決める → 失敗を確定する → 行動を解く → 記録する」という一本道 coordinator として上から読める形を優先する。
- ただし coordinator が全判定を抱え込まないよう、pursuit failure と foraging は専任ルールとして coordinator から読める位置に分離する。
- `WorldSimulationService` facade は order coordinator のまま残し、Phase 12 の分離先は facade の外側で読める monster behavior 協調オブジェクト群とする。

### Survival / lifecycle の境界
- 飢餓死と老衰判定は behavior 側の gate から外し、spawn / respawn と同じ lifecycle 側の「生存進行」文脈へ寄せる。
- lifecycle は大きく `spawn系` と `survival系` の 2 つの読み口に分けたい。
- spawn と respawn は完全分離ではなく、同じ coordinator 内で「新規 spawn」と「既存個体の respawn」の分岐が見える形にする。
- survival では「生き延びる / 死ぬ / 餌を求めて移る」を近い文脈で読めるようにする。

### Pursuit failure の責務
- monster pursuit の失敗確定は action resolver の内部責務に吸収せず、behavior coordinator の前後から呼べる専任ルールとして分離する。
- `selected_target` 不在、`last_known` 到達、`TARGET_MISSING` / `VISION_LOST_AT_LAST_KNOWN` など、Phase 5 で固定した pursuit の意味づけを壊さない。
- Phase 12 では「どこで failure を確定するか」を読みやすくすることが主目的であり、monster pursuit の語彙自体は既存方針を引き継ぐ。

### Foraging の責務
- 餌の観測と選択は target context へ吸収せず、monster behavior から読める独立 foraging ルールとして切り出す。
- foraging は pursuit / combat と別の意図として読めることを優先する。
- behavior coordinator からは「foraging facts を作る」「foraging rule が target を返す」という関係が見える形を望む。

### Hunger migration policy の形
- Phase 12 の hunger migration policy は「候補選定ロジック」が単独で読めることを最優先にする。
- policy は repository 非依存とし、「飢餓が閾値以上」「嗜好する餌がない」「spot に餌がない」といった facts を入力として受け取る。
- 1 tick に 1 体、最も飢餓が高い個体を選ぶ判定を policy に閉じ込める。
- 同率時は新しい複雑な優先順位を増やさず、入力順や既存順を尊重する扱いでよい。
- 接続先の選び方は policy の主責務に含めず、Phase 12 では「誰を移住させるか」を中心に切り出す。

### Dependency boundary
- 判定は repository 非依存、適用だけ application 側依存、を Phase 12 の基本方針にする。
- map / repository / transition service を触る保存・配置変更は application / stage 側に残してよい。
- 完全な dependency inversion を目的化せず、「業務ルールが単体で読める」状態を優先する。

### Claude's Discretion
- coordinator / policy / rule / evaluator など最終命名
- foraging facts と pursuit facts を別 DTO にするか、より薄い値の束にするか
- lifecycle の中で starvation / old age / migration を 1 つの survival collaborator にまとめるか、近接した複数 rule にするか

### Deferred Ideas (OUT OF SCOPE)
- 飢餓移住の接続先選択ルールを賢くする改善
- monster action resolver 自体の大型再設計
- stage service / policy 単位テストの厚み付け全般
- 新しい monster behavior state や capability の追加
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WSPOL-01 | 飢餓移住の「1 tick に 1 体、最も飢餓が高い個体を移住させる」判定を repository 非依存の policy として抽出できる | `facts -> policy -> application apply` の 2 段分離、入力順 tie-break、`_process_hunger_migration_for_spot()` の candidate 選定だけを純粋化 |
| WSPOL-02 | モンスター lifecycle / behavior 周辺の業務ルールは、`WorldSimulationService` 本体から読める責務境界を持つ小さな協調オブジェクトへ移せる | lifecycle を `spawn/respawn` と `survival` に寄せ、behavior を一本道 coordinator + `foraging` + `pursuit failure` rule に整理 |
</phase_requirements>

## Summary

Phase 11 で `WorldSimulationService` は stage facade まで薄くなりましたが、monster 周辺の業務ルール本体はまだ callback 経由で本体 private helper に残っています。特に behavior は `観測作成 -> 遷移 -> pursuit failure 確定 -> action resolve -> record/save` が [`world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py) に直列で存在し、lifecycle は [`world_simulation_monster_behavior_stage_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py) の `_can_actor_act()` に starvation / old age が残っているため、責務境界がまだコード上で読み取りにくい状態です。

この phase の安全な分離単位は既に見えています。hunger migration は現在も `_process_hunger_migration_for_spot()` の中で「候補選定」と「map transition / save」が連続しているだけなので、前半を repository 非依存 policy に切り出しやすいです。behavior 側も `BehaviorStateTransitionService` 自体は純粋 service なので、その前後にある foraging と pursuit failure を専任 rule として切り出し、一本道 coordinator から順番に読む形にすれば、既存の tick order を崩さずに整理できます。

**Primary recommendation:** `WorldSimulationService` の callback を減らすのではなく、monster lifecycle / behavior stage が依存する collaborator を増やし、`判定は pure/facts-based・適用は stage/application` の境界で切り分ける。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `>=3.10` | 実装言語 | repo の runtime 前提 |
| pytest | `8.4.1` | phase の回帰テスト | 既存 suite がこれで統一 |
| `WorldSimulationMonsterLifecycleStageService` | repo current | lifecycle stage の entry | Phase 11 で固定済みの委譲境界 |
| `WorldSimulationMonsterBehaviorStageService` | repo current | behavior stage の entry | active spot / actor loop を既に担当 |
| `BehaviorStateTransitionService` | repo current | pure な状態遷移判定 | repository 非依存の既存実績がある |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `MonsterActionResolverImpl` | repo current | action resolve | pursuit failure 確定後の最終 action 決定点として維持 |
| `GatewayBasedConnectedSpotsProvider` | repo current | connected spot 解決 | hunger migration apply 側で行き先候補を得るとき |
| `MapTransitionService` | repo current | object placement 更新 | hunger migration apply の side effect に限定 |
| `InMemory*Repository` 群 | repo current | focused application tests | policy/unit ではなく orchestration test で使う |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pure policy + stage apply | repository-aware policy | 実装は短いが WSPOL-01 を満たせない |
| coordinator + small rules | action resolver への吸収 | 行動解決と失敗意味づけが混ざり、Phase 5 semantics を壊しやすい |
| lifecycle survival collaborator | behavior stage gate 維持 | starvation / old-age が behavior 側に残り WSPOL-02 不成立 |

**Installation:**
```bash
python -m pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/application/world/services/
├── world_simulation_monster_lifecycle_stage_service.py   # stage entry
├── world_simulation_monster_behavior_stage_service.py    # stage entry
├── monster_lifecycle_survival_coordinator.py             # starvation / old-age / migration orchestration
├── monster_behavior_coordinator.py                       # observe -> transition -> fail -> resolve -> record
├── hunger_migration_policy.py                            # pure candidate selection
├── monster_foraging_rule.py                              # feed facts -> selected feed target
└── monster_pursuit_failure_rule.py                       # pure-ish pursuit failure evaluation
```

### Pattern 1: Lifecycle は `spawn/respawn` と `survival` で読む
**What:** lifecycle stage は `spawn系` と `survival系` を並べる coordinator にし、starvation / old age / migration を behavior gate から外す。  
**When to use:** monster の生存進行が行動可否より先に決まる現在の tick 契約を保ちたいとき。  
**Example:**
```python
class MonsterLifecycleSurvivalCoordinator:
    def run_for_spot(self, physical_map, current_tick):
        self._progress_survival(physical_map, current_tick)
        self._apply_hunger_migration_if_needed(physical_map, current_tick)
```

### Pattern 2: Behavior は一本道 coordinator に固定する
**What:** behavior coordinator は `facts作成 -> observation -> transition -> pursuit failure -> resolve -> record` の順だけを持ち、細かな判定は rule へ委譲する。  
**When to use:** private helper を飛び回らずに phase の責務境界を読めるようにしたいとき。  
**Example:**
```python
class MonsterBehaviorCoordinator:
    def run_actor(self, actor, physical_map, current_tick):
        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster is None:
            return
        foraging = self._foraging_rule.evaluate(actor, physical_map, monster, current_tick)
        observation = self._observation_factory.build(actor, physical_map, current_tick, foraging)
        transition = self._transition_service.compute_transition(...)
        monster.apply_behavior_transition(transition, current_tick)
        failure = self._pursuit_failure_rule.evaluate_pre_action(monster, actor.coordinate, physical_map, observation)
        if failure is not None:
            return self._fail_and_save(monster, failure, current_tick)
        action = self._action_resolver_factory(physical_map, actor).resolve_action(monster, observation, actor.coordinate)
        failure = self._pursuit_failure_rule.evaluate_post_action(monster, actor.coordinate, observation, action)
        if failure is not None:
            return self._fail_and_save(monster, failure, current_tick)
        self._record_action(monster, action, current_tick)
```

### Pattern 3: Hunger migration は `facts -> policy -> apply`
**What:** candidate 選定だけ pure policy にし、connected spot / gateway / map transition は application 側 apply coordinator に残す。  
**When to use:** WSPOL-01 を満たしつつ既存の map side effect をそのまま活かしたいとき。  
**Example:**
```python
@dataclass(frozen=True)
class HungerMigrationCandidate:
    monster_id: object
    hunger: float
    forage_threshold: float
    has_preferred_feed: bool
    spot_has_feed: bool


class HungerMigrationPolicy:
    def select_migrant(self, candidates):
        eligible = [
            c for c in candidates
            if c.hunger >= c.forage_threshold
            and c.has_preferred_feed
            and not c.spot_has_feed
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda c: c.hunger)
```

### Anti-Patterns to Avoid
- **Rule extraction that still calls repositories:** policy / rule が `find_by_spot_id()` や `find_by_id()` を内部で叩くと、pure evaluation の旨味が消える。
- **Behavior coordinator that owns all if/else:** private helper を class move しただけで読み口が改善しない。
- **Resolver-centric pursuit failure:** `SEARCH at last-known` の failure semantics が action resolution の incidental behavior に埋もれる。
- **Generic policy framework:** この phase は monster 専用 rule の可読性改善で十分で、抽象化レイヤ追加は逆効果。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| behavior state transition | 新しい状態遷移エンジン | `BehaviorStateTransitionService` を継続利用 | 既に pure service 化されており、phase の主目的ではない |
| hunger migration selection | repository-aware evaluator | facts DTO + `HungerMigrationPolicy` | WSPOL-01 の repository 非依存条件を満たせる |
| pursuit failure meaning | action resolver 内の隠れ判定 | 専任 `MonsterPursuitFailureRule` | `TARGET_MISSING` / `VISION_LOST_AT_LAST_KNOWN` を明示維持できる |
| feed eligibility | 独自の item 判定 | `is_feed_for_monster()` + loot table lookup | 既存の餌判定 semantics を再利用できる |

**Key insight:** この phase で新規に作るべきなのは「汎用基盤」ではなく、「既存 helper 群の責務を読める形に並べ直す薄い協調オブジェクト」です。

## Common Pitfalls

### Pitfall 1: starvation / old age を behavior stage に残す
**What goes wrong:** lifecycle / behavior の境界が曖昧なままで、WSPOL-02 の成功条件を満たしにくい。  
**Why it happens:** `_can_actor_act()` が既に gate と死亡処理を一緒に持っているため、そこを入口に据え続けてしまう。  
**How to avoid:** behavior stage は `active_time` と busy 判定までに寄せ、死亡進行は lifecycle survival collaborator へ先出しする。  
**Warning signs:** `WorldSimulationMonsterBehaviorStageService` が `monster_repository.save()` と `process_sync_events()` を死亡理由ごとに持ち続けている。

### Pitfall 2: hunger migration policy に destination 選定まで含める
**What goes wrong:** policy が gateway / map repository に依存し始め、WSPOL-01 を満たせない。  
**Why it happens:** 現状 `_process_hunger_migration_for_spot()` が 1 メソッドで完結しているため、一括抽出したくなる。  
**How to avoid:** policy は migrant selection のみ、destination と transition は application apply に固定する。  
**Warning signs:** policy constructor に repository / provider / service が入る。

### Pitfall 3: pursuit failure を pre-action か post-action の片側だけに寄せる
**What goes wrong:** `TARGET_MISSING` と `VISION_LOST_AT_LAST_KNOWN` のどちらかが退行する。  
**Why it happens:** 現在の実装は `physical_map.get_object()` ベースの pre-action 判定と、`SEARCH` で move しない場合の post-action 判定に分かれている。  
**How to avoid:** 1つの rule object に `evaluate_pre_action()` と `evaluate_post_action()` を持たせる。  
**Warning signs:** `VISION_LOST_AT_LAST_KNOWN` の既存テストが落ちる、または resolver に failure enum が流れ込む。

### Pitfall 4: foraging を target context に混ぜる
**What goes wrong:** pursuit / combat / forage の意図が区別しづらくなる。  
**Why it happens:** observation build の入力数を減らしたくなるため。  
**How to avoid:** `visible_feed` と `selected_feed_target` を返す foraging rule を独立させ、behavior coordinator が observation に渡す。  
**Warning signs:** `TargetSelectionContext` が feed 情報を抱え始める。

## Code Examples

Verified patterns from current codebase:

### Hunger migration selection is already separable from apply
```python
for monster in monsters_on_spot:
    if monster.coordinate is None:
        continue
    if monster.hunger < monster.template.forage_threshold:
        continue
    if not monster.template.preferred_feed_item_spec_ids:
        continue
    if self._spot_has_feed_for_monster(physical_map, monster, current_tick):
        continue
    candidates.append(monster)
```
Source: [`world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L801)

### Pursuit failure has two distinct checkpoints today
```python
failure_reason = self._resolve_monster_pursuit_failure_reason(...)
action = resolver.resolve_action(monster, observation, actor.coordinate)
if self._should_fail_monster_search_at_last_known(...):
    monster.fail_pursuit(...)
```
Source: [`world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L515)

### Behavior transition is already a pure domain service
```python
transition_result = BehaviorStateTransitionService().compute_transition(
    observation=observation,
    snapshot=snapshot,
    actor_id=monster.world_object_id,
    actor_coordinate=actor.coordinate,
)
```
Source: [`world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L507)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `WorldSimulationService` private helper に monster rule を集約 | Phase 11 で stage facade 化し、Phase 12 で stage 内 collaborator 化するのが自然 | 2026-03-14 Phase 11 | facade の順序保証はそのまま、rule だけ外へ出せる |
| behavior stage が死亡 gate も担当 | lifecycle survival collaborator へ移すのが現 phase の正道 | Phase 12 target | lifecycle / behavior の責務境界が明示される |
| hunger migration が 1 method で候補選定から transition まで担当 | candidate selection を pure policy、apply を stage へ分離 | Phase 12 target | WSPOL-01 を直接満たせる |

**Deprecated/outdated:**
- `WorldSimulationMonsterBehaviorStageService._can_actor_act()` に starvation / old-age を置く構成: Phase 12 の責務境界とは不整合。
- `_process_hunger_migration_for_spot()` の monolithic 実装: WSPOL-01 観点では途中までしか分離されていない。

## Open Questions

1. **survival collaborator を 1 つにまとめるか**
   - What we know: starvation / old age / migration は同じ lifecycle 文脈に寄せる判断が固定している
   - What's unclear: 1 collaborator にするか、`death progress` と `migration` を分けるか
   - Recommendation: Phase 12 では 1 つの `MonsterLifecycleSurvivalCoordinator` にまとめ、内部 rule 分離で止める

2. **foraging facts と pursuit facts の DTO 粒度**
   - What we know: foraging は独立 rule、pursuit failure も独立 rule にしたい
   - What's unclear: 専用 DTO を2種類に分けるか、既存 object 群をそのまま渡すか
   - Recommendation: pure policy 化が必要な hunger migration 以外は、まず薄い引数束か dataclass で始めて DTO 増殖を避ける

3. **命名を `policy` と `rule` でどう分けるか**
   - What we know: hunger migration は repository 非依存で単独評価したいので `policy` が自然
   - What's unclear: foraging / pursuit failure を `rule` と呼ぶか `evaluator` と呼ぶか
   - Recommendation: `policy` は pure selection、`rule` は behavior coordinator の前後判定、と語彙を固定する

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 8.4.1` |
| Config file | `pytest.ini`, `pyproject.toml` |
| Quick run command | `pytest tests/application/world/services/test_hunger_migration.py -v` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSPOL-01 | highest-hunger single migrant is selected from pure facts and tie keeps input order | unit | `pytest tests/application/world/services/test_hunger_migration_policy.py -v` | ❌ Wave 0 |
| WSPOL-01 | selected migrant is transitioned by lifecycle apply path without changing external contract | integration | `pytest tests/application/world/services/test_hunger_migration.py -v` | ✅ |
| WSPOL-02 | behavior coordinator preserves pursuit failure semantics for `TARGET_MISSING` and `VISION_LOST_AT_LAST_KNOWN` | integration | `pytest tests/application/world/services/test_world_simulation_service.py -k "monster_search_at_last_known or monster_missing_target" -v` | ✅ |
| WSPOL-02 | lifecycle moves starvation / old-age handling out of behavior stage boundary | unit | `pytest tests/application/world/services/test_monster_lifecycle_survival_coordinator.py -v` | ❌ Wave 0 |
| WSPOL-02 | behavior coordinator reads linearly with foraging / pursuit failure collaborators | unit | `pytest tests/application/world/services/test_monster_behavior_coordinator.py -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/application/world/services/test_hunger_migration.py -v`
- **Per wave merge:** `pytest tests/application/world/services/test_world_simulation_service.py -k "monster or pursuit" -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/application/world/services/test_hunger_migration_policy.py` — covers WSPOL-01 pure selection semantics
- [ ] `tests/application/world/services/test_monster_behavior_coordinator.py` — covers coordinator sequencing and collaborator boundaries for WSPOL-02
- [ ] `tests/application/world/services/test_monster_lifecycle_survival_coordinator.py` — covers starvation / old-age / migration orchestration boundary for WSPOL-02

## Sources

### Primary (HIGH confidence)
- [`12-CONTEXT.md`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/.planning/phases/12-monster-policy-separation/12-CONTEXT.md) - locked decisions, discretion, deferred scope
- [`REQUIREMENTS.md`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/.planning/REQUIREMENTS.md) - WSPOL-01 / WSPOL-02 requirement text
- [`world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py) - current monster helper implementations and stage wiring
- [`world_simulation_monster_behavior_stage_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py) - current behavior gate and starvation / old-age placement
- [`world_simulation_monster_lifecycle_stage_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py) - current lifecycle stage entry
- [`behavior_state_transition_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py) - existing pure transition pattern
- [`test_hunger_migration.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/tests/application/world/services/test_hunger_migration.py) - current hunger migration and feed checks
- [`test_world_simulation_service.py`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/tests/application/world/services/test_world_simulation_service.py) - pursuit failure regression coverage
- [`pyproject.toml`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/pyproject.toml) - Python / pytest versions
- [`pytest.ini`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/pytest.ini) - active test config

### Secondary (MEDIUM confidence)
- [`STATE.md`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/.planning/STATE.md) - milestone continuity and current concerns
- [`ROADMAP.md`](/Users/minagawa/.codex/worktrees/81bc/ai_rpg_world/.planning/ROADMAP.md) - phase success criteria and dependency placement

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - repo-local config and existing stage/services/tests directly confirm it
- Architecture: MEDIUM - recommended collaborator split is inferred from current seams and locked decisions, not yet implemented
- Pitfalls: HIGH - each one maps to concrete current code paths and existing regression tests

**Research date:** 2026-03-14
**Valid until:** 2026-04-13
