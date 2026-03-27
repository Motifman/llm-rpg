"""Helpers for normalized skill-related SQLite persistence."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect, HitEffectType
from ai_rpg_world.domain.player.enum.player_enum import Element, Race
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import AwakenState, SkillLoadoutAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_deck import SkillDeck
from ai_rpg_world.domain.skill.value_object.skill_deck_exp_table import SkillDeckExpTable
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern, SkillHitTimelineSegment
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_proposal import SkillProposal
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


def build_skill_spec(
    *,
    row: object,
    required_skill_rows: Iterable[int],
    slayer_race_rows: Iterable[str],
    hit_effect_rows: Iterable[tuple[str, int, float, float]],
    segment_rows: Iterable[object],
    coordinate_rows: Iterable[object],
) -> SkillSpec:
    coords_by_segment: dict[int, list[RelativeCoordinate]] = defaultdict(list)
    for coord_row in coordinate_rows:
        coords_by_segment[int(coord_row["segment_index"])].append(
            RelativeCoordinate(
                dx=int(coord_row["dx"]),
                dy=int(coord_row["dy"]),
                dz=int(coord_row["dz"]),
            )
        )
    segments = []
    for segment_row in segment_rows:
        segment_index = int(segment_row["segment_index"])
        segments.append(
            SkillHitTimelineSegment(
                start_offset_ticks=int(segment_row["start_offset_ticks"]),
                duration_ticks=int(segment_row["duration_ticks"]),
                shape=HitBoxShape(coords_by_segment[segment_index]),
                velocity=HitBoxVelocity(
                    dx=float(segment_row["velocity_dx"]),
                    dy=float(segment_row["velocity_dy"]),
                    dz=float(segment_row["velocity_dz"]),
                ),
                spawn_offset=RelativeCoordinate(
                    dx=int(segment_row["spawn_dx"]),
                    dy=int(segment_row["spawn_dy"]),
                    dz=int(segment_row["spawn_dz"]),
                ),
                segment_power_multiplier=float(segment_row["segment_power_multiplier"]),
            )
        )
    return SkillSpec(
        skill_id=SkillId(int(row["skill_id"])),
        name=row["name"],
        element=Element(row["element"]),
        deck_cost=int(row["deck_cost"]),
        cast_lock_ticks=int(row["cast_lock_ticks"]),
        cooldown_ticks=int(row["cooldown_ticks"]),
        power_multiplier=float(row["power_multiplier"]),
        hit_pattern=SkillHitPattern(
            pattern_type=SkillHitPatternType(row["pattern_type"]),
            timeline_segments=tuple(segments),
        ),
        mp_cost=row["mp_cost"],
        stamina_cost=row["stamina_cost"],
        hp_cost=row["hp_cost"],
        slayer_races=tuple(Race(race) for race in slayer_race_rows),
        hit_effects=tuple(
            HitEffect(
                effect_type=HitEffectType(effect_type),
                duration_ticks=duration_ticks,
                intensity=intensity,
                chance=chance,
            )
            for effect_type, duration_ticks, intensity, chance in hit_effect_rows
        ),
        required_skill_ids=tuple(SkillId(skill_id) for skill_id in required_skill_rows),
        is_awakened_deck_only=bool(row["is_awakened_deck_only"]),
        targeting_range=int(row["targeting_range"]),
    )


def build_skill_loadout(
    *,
    row: object,
    slot_rows: Iterable[object],
    cooldown_rows: Iterable[tuple[int, int]],
    skill_specs_by_id: dict[int, SkillSpec],
) -> SkillLoadoutAggregate:
    normal_slots = [None] * 5
    awakened_slots = [None] * 5
    for slot_row in slot_rows:
        skill = skill_specs_by_id.get(int(slot_row["skill_id"]))
        if skill is None:
            continue
        target = normal_slots if slot_row["deck_tier"] == DeckTier.NORMAL.value else awakened_slots
        target[int(slot_row["slot_index"])] = skill
    return SkillLoadoutAggregate(
        loadout_id=SkillLoadoutId(int(row["loadout_id"])),
        owner_id=int(row["owner_id"]),
        normal_deck=SkillDeck(
            capacity=int(row["normal_capacity"]),
            deck_tier=DeckTier.NORMAL,
            slots=tuple(normal_slots),
        ),
        awakened_deck=SkillDeck(
            capacity=int(row["awakened_capacity"]),
            deck_tier=DeckTier.AWAKENED,
            slots=tuple(awakened_slots),
        ),
        awaken_state=AwakenState(
            is_active=bool(row["awaken_is_active"]),
            active_until_tick=int(row["awaken_active_until_tick"]),
            cooldown_reduction_rate=float(row["awaken_cooldown_reduction_rate"]),
        ),
        skill_cooldowns_until={skill_id: ready_at_tick for skill_id, ready_at_tick in cooldown_rows},
        cast_lock_until_tick=int(row["cast_lock_until_tick"]),
    )


def build_skill_deck_progress(
    *,
    row: object,
    capacity_bonus_rows: Iterable[tuple[int, int]],
    proposal_rows: Iterable[object],
    required_skill_rows: Iterable[object],
) -> SkillDeckProgressAggregate:
    required_by_proposal: dict[int, list[SkillId]] = defaultdict(list)
    for required_row in required_skill_rows:
        required_by_proposal[int(required_row["proposal_id"])].append(
            SkillId(int(required_row["skill_id"]))
        )
    proposals = [
        SkillProposal(
            proposal_id=int(proposal_row["proposal_id"]),
            proposal_type=SkillProposalType(proposal_row["proposal_type"]),
            offered_skill_id=SkillId(int(proposal_row["offered_skill_id"])),
            deck_tier=DeckTier(proposal_row["deck_tier"]),
            target_slot_index=proposal_row["target_slot_index"],
            required_skill_ids=tuple(required_by_proposal[int(proposal_row["proposal_id"])]),
            reason=proposal_row["reason"],
        )
        for proposal_row in proposal_rows
    ]
    return SkillDeckProgressAggregate(
        progress_id=SkillDeckProgressId(int(row["progress_id"])),
        owner_id=int(row["owner_id"]),
        deck_level=int(row["deck_level"]),
        deck_exp=int(row["deck_exp"]),
        exp_table=SkillDeckExpTable(
            base_exp=int(row["exp_table_base_exp"]),
            exponent=float(row["exp_table_exponent"]),
            level_offset=int(row["exp_table_level_offset"]),
        ),
        capacity_growth_per_level=int(row["capacity_growth_per_level"]),
        capacity_bonus_by_level={level: bonus for level, bonus in capacity_bonus_rows},
        pending_proposals=proposals,
    )

