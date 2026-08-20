"""シナリオに書いた空腹の進み方が、実際に世界を動かすところまでを見る。

## なぜこの試験が要るか

**宣言を読めることと、宣言が効くことは別**である。設定に値が入っていても、
世界を組むところで渡し忘れれば既定のまま進み、**変えたつもりで変わっていない
run** になる。しかも例外は出ない — run が終わって「空腹が上がっていない」で
しか気づけない。#1189 (初期注文が trace に残らない) と同じ形の静かな失敗。

そこで**実際に手番を進めて、空腹が宣言どおり増えること**まで見る。読み込みの
単体試験は上流にあるが、上流が正しくても材料が届かなければ意味がない。

さらに、**宣言しない世界がいまと同じ進み方のまま**であることも見る。既定が
動くと過去の run と比べられなくなる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v1.json"
)

_TICKS = 5


def _world(tmp_path: Path, needs: Dict[str, Any] | None) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    if needs is None:
        raw.pop("needs", None)
    else:
        raw["needs"] = needs
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _need_after_ticks(runtime: Any, need: NeedType, ticks: int) -> int:
    before = _need(runtime, need)
    for _ in range(ticks):
        runtime.advance_tick()
    return _need(runtime, need) - before


def _need(runtime: Any, need: NeedType) -> int:
    status = runtime._player_status_repo.find_by_id(PlayerId(1))
    return int(status.needs.get(need).value)


class TestTheDeclaredRateReachesTheWorld:
    """宣言した進み方で、実際に空腹が増える。"""

    def test_a_declared_hunger_rate_doubles_the_pace(self, tmp_path: Path) -> None:
        """`hunger_per_tick: 2` の世界では、5 手番で空腹が 10 増える。"""
        runtime = _world(tmp_path, {"hunger_per_tick": 2})

        assert _need_after_ticks(runtime, NeedType.HUNGER, _TICKS) == 10

    def test_a_declared_fatigue_rate_makes_idling_tiring(self, tmp_path: Path) -> None:
        """`fatigue_per_tick: 1` を宣言すると、何もしなくても疲労が増える。

        既定では行動でのみ増えるので、**宣言しない限りここは 0 のまま**。
        """
        runtime = _world(tmp_path, {"fatigue_per_tick": 1})

        assert _need_after_ticks(runtime, NeedType.FATIGUE, _TICKS) == 5


class TestAWorldThatDeclaresNothingDoesNotMove:
    """宣言しない世界は、いまと同じ進み方のまま (**正の対照**)。"""

    def test_hunger_still_rises_by_one_per_tick(self, tmp_path: Path) -> None:
        """`needs` 節を書かない世界の空腹は、5 手番で 5 増える。"""
        runtime = _world(tmp_path, None)

        assert _need_after_ticks(runtime, NeedType.HUNGER, _TICKS) == 5

    def test_fatigue_still_does_not_rise_on_its_own(self, tmp_path: Path) -> None:
        """`needs` 節を書かない世界では、何もしなければ疲労は増えない。"""
        runtime = _world(tmp_path, None)

        assert _need_after_ticks(runtime, NeedType.FATIGUE, _TICKS) == 0

    def test_declaring_only_starvation_damage_leaves_the_pace_alone(
        self, tmp_path: Path,
    ) -> None:
        """飢餓ダメージだけを宣言した世界も、空腹の進み方は既定のまま。

        既存シナリオ (`needs` に飢餓ダメージだけ書いてある) の挙動を
        **1 ミリも変えない**ことを見る。
        """
        runtime = _world(tmp_path, {"starvation_damage_per_tick": 1})

        assert _need_after_ticks(runtime, NeedType.HUNGER, _TICKS) == 5
