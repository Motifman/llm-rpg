"""DefaultRecentEventsFormatter のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)


class TestDefaultRecentEventsFormatter:
    """DefaultRecentEventsFormatter の正常・境界・例外ケース"""

    @pytest.fixture
    def formatter(self):
        return DefaultRecentEventsFormatter()

    @pytest.fixture
    def sample_observation(self):
        return ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="プレイヤーがスポットに到着しました。",
                structured={"type": "gateway"},
                observation_category="self_only",
            ),
        )

    @pytest.fixture
    def sample_action_result(self):
        return ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="move_to を実行",
            result_summary="スポットAに到着しました。",
        )

    def test_format_empty_lists_returns_placeholder(self, formatter):
        """観測・行動結果が空のときプレースホルダ文"""
        text = formatter.format([], [])
        assert "直近の出来事はありません" in text

    def test_format_observations_only(self, formatter, sample_observation):
        """観測のみのとき観測文が並ぶ"""
        text = formatter.format([sample_observation], [])
        assert "プレイヤーがスポットに到着しました。" in text
        assert "- " in text

    def test_format_observation_with_game_time_label_prepends_label(self, formatter):
        """観測に game_time_label があるとき「[ラベル] 観測文」形式で出力される"""
        entry_with_time = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="宝箱を開けました。",
                structured={"type": "chest"},
                observation_category="self_only",
            ),
            game_time_label="1年2月3日 12:30:45",
        )
        text = formatter.format([entry_with_time], [])
        assert "[1年2月3日 12:30:45] 宝箱を開けました。" in text

    def test_format_observation_without_game_time_label_no_bracket_prefix(self, formatter):
        """game_time_label が None のときは観測文のみ（[○年○月…] のプレフィックスなし）"""
        entry_no_time = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="宝箱を開けました。",
                structured={"type": "chest"},
                observation_category="self_only",
            ),
        )
        text = formatter.format([entry_no_time], [])
        assert "宝箱を開けました。" in text
        assert "[1年" not in text and "[2年" not in text

    def test_format_action_results_only(self, formatter, sample_action_result):
        """行動結果のみのとき行動→結果が並ぶ"""
        text = formatter.format([], [sample_action_result])
        assert "[行動]" in text
        assert "move_to を実行" in text
        assert "[結果]" in text
        assert "スポットAに到着しました。" in text

    def test_format_merges_observations_and_action_results(
        self, formatter, sample_observation, sample_action_result
    ):
        """観測と行動結果の両方があるときマージされて出力される"""
        text = formatter.format([sample_observation], [sample_action_result])
        assert "プレイヤーがスポットに到着しました。" in text
        assert "move_to を実行" in text

    def test_observations_not_list_raises_type_error(
        self, formatter, sample_action_result
    ):
        """observations が list でないとき TypeError"""
        with pytest.raises(TypeError, match="observations must be list"):
            formatter.format("not a list", [sample_action_result])  # type: ignore[arg-type]

    def test_action_results_not_list_raises_type_error(
        self, formatter, sample_observation
    ):
        """action_results が list でないとき TypeError"""
        with pytest.raises(TypeError, match="action_results must be list"):
            formatter.format([sample_observation], None)  # type: ignore[arg-type]

    def test_observations_contain_non_entry_raises_type_error(
        self, formatter, sample_action_result
    ):
        """observations の要素が ObservationEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="observations must contain only ObservationEntry"):
            formatter.format(["invalid"], [sample_action_result])  # type: ignore[list-item]

    def test_action_results_contain_non_entry_raises_type_error(
        self, formatter, sample_observation
    ):
        """action_results の要素が ActionResultEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="action_results must contain only ActionResultEntry"):
            formatter.format([sample_observation], ["invalid"])  # type: ignore[list-item]
