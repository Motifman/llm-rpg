"""作業とその偽装が、シナリオの宣言だけで成立することを保証する。

## 何を確かめたいか

本家のインポスターは**作業のふりができる**。これが無いと、作業をしていない
人が即座に割れてしまい、疑いの余地が消える。

engine に「偽の作業」という概念を足さずに書けるはず、という読みでこの
シナリオを組んだ。同じ対象に 2 つの interaction を宣言し、

- クルー版: `PLAYER_STATE_IS {role: crew}` → フラグを立てる
- 偽装版:   `PLAYER_STATE_IS {role: keeper}` → 何も立てない

の 2 つに、**同じ display_label と同じ witness_observation_message** を持たせる。
第三者に届く文が同一なら、外からは区別が付かない。

このテストはその読みが当たっているかを実地で確かめる。落ちるなら、engine 側に
「効果だけを条件付きにする」仕組みが要るということになる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)   # crew
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper
_AOI = PlayerId(4)    # crew


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _move_to(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
    )
    runtime._spot_graph_repo.save(graph)


def _progress(runtime) -> str:
    for line in runtime.build_observation(_MORI).splitlines():
        if "作業の進み" in line:
            return line
    return ""


def _witness_prose(runtime, player_id: PlayerId) -> list[str]:
    return [e.output.prose for e in runtime._obs_buffer.get_observations(player_id)]


class TestCrewWorkCounts:
    """クルーの作業は進捗になる。"""

    def test_completing_one_advances_the_progress(self, runtime) -> None:
        """1 個終わらせると 1 進む。"""
        _move_to(runtime, _MORI, "corridor")

        result = runtime.do_interact(_MORI, "junction_box", "tighten_wiring")

        assert result is not None
        assert "1/5" in _progress(runtime)

    def test_four_of_five_reach_the_threshold(self, runtime) -> None:
        """5 つのうち 4 つで必要数に到達する。

        全部を要求すると、1 人倒れただけで詰む。余白を 1 つ残す。

        救難信号 (distress_sent) も 5 つのうちの 1 つ。独立した勝利条件に
        すると **OR で評価されて一人勝ちの経路が残る**ため、作業と同じ
        並びに畳んである。
        """
        for player, spot, obj, action in (
            (_MORI, "corridor", "junction_box", "tighten_wiring"),
            (_SENA, "generator_room", "fuel_gauge", "log_fuel"),
            (_AOI, "radio_room", "antenna_panel", "align_antenna"),
            (_MORI, "storage", "inventory_ledger", "count_supplies"),
        ):
            _move_to(runtime, player, spot)
            runtime.do_interact(player, obj, action)

        assert "必要数に到達" in _progress(runtime)


class TestTheKeeperCanPretend:
    """襲う側は作業のふりができる。"""

    def test_pretending_does_not_advance_the_progress(self, runtime) -> None:
        """ふりをしても進捗は増えない。

        増えたら偽装ではなく本当の作業になる。
        """
        _move_to(runtime, _KUZE, "corridor")

        runtime.do_interact(_KUZE, "junction_box", "tighten_wiring_pretend")

        assert "0/5" in _progress(runtime)

    def test_the_keeper_cannot_do_the_real_one(self, runtime) -> None:
        """本物の手順は使えない。

        使えると、襲う側が勝ち筋を進めてしまう。
        """
        _move_to(runtime, _KUZE, "corridor")

        with pytest.raises(Exception):
            runtime.do_interact(_KUZE, "junction_box", "tighten_wiring")

    def test_a_witness_cannot_tell_the_difference(self, runtime) -> None:
        """**目撃者に届く文が、本物とふりで同一になる。**

        ここが本テストの主眼。違う文が届くなら、engine に「効果だけを
        条件付きにする」仕組みを足さないと偽装が成立しない。
        """
        _move_to(runtime, _MORI, "corridor")
        _move_to(runtime, _KUZE, "corridor")
        _move_to(runtime, _SENA, "corridor")

        runtime.do_interact(_MORI, "junction_box", "tighten_wiring")
        real = [p for p in _witness_prose(runtime, _SENA) if "配線箱" in p]

        runtime.do_interact(_KUZE, "junction_box", "tighten_wiring_pretend")
        after = [p for p in _witness_prose(runtime, _SENA) if "配線箱" in p]
        fake = after[len(real):]

        assert real and fake, (real, after)
        # 行為者の名前だけを差し替えれば一致するはず。
        assert real[-1].replace("モリ", "＿") == fake[-1].replace("クゼ", "＿")


class TestDuplicateObjectIdsAreRejected:
    """同じ場所に同じ id の対象を 2 つ書けない。

    **この PR で実際に踏んだ。** 物資庫に既にあった `supply_shelf` と同じ id で
    作業対象を足したところ、JSON には確かに書いてあるのに実行時は
    「そんな操作は無い」で落ちた。後から書いたほうが引けなくなるためで、
    症状から原因にたどり着くまでが長い。読み込み時に止める。
    """

    def test_a_duplicate_id_fails_to_load(self, tmp_path) -> None:
        """重複した object id は読み込み時に落ちる。"""
        import json

        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
            ScenarioLoader,
        )

        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        storage = [s for s in raw["spots"] if s["id"] == "storage"][0]
        duplicate = dict(storage["interior"]["objects"][0])
        storage["interior"]["objects"].append(duplicate)
        path = tmp_path / "dup.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(path)
