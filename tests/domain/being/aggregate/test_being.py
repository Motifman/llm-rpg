"""Being 集約ルートの構成・不変条件挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


class TestBeingConstruction:
    """Being 集約のコンストラクタ挙動。"""

    def test_BeingId_と_Identity_を渡すと生成できる(self) -> None:
        """正しい型の引数で集約が生成され、property で取り出せる。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.being_id == BeingId("ada")
        assert being.identity == _identity()

    def test_being_id_が_BeingId_でないと_TypeError_を投げる(self) -> None:
        """being_id が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            Being(being_id="ada", identity=_identity())  # type: ignore[arg-type]

    def test_identity_が_BeingIdentity_でないと_TypeError_を投げる(self) -> None:
        """identity が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="identity"):
            Being(being_id=BeingId("ada"), identity="アダ")  # type: ignore[arg-type]

    def test_初期状態では_events_が空(self) -> None:
        """AggregateRoot 由来の event リストは初期空。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.get_events() == []
