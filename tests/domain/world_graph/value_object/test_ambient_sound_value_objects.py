"""AmbientSound 系値オブジェクトのテスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    AmbientSoundAtlasValidationException,
    AmbientSoundConfigValidationException,
    AmbientSoundDefValidationException,
    AmbientSoundFilterValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundAtlas,
    AmbientSoundConfig,
    AmbientSoundThrottleConfig,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_def import (
    AmbientSoundDef,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_filter import (
    AmbientSoundFilter,
)


def _def(*, id_: str, tags: tuple = ()) -> AmbientSoundDef:
    return AmbientSoundDef(
        id=id_,
        tags=frozenset(tags),
        prose="どこかで音がする",
        probability_per_tick=0.05,
        sound_strength=0.3,
        filters=AmbientSoundFilter(),
    )


class TestAmbientSoundFilter:
    """AmbientSoundFilter のマッチング・バリデーション挙動。"""

    def test_default_matches_anything(self) -> None:
        """既定値（全て None / False）のフィルタは全条件にマッチする。"""
        f = AmbientSoundFilter()
        assert f.matches_phase("night") is True
        assert f.matches_phase(None) is True
        assert f.matches_weather("RAIN") is True
        assert f.matches_weather(None) is True
        assert f.matches_outdoor(True) is True
        assert f.matches_outdoor(False) is True

    def test_phases_filter(self) -> None:
        """phases に含まれるフェーズ名のみマッチし、None は不一致扱い。"""
        f = AmbientSoundFilter(phases=frozenset({"night"}))
        assert f.matches_phase("night") is True
        assert f.matches_phase("day") is False
        assert f.matches_phase(None) is False

    def test_weather_filter(self) -> None:
        """weather_types に含まれる天候のみマッチし、None は不一致扱い。"""
        f = AmbientSoundFilter(weather_types=frozenset({"RAIN"}))
        assert f.matches_weather("RAIN") is True
        assert f.matches_weather("CLEAR") is False
        assert f.matches_weather(None) is False

    def test_indoor_only_blocks_outdoor(self) -> None:
        """indoor_only=True は屋外スポットでの発火をブロックする。"""
        f = AmbientSoundFilter(indoor_only=True)
        assert f.matches_outdoor(False) is True
        assert f.matches_outdoor(True) is False

    def test_outdoor_only_blocks_indoor(self) -> None:
        """outdoor_only=True は屋内スポットでの発火をブロックする。"""
        f = AmbientSoundFilter(outdoor_only=True)
        assert f.matches_outdoor(True) is True
        assert f.matches_outdoor(False) is False

    def test_both_only_flags_rejected(self) -> None:
        """indoor_only と outdoor_only を同時に True にすると ValidationException を投げる。"""
        with pytest.raises(AmbientSoundFilterValidationException):
            AmbientSoundFilter(indoor_only=True, outdoor_only=True)


class TestAmbientSoundDef:
    """AmbientSoundDef のバリデーション挙動。"""

    def test_valid_def(self) -> None:
        """正常な値で構築できる。"""
        d = _def(id_="x", tags=("a",))
        assert d.id == "x"

    @pytest.mark.parametrize("p", [-0.01, 1.01])
    def test_probability_out_of_range(self, p: float) -> None:
        """probability_per_tick が [0.0, 1.0] の範囲外なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundDefValidationException, match="probability"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="p",
                probability_per_tick=p, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )

    @pytest.mark.parametrize("s", [-0.01, 1.01])
    def test_strength_out_of_range(self, s: float) -> None:
        """sound_strength が [0.0, 1.0] の範囲外なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundDefValidationException, match="sound_strength"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="p",
                probability_per_tick=0.5, sound_strength=s,
                filters=AmbientSoundFilter(),
            )

    def test_empty_id_rejected(self) -> None:
        """id が空文字列なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundDefValidationException, match="id"):
            AmbientSoundDef(
                id="", tags=frozenset(), prose="p",
                probability_per_tick=0.5, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )

    def test_empty_prose_rejected(self) -> None:
        """prose が空文字列なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundDefValidationException, match="prose"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="",
                probability_per_tick=0.5, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )


class TestAmbientSoundAtlas:
    """AmbientSoundAtlas の基本操作と一意性検証。"""

    def test_empty_atlas(self) -> None:
        """空 atlas は is_empty()=True を返し、候補抽出も空。"""
        atlas = AmbientSoundAtlas(defs=())
        assert atlas.is_empty()
        assert atlas.candidates_for_tags(frozenset({"x"})) == ()

    def test_duplicate_ids_rejected(self) -> None:
        """同一 id の def が複数あると ValidationException を投げる。"""
        with pytest.raises(AmbientSoundAtlasValidationException, match="Duplicate"):
            AmbientSoundAtlas(defs=(_def(id_="a"), _def(id_="a")))

    def test_find_by_id(self) -> None:
        """id 指定で def を取り出せる。未登録 id は None。"""
        atlas = AmbientSoundAtlas(defs=(_def(id_="drip"), _def(id_="wind")))
        assert atlas.find_by_id("drip") is not None
        assert atlas.find_by_id("none") is None

    def test_candidates_for_tags_intersects(self) -> None:
        """spot_tags と def.tags が交差する def をすべて返す。"""
        atlas = AmbientSoundAtlas(defs=(
            _def(id_="a", tags=("wet",)),
            _def(id_="b", tags=("windy",)),
            _def(id_="c", tags=("wet", "abandoned")),
        ))
        result = atlas.candidates_for_tags(frozenset({"wet"}))
        assert {d.id for d in result} == {"a", "c"}

    def test_candidates_with_empty_spot_tags(self) -> None:
        """spot_tags が空集合なら候補も空。"""
        atlas = AmbientSoundAtlas(defs=(_def(id_="a", tags=("wet",)),))
        assert atlas.candidates_for_tags(frozenset()) == ()


class TestAmbientSoundThrottleConfig:
    """AmbientSoundThrottleConfig のバリデーション挙動。"""

    def test_negative_gap_rejected(self) -> None:
        """min_gap_ticks_per_player が負の値なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundConfigValidationException):
            AmbientSoundThrottleConfig(min_gap_ticks_per_player=-1)

    def test_negative_dedup_rejected(self) -> None:
        """dedup_window_size が負の値なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundConfigValidationException):
            AmbientSoundThrottleConfig(dedup_window_size=-1)


class TestAmbientSoundConfig:
    """AmbientSoundConfig のバリデーション挙動。"""

    def test_invalid_interval_rejected(self) -> None:
        """update_interval_ticks が 0 以下なら ValidationException を投げる。"""
        with pytest.raises(AmbientSoundConfigValidationException):
            AmbientSoundConfig(
                enabled=True,
                update_interval_ticks=0,
                throttle=AmbientSoundThrottleConfig(),
                atlas=AmbientSoundAtlas(defs=()),
            )

    def test_valid_config(self) -> None:
        """正常な値で構築でき、フィールドが反映される。"""
        cfg = AmbientSoundConfig(
            enabled=True,
            update_interval_ticks=3,
            throttle=AmbientSoundThrottleConfig(),
            atlas=AmbientSoundAtlas(defs=()),
        )
        assert cfg.update_interval_ticks == 3
