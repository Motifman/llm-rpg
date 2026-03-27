"""In-memory skill repositories tests."""

from __future__ import annotations

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import (
    SkillDeckProgressAggregate,
)
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import (
    SkillDeckProgressId,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_skill_deck_progress_repository import (
    InMemorySkillDeckProgressRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_spec_repository import (
    InMemorySkillSpecRepository,
)


def _skill_spec(skill_id: int, name: str = "Slash") -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=name,
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.0,
        hit_pattern=SkillHitPattern.single_pulse(
            SkillHitPatternType.MELEE, HitBoxShape.single_cell()
        ),
    )


def test_in_memory_skill_loadout_repository_find_by_owner() -> None:
    repo = InMemorySkillLoadoutRepository(data_store=InMemoryDataStore())
    loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 5, 7)
    repo.save(loadout)

    found = repo.find_by_owner_id(100)
    assert found is not None
    assert found.loadout_id == SkillLoadoutId(1)


def test_in_memory_skill_deck_progress_repository_find_by_owner() -> None:
    repo = InMemorySkillDeckProgressRepository(data_store=InMemoryDataStore())
    progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 200)
    repo.save(progress)

    found = repo.find_by_owner_id(200)
    assert found is not None
    assert found.progress_id == SkillDeckProgressId(1)


def test_in_memory_skill_spec_repository_writer_methods() -> None:
    repo = InMemorySkillSpecRepository()
    spec = _skill_spec(1)
    repo.replace_spec(spec)

    loaded = repo.find_by_id(SkillId(1))
    assert loaded is not None
    assert loaded.name == "Slash"
    assert repo.delete_spec(SkillId(1)) is True
    assert repo.find_by_id(SkillId(1)) is None
