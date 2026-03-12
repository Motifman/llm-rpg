# Phase 8: Skill Runtime Context And Tool Contracts - Research

**Researched:** 2026-03-12
**Domain:** LLM skill runtime context, tool contracts, and label-to-canonical argument resolution
**Confidence:** HIGH

## User Constraints

### Locked Decisions
- 装備系は action-first とし、装備候補スキルラベルと装備先 slot ラベルを分けて出す
- `skill_equip` は分離されたラベル同士を組み合わせて canonical args へ解決する
- 進化提案は proposal 1件につき 1 ラベルを出し、`accept` / `reject` の両方から同じ proposal label を使う
- slot は通常デッキと覚醒デッキを分けた tiered slot として見せる
- 覚醒モードは発動可能時のみ単一 action label を出す

### Tool contract expectations
- 既存の `combat_use_skill` と同じく、人間向けラベルから内部 ID を解決する contract を維持する
- LLM には raw `skill_id` や `slot_index` を直接選ばせない
- 覚醒モードは「発動するか」の意思決定のみを tool contract に含め、数値パラメータは含めない

### Availability expectations
- Phase 8 の段階で availability 設計の土台を入れ、後続フェーズで具象化しやすいようにする
- proposal・slot・awakened action は runtime context に存在しない場合、対応 tool は候補に出せない前提で設計する

### Claude's Discretion
- proposal / slot / awakened action 用の label prefix 命名
- UI context 上での補助文言や並び順
- 既存 `ToolRuntimeTargetDto` を拡張するか、専用 DTO を足すかの実装方針

### Deferred Ideas (OUT OF SCOPE)
- equip 候補を「スキルと slot の組み合わせ済みラベル」で見せる案
- 覚醒モードを loadout ごとに選ばせる案
- pursuit follow/chase 差分や group control など v1.1 外の機能拡張

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKRT-01 | skill 系 tool runtime context は proposal・equip slot・装備候補・awakened action の判断に必要なラベル候補を提供できる | `PlayerCurrentStateDto` と supplemental builder に新しい skill read-model DTO 群を追加し、`DefaultLlmUiContextBuilder` で labels + runtime targets を同時生成する |
| SKTL-02 | `skill_equip` は人間向けラベルから `loadout_id` / `deck_tier` / `slot_index` / `skill_id` を解決して実行できる | `DefaultToolArgumentResolver` に skill-specific kind validation を追加し、skill candidate label と slot label の組み合わせから canonical args を返す |

## Summary

このフェーズは新しい skill 実行そのものではなく、既存 LLM tooling 基盤の上に skill 系 read model と label contract を増設するフェーズとして切るのが正しいです。現状の実装は `usable_skills -> K* label -> combat_use_skill` という 1 本の skill 導線だけが完成しており、同じ構造で `proposal label`、`equip candidate label`、`slot label`、`awakened action label` を追加すれば、後続フェーズは executor 側に薄く接続するだけで済みます。

既存パターンでは `PlayerCurrentStateDto` が availability 判定の材料を持ち、`DefaultLlmUiContextBuilder` が画面文言と `ToolRuntimeContextDto.targets` を一緒に組み立て、`DefaultToolArgumentResolver` が tool ごとに label kind を検証して canonical args に解決します。この分業は Phase 8 の要求と一致しているため、別系統の skill runtime container を新設するより、world current-state の補助 read model を skill 系に拡張する方が整合的です。

