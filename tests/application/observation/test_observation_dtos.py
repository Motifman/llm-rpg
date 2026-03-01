"""ObservationOutput / ObservationEntry のテスト（正常・バリデーション例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)


class TestObservationOutput:
    """ObservationOutput の正常・例外ケース"""

    def test_create_with_valid_prose_and_structured(self):
        """prose が str、structured が dict なら正常に生成される"""
        out = ObservationOutput(prose="テスト文", structured={"type": "test", "key": 1})
        assert out.prose == "テスト文"
        assert out.structured == {"type": "test", "key": 1}

    def test_structured_can_be_empty_dict(self):
        """structured が空 dict でも許容される"""
        out = ObservationOutput(prose="", structured={})
        assert out.prose == ""
        assert out.structured == {}

    def test_prose_not_str_raises_type_error(self):
        """prose が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="prose must be str"):
            ObservationOutput(prose=123, structured={})

    def test_structured_not_dict_raises_type_error(self):
        """structured が dict でない場合 TypeError"""
        with pytest.raises(TypeError, match="structured must be dict"):
            ObservationOutput(prose="a", structured="not a dict")


class TestObservationEntry:
    """ObservationEntry の正常・例外ケース"""

    @pytest.fixture
    def sample_output(self):
        return ObservationOutput(prose="観測文", structured={"type": "event"})

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
