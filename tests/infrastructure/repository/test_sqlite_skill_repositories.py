"""SQLite skill repositories tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import (
    SkillDeckProgressAggregate,
)
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import (
    SkillDeckProgressId,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
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


_LEGACY_CHILD_TABLES = (
    "game_skill_spec_hit_effects",
    "game_skill_spec_hit_pattern_segments",
    "game_skill_spec_hit_pattern_coords",
)


def _legacy_database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    SqliteSkillSpecRepository.for_connection(conn)
    # 削除前の保存形式をSQLで固定し、消すドメイン型でfixtureを組み立てない。
    conn.executescript("""
        INSERT INTO game_skill_specs VALUES
            (1, '旧スキル', 'neutral', 1, 2, 5, 1.5, 'projectile', 3, 4, 5, 0, 6);
        INSERT INTO game_skill_spec_required_skills VALUES (1, 0, 2);
        INSERT INTO game_skill_spec_slayer_races VALUES (1, 0, 'human');
        INSERT INTO game_skill_spec_hit_effects VALUES (1, 0, 'poison', 3, 2.0, 0.5);
        INSERT INTO game_skill_spec_hit_pattern_segments VALUES (1, 0, 0, 2, 1, 0, 0, 0, 0, 0, 1.2);
        INSERT INTO game_skill_spec_hit_pattern_coords VALUES (1, 0, 0, 1, 0, 0);
    """)
    return conn


def test_legacy_definition_restores_only_current_values() -> None:
    """旧DBの形・速度・追加効果を読み捨てても、消費・前提・特効・射程は復元できる。"""
    from ai_rpg_world.domain.player.enum.player_enum import Race

    conn = _legacy_database()
    repo = SqliteSkillSpecRepository.for_connection(conn)
    expected = SkillSpec(
        skill_id=SkillId(1),
        name="旧スキル",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=2,
        cooldown_ticks=5,
        power_multiplier=1.5,
        mp_cost=3,
        stamina_cost=4,
        hp_cost=5,
        required_skill_ids=(SkillId(2),),
        slayer_races=(Race.HUMAN,),
        targeting_range=6,
    )
    assert repo.find_by_id(SkillId(1)) == expected
    assert repo.find_by_ids([SkillId(1)]) == [expected]
    assert repo.find_all() == [expected]
    assert all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1 for table in _LEGACY_CHILD_TABLES)


def test_new_definition_satisfies_legacy_not_null_without_hit_rows() -> None:
    """新規定義は旧必須列を空文字で満たし、当たり判定の子行を作らず往復する。"""
    conn = sqlite3.connect(":memory:")
    writer = SqliteSkillSpecWriter.for_standalone_connection(conn)
    spec = _skill_spec(1)
    writer.replace_spec(spec)
    assert SqliteSkillSpecRepository.for_connection(conn).find_by_id(SkillId(1)) == spec
    assert conn.execute("SELECT pattern_type FROM game_skill_specs").fetchone()[0] == ""
    assert all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0 for table in _LEGACY_CHILD_TABLES)


@pytest.mark.parametrize("operation", ["replace", "delete"])
def test_replacing_or_deleting_legacy_definition_removes_old_children(operation: str) -> None:
    """旧定義を置換または削除すると、その定義に属する退役した子行も消える。"""
    conn = _legacy_database()
    writer = SqliteSkillSpecWriter.for_standalone_connection(conn)
    if operation == "replace":
        writer.replace_spec(_skill_spec(1))
        assert conn.execute("SELECT pattern_type FROM game_skill_specs").fetchone()[0] == ""
    else:
        assert writer.delete_spec(SkillId(1))
        assert SqliteSkillSpecRepository.for_connection(conn).find_by_id(SkillId(1)) is None
    assert all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0 for table in _LEGACY_CHILD_TABLES)


def test_legacy_equipped_definition_restores_with_cooldowns() -> None:
    """旧当たり判定を持つスキルの装備を読むと、枠・詠唱ロック・クールダウンは復元される。"""
    conn = _legacy_database()
    repo = SqliteSkillLoadoutRepository.for_standalone_connection(conn)
    loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 5, 7)
    loadout.equip_skill(DeckTier.NORMAL, 0, _skill_spec(1))
    repo.save(loadout)
    conn.execute("UPDATE game_skill_loadouts SET cast_lock_until_tick = 10 WHERE loadout_id = 1")
    conn.execute("INSERT INTO game_skill_loadout_cooldowns VALUES (1, 1, 20)")
    loaded = repo.find_by_owner_id(100)
    assert loaded is not None
    skill = loaded.normal_deck.get_skill(0)
    assert skill == SqliteSkillSpecRepository.for_connection(conn).find_by_id(SkillId(1))
    assert not hasattr(skill, "hit_pattern")
    assert loaded.cast_lock_until_tick == 10
    assert not loaded.can_use_skill(0, current_tick=19)
    assert loaded.can_use_skill(0, current_tick=20)


def test_invalid_current_value_in_legacy_definition_still_fails() -> None:
    """旧当たり判定を無視しても、現役のスキル消費が負なら復元を拒否する。"""
    from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillSpecValidationException

    conn = _legacy_database()
    conn.execute("UPDATE game_skill_specs SET mp_cost = -1")
    with pytest.raises(SkillSpecValidationException, match="mp_cost"):
        SqliteSkillSpecRepository.for_connection(conn).find_by_id(SkillId(1))