**Primary recommendation:** `PlayerCurrentStateDto` と `ToolRuntimeTargetDto` ファミリを skill 専用 read model で拡張し、`skill_equip` / `skill_accept_proposal` / `skill_reject_proposal` / `skill_activate_awakened_mode` の contract を既存 `combat_use_skill` と同じ label-driven resolver パターンで追加する。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | >=3.10 | 実装言語 | 既存コードベース全体が dataclass 中心の Python レイヤード構成 |
| pytest | 8.4.1 | テスト実行 | LLM / world / skill 系の既存テスト基盤が統一済み |
| pydantic | 2.8.2 | 周辺構成の validation | 既存依存に含まれるが、この phase の中心は dataclass DTO |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| coverage | 7.9.2 | 変更影響の確認 | phase gate 前の回帰確認 |
| litellm | 1.44.9 | LLM client backend | この phase では tool schema 提供側との整合確認のみ |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `PlayerCurrentStateDto` を拡張 | 別 skill runtime context DTO を並立 | builder / availability / prompt wiring の分岐が増え、既存 LLM パターンから外れる |
| `ToolRuntimeTargetDto` 継承追加 | 単一 `kind` 文字列 + 汎用フィールドだけで押し切る | resolver の型安全が落ち、invalid kind rejection のテスト粒度が弱くなる |
| label-driven resolver | raw ids を tool params に直接公開 | 要件違反。LLM に内部 ID を選ばせることになる |

**Installation:**
```bash
python -m pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/
├── application/world/contracts/dtos.py                  # skill runtime read model DTO を追加
├── application/world/services/player_supplemental_context_builder.py
├── application/llm/contracts/dtos.py                    # skill target DTO を追加
├── application/llm/services/ui_context_builder.py       # label text + runtime target 生成
├── application/llm/services/tool_definitions.py         # tool schema と availability 登録
├── application/llm/services/tool_argument_resolver.py   # label -> canonical args
└── application/llm/services/executors/world_executor.py # Phase 8 では原則据え置き、後続接続点だけ確認
```

### Pattern 1: Current-State First Read Model
**What:** runtime labels の元データは `PlayerCurrentStateDto` に集約し、builder はその DTO から text と targets を同時生成する。
**When to use:** availability と UI text が同じデータ源を共有すべき skill tool。
**Example:**
```python
# Source: src/ai_rpg_world/application/world/services/player_current_state_builder.py
return PlayerCurrentStateDto(
    ...,
    usable_skills=self._supplemental_context_builder.build_usable_skills(query.player_id),
    ...
)
```

### Pattern 2: Typed Runtime Targets Per Label Family
**What:** label は `ToolRuntimeTargetDto` 派生 DTO として持ち、resolver 側は `isinstance` で kind を強制する。
**When to use:** 同じ文字列 label でも tool ごとに期待する対象種別が異なる場合。
**Example:**
```python
# Source: src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
skill = self._require_target_type(
    skill_label,
    runtime_context,
    "スキルラベル",
    (SkillToolRuntimeTargetDto,),
)
```

### Pattern 3: Availability Uses Read-Model Presence, Not Business Logic Duplication
**What:** tool visibility は current-state に候補があるかどうかで判定し、詳細バリデーションは resolver / application service に任せる。
**When to use:** proposal, slot, awakened action のように「候補がなければ出さない」が主契約の tool。
**Example:**
```python
# Source: src/ai_rpg_world/application/llm/services/availability_resolvers.py
class CombatUseSkillAvailabilityResolver(IAvailabilityResolver):
    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and bool(context.usable_skills)
```

### Recommended Skill Runtime DTO Split
Use explicit read models on the world side:

- `EquipableSkillCandidateDto`
- `SkillEquipSlotDto`
- `PendingSkillProposalDto`
- `AwakenedActionDto`

Use explicit runtime target DTOs on the LLM side:

- `SkillEquipCandidateToolRuntimeTargetDto`
- `SkillEquipSlotToolRuntimeTargetDto`
- `SkillProposalToolRuntimeTargetDto`
- `AwakenedActionToolRuntimeTargetDto`

This is preferable to overloading `SkillToolRuntimeTargetDto`, because Phase 8 needs different canonical payloads:

- equip candidate label resolves `skill_id`
- slot label resolves `loadout_id` + `deck_tier` + `slot_index`
- proposal label resolves `progress_id` + `proposal_id`
- awakened action label resolves `loadout_id` only

### Label Prefix Recommendation

| Label family | Prefix | Reason |
|--------------|--------|--------|
| equip candidate skill | `EK` | visually close to existing `K*` while distinguishing from combat-usable skill |
| equip slot | `ES` | slot labels need different selection semantics from skill labels |
| pending proposal | `SP` | avoids collision with `S*` destination labels and makes skill proposal explicit |
| awakened action | `AW` | one-shot action label, readable in prompt text |

