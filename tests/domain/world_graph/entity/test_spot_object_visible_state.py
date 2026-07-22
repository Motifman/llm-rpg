"""Phase 4-E: SpotObject.visible_state が hidden_state_keys を除外することを検証する。

第三者プロンプトに「trap_armed」のような仕掛け値が漏れないようにするための
静的 visibility 属性。effect の visibility (HIDDEN) とは独立。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_object import (
    VISIBLE_STATE_TAGS_KEY,
    SpotObject,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotObjectValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _make(
    state: dict,
    hidden: frozenset = frozenset(),
    unavailable_hint: str | None = None,
) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="燭台",
        description="",
        object_type=SpotObjectTypeEnum.OTHER,
        state=state,
        interactions=(),
        hidden_state_keys=hidden,
        unavailable_hint=unavailable_hint,
    )


class TestVisibleState:
    """SpotObject.visible_state が prompt に出してよい状態だけを返す挙動を保証する。"""

    def test_returns_full_state_by_default(self) -> None:
        """hidden_state_keys が空なら全キーを返す。"""
        obj = _make({"lit": True, "fuel": 5})
        assert obj.visible_state() == {"lit": True, "fuel": 5}

    def test_excludes_hidden_keys(self) -> None:
        """hidden_state_keys に列挙されたキーは visible_state から除外される。"""
        obj = _make(
            state={"lit": True, "trap_armed": True, "secret": "answer"},
            hidden=frozenset({"trap_armed", "secret"}),
        )
        assert obj.visible_state() == {"lit": True}

    def test_does_not_mutate_original_state(self) -> None:
        """visible_state() は元の state を破壊しない (重要: effect 適用は state 全体を見る)。"""
        original = {"lit": True, "trap_armed": True}
        obj = _make(state=original, hidden=frozenset({"trap_armed"}))
        _ = obj.visible_state()
        # オブジェクト自身の state は影響を受けない
        assert obj.state == {"lit": True, "trap_armed": True}
        # 元の dict も mutate されない
        assert original == {"lit": True, "trap_armed": True}

    def test_hides_available_when_true(self) -> None:
        """available=true は正常状態なので prompt 用 state には表示しない。"""
        obj = _make({"available": True, "opened": False})

        assert obj.visible_state() == {"opened": False}

    def test_renders_available_false_as_recovery_hint(self) -> None:
        """available=false は生 boolean でなく、中立の復帰ヒントへ変換する。"""
        obj = _make({"available": False, "opened": True})

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は採れない・時間を置けば戻る",),
            "opened": True,
        }

    def test_uses_author_defined_unavailable_hint(self) -> None:
        """unavailable_hint があれば、available=false の表示に作者指定文を使う。"""
        obj = _make(
            {"available": False},
            unavailable_hint="今は汲めない・時間を置けば戻る",
        )

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は汲めない・時間を置けば戻る",)
        }

    def test_hides_last_harvest_tick(self) -> None:
        """last_harvest_tick は再生判定用の内部 tick なので prompt 用 state には表示しない。"""
        obj = _make({"available": False, "last_harvest_tick": 42})

        assert obj.visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("今は採れない・時間を置けば戻る",)
        }

    def test_rejects_empty_unavailable_hint(self) -> None:
        """unavailable_hint が空白だけなら、次の一手が読める表示にならないため拒否する。"""
        with pytest.raises(SpotObjectValidationException):
            _make({"available": False}, unavailable_hint="  ")
