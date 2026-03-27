"""SQLite quest repository tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.infrastructure.repository.sqlite_quest_repository import (
    SqliteQuestRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _quest(quest_id: int) -> QuestAggregate:
    quest = QuestAggregate.issue_quest(
        quest_id=QuestId(quest_id),
        objectives=[
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=99,
                required_count=3,
            )
        ],
        reward=QuestReward.of(gold=50),
        scope=QuestScope.public_scope(),
    )
    quest.accept_by(PlayerId(777))
    return quest


def test_quest_repository_roundtrip_and_accepted_lookup() -> None:
    conn = sqlite3.connect(":memory:")
    repo: QuestRepository = SqliteQuestRepository.for_standalone_connection(conn)

    repo.save(_quest(1))

    loaded = repo.find_by_id(QuestId(1))
    assert loaded is not None
    assert loaded.quest_id == QuestId(1)

    accepted = repo.find_accepted_quests_by_player(PlayerId(777))
    assert [quest.quest_id for quest in accepted] == [QuestId(1)]


def test_quest_repository_generates_ids_inside_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)

    with uow:
        repo = SqliteQuestRepository.for_shared_unit_of_work(uow.connection)
        assert repo.generate_quest_id() == QuestId(1)
        assert repo.generate_quest_id() == QuestId(2)