### UI Ordering Recommendation
Present skill-related sections after `使用可能スキル` and before quest/guild/shop sections:

1. `スキル装備候補`
2. `装備先スロット`
3. `保留中スキル提案`
4. `覚醒モード`

This keeps all skill decisions adjacent while preserving the current builder’s coarse ordering.

### Anti-Patterns to Avoid
- **Combined equip labels:** do not pre-compose skill+slot into one label. It violates the locked action-first decision and explodes label count.
- **Raw integer passthrough:** do not add `skill_id`, `slot_index`, or `proposal_id` as public tool params.
- **Duplicated availability logic in executor:** tool visibility should come from read-model presence, not ad hoc checks scattered in executor code.
- **Overloading `SkillToolRuntimeTargetDto`:** equip candidate, proposal, combat skill, and awakened action have different canonical payload shapes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| label parsing | prefix string slicing in executor | `DefaultToolArgumentResolver` + typed runtime target lookup | existing pattern already centralizes invalid-label rejection |
| skill visibility rules | bespoke tool-by-tool booleans detached from current state | `PlayerCurrentStateDto` presence-based availability | keeps prompt text, runtime labels, and available tool list consistent |
| proposal state cache | separate in-memory LLM-only proposal store | read from `SkillDeckProgressAggregate.pending_proposals` via supplemental builder | avoids stale proposal labels after accept/reject |
| awakened numeric input | duration/cooldown/MP fields in tool schema | single action label resolving to server-side defaults later | matches locked constraint and prevents unsafe tuning |

**Key insight:** this phase should only expose enough structured state for safe LLM choice. The domain/application layers for execution already exist; duplicating or bypassing them would create two incompatible skill systems.

## Common Pitfalls

### Pitfall 1: Mixing Combat Skill Labels With Equip Candidate Labels
**What goes wrong:** `K1`-style combat labels and equip candidate labels both mean “skill”, but they resolve to different canonical args.
**Why it happens:** both refer to skills, and `SkillToolRuntimeTargetDto` currently only carries loadout/slot fields.
**How to avoid:** keep equip candidates in a separate DTO and prefix family from combat skills.
**Warning signs:** resolver branches start checking `kind == "skill"` and then conditionally reading unrelated fields.

### Pitfall 2: Availability Without Matching Runtime Targets
**What goes wrong:** a tool appears in the available tools list, but the prompt has no matching labels to choose from.
**Why it happens:** resolver/registry work is added before current-state builder work.
**How to avoid:** define availability in terms of the same `PlayerCurrentStateDto` collections that the UI builder renders.
**Warning signs:** tool is registered, but `ToolRuntimeContextDto.targets` does not contain its label family in tests.

### Pitfall 3: Proposal Labels With No Stable Progress Identity
**What goes wrong:** accept/reject cannot resolve a proposal uniquely once multiple players or new proposal refreshes exist.
**Why it happens:** event payload only carries `proposal_id`, while the command service needs `progress_id` + `proposal_id`.
**How to avoid:** proposal runtime targets must carry both `progress_id` and `proposal_id`.
**Warning signs:** resolver signatures start inferring progress from player only, or proposal tool tests depend on hidden global lookup.

### Pitfall 4: Treating Awakened Action As a Raw Loadout Operation
**What goes wrong:** tool contract leaks `duration_ticks`, `cooldown_reduction_rate`, or resource numbers.
**Why it happens:** `ActivatePlayerAwakenedModeCommand` currently requires those numeric fields.
**How to avoid:** Phase 8 should define only a label that resolves to `loadout_id`; Phase 10 can add a facade service that supplies server defaults.
**Warning signs:** tool schema contains integers/floats for awakened activation.

