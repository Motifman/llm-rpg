import pytest
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType


class TestQuestObjective:
    """QuestObjective値オブジェクトのテスト"""

    def test_create_kill_monster_objective(self):
        """KILL_MONSTER目標が正しく作成されること"""
        obj = QuestObjective(
            objective_type=QuestObjectiveType.KILL_MONSTER,
            target_id=101,
            required_count=3,
            current_count=0,
        )
        assert obj.objective_type == QuestObjectiveType.KILL_MONSTER
        assert obj.target_id == 101
        assert obj.required_count == 3
        assert obj.current_count == 0
        assert obj.is_completed() is False

    def test_with_progress_increases_count(self):
        """with_progressで進捗が加算されること"""
        obj = QuestObjective(
            objective_type=QuestObjectiveType.KILL_MONSTER,
            target_id=101,
            required_count=3,
            current_count=0,
        )
        obj2 = obj.with_progress(1)
        assert obj2.current_count == 1
        assert obj2.required_count == 3
        assert obj.current_count == 0  # 不変

    def test_with_progress_caps_at_required(self):
        """with_progressはrequired_countを超えないこと"""
        obj = QuestObjective(
            objective_type=QuestObjectiveType.KILL_MONSTER,
            target_id=101,
            required_count=2,
            current_count=1,
        )
        obj2 = obj.with_progress(5)
        assert obj2.current_count == 2
        assert obj2.is_completed() is True

    def test_is_completed_when_met(self):
        """required_countに達するとis_completedがTrueになること"""
        obj = QuestObjective(
            objective_type=QuestObjectiveType.KILL_MONSTER,
            target_id=101,
            required_count=2,
            current_count=2,
        )
        assert obj.is_completed() is True

    def test_required_count_zero_raises(self):
        """required_countが0以下は例外"""
        with pytest.raises(ValueError):
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=0,
                current_count=0,
            )

    def test_current_count_negative_raises(self):
        """current_countが負は例外"""
        with pytest.raises(ValueError):
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=3,
                current_count=-1,
            )

    def test_current_count_over_required_raises(self):
        """current_countがrequired_countを超えると例外"""
        with pytest.raises(ValueError):
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=3,
                current_count=4,
            )
