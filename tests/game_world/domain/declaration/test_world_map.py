from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.declaration.world_map import WorldMap, WorldMapWording
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import Ticks
from tests.game_world.support.world_design_for_tests import (
    half_hour_ticks_from_midnight,
    nouns,
    passage,
    spot,
    world_map_wording,
)


def _lit(name: str, lighting: Lighting) -> SpotDeclaration:
    return dataclasses.replace(spot(name), atmosphere=dataclasses.replace(spot(name).atmosphere, lighting=lighting))


def _written(*passages: PassageDeclaration, spots: tuple[SpotDeclaration, ...] | None = None) -> str:
    declared = nouns(spots=spots or (spot("井戸"), spot("広場"), spot("倉庫")), passages=passages)
    return WorldMap.drawn_from(declared).written_with(world_map_wording(), half_hour_ticks_from_midnight())


class TestWorldMapWrittenWith:
    """WorldMap が、宣言された場所と通路から、場所ごとに行き先と所要時間を 1 行で書く挙動を保証する。"""

    def test_two_way_passage_appears_from_both_ends_in_minutes(self) -> None:
        """1 日 48 tick の世界で 2 tick の双方向の通路は、両端の場所の行に、相手まで 60 分と載る。"""
        written = _written(passage("p", ("井戸", "広場"), travel_ticks=2), spots=(spot("井戸"), spot("広場")))

        assert written == "  井戸 (明るい) → 広場 まで 60 分\n  広場 (明るい) → 井戸 まで 60 分"

    def test_one_way_passage_appears_only_from_its_start(self) -> None:
        """一方通行の通路は、出る側の行にだけ載り、着く側の行は行き来できる先が無いと書く。"""
        written = _written(passage("p", ("井戸", "広場"), two_way=False), spots=(spot("井戸"), spot("広場")))

        assert written == "  井戸 (明るい) → 広場 まで 30 分\n  広場 (明るい) — 行き来できる先は無い"

    def test_hidden_passage_is_left_off(self) -> None:
        """見つかるまで隠れている通路は、地図に載らない。"""
        hidden = dataclasses.replace(passage("secret", ("井戸", "広場")), hidden_until_revealed=True)

        written = _written(hidden, spots=(spot("井戸"), spot("広場")))

        assert written == "  井戸 (明るい) — 行き来できる先は無い\n  広場 (明るい) — 行き来できる先は無い"

    def test_shorter_of_two_passages_to_the_same_place_is_shown(self) -> None:
        """同じ相手へ通路が 2 本あるとき、短いほうの時間だけを 1 度載せる。"""
        written = _written(
            passage("long", ("井戸", "広場"), travel_ticks=3),
            passage("short", ("井戸", "広場"), travel_ticks=1),
            spots=(spot("井戸"), spot("広場")),
        )

        assert written.splitlines()[0] == "  井戸 (明るい) → 広場 まで 30 分"

    def test_exits_are_ordered_by_time_then_name(self) -> None:
        """行き先は近い順に並び、同じ時間なら名前の順に並ぶ。"""
        written = _written(
            passage("a", ("井戸", "広場"), travel_ticks=2),
            passage("b", ("井戸", "倉庫"), travel_ticks=2),
            passage("c", ("井戸", "門"), travel_ticks=1),
            spots=(spot("井戸"), spot("広場"), spot("倉庫"), spot("門")),
        )

        assert written.splitlines()[0] == "  井戸 (明るい) → 門 まで 30 分 / 倉庫 まで 60 分 / 広場 まで 60 分"

    def test_places_follow_declaration_order_with_their_lighting(self) -> None:
        """場所は宣言の順に並び、それぞれの明るさの言葉が添えられる。"""
        written = _written(spots=(_lit("坑道", Lighting.PITCH_DARK), _lit("詰所", Lighting.DUSKY)))

        assert written == "  坑道 (真っ暗) — 行き来できる先は無い\n  詰所 (薄暗い) — 行き来できる先は無い"

    def test_minutes_follow_the_clock_of_a_day_that_does_not_divide_evenly(self) -> None:
        """1 日 100 tick の世界で 5 tick の通路は、時計と同じく 5 × 1440 ÷ 100 を切り捨てた 72 分と書く。"""
        declared = nouns(spots=(spot("井戸"), spot("広場")), passages=(passage("p", ("井戸", "広場"), travel_ticks=5),))
        day_night = dataclasses.replace(half_hour_ticks_from_midnight(), ticks_per_day=Ticks(100))

        written = WorldMap.drawn_from(declared).written_with(world_map_wording(), day_night)

        assert written.splitlines()[0] == "  井戸 (明るい) → 広場 まで 72 分"

    def test_world_without_day_night_counts_turns(self) -> None:
        """昼夜の無い世界では、所要時間を分ではなく tick の数で書く。"""
        declared = nouns(spots=(spot("井戸"), spot("広場")), passages=(passage("p", ("井戸", "広場"), travel_ticks=3),))

        written = WorldMap.drawn_from(declared).written_with(world_map_wording(), NoDayNight())

        assert written.splitlines()[0] == "  井戸 (明るい) → 広場 まで 3 手ぶん"


def _outdoor(name: str) -> SpotDeclaration:
    return dataclasses.replace(spot(name), atmosphere=dataclasses.replace(spot(name).atmosphere, outdoor=True))


class TestOutdoorPlaces:
    """屋外の場所の明るさが、夜や悪天候で暗くなることの分かる書き方で地図に載ることを保証する。"""

    def test_outdoor_place_says_its_lighting_is_by_day(self) -> None:
        """昼夜のある世界で、屋外の広場は「昼は明るい」と書き、屋内の井戸は「明るい」のまま書く。"""
        written = _written(passage("p", ("井戸", "広場")), spots=(spot("井戸"), _outdoor("広場")))

        assert written.splitlines() == ["  井戸 (明るい) → 広場 まで 30 分", "  広場 (昼は明るい) → 井戸 まで 30 分"]

    def test_outdoor_place_in_a_world_without_day_night_keeps_its_lighting(self) -> None:
        """昼夜の無い世界では、屋外の広場も「明るい」のまま書く。"""
        declared = nouns(spots=(_outdoor("広場"),), passages=())

        written = WorldMap.drawn_from(declared).written_with(world_map_wording(), NoDayNight())

        assert written == "  広場 (明るい) — 行き来できる先は無い"


class TestWorldMapWording:
    """WorldMapWording が、地図を描けない言い回しを作るときに断る挙動を保証する。"""

    def test_missing_lighting_word_is_refused(self) -> None:
        """明るさのどれかに言葉が無いと、ValueOutOfRangeException を投げる。"""
        lighting = dict(world_map_wording().lighting)
        del lighting[Lighting.DARK]

        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(world_map_wording(), lighting=lighting)

    @pytest.mark.parametrize("field", ["place", "place_without_exits", "exit", "minutes", "turns", "outdoor_lighting"])
    def test_unfillable_wording_is_refused(self, field: str) -> None:
        """言い回しに埋められない名前があると、ValueOutOfRangeException を投げる。"""
        fields: dict[str, object] = {field: "{unknown}"}

        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(world_map_wording(), **fields)  # type: ignore[arg-type]

    @pytest.mark.parametrize("wording", ["{spot.name}", "{spot[0]}"])
    def test_wording_reaching_into_a_value_is_refused(self, wording: str) -> None:
        """言い回しが値の属性や添字を読もうとすると、素の例外ではなく ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            dataclasses.replace(world_map_wording(), exit=wording)