### Pitfall 5: Missing Observation Follow-Through Assumptions
**What goes wrong:** phase plan assumes proposal generation already produces useful player-facing prose, but formatter currently returns `None`.
**Why it happens:** observation recipient wiring exists, but `ObservationFormatter._format_skill_proposal_generated` is not implemented.
**How to avoid:** keep runtime context as the source of truth for proposal choices in Phase 8 and do not scope-creep proposal observation fixes into this phase.
**Warning signs:** plan tasks start including observation formatting work unrelated to SKRT-01/SKTL-02.

## Code Examples

Verified patterns from repo sources:

### Build Labels And Targets Together
```python
# Source: src/ai_rpg_world/application/llm/services/ui_context_builder.py
for skill in skills:
    counters["K"] += 1
    label = f"K{counters['K']}"
    lines.append(f"- {label}: {skill.display_name}{suffix}")
    runtime_targets[label] = SkillToolRuntimeTargetDto(
        label=label,
        kind="skill",
        display_name=skill.display_name,
        skill_loadout_id=skill.skill_loadout_id,
        skill_slot_index=skill.skill_slot_index,
    )
```

### Resolve Label Pairs Into Canonical Args
```python
# Source pattern: src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
slot = self._require_target_type(
    slot_label,
    runtime_context,
    "装備先スロットラベル",
    (SkillEquipSlotToolRuntimeTargetDto,),
)
skill = self._require_target_type(
    skill_label,
    runtime_context,
    "装備候補スキルラベル",
    (SkillEquipCandidateToolRuntimeTargetDto,),
)
return {
    "loadout_id": slot.skill_loadout_id,
    "deck_tier": slot.deck_tier,
    "slot_index": slot.skill_slot_index,
    "skill_id": skill.skill_id,
}
```

