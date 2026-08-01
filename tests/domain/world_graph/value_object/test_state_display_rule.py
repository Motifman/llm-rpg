"""StateDisplayRule が state 表示ルールとして成立する値だけを受け付けることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    StateDisplayRuleValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
)


class TestStateDisplayRule:
    """StateDisplayRule の key/value/text バリデーションを保証する。"""

    def test_accepts_primitive_value_and_text(self) -> None:
        """key/value/text が妥当なら、表示ルールを構築できる。"""
        rule = StateDisplayRule(key="opened", value=False, text="蓋は閉じたまま")

        assert rule.key == "opened"
        assert rule.value is False
        assert rule.text == "蓋は閉じたまま"

    @pytest.mark.parametrize("key", ["", "   ", 123])
    def test_rejects_empty_or_non_string_key(self, key) -> None:
        """key が空白または文字列以外なら、state key として使えないため拒否する。"""
        with pytest.raises(StateDisplayRuleValidationException, match="key"):
            StateDisplayRule(key=key, value=False, text="蓋は閉じたまま")

    @pytest.mark.parametrize("value", [[], {}, {"opened": False}])
    def test_rejects_non_primitive_value(self, value) -> None:
        """value が JSON primitive 以外なら、state の単一値比較に使えないため拒否する。"""
        with pytest.raises(StateDisplayRuleValidationException, match="value"):
            StateDisplayRule(key="opened", value=value, text="蓋は閉じたまま")

    @pytest.mark.parametrize("text", ["", "   ", 123])
    def test_rejects_empty_or_non_string_text(self, text) -> None:
        """text が空白または文字列以外なら、prompt の表示文として使えないため拒否する。"""
        with pytest.raises(StateDisplayRuleValidationException, match="text"):
            StateDisplayRule(key="opened", value=False, text=text)

    @pytest.mark.parametrize("at_least", [True, 3.0, "3"])
    def test_rejects_non_integer_at_least(self, at_least) -> None:
        """at_least は bool・浮動小数・文字列へ暗黙変換せず、整数だけを受け付ける。"""
        with pytest.raises(StateDisplayRuleValidationException, match="at_least"):
            StateDisplayRule(
                key="count",
                value=None,
                text="3 個以上ある",
                at_least=at_least,
            )
