"""失敗の目撃文が、内部の識別子を漏らさないことを保証する。

## 実 run で見つかった

station_drill_005 で、同席者にこう届いていた。

    セナが気象記録簿のlog_weatherを試みたが、いまその手順に取りかかる段ではない。

`log_weather` は engine の識別子で、人が口にする言葉ではない。#892 が他の
section で潰した「engine の語彙をプロンプトに出さない」が、失敗観測に残って
いた。

## それ以上に、秘匿の穴

偽装版の action_name は `log_weather_pretend` である。**偽装が何かの前提で
失敗すると、`_pretend` という文字列が目撃者に配られる。** 秘匿役職の
シナリオでは、それだけで終わる。

station_drill_005 では 0 件だったが、偶然にすぎない。今の偽装は役割条件しか
持たないので、キーパーは失敗しない。役割で守った object 行動に前提条件を
1 つ足した瞬間に漏れる。

## display_label に直すと両方塞がる

本物と偽装は**同じ display_label** を持つ (それが偽装の成立条件だった)。
表示をラベルに切り替えると、失敗文も本物と偽装で同一になる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)   # crew
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    graph = rt._spot_graph_repo.find_graph()
    for pid in (_MORI, _SENA, _KUZE):
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(
            EntityId.create(int(pid)),
            SpotId.create(rt.id_mapper.get_int("spot", "hall")),
        )
    rt._spot_graph_repo.save(graph)
    return rt


def _witness_prose(runtime, player_id: PlayerId) -> list[str]:
    return [
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)
        if (e.output.structured or {}).get("type") == "spot_object_interaction_failed"
    ]


def _fail_a_step(runtime, actor: PlayerId) -> None:
    """段の噛み合わない手を出して失敗させる (2 段目をいきなり試す)。"""
    try:
        runtime.do_interact(actor, "weather_log", "log_weather_2")
    except Exception:
        pass


class TestNoInternalIdentifierReachesWitnesses:
    """目撃文に内部の識別子が出ない。"""

    def test_the_action_name_is_not_shown(self, runtime) -> None:
        """`log_weather_2` のような識別子が文に出ない。"""
        _fail_a_step(runtime, _MORI)

        prose = _witness_prose(runtime, _SENA)
        assert prose, "失敗の目撃が届いていない"
        assert "log_weather" not in prose[-1], prose[-1]

    def test_the_display_label_is_shown_instead(self, runtime) -> None:
        """代わりにシナリオが書いた日本語が出る。

        識別子を消すだけだと「何を試みたのか」が分からなくなる。他者の
        失敗から学べることが元の狙いなので、意味は残す。
        """
        _fail_a_step(runtime, _MORI)

        assert "気象を記録する" in _witness_prose(runtime, _SENA)[-1]

    def test_the_reason_is_still_shown(self, runtime) -> None:
        """失敗の理由は今までどおり伝わる。"""
        _fail_a_step(runtime, _MORI)

        assert "段ではない" in _witness_prose(runtime, _SENA)[-1]


class TestTheFakeIsIndistinguishableWhenItFails:
    """偽装が失敗しても、本物の失敗と見分けがつかない。"""

    def test_the_pretend_suffix_never_reaches_a_witness(self, runtime) -> None:
        """`_pretend` が目撃者に届かない。

        **これが本テストの主眼。** 届いた時点で秘匿役職は終わる。
        """
        # 役割条件を満たさない crew に偽装版を出させて失敗させる。
        # (キーパー自身は役割条件を満たすので失敗しない)
        try:
            runtime.do_interact(_MORI, "weather_log", "log_weather_pretend")
        except Exception:
            pass

        for prose in _witness_prose(runtime, _SENA):
            assert "pretend" not in prose, prose

    def test_a_role_rejected_attempt_is_not_broadcast_at_all(self, runtime) -> None:
        """役割で弾かれた失敗は、目撃者に一切配られない。

        ラベルに直しても**理由の文が役割を明かす**。「その手順は自分の
        担当ではない」が同席者に届けば、その人が担当外だと分かる。

        本人にはツール結果として返るので、学習材料は失われない。#905 で
        候補一覧に置いたのと同じ原則を、失敗観測にも通す。
        """
        before = len(_witness_prose(runtime, _SENA))

        try:
            runtime.do_interact(_KUZE, "weather_log", "log_weather_2")
        except Exception:
            pass

        assert len(_witness_prose(runtime, _SENA)) == before

    def test_a_normal_failure_is_still_broadcast(self, runtime) -> None:
        """役割と無関係な失敗は今までどおり配られる。

        消しすぎると「他者の失敗から学ぶ」という元の狙いが消える。
        """
        before = len(_witness_prose(runtime, _SENA))

        try:
            runtime.do_interact(_MORI, "weather_log", "log_weather_2")
        except Exception:
            pass

        assert len(_witness_prose(runtime, _SENA)) > before