### Use Presence-Based Availability
```python
# Source pattern: src/ai_rpg_world/application/llm/services/availability_resolvers.py
class SkillEquipAvailabilityResolver(IAvailabilityResolver):
    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return (
            context is not None
            and bool(context.equipable_skill_candidates)
            and bool(context.skill_equip_slots)
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| prompt text only, no structured label resolution | `ToolRuntimeContextDto.targets` + typed DTO lookup | already established in v1.0/v1.1 base | new skill tools should extend the same mechanism |
| single combat skill label family | multiple skill label families per decision type | required in Phase 8 | prevents semantic overload between combat, equip, proposal, awakened |
| executor-level raw arg passing | resolver-level canonical argument construction | already standard in current LLM stack | keeps tools safe and testable |

**Deprecated/outdated:**
- Treating every skill-facing action as a `K*` label: insufficient once equip/proposal/awakened each require different canonical payloads.
- Assuming proposal observation text already exists: current formatter returns `None` for `SkillProposalGeneratedEvent`.

## Open Questions

1. **Where should pending proposal read models be built?**
   - What we know: `SkillCommandService.accept_skill_proposal(...)` and `reject_skill_proposal(...)` need `progress_id`, and `SkillDeckProgressAggregate.pending_proposals` exposes the domain data.
   - What's unclear: there is no existing supplemental builder dependency for `SkillDeckProgressRepository`.
   - Recommendation: add `SkillDeckProgressRepository` to `PlayerSupplementalContextBuilder` and build proposal DTOs there, not in the UI builder.

2. **How should deck tier be represented in runtime targets?**
   - What we know: `DeckTier` enum values are `normal` / `awakened`, and `ToolRuntimeTargetDto` currently stores plain serializable fields.
   - What's unclear: whether to store enum instances or normalized strings in DTOs.
   - Recommendation: store `deck_tier` as string value on runtime targets for consistency with current DTO style, then convert to `DeckTier` in resolver or executor boundary.

3. **Should awakened action exist when loadout is present but not activatable?**
   - What we know: locked decision says awakened action appears only when activatable; Phase 10 owns concrete rules.
   - What's unclear: exact activatable predicate before the Phase 10 facade exists.
   - Recommendation: in Phase 8, define the DTO and resolver contract, but keep availability implementation conservative and data-driven so Phase 10 can refine it without schema churn.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/application/llm/test_ui_context_builder.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_definitions.py tests/application/llm/test_availability_resolvers.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKRT-01 | runtime context exposes proposal, equip slot, equip candidate, awakened action labels | unit | `pytest tests/application/llm/test_ui_context_builder.py -x` | ✅ |
| SKRT-01 | current-state builder/supplemental builder populate new skill read models | unit | `pytest tests/application/world/test_player_supplemental_context_builder.py -x` | ❌ Wave 0 |
| SKTL-02 | `skill_equip` resolves skill label + slot label into `loadout_id` / `deck_tier` / `slot_index` / `skill_id` | unit | `pytest tests/application/llm/test_tool_argument_resolver.py -x` | ✅ |
| SKTL-02 | `skill_equip` schema and availability are registered only when candidates exist | unit | `pytest tests/application/llm/test_tool_definitions.py tests/application/llm/test_availability_resolvers.py -x` | ✅ |

### Sampling Rate
- **Per task commit:** `pytest tests/application/llm/test_ui_context_builder.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_definitions.py tests/application/llm/test_availability_resolvers.py -x`
- **Per wave merge:** `pytest tests/application/llm -x`
- **Phase gate:** `pytest`

### Wave 0 Gaps
- [ ] `tests/application/world/test_player_supplemental_context_builder.py` — covers new proposal/equip-slot/awakened read models for SKRT-01
- [ ] `tests/application/llm/test_tool_constants.py` — add new tool-name and prefix assertions for skill tools
- [ ] `tests/application/llm/test_available_tools_provider.py` — verify tool visibility follows new availability resolvers

## Sources

### Primary (HIGH confidence)
- `src/ai_rpg_world/application/llm/contracts/dtos.py` - current runtime target and runtime context DTO design
- `src/ai_rpg_world/application/llm/services/ui_context_builder.py` - label generation and runtime target assembly pattern
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py` - typed label resolution and invalid-kind rejection pattern
- `src/ai_rpg_world/application/llm/services/tool_definitions.py` - tool schema and default registration pattern
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py` - presence-based tool visibility rules
- `src/ai_rpg_world/application/world/contracts/dtos.py` - `PlayerCurrentStateDto` and current skill/world read model boundaries
- `src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py` - current supplemental read model assembly for `usable_skills`
- `src/ai_rpg_world/application/world/services/player_current_state_builder.py` - single assembly point for current-state DTO population
- `src/ai_rpg_world/application/skill/contracts/commands.py` - canonical command arguments for equip/proposal/awakened actions
- `src/ai_rpg_world/application/skill/services/skill_command_service.py` - existing application services that later phases will invoke
- `src/ai_rpg_world/application/llm/services/executors/world_executor.py` - current combat skill executor boundary
- `src/ai_rpg_world/domain/skill/aggregate/skill_deck_progress_aggregate.py` - pending proposal source of truth
- `src/ai_rpg_world/domain/skill/aggregate/skill_loadout_aggregate.py` - awakened state and deck-tier behavior
- `src/ai_rpg_world/domain/skill/value_object/skill_proposal.py` - proposal payload fields needed for runtime labels
- `src/ai_rpg_world/domain/skill/event/skill_events.py` - current skill event payloads and their limits
- `src/ai_rpg_world/application/observation/services/observation_formatter.py` - observation gap for proposal-generated events
- `tests/application/llm/test_ui_context_builder.py` - current UI context testing style
- `tests/application/llm/test_tool_argument_resolver.py` - current resolver testing style
- `tests/application/llm/test_tool_definitions.py` - current tool schema/registration testing style
- `tests/application/llm/test_availability_resolvers.py` - current availability testing style
- `pyproject.toml` - package/runtime versions
- `pytest.ini` - pytest configuration

### Secondary (MEDIUM confidence)
- None.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - entirely repo-verified via `pyproject.toml`, `pytest.ini`, and existing code structure
- Architecture: HIGH - recommendation follows stable existing builder/resolver/registry patterns already used across LLM tools
- Pitfalls: HIGH - derived from concrete mismatches between current DTOs, command contracts, and observation gaps in repo code

**Research date:** 2026-03-12
**Valid until:** 2026-04-11
