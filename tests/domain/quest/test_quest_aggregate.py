import pytest
from datetime import datetime

from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus, QuestObjectiveType
from ai_rpg_world.domain.quest.exception.quest_exception import (
    InvalidQuestStatusException,
    CannotAcceptQuestException,
    CannotCancelQuestException,
    QuestObjectivesNotCompleteException,
)
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestIssuedEvent,
    QuestAcceptedEvent,
    QuestCompletedEvent,
    QuestCancelledEvent,
)
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class TestQuestAggregate:
    """QuestAggregateのテスト"""

    @pytest.fixture
    def quest_id(self) -> QuestId:
        return QuestId(1)

    @pytest.fixture
    def player_id(self) -> PlayerId:
        return PlayerId(1)

    @pytest.fixture
    def other_player_id(self) -> PlayerId:
        return PlayerId(2)

    @pytest.fixture
    def objectives(self) -> list:
        return [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]

    @pytest.fixture
    def reward(self) -> QuestReward:
        return QuestReward.of(gold=100, exp=50)

    @pytest.fixture
    def scope(self) -> QuestScope:
        return QuestScope.public_scope()

    @pytest.fixture
    def open_quest(
        self, quest_id, objectives, reward, scope
    ) -> QuestAggregate:
        return QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
        )

    @pytest.fixture
    def accepted_quest(
        self, quest_id, objectives, reward, scope, player_id
    ) -> QuestAggregate:
        q = QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
        )
        q.accept_by(player_id)
        return q

    class TestIssueQuest:
        def test_issue_quest_success(self, quest_id, objectives, reward, scope):
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=None,
                guild_id=None,
            )
            assert q.quest_id == quest_id
            assert q.status == QuestStatus.OPEN
            assert q.issuer_player_id is None
            assert q.acceptor_player_id is None
            assert len(q.objectives) == 1
            assert q.reward == reward
            assert q.scope == scope

        def test_issue_quest_emits_event(self, quest_id, objectives, reward, scope):
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=None,
                guild_id=None,
            )
            events = q.get_events()
            assert len(events) == 1
            assert isinstance(events[0], QuestIssuedEvent)
            assert events[0].aggregate_id == quest_id

        def test_issue_quest_empty_objectives_raises(
            self, quest_id, reward, scope
        ):
            with pytest.raises(ValueError):
                QuestAggregate.issue_quest(
                    quest_id=quest_id,
                    objectives=[],
                    reward=reward,
                    scope=scope,
                    issuer_player_id=None,
                    guild_id=None,
                )

    class TestAcceptBy:
        def test_accept_by_success(self, open_quest, player_id):
            open_quest.accept_by(player_id)
            assert open_quest.status == QuestStatus.ACCEPTED
            assert open_quest.acceptor_player_id == player_id
            events = open_quest.get_events()
            assert any(isinstance(e, QuestAcceptedEvent) for e in events)

        def test_accept_when_not_open_raises(self, accepted_quest, other_player_id):
            with pytest.raises(InvalidQuestStatusException):
                accepted_quest.accept_by(other_player_id)

        def test_accept_direct_scope_wrong_player_raises(
            self, quest_id, objectives, reward, player_id, other_player_id
        ):
            scope = QuestScope.direct_scope(player_id)
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=None,
                guild_id=None,
            )
            with pytest.raises(CannotAcceptQuestException):
                q.accept_by(other_player_id)

        def test_accept_direct_scope_correct_player_succeeds(
            self, quest_id, objectives, reward, player_id
        ):
            scope = QuestScope.direct_scope(player_id)
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=None,
                guild_id=None,
            )
            q.accept_by(player_id)
            assert q.status == QuestStatus.ACCEPTED
            assert q.acceptor_player_id == player_id

    class TestAdvanceObjective:
        def test_advance_objective_success(self, accepted_quest):
            q = accepted_quest
            r = q.advance_objective(QuestObjectiveType.KILL_MONSTER, 101)
            assert r is True
            assert q.objectives[0].current_count == 1

        def test_advance_objective_wrong_type_returns_false(self, accepted_quest):
            r = accepted_quest.advance_objective(
                QuestObjectiveType.REACH_SPOT, 101
            )
            assert r is False

        def test_advance_objective_wrong_target_returns_false(self, accepted_quest):
            r = accepted_quest.advance_objective(
                QuestObjectiveType.KILL_MONSTER, 999
            )
            assert r is False

        def test_advance_objective_when_not_accepted_returns_false(
            self, open_quest
        ):
            r = open_quest.advance_objective(
                QuestObjectiveType.KILL_MONSTER, 101
            )
            assert r is False

        def test_advance_objective_caps_at_required(self, accepted_quest):
            q = accepted_quest
            q.advance_objective(QuestObjectiveType.KILL_MONSTER, 101)
            q.advance_objective(QuestObjectiveType.KILL_MONSTER, 101)
            q.advance_objective(QuestObjectiveType.KILL_MONSTER, 101)
            assert q.objectives[0].current_count == 2
            assert q.is_all_objectives_completed() is True

    class TestComplete:
        def test_complete_success(self, quest_id, objectives, reward, scope, player_id):
            obj = QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=2,
            )
            q = QuestAggregate(
                quest_id=quest_id,
                status=QuestStatus.ACCEPTED,
                objectives=[obj],
                reward=reward,
                scope=scope,
                acceptor_player_id=player_id,
            )
            q.complete()
            assert q.status == QuestStatus.COMPLETED
            events = q.get_events()
            assert any(isinstance(e, QuestCompletedEvent) for e in events)

        def test_complete_when_not_accepted_raises(self, open_quest):
            with pytest.raises(InvalidQuestStatusException):
                open_quest.complete()

        def test_complete_when_objectives_not_done_raises(
            self, accepted_quest
        ):
            with pytest.raises(QuestObjectivesNotCompleteException):
                accepted_quest.complete()

    class TestCancelBy:
        def test_cancel_by_acceptor_success(self, accepted_quest, player_id):
            accepted_quest.cancel_by(player_id)
            assert accepted_quest.status == QuestStatus.CANCELLED
            events = accepted_quest.get_events()
            assert any(isinstance(e, QuestCancelledEvent) for e in events)

        def test_cancel_by_issuer_success(
            self, quest_id, objectives, reward, scope, player_id
        ):
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=player_id,
                guild_id=None,
            )
            q.cancel_by(player_id)
            assert q.status == QuestStatus.CANCELLED

        def test_cancel_by_other_player_raises(
            self, accepted_quest, other_player_id
        ):
            with pytest.raises(CannotCancelQuestException):
                accepted_quest.cancel_by(other_player_id)

        def test_cancel_when_completed_raises(
            self, quest_id, objectives, reward, scope, player_id
        ):
            obj = QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=1,
                current_count=1,
            )
            q = QuestAggregate(
                quest_id=quest_id,
                status=QuestStatus.ACCEPTED,
                objectives=[obj],
                reward=reward,
                scope=scope,
                acceptor_player_id=player_id,
            )
            q.complete()
            with pytest.raises(InvalidQuestStatusException):
                q.cancel_by(player_id)

    class TestCanBeAcceptedBy:
        def test_open_public_can_be_accepted_by_any(
            self, open_quest, player_id, other_player_id
        ):
            assert open_quest.can_be_accepted_by(player_id) is True
            assert open_quest.can_be_accepted_by(other_player_id) is True

        def test_accepted_quest_cannot_be_accepted(
            self, accepted_quest, other_player_id
        ):
            assert accepted_quest.can_be_accepted_by(other_player_id) is False

    class TestIsIssuerOrAcceptor:
        def test_issuer_is_included(
            self, quest_id, objectives, reward, scope, player_id
        ):
            q = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=player_id,
                guild_id=None,
            )
            assert q.is_issuer_or_acceptor(player_id) is True

        def test_acceptor_is_included(self, accepted_quest, player_id):
            assert accepted_quest.is_issuer_or_acceptor(player_id) is True

        def test_other_player_not_included(
            self, accepted_quest, other_player_id
        ):
            assert accepted_quest.is_issuer_or_acceptor(other_player_id) is False
