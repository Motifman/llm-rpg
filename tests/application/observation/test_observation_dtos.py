"""ObservationOutput / ObservationEntry のテスト（正常・バリデーション例外）

仕様: ObservationOutput は observation_category（self_only / social / environment）を必ず持つ。
省略時はデフォルト self_only。テストでは仕様に合わせて category を明示する。
"""

from datetime import datetime

import pytest

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
    SubjectUnknownView,
    WithheldFromStrangers,
)


class TestObservationOutput:
    """ObservationOutput の正常・例外ケース"""

    def test_create_with_valid_prose_structured_and_category(self):
        """prose / structured / observation_category を指定して正常に生成される（仕様どおり）"""
        out = ObservationOutput(
            prose="テスト文",
            structured={"type": "test", "key": 1},
            observation_category="self_only",
        )
        assert out.prose == "テスト文"
        assert out.structured == {"type": "test", "key": 1}
        assert out.observation_category == "self_only"

    def test_structured_can_be_empty_dict(self):
        """structured が空 dict でも許容される。category は仕様どおり明示する。"""
        out = ObservationOutput(
            prose="",
            structured={},
            observation_category="self_only",
        )
        assert out.prose == ""
        assert out.structured == {}
        assert out.observation_category == "self_only"

    def test_observation_category_default_is_self_only(self):
        """observation_category を省略した場合デフォルトは self_only"""
        out = ObservationOutput(prose="x", structured={})
        assert out.observation_category == "self_only"

    def test_observation_category_accepts_valid_values(self):
        """observation_category に self_only / social / environment を指定できる"""
        for cat in ("self_only", "social", "environment"):
            out = ObservationOutput(prose="x", structured={}, observation_category=cat)
            assert out.observation_category == cat

    def test_observation_category_invalid_raises_type_error(self):
        """observation_category が不正な値の場合 TypeError"""
        with pytest.raises(TypeError, match="observation_category"):
            ObservationOutput(prose="x", structured={}, observation_category="invalid")

    def test_prose_not_str_raises_type_error(self):
        """prose が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="prose must be str"):
            ObservationOutput(prose=123, structured={})

    def test_structured_not_dict_raises_type_error(self):
        """structured が dict でない場合 TypeError"""
        with pytest.raises(TypeError, match="structured must be dict"):
            ObservationOutput(prose="a", structured="not a dict")

    def test_schedules_turn_breaks_movement_default_are_false(self):
        """schedules_turn / breaks_movement を省略した場合デフォルトは False"""
        out = ObservationOutput(prose="x", structured={})
        assert out.schedules_turn is False
        assert out.breaks_movement is False

    def test_schedules_turn_breaks_movement_true(self):
        """schedules_turn=True, breaks_movement=True で生成できる"""
        out = ObservationOutput(
            prose="戦闘不能になりました。",
            structured={"type": "player_downed"},
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=True,
        )
        assert out.schedules_turn is True
        assert out.breaks_movement is True

    def test_schedules_turn_not_bool_raises_type_error(self):
        """schedules_turn が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="schedules_turn must be bool"):
            ObservationOutput(
                prose="x",
                structured={},
                schedules_turn="yes",  # type: ignore[arg-type]
            )

    def test_breaks_movement_not_bool_raises_type_error(self):
        """breaks_movement が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="breaks_movement must be bool"):
            ObservationOutput(
                prose="x",
                structured={},
                breaks_movement="yes",  # type: ignore[arg-type]
            )


class TestObservationEntry:
    """ObservationEntry の正常・例外ケース"""

    @pytest.fixture
    def sample_output(self):
        """仕様どおり observation_category を明示した観測出力"""
        return ObservationOutput(
            prose="観測文",
            structured={"type": "event"},
            observation_category="self_only",
        )

    def test_create_with_valid_occurred_at_and_output(self, sample_output):
        """occurred_at が datetime、output が ObservationOutput なら正常に生成される"""
        now = datetime.now()
        entry = ObservationEntry(occurred_at=now, output=sample_output)
        assert entry.occurred_at == now
        assert entry.output is sample_output

    def test_occurred_at_not_datetime_raises_type_error(self, sample_output):
        """occurred_at が datetime でない場合 TypeError"""
        with pytest.raises(TypeError, match="occurred_at must be datetime"):
            ObservationEntry(occurred_at="2025-01-01", output=sample_output)

    def test_output_not_observation_output_raises_type_error(self):
        """output が ObservationOutput でない場合 TypeError"""
        now = datetime.now()
        with pytest.raises(TypeError, match="output must be ObservationOutput"):
            ObservationEntry(occurred_at=now, output="invalid")

    def test_game_time_label_optional_default_none(self, sample_output):
        """game_time_label を省略した場合デフォルトは None"""
        now = datetime.now()
        entry = ObservationEntry(occurred_at=now, output=sample_output)
        assert entry.game_time_label is None

    def test_game_time_label_can_be_set(self, sample_output):
        """game_time_label に文字列を指定できること"""
        now = datetime.now()
        entry = ObservationEntry(
            occurred_at=now,
            output=sample_output,
            game_time_label="1年2月3日 12:30:45",
        )
        assert entry.game_time_label == "1年2月3日 12:30:45"

    def test_game_time_label_not_str_raises_type_error(self, sample_output):
        """game_time_label が str でも None でもない場合 TypeError"""
        now = datetime.now()
        with pytest.raises(TypeError, match="game_time_label must be str or None"):
            ObservationEntry(
                occurred_at=now,
                output=sample_output,
                game_time_label=123,  # type: ignore[arg-type]
            )


class TestSubjectUnknownView:
    """話し手を知らない受け手向けの版を、話し手の名前と組で持つことを保証する。"""

    def test_output_keeps_subject_name_and_view_for_unknown_subject(self):
        """話し手の名前と、名前を伏せた本文・structured を渡すと、そのまま読める。"""
        view = SubjectUnknownView(prose="誰かが言った: 「やあ」", structured={"type": "player_spoke"})
        out = ObservationOutput(
            prose="ノアが言った: 「やあ」",
            structured={"type": "player_spoke", "speaker": "ノア"},
            subject_name="ノア",
            if_subject_unknown=view,
        )

        assert out.subject_name == "ノア"
        assert out.if_subject_unknown == view

    def test_without_view_both_are_none(self):
        """何も渡さなければ、話し手の名前も伏せた版も None になる。"""
        out = ObservationOutput(prose="x", structured={})

        assert (out.subject_name, out.if_subject_unknown) == (None, None)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"subject_name": "ノア"},
            {"if_subject_unknown": SubjectUnknownView(prose="誰か", structured={})},
            {"subject_name": " ", "if_subject_unknown": SubjectUnknownView(prose="誰か", structured={})},
        ],
        ids=["name_only", "view_only", "blank_name"],
    )
    def test_name_and_view_must_come_together(self, kwargs):
        """話し手の名前と伏せた版は片方だけでは持てず、名前が空でも持てない (TypeError)。"""
        with pytest.raises(TypeError):
            ObservationOutput(prose="x", structured={}, **kwargs)


class TestWithheldFromStrangers:
    """主体を知らない受け手には届けない観測を、主体の名前と組で持てることを保証する。"""

    def _withheld(self) -> ObservationOutput:
        return ObservationOutput(
            prose="遠くで誰かが動けるようになった気配がした。",
            structured={"type": "player_revived", "actor": "ノア"},
            subject_name="ノア",
            if_subject_unknown=WithheldFromStrangers(),
        )

    def test_view_for_unknown_subject_is_nothing(self):
        """届けない印を持つ観測を主体を知らない受け手の版にすると None になる。"""
        assert self._withheld().as_subject_unknown() is None

    def test_view_for_known_subject_drops_the_mark(self):
        """主体を知っている受け手の版は、本文と structured をそのまま残し、印を外す。"""
        seen = self._withheld().as_subject_known()

        assert seen.structured["actor"] == "ノア"
        assert (seen.subject_name, seen.if_subject_unknown) == (None, None)

    def test_mark_needs_a_subject_name(self):
        """届けない印だけを渡し、主体の名前を渡さないと TypeError になる。"""
        with pytest.raises(TypeError):
            ObservationOutput(prose="x", structured={}, if_subject_unknown=WithheldFromStrangers())
