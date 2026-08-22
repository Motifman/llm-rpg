"""gold を世界のものへ納められる (供物競争の土台、PR ②)。

供物競争シナリオは「gold を祭壇へ納める」を勝利条件の一部にする。engine には
gold を減らす interaction 効果が無かったので、次の 3 点を足した。

1. `DEPOSIT_GOLD_TO_OBJECT`: 行為者の gold を object.state の累積値へ移す
2. `PLAYER_GOLD_AT_LEAST`: 所持金の前提条件。1 とのペアを読み込みで強制する
   (支払いは効果の後なので、前提で受け止めないと部分成功が作れてしまう)
3. `OBJECT_STATE_INT_GREATER_THAN_OTHER`: 2 つの object.state の整数比較。
   80 tick 時の判定勝ち (東西の祭壇の納品数比較) 用

金銭が動く経路の規約 (**部分成功なし** / **凍結 gold は先に available_gold を
通す**) を、納める経路にも守らせる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_RICH = PlayerId(1)
_POOR = PlayerId(2)
_HERB = "薬草"

_OFFER_COST = 10


def _altar(object_id: str, name: str) -> Dict[str, Any]:
    return {
        "id": object_id,
        "name": name,
        "description": "供物を受ける石の祭壇。",
        "object_type": "OTHER",
        "state": {"gold_offered": 0},
        "interactions": [
            {
                "action_name": "offer_gold",
                "display_label": "gold を納める",
                "witness_observation_message": "{actor}が" + name + "へ供物を納めた。",
                "preconditions": [
                    {
                        "condition_type": "PLAYER_GOLD_AT_LEAST",
                        "gold_threshold": _OFFER_COST,
                        "failure_message": "納めるだけの持ち合わせがない。",
                    }
                ],
                "effects": [
                    {
                        "effect_type": "DEPOSIT_GOLD_TO_OBJECT",
                        "parameters": {
                            "state_key": "gold_offered",
                            "amount": _OFFER_COST,
                        },
                    }
                ],
            }
        ],
    }


def _base_raw() -> Dict[str, Any]:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    raw["players"][0]["initial_gold"] = 30
    raw["players"].append({
        "id": "poor", "name": "貧しい人", "spawn_spot": spawn,
        "initial_items": [], "initial_gold": _OFFER_COST - 1,
        "persona_prompt": "あなたは貧しい人。",
    })
    raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": 24}
    square = next(s for s in raw["spots"] if s["id"] == "market_square")
    square["interior"]["objects"].extend([
        _altar("east_altar", "東の祭壇"),
        _altar("west_altar", "西の祭壇"),
    ])
    return raw


def _runtime(tmp_path: Path, raw: Dict[str, Any]) -> Any:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    path = tmp_path / "altar_town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _gold(runtime: Any, player_id: PlayerId) -> int:
    return runtime._player_status_repo.find_by_id(player_id).gold.value


def _altar_count(runtime: Any, object_id: str) -> int:
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

    interior = runtime._spot_interior_repo.find_by_spot_id(
        SpotId.create(runtime.id_mapper.get_int("spot", "market_square"))
    )
    obj = interior.get_object(
        SpotObjectId.create(runtime.id_mapper.get_int("object", object_id))
    )
    return int(obj.state.get("gold_offered", 0))


def _offer(runtime: Any, player_id: PlayerId, object_id: str = "east_altar"):
    from ai_rpg_world.domain.common.value_object import WorldTick
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

    return runtime._interaction_service.execute_interaction(
        player_id,
        SpotObjectId.create(runtime.id_mapper.get_int("object", object_id)),
        "offer_gold",
        current_tick=WorldTick(runtime.current_tick()),
    )


class TestGoldMovesIntoTheAltar:
    """納めると gold が減り、祭壇の数が増える。片方だけは起きない。"""

    def test_offering_pays_gold_and_raises_the_count(self, tmp_path: Path) -> None:
        """30G 持ちが 10G を納めると、所持金 20G・祭壇 10 になる。

        支払いとカウンタが同じ額で動くこと (総量が保存されること) まで見る。
        """
        runtime = _runtime(tmp_path, _base_raw())

        _offer(runtime, _RICH)

        assert _gold(runtime, _RICH) == 20
        assert _altar_count(runtime, "east_altar") == 10

    def test_exactly_enough_gold_is_enough(self, tmp_path: Path) -> None:
        """所持金がちょうど gold_threshold なら納められる (**境界は以上**)。

        30G から 10G ずつ 3 回納めると、3 回目は残高ちょうど 10G で通り、
        最後は 0G になる。境界を「超」で書く変異はここで落ちる。
        """
        runtime = _runtime(tmp_path, _base_raw())

        for _ in range(3):
            _offer(runtime, _RICH)

        assert _gold(runtime, _RICH) == 0
        assert _altar_count(runtime, "east_altar") == 30

    def test_the_poor_are_refused_and_nothing_moves(self, tmp_path: Path) -> None:
        """gold_threshold 未満だと断られ、所持金も祭壇も動かない。

        断り文はシナリオの failure_message がそのまま出る。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        runtime = _runtime(tmp_path, _base_raw())

        with pytest.raises(InteractionNotAllowedException) as exc:
            _offer(runtime, _POOR)

        assert "持ち合わせ" in str(exc.value)
        assert _gold(runtime, _POOR) == _OFFER_COST - 1
        assert _altar_count(runtime, "east_altar") == 0

    def test_frozen_gold_cannot_be_offered(self, tmp_path: Path) -> None:
        """同席取引に差し出して凍結中の gold は納められない。

        30G 持ちが 25G を取引に出すと、残り 5G では 10G を納められない。
        前提条件 (生の所持金 30G) は通ってしまうので、永続化前のガードが
        受け止める。祭壇も所持金も動かない = 部分成功を作らない。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        runtime = _runtime(tmp_path, _base_raw())
        runtime._player_trade_service.offer(
            _RICH, target=_POOR,
            gives_items=(), gives_gold=25,
            asks_item_labels=({"item_label": _HERB, "quantity": 1},),
            asks_gold=0,
            current_tick=runtime.current_tick(),
        )

        with pytest.raises(InteractionNotAllowedException) as exc:
            _offer(runtime, _RICH)

        assert "取引に差し出している" in str(exc.value)
        assert _gold(runtime, _RICH) == 30
        assert _altar_count(runtime, "east_altar") == 0


class TestTheLoaderRefusesUnsafeOfferings:
    """支払いが途中死しうる宣言は、読み込みで止まる。"""

    def test_deposit_without_gold_precondition_is_refused(
        self, tmp_path: Path
    ) -> None:
        """PLAYER_GOLD_AT_LEAST の無い DEPOSIT_GOLD_TO_OBJECT は読み込みで落ちる。

        前提で受け止めないと「カウンタは増えたのに払えない」部分成功が
        作れてしまうため、宣言の時点で止める。
        """
        raw = _base_raw()
        square = next(s for s in raw["spots"] if s["id"] == "market_square")
        altar = next(o for o in square["interior"]["objects"] if o["id"] == "east_altar")
        altar["interactions"][0]["preconditions"] = []

        with pytest.raises(ScenarioLoadError, match="PLAYER_GOLD_AT_LEAST"):
            _runtime(tmp_path, raw)

    def test_a_threshold_below_the_amount_is_refused(self, tmp_path: Path) -> None:
        """gold_threshold が納める額を下回る宣言も読み込みで落ちる。"""
        raw = _base_raw()
        square = next(s for s in raw["spots"] if s["id"] == "market_square")
        altar = next(o for o in square["interior"]["objects"] if o["id"] == "east_altar")
        altar["interactions"][0]["preconditions"][0]["gold_threshold"] = _OFFER_COST - 1

        with pytest.raises(ScenarioLoadError, match="下回っています"):
            _runtime(tmp_path, raw)

    def test_a_non_positive_amount_is_refused(self, tmp_path: Path) -> None:
        """amount が正の整数でない宣言は読み込みで落ちる。"""
        raw = _base_raw()
        square = next(s for s in raw["spots"] if s["id"] == "market_square")
        altar = next(o for o in square["interior"]["objects"] if o["id"] == "east_altar")
        altar["interactions"][0]["effects"][0]["parameters"]["amount"] = 0

        with pytest.raises(ScenarioLoadError, match="amount"):
            _runtime(tmp_path, raw)


class TestOneAltarCanBeJudgedAgainstTheOther:
    """2 つの祭壇の数を比べる述語が、判定イベントとして動く。"""

    def _raw_with_judgment(self) -> Dict[str, Any]:
        raw = _base_raw()
        raw["scenario_events"] = [
            {
                "id": "east_is_ahead",
                "trigger": "ON_TICK",
                "once": True,
                "observation": {
                    "category": "environment",
                    "recipients": "all_players",
                    "schedules_turn": False,
                    "breaks_movement": False,
                },
                "conditions": [
                    {
                        "condition_type": "OBJECT_STATE_INT_GREATER_THAN_OTHER",
                        "target_object": "east_altar",
                        "state_key": "gold_offered",
                        "other_object": "west_altar",
                        "other_state_key": "gold_offered",
                    }
                ],
                "effects": [
                    {
                        "effect_type": "SET_FLAG",
                        "parameters": {"flag_name": "east_is_ahead"},
                    },
                    {
                        "effect_type": "SHOW_MESSAGE",
                        "parameters": {"message": "東の祭壇が上回っている。"},
                    },
                ],
            }
        ]
        return raw

    def test_the_flag_rises_only_when_strictly_greater(self, tmp_path: Path) -> None:
        """東 10 / 西 0 で判定フラグが立つ。

        納める → tick を進める → 世界フラグ、の実経路で確かめる。
        """
        runtime = _runtime(tmp_path, self._raw_with_judgment())
        _offer(runtime, _RICH, "east_altar")

        runtime.advance_tick()

        assert "east_is_ahead" in runtime._world_flag_state.as_frozen_set()

    def test_a_tie_does_not_rise(self, tmp_path: Path) -> None:
        """東 10 / 西 10 (同値) では立たない (**引き分けは不成立**)。

        「以上」で書くと引き分けが両勝ちに化けるので、厳密比較を固定する。
        """
        runtime = _runtime(tmp_path, self._raw_with_judgment())
        _offer(runtime, _RICH, "east_altar")
        _offer(runtime, _RICH, "west_altar")

        runtime.advance_tick()

        assert "east_is_ahead" not in runtime._world_flag_state.as_frozen_set()
