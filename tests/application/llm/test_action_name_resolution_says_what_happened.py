"""操作名の解決が、何が起きたのかを呼び出し側に伝える。

## 4 つの結末が 1 つの文字列に潰れていた

``_pick_action_name`` は、性質の違う 4 つの結末をすべて ``str`` で返していた。

| 実際に起きたこと          | 返り値   |
|---------------------------|----------|
| 生値がそのまま一覧に在った | その名前 |
| 崩れを直して一覧に当てた   | 直した名前 |
| 一覧に無く、生値を先へ送った | 生値   |
| 候補集合が空で、判定していない | 生値   |

呼び出し側は、置換したのかどうかも、判定したのかどうかも読めない。そのため
「置換した」を履歴・trace・結果文の 3 箇所へ出すときに、それぞれが別々に
判定し直すことになる。片方だけ直して片方が黙る形が生まれる。

## 判定していないことを、当たらなかったことと同じにしない

候補集合が空になるのは、行為者に操作をすべて伏せた物体のとき
(design_decisions #46)。ここで意味による選び直し (#1321) を走らせると、
伏せた操作の存在を確率として漏らしかねない。**当たらなかった**と
**判定していない**を別の値にして、呼び出し側が分けられるようにする。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    ActionNameSource,
    SpotGraphArgumentResolver,
    pick_action_name,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    CANONICAL_IDENTIFIERS_KEY,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)


def _field(*interactions: str) -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label="OBJ1",
        kind="spot_graph_object",
        display_name="麦畑",
        world_object_id=10,
        available_interactions=interactions,
    )


class TestActionNameResolutionSaysWhatHappened:
    """操作名の解決結果が、送る値だけでなく「何が起きたか」を持つことを保証する。"""

    def test_a_name_that_is_already_offered_is_reported_as_verbatim(self) -> None:
        """一覧にある名前をそのまま渡すと、送る値は生値のままで source は verbatim になる。"""
        resolution = pick_action_name("reap_wheat", _field("reap_wheat", "water_field"))

        assert resolution.value == "reap_wheat"
        assert resolution.original == "reap_wheat"
        assert resolution.source is ActionNameSource.VERBATIM

    @pytest.mark.parametrize(
        "raw",
        ['"reap_wheat"', "'reap_wheat'", '麦を刈り取る → "reap_wheat"'],
    )
    def test_a_copied_display_form_is_reported_as_normalized(self, raw: str) -> None:
        """表示の写し崩れは一覧の名前へ寄り、source は normalized で生値が original に残る。"""
        resolution = pick_action_name(raw, _field("reap_wheat"))

        assert resolution.value == "reap_wheat"
        assert resolution.original == raw
        assert resolution.source is ActionNameSource.NORMALIZED
        assert resolution.was_replaced is True

    def test_an_invented_name_is_reported_as_unresolved(self) -> None:
        """一覧に無い名前は生値のまま送られ、source は unresolved になる。"""
        resolution = pick_action_name("gather", _field("reap_wheat", "water_field"))

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.UNRESOLVED
        assert resolution.was_replaced is False

    def test_an_empty_candidate_set_is_reported_as_not_offered(self) -> None:
        """候補集合が空のときは、当たらなかったのではなく判定していないと分かる。"""
        resolution = pick_action_name("gather", _field())

        assert resolution.value == "gather"
        assert resolution.source is ActionNameSource.NOT_OFFERED

    def test_surrounding_whitespace_is_dropped_before_deciding(self) -> None:
        """前後の空白だけの違いは、original にも残さず verbatim として扱う。"""
        resolution = pick_action_name("  reap_wheat  ", _field("reap_wheat"))

        assert resolution.original == "reap_wheat"
        assert resolution.source is ActionNameSource.VERBATIM
        assert resolution.was_replaced is False


class TestInteractStillSendsTheSameActionName:
    """interact の引数解決が、解決結果を型で受けても従来と同じ値を送ることを保証する。"""

    def _resolve(self, action_name: str) -> dict:
        context = ToolRuntimeContextDto(
            targets={"OBJ1": _field("reap_wheat", "water_field")}
        )
        result = SpotGraphArgumentResolver().resolve_args(
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"target_label": "麦畑", "action_name": action_name, "inner_thought": ""},
            context,
        )
        assert result is not None
        return result

    def test_a_copied_display_form_is_sent_as_the_offered_name(self) -> None:
        """quote つきで書かれた操作名は、一覧の名前に直して executor へ送られる。"""
        assert self._resolve('"reap_wheat"')["action_name"] == "reap_wheat"

    def test_an_invented_name_is_still_sent_unchanged(self) -> None:
        """一覧に無い名前は直さずに送り、従来どおり実行時に失敗させる (**正の対照**)。"""
        assert self._resolve("gather")["action_name"] == "gather"

    def test_the_offered_name_is_what_the_history_keeps(self) -> None:
        """直した操作名は、次に真似して通る形として履歴用の正規値に残る。"""
        resolved = self._resolve('"reap_wheat"')

        assert resolved[CANONICAL_IDENTIFIERS_KEY]["action_name"] == "reap_wheat"
