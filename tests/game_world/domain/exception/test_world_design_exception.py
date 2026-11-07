from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException
from ai_rpg_world.game_world.domain.exception.world_design_exception import (
    NoDesignFlawsException,
    UnknownNameFlaw,
    WorldDesignException,
    WorldDesignFlawsException,
)


def _flaw(name: str, reason: str) -> DesignFlaw:
    return DesignFlaw(DesignLocation("object", name, "spot_id"), reason)


class TestWorldDesignFlawsException:
    """WorldDesignFlawsException が、集めた設計の誤りを 1 つも欠かさず、渡した順に持って投げられることを保証する。"""

    def test_keeps_every_flaw_in_the_given_order(self) -> None:
        """3 つの DesignFlaw を渡すと、flaws に 3 つとも渡した順に持つ。"""
        first = _flaw("lift_lever", "spot 'hal' is not declared")
        second = _flaw("crate", "spot 'cellar' is not declared")
        third = _flaw("lamp", "spot 'attic' is not declared")

        exception = WorldDesignFlawsException([first, second, third])

        assert exception.flaws == (first, second, third)

    def test_cannot_be_raised_without_any_flaw(self) -> None:
        """DesignFlaw を 1 つも渡さないと NoDesignFlawsException を投げ、WorldDesignFlawsException は作られない。"""
        with pytest.raises(NoDesignFlawsException):
            WorldDesignFlawsException([])

    def test_message_lists_every_flaw_one_per_line(self) -> None:
        """メッセージは、誤りごとに「宣言の種類 '名前' 欄: 理由」を 1 行で、渡した順に並べる。"""
        exception = WorldDesignFlawsException(
            [
                DesignFlaw(DesignLocation("object", "lift_lever", "spot_id"), "spot 'hal' is not declared"),
                DesignFlaw(DesignLocation("character", "aki", "spawn_spot"), "spot 'cellar' is not declared"),
            ]
        )

        assert str(exception) == (
            "object 'lift_lever' spot_id: spot 'hal' is not declared\n"
            "character 'aki' spawn_spot: spot 'cellar' is not declared"
        )

    def test_is_a_world_design_domain_exception(self) -> None:
        """WorldDesignFlawsException は WorldDesignException であり、game_world のドメイン例外でもある。"""
        exception = WorldDesignFlawsException([_flaw("lift_lever", "x")])

        assert isinstance(exception, WorldDesignException)
        assert isinstance(exception, GameWorldDomainException)


class TestUnknownNameFlaw:
    """名前を引けなかったときに投げる UnknownNameFlaw が、読む側がそのまま記録できる DesignFlaw を 1 つ持つことを保証する。"""

    def test_keeps_the_flaw_to_be_recorded(self) -> None:
        """渡した DesignFlaw を flaw にそのまま持つ。"""
        flaw = _flaw("lift_lever", "spot 'hal' is not declared")

        assert UnknownNameFlaw(flaw).flaw == flaw

    def test_message_shows_location_and_reason(self) -> None:
        """メッセージは「宣言の種類 '名前' 欄: 理由」の 1 行になる。"""
        flaw = DesignFlaw(DesignLocation("character", "aki", "spawn_spot"), "spot 'hal' is not declared")

        assert str(UnknownNameFlaw(flaw)) == "character 'aki' spawn_spot: spot 'hal' is not declared"

    def test_is_a_world_design_exception_but_not_the_collected_flaws(self) -> None:
        """UnknownNameFlaw は WorldDesignException だが、集めた誤りを投げる WorldDesignFlawsException ではない。"""
        exception = UnknownNameFlaw(_flaw("lift_lever", "x"))

        assert isinstance(exception, WorldDesignException)
        assert not isinstance(exception, WorldDesignFlawsException)
