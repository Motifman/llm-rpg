"""追放された者がその場から居なくなることを保証する。

## キルと追放は違う

    キル   自由時間に密室で起きる。誰も知らない。**死体はその場に残り**、
           見つけた者が通報できる。
    追放   会議の最後に全員の前で決まる。結果も全員に届いている。
           死体を残す理由が無い。

実 run では追放された者が graph に残り、同席者行にこう出続けていた。

    - "クゼ" (死亡している) 〔手ぶら〕 [背後から襲う, 持ち物を奪う, tend_to_player]

#912 で行動候補は消えたが、**行そのものは残っていた**。全員の前で追放した
相手が、その後もずっと同じ部屋に「居る」ことになる。

## 死体は消さない

念のため書いておく。この PR で消すのは**追放**された者だけ。殺された者の
死体を消すと通報が成立しなくなる。
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

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _row_for(runtime, name: str, viewer: PlayerId = _MORI) -> str:
    for line in runtime.build_observation(viewer).splitlines():
        if name in line and '"' in line:
            return line
    return ""


def _is_placed(runtime, player_id: PlayerId) -> bool:
    graph = runtime._spot_graph_repo.find_graph()
    try:
        graph.get_entity_spot(EntityId.create(int(player_id)))
        return True
    except Exception:
        return False


class TestEjectionRemovesThePlayer:
    """追放された者は世界から居なくなる。"""

    def test_they_leave_the_graph(self, runtime) -> None:
        """graph 上に居なくなる。"""
        assert _is_placed(runtime, _KUZE)

        runtime.eject_player(_KUZE)

        assert not _is_placed(runtime, _KUZE)

    def test_their_row_disappears(self, runtime) -> None:
        """同席者行から消える。

        **これが実 run で残っていた。** 全員の前で追放した相手が、その後も
        ずっと同じ部屋に「居る」ことになっていた。
        """
        runtime.eject_player(_KUZE)

        assert _row_for(runtime, "クゼ") == ""

    def test_the_outcome_is_still_recorded(self, runtime) -> None:
        """追放そのものは記録に残る。

        graph から外すのは配置の話で、勝敗の判定はこちらを見る。
        """
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )

        runtime.eject_player(_KUZE)

        assert runtime._player_outcome_registry.get_outcome(_KUZE) is (
            PlayerOutcomeEnum.EJECTED
        )


class TestAKilledBodyStays:
    """殺された者の死体は残る。"""

    def test_the_corpse_is_still_in_the_room(self, runtime) -> None:
        """倒れた相手は graph 上に残る。

        **消すと通報が成立しない。** 追放と同じ扱いにしてはいけない。
        """
        status = runtime._player_status_repo.find_by_id(_SENA)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)

        assert _is_placed(runtime, _SENA)
        assert _row_for(runtime, "セナ") != ""


class TestMeetingsSkipTheEjected:
    """会議の集合が、追放された者を巻き込まない。"""

    def test_gathering_does_not_fail_on_an_ejected_player(self, runtime) -> None:
        """追放者が居ても集合が成立する。

        追放者は graph 上に居ないので、集めようとすると例外になる。
        握り潰されて warning に落ちるだけだが、**毎回無駄な失敗が出る**。
        """
        runtime.eject_player(_KUZE)
        for pid, spot in ((_MORI, "corridor"), (_SENA, "storage")):
            graph = runtime._spot_graph_repo.find_graph()
            graph.unplace_entity(EntityId.create(int(pid)))
            graph.place_entity(
                EntityId.create(int(pid)),
                SpotId.create(runtime.id_mapper.get_int("spot", spot)),
            )
            runtime._spot_graph_repo.save(graph)

        assert runtime.call_emergency_meeting(_AOI).success

        graph = runtime._spot_graph_repo.find_graph()
        gathered = {
            int(graph.get_entity_spot(EntityId.create(int(p))))
            for p in (_MORI, _SENA, _AOI)
        }
        assert len(gathered) == 1

    def test_the_ejected_player_is_not_brought_back(self, runtime) -> None:
        """集合で呼び戻されない。"""
        runtime.eject_player(_KUZE)

        runtime.call_emergency_meeting(_AOI)

        assert not _is_placed(runtime, _KUZE)
