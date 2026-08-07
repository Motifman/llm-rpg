"""役割で弾かれる行動を、他の役割の人に見せないことを保証する。

## 実 run で見つかった漏れ

`station_drill` の配線箱の行が、crew にもこう出ていた。

    - "配線箱" — … [配線の結束を締め直す (tighten_wiring),
                    配線の結束を締め直す (tighten_wiring_pretend)]

`tighten_wiring_pretend` は keeper 専用 (`PLAYER_STATE_IS {role: keeper}`)。
crew が呼ぶと `その手順は自分の担当ではない` で弾かれる。

2 つまずい。

1. **秘匿が漏れる。** crew は自分の行動候補を読むだけで「この作業には偽装版
   がある」と分かる。役割を伏せる意味が薄れる
2. **選べるのに必ず失敗する手が並ぶ。** #860 で潰した形そのもの

## なぜ「いまできない」にも出さないのか

この一覧には満たしていない前提条件を「いまできない」に回す仕組みがある
(`blocking_hints`)。物理的な条件 (暗すぎる / 部品が足りない) はそこに出す
のが正しい。**役割は違う。** 「いまできない」に回しても、偽装版が存在する
ことは伝わってしまう。

行ごと消す。#860 で同席者の行に置いた不変条件と同じ:
**その行に出す判断の材料は、見る人に既に見えている事実だけに限る。**
役割は見えていないので、役割で決まる候補は出せない。
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

_MORI = PlayerId(1)   # crew (気象記録の担当)
_SENA = PlayerId(2)   # crew (配線箱の担当)
_KUZE = PlayerId(3)   # keeper


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    graph = rt._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(_MORI)))
    graph.place_entity(
        EntityId.create(int(_MORI)),
        SpotId.create(rt.id_mapper.get_int("spot", "storage")),
    )
    rt._spot_graph_repo.save(graph)
    rt.build_observation(_MORI)
    rt.do_interact(_MORI, "emergency_lantern_case", "take_lantern")
    graph = rt._spot_graph_repo.find_graph()
    for pid in (_MORI, _SENA, _KUZE):
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(
            EntityId.create(int(pid)),
            SpotId.create(rt.id_mapper.get_int("spot", "corridor")),
        )
    rt._spot_graph_repo.save(graph)
    return rt


def _object_lines(runtime, player_id: PlayerId) -> str:
    """配線箱に関する行 (候補一覧と「いまできない」の両方) をまとめて返す。"""
    lines = runtime.build_observation(player_id).splitlines()
    picked = []
    for i, line in enumerate(lines):
        if "配線箱" in line:
            picked.append(line)
            if i + 1 < len(lines) and "いまできない" in lines[i + 1]:
                picked.append(lines[i + 1])
    return "\n".join(picked)


class TestTheFakeActionIsHiddenFromCrew:
    """偽装版は keeper にしか見えない。"""

    def test_crew_does_not_see_it(self, runtime) -> None:
        """crew の行に偽装版が出ない。

        ここが本テストの主眼。出ると「偽装という手がある」ことが
        全員に伝わる。
        """
        assert "tighten_wiring_pretend" not in _object_lines(runtime, _MORI)

    def test_it_is_not_pushed_into_the_blocked_list_either(self, runtime) -> None:
        """「いまできない」にも出ない。

        **消し方を間違えると、こちらに移るだけで漏れは残る。** 候補から
        外して blocked に回す実装だと上のテストは通ってしまう。
        """
        assert "偽装" not in _object_lines(runtime, _MORI)
        assert "pretend" not in _object_lines(runtime, _MORI)

    def test_the_keeper_still_sees_it(self, runtime) -> None:
        """keeper には出る。

        消しすぎると偽装そのものができなくなる。
        """
        assert "tighten_wiring_pretend" in _object_lines(runtime, _KUZE)


class TestUnrelatedActionsAreUntouched:
    """役割と関係の無い行動は今までどおり出る。"""

    def test_the_assigned_crew_sees_the_real_task(self, runtime) -> None:
        """本物の作業は、担当のクルーには出る。

        本物は `PLAYER_STATE_IS {role: crew, duty: wiring}` で守られている。
        keeper に出ないだけでなく、**担当外のクルーにも出ない**。
        ここで確かめるのは、守りすぎて担当者にも出なくなっていないこと。
        """
        line = _object_lines(runtime, _SENA)

        assert '"tighten_wiring"' in line

    def test_the_keeper_does_not_see_the_real_task(self, runtime) -> None:
        """keeper には本物の作業が出ない。

        出ると「本当は自分にはできない作業」を試し続ける。裏返しの同じ問題。
        """
        line = _object_lines(runtime, _KUZE)
        # 偽装版は含まれるので、本物だけを見分ける。
        assert "tighten_wiring," not in line
        assert "(tighten_wiring)" not in line

    def test_actions_without_a_role_condition_are_shown(self, runtime) -> None:
        """役割条件を持たない行動は誰にでも出る。

        消す範囲を広げすぎていないかを見る。集会室の当番表は誰でも読める。
        """
        graph = runtime._spot_graph_repo.find_graph()
        graph.unplace_entity(EntityId.create(int(_MORI)))
        graph.place_entity(
            EntityId.create(int(_MORI)),
            SpotId.create(runtime.id_mapper.get_int("spot", "hall")),
        )
        runtime._spot_graph_repo.save(graph)

        assert "read_board" in runtime.build_observation(_MORI)
