"""Phase 4-E: SpotObject.visible_state が hidden_state_keys を除外することを検証する。

第三者プロンプトに「trap_armed」のような仕掛け値が漏れないようにするための
静的 visibility 属性。effect の visibility (HIDDEN) とは独立。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _make(state: dict, hidden: frozenset = frozenset()) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="燭台",
        description="",
        object_type=SpotObjectTypeEnum.OTHER,
        state=state,
        interactions=(),
        hidden_state_keys=hidden,
    )


class TestVisibleState:
    """SpotObject.visible_state の挙動。"""

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
