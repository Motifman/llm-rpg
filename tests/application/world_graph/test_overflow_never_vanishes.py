"""持ちきれなかった品は、黙って消えずに行き先へ渡る。

`PlayerInventoryAggregate.acquire_item` は満杯だと**黙って品を捨てる** (溢れ
イベントを出して return する)。そのイベントを publish する経路はどこにも無い
ので、結果メッセージにも観測にも trace にも残らない。

10 経路を個別に直しても、**11 個目を足した人が同じ穴を空ける**。溢れを捕まえる
場所は付与ヘルパー 1 箇所にして、行き先を**必須引数**で受ける。渡し忘れは型
エラーになるので、新しい経路を足す人は書いた瞬間に「溢れをどうするか」を
決めることになる。

品は**入るぶんだけ作る**。作ってから捨てると、`item_repository` に持ち主の
いない instance が残る。
"""

from __future__ import annotations

import inspect
from typing import Any, List, Tuple

import pytest


from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PLAYER = PlayerId(1)


class _Sink:
    """溢れを受け取ったことだけを覚えておく行き先。"""

    def __init__(self) -> None:
        self.calls: List[Tuple[PlayerId, Tuple[ItemSpecId, ...]]] = []

    def __call__(self, player_id: PlayerId, spec_ids: Tuple[ItemSpecId, ...]) -> None:
        self.calls.append((player_id, tuple(spec_ids)))

    @property
    def overflowed(self) -> Tuple[ItemSpecId, ...]:
        return tuple(spec for _pid, specs in self.calls for spec in specs)


@pytest.fixture()
def world(tmp_path) -> Any:
    """薬草のある市場町を 1 人で立てる。"""
    import json
    from pathlib import Path

    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    town = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"
    path = tmp_path / "market_town_v1.json"
    path.write_text(town.read_text(encoding="utf-8"), encoding="utf-8")
    return create_world_runtime(str(path))


@pytest.fixture()
def herb(world: Any) -> int:
    return world._item_spec_repo.find_by_name("薬草").item_spec_id.value


def _held(runtime: Any, spec_id: int) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return sum(c for s, c in counts.items() if s.value == spec_id)


def _free_slots(runtime: Any) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    return int(inventory.get_inventory_summary()["empty_inventory_slots"])


def _grant(runtime: Any, spec_id: int, count: int, sink: Any) -> None:
    grant_item_specs_to_inventory(
        _PLAYER,
        tuple(ItemSpecId.create(spec_id) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=sink,
    )


class TestWhatFitsGoesInAndTheRestGoesToTheSink:
    """入るぶんは所持品へ、入らないぶんは行き先へ。"""

    def test_everything_fits_when_there_is_room(self, world: Any, herb: int) -> None:
        """空きがあるぶんは、そのまま所持品に入る。"""
        sink = _Sink()

        _grant(world, herb, 3, sink)

        assert _held(world, herb) == 3

    def test_the_sink_is_left_alone_when_everything_fits(
        self, world: Any, herb: int
    ) -> None:
        """全部入るときは、行き先が呼ばれない (**正の対照**)。

        毎回呼んでいると、地面に落ちる観測が入らなかったときにも出てしまう。
        """
        sink = _Sink()

        _grant(world, herb, 3, sink)

        assert sink.calls == []

    def test_the_overflow_goes_to_the_sink(self, world: Any, herb: int) -> None:
        """空きを超えたぶんは、行き先へ渡る。"""
        free = _free_slots(world)
        sink = _Sink()

        _grant(world, herb, free + 2, sink)

        assert len(sink.overflowed) == 2
        assert all(spec.value == herb for spec in sink.overflowed)

    def test_everything_goes_to_the_sink_when_full(self, world: Any, herb: int) -> None:
        """最初から満杯なら、渡した全部が行き先へ行く。"""
        _grant(world, herb, _free_slots(world), _Sink())
        sink = _Sink()

        _grant(world, herb, 3, sink)

        assert len(sink.overflowed) == 3

    def test_the_player_is_told_to_the_sink(self, world: Any, herb: int) -> None:
        """行き先には、誰の溢れかも渡る (落とす場所を決めるのに要る)。"""
        free = _free_slots(world)
        sink = _Sink()

        _grant(world, herb, free + 1, sink)

        assert sink.calls[0][0] == _PLAYER


class TestNoOrphanInstancesAreLeftBehind:
    """入らない品は、そもそも作らない。"""

    def test_only_what_fits_is_created(self, world: Any, herb: int) -> None:
        """作られる instance は、所持品に入ったぶんだけ。

        作ってから捨てると、`item_repository` に**持ち主のいない instance**が
        残る。数を数える分析 (世界にいくつあるか) が狂い、腐敗の対象にも
        入り続ける。
        """
        free = _free_slots(world)
        before = len(world._item_repo.find_by_spec_id(ItemSpecId.create(herb)))

        _grant(world, herb, free + 5, _Sink())

        created = len(world._item_repo.find_by_spec_id(ItemSpecId.create(herb))) - before
        assert created == free


class TestTheSinkCannotBeForgotten:
    """行き先は必須引数で、渡し忘れが型エラーになる。"""

    def test_the_sink_is_a_required_argument(self) -> None:
        """`overflow_sink` に既定値が無い。

        既定値を置くと**渡し忘れが今日と同じ静かな失敗に戻る**。新しい付与
        経路を足した人が、書いた瞬間に「溢れをどうするか」を決めることに
        なる形を、署名そのもので守る。
        """
        parameter = inspect.signature(grant_item_specs_to_inventory).parameters[
            "overflow_sink"
        ]

        assert parameter.default is inspect.Parameter.empty
