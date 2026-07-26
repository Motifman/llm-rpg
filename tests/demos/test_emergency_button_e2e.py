"""緊急招集ボタンで会議が始まることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 8 後半。

## なぜ tool ではなく場所に置く object にしたか

tool にすると、どこからでも呼べる「会議を開く権利」になる。本家の緊急
ボタンは会議室にあり、**押しに行く**必要がある。押しに行く途中で襲われる、
ボタンの前に誰が居たかが手がかりになる、といった質感はすべて「そこまで
移動する」から生まれる。

## 配線が無いときに黙って捨てない

TELEPORT_ENTITY は長らく「spec を組み立てるだけで消費者が居ない」状態で、
シナリオに書いても何も起きない dead code だった (隠し通路・ベント・魔法陣
が表現できない原因)。同じ形を避けるため、CALL_MEETING が宣言されているのに
招集の配線が無い構成は例外で止める。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _press(runtime, player_id: PlayerId):
    return runtime.do_interact(player_id, "emergency_button", "press_emergency_button")


class TestPressingTheButton:
    """ボタンを押すと会議が始まる。"""

    def test_a_meeting_begins(self, runtime) -> None:
        """押した時点でフェーズが会議に変わる。

        **これが本 PR の目的**。ここまで会議を始める手段は死体の報告だけ
        だった。誰も倒れていない状況で疑いを共有する手段が無いと、襲われる
        まで誰も何も言えない。
        """
        _press(runtime, _KUZE)

        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_everyone_gathers_at_the_button(self, runtime) -> None:
        """押した人の場所に全員が集まる。

        集めないと、発話が hop 越しに届かない相手が出る (設計 doc H-3)。

        **先に散らすのが要点。** 全員が hall 生まれなので、散らさないと
        「集まっている」が最初から成立していて何も確かめられない。同じ
        空振りを #865 で一度作っている。
        """
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = runtime._spot_graph_repo.find_graph()
        for pid, spot_name in ((_MORI, "storage"), (_SENA, "corridor")):
            graph.unplace_entity(EntityId.create(int(pid)))
            graph.place_entity(
                EntityId.create(int(pid)),
                SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
            )
        runtime._spot_graph_repo.save(graph)

        def _spot_of(pid):
            g = runtime._spot_graph_repo.find_graph()
            return g.get_entity_spot(EntityId.create(int(pid)))

        assert len({_spot_of(p) for p in (_MORI, _SENA, _KUZE)}) == 3

        _press(runtime, _KUZE)

        assert len({_spot_of(p) for p in (_MORI, _SENA, _KUZE)}) == 1

    def test_the_button_can_only_be_used_once(self, runtime) -> None:
        """同じ人は二度押せない。

        持ち札は一人 1 回。二度押せると、疑われた側が会議を連発して議論を
        流せる。
        """
        _press(runtime, _KUZE)
        runtime.end_meeting(reason="vote_concluded")

        second = _press(runtime, _KUZE)

        # 二度目は interaction 自体は成立するが、招集は拒否される。
        # **拒否の理由が本人に返ることまで確かめる。** 返らないと「押した。
        # 以上」だけが残り、なぜ集まらなかったのか分からない。
        assert any("二度" in m for m in second.messages), second.messages


class TestTheWiringIsNotOptional:
    """招集の配線が無い構成は起動を通さない。"""

    def test_an_unwired_service_raises(self, runtime) -> None:
        """配線を外した状態で押すと例外になる。

        **黙って捨てない**ことが要点。捨てると「シナリオに書いたのに
        押しても何も起きない」になり、trace には成功した interact だけが
        残る。TELEPORT_ENTITY で実際に起きた形。
        """
        from ai_rpg_world.application.common.exceptions import ApplicationException

        runtime._interaction_service.set_meeting_caller(None)

        with pytest.raises(ApplicationException):
            _press(runtime, _MORI)
