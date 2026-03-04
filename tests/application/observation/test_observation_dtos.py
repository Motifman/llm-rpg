"""ObservationOutput / ObservationEntry のテスト（正常・バリデーション例外）

仕様: ObservationOutput は observation_category（self_only / social / environment）を必ず持つ。
省略時はデフォルト self_only。テストでは仕様に合わせて category を明示する。
"""

import pytest
from datetime import datetime

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
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

    def test_causes_interrupt_default_is_false(self):
        """causes_interrupt を省略した場合デフォルトは False"""
        out = ObservationOutput(prose="x", structured={})
        assert out.causes_interrupt is False

    def test_causes_interrupt_true(self):
        """causes_interrupt=True で生成できる"""
        out = ObservationOutput(
            prose="戦闘不能になりました。",
            structured={"type": "player_downed"},
            observation_category="self_only",
            causes_interrupt=True,
        )
        assert out.causes_interrupt is True

    def test_causes_interrupt_not_bool_raises_type_error(self):
        """causes_interrupt が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="causes_interrupt must be bool"):
            ObservationOutput(
                prose="x", structured={}, causes_interrupt="yes"  # type: ignore[arg-type]
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
