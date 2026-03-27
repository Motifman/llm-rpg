"""SQLite skill repositories tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import (
    SkillDeckProgressAggregate,
)
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import (
    SkillDeckProgressId,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.infrastructure.repository.sqlite_skill_deck_progress_repository import (
    SqliteSkillDeckProgressRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_loadout_repository import (
    SqliteSkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_spec_repository import (
    SqliteSkillSpecRepository,
    SqliteSkillSpecWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _skill_spec(skill_id: int, name: str = "Slash") -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=name,
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.1,
        hit_pattern=SkillHitPattern.single_pulse(
            SkillHitPatternType.MELEE,
            HitBoxShape.single_cell(),
        ),
    )


def test_skill_loadout_repository_roundtrip_and_owner_lookup() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteSkillLoadoutRepository.for_standalone_connection(conn)
    writer = SqliteSkillSpecWriter.for_standalone_connection(conn)
    writer.replace_spec(_skill_spec(1))

    loadout = SkillLoadoutAggregate.create(
        loadout_id=SkillLoadoutId(1),
        owner_id=100,
        normal_capacity=5,
        awakened_capacity=7,
    )
    loadout.equip_skill(DeckTier.NORMAL, 0, _skill_spec(1))
    repo.save(loadout)

    loaded = repo.find_by_id(SkillLoadoutId(1))
    assert loaded is not None
    assert loaded.owner_id == 100
    assert loaded.normal_deck.get_skill(0) is not None

    by_owner = repo.find_by_owner_id(100)
    assert by_owner is not None
    assert by_owner.loadout_id == SkillLoadoutId(1)


def test_skill_deck_progress_repository_roundtrip_and_owner_lookup() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteSkillDeckProgressRepository.for_standalone_connection(conn)

    progress = SkillDeckProgressAggregate(
        progress_id=SkillDeckProgressId(1),
        owner_id=200,
    )
    progress.grant_exp(120)
    repo.save(progress)

    loaded = repo.find_by_id(SkillDeckProgressId(1))
    assert loaded is not None
    assert loaded.owner_id == 200

    by_owner = repo.find_by_owner_id(200)
    assert by_owner is not None
    assert by_owner.progress_id == SkillDeckProgressId(1)


def test_skill_spec_reader_and_writer_roundtrip() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteSkillSpecRepository.for_connection(conn)
    writer = SqliteSkillSpecWriter.for_standalone_connection(conn)

    writer.replace_spec(_skill_spec(1, "Slash"))

    loaded = repo.find_by_id(SkillId(1))
    assert loaded is not None
    assert loaded.name == "Slash"


def test_skill_spec_shared_writer_requires_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    writer = SqliteSkillSpecWriter.for_shared_unit_of_work(conn)

    with pytest.raises(RuntimeError, match="writer"):
        writer.replace_spec(_skill_spec(1))


def test_skill_spec_shared_writer_works_inside_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)

    with uow:
        writer = SqliteSkillSpecWriter.for_shared_unit_of_work(uow.connection)
        repo = SqliteSkillSpecRepository.for_connection(uow.connection)
        writer.replace_spec(_skill_spec(1))
        assert repo.find_by_id(SkillId(1)) is not None
