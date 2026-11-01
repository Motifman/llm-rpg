"""納める gold が足りずに物体の操作が断られたとき、同じ場所の人にも失敗が見えることを保証する (#1957)。

前提で断られた失敗は、他人の失敗から学べるように同じ場所の人へ常に見せる (#356)。
取引に差し出して凍結中の gold は前提 (生の所持金) を素通りし、保存の前の確かめで断られる。
その断りも前提の失敗と同じく周りに見せる。ただし所持金の額は本人だけが知ることなので見せない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_TOWN = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"
_OFFERER = PlayerId(1)
_WITNESS = PlayerId(2)
_OFFER_COST = 10
_OFFERER_GOLD = 30


def _altar() -> dict[str, Any]:
    return {
        "id": "altar",
        "name": "石の祭壇",
        "description": "供物を受ける石の祭壇。",
        "object_type": "OTHER",
        "state": {"gold_offered": 0},
        "interactions": [
            {
                "action_name": "offer_gold",
                "display_label": "gold を納める",
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
                        "parameters": {"state_key": "gold_offered", "amount": _OFFER_COST},
                    }
                ],
            }
        ],
    }


def _runtime(tmp_path: Path) -> Any:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    raw: dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    raw["players"][0]["initial_gold"] = _OFFERER_GOLD
    raw["players"].append(
        {
            "id": "witness",
            "name": "居合わせた人",
            "spawn_spot": spawn,
            "initial_items": [],
            "initial_gold": 0,
            "persona_prompt": "あなたは居合わせた人。",
        }
    )
    raw["player_trade"] = {"enabled": True, "offer_expires_in_ticks": 24}
    square = next(s for s in raw["spots"] if s["id"] == spawn)
    square["interior"]["objects"].append(_altar())
    path = tmp_path / "altar_town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _freeze_gold(runtime: Any, amount: int) -> None:
    runtime._player_trade_service.offer(
        _OFFERER,
        target=_WITNESS,
        gives_items=(),
        gives_gold=amount,
        asks_item_labels=({"item_label": "薬草", "quantity": 1},),
        asks_gold=0,
        current_tick=runtime.current_tick(),
    )
    runtime._obs_buffer.drain(_WITNESS)


def _offer(runtime: Any):
    return runtime._interaction_service.execute_interaction(
        _OFFERER,
        SpotObjectId.create(runtime.id_mapper.get_int("object", "altar")),
        "offer_gold",
        current_tick=WorldTick(runtime.current_tick()),
    )


def _witnessed_failures(runtime: Any) -> list[Any]:
    return [
        obs
        for obs in runtime._obs_buffer.get_observations(_WITNESS)
        if obs.output.structured.get("type") == "spot_object_interaction_failed"
    ]


def test_witness_sees_the_failure_when_frozen_gold_leaves_too_little_to_offer(tmp_path: Path) -> None:
    """30G のうち 25G を取引に出した人が 10G を納めようとして断られると、同じ場所の人の観測に失敗が 1 件出る。"""
    runtime = _runtime(tmp_path)
    _freeze_gold(runtime, 25)

    with pytest.raises(InteractionNotAllowedException):
        _offer(runtime)

    failures = _witnessed_failures(runtime)
    assert len(failures) == 1
    assert "gold を納める" in failures[0].output.prose


def test_offerer_still_gets_the_amounts_and_keeps_the_gold(tmp_path: Path) -> None:
    """断られた本人には、納める額と使える額を含む今までどおりの文が返り、所持金は減らない。"""
    runtime = _runtime(tmp_path)
    _freeze_gold(runtime, 25)

    with pytest.raises(InteractionNotAllowedException) as exc:
        _offer(runtime)

    assert str(exc.value) == (
        "10G を納めるには手持ちが足りません。いま使えるのは 5G です "
        "(取引に差し出している gold は、返事が来るまで使えません)。"
    )
    assert runtime._player_status_repo.find_by_id(_OFFERER).gold.value == _OFFERER_GOLD


def test_witnessed_failure_does_not_reveal_the_offerers_gold(tmp_path: Path) -> None:
    """周りに見える失敗の文と構造化した値に、本人の使える額 (5G) も取引に出した額 (25G) も出ない。"""
    runtime = _runtime(tmp_path)
    _freeze_gold(runtime, 25)

    with pytest.raises(InteractionNotAllowedException):
        _offer(runtime)

    (failure,) = _witnessed_failures(runtime)
    shown = failure.output.prose + json.dumps(failure.output.structured, ensure_ascii=False)
    assert "5G" not in shown
    assert "25G" not in shown
    assert "取引に差し出している" not in shown


def test_no_failure_is_witnessed_when_the_offerer_can_pay(tmp_path: Path) -> None:
    """凍結を差し引いても足りる (30G のうち 5G を取引に出し、10G を納める) とき、失敗の観測は出ない。"""
    runtime = _runtime(tmp_path)
    _freeze_gold(runtime, 5)

    _offer(runtime)

    assert _witnessed_failures(runtime) == []
