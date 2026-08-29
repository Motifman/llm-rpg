"""現行WorldRuntimeの同席取引が操作単位で状態と観測を確定する契約。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import PlayerTradeOfferEvent
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from tests.support.overflow_sinks import IGNORE_OVERFLOW


_SCENARIO = Path("data/scenarios/market_town_v1.json")
_OFFERER = PlayerId(1)
_TARGET = PlayerId(2)
_HERB = "薬草"


@pytest.fixture()
def runtime(tmp_path: Path) -> Any:
    """同じ場所に二人がいる本番構成の市場町を作る。"""
    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["players"].append(
        {
            "id": "trade_target",
            "name": "取引相手",
            "spawn_spot": raw["players"][0]["spawn_spot"],
            "initial_items": [],
            "initial_gold": 100,
            "persona_prompt": "あなたは取引相手。",
        }
    )
    raw["player_trade"] = {"enabled": True}
    path = tmp_path / "trade_scope.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _spec_id(runtime: Any, label: str) -> ItemSpecId:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id


def _give(runtime: Any, player_id: PlayerId, label: str) -> None:
    grant_item_specs_to_inventory(
        player_id,
        (_spec_id(runtime, label),),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _held(runtime: Any, player_id: PlayerId, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    return count_owned_item_instances_by_spec(
        inventory,
        runtime._item_repo,
    ).get(_spec_id(runtime, label), 0)


def _offer_herb_for_gold(runtime: Any):
    return runtime._player_trade_service.offer(
        _OFFERER,
        target=_TARGET,
        gives_items=(),
        gives_gold=5,
        asks_item_labels=({"item_label": _HERB, "quantity": 1},),
        asks_gold=0,
        current_tick=runtime.current_tick(),
    )


def _capture_trade_events(runtime: Any, monkeypatch: pytest.MonkeyPatch):
    delivered: list[PlayerTradeOfferEvent] = []
    original = runtime._speech_event_publisher.publish_all

    def capture(events):
        delivered.extend(
            event for event in events if isinstance(event, PlayerTradeOfferEvent)
        )
        return original(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture)
    return delivered


def test_offer_inventory_failure_rolls_back_offer_reservation_and_observation(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """提案時の予約保存失敗は提案ID・予約・成功観測を一切残さない。"""
    _give(runtime, _OFFERER, _HERB)
    delivered = _capture_trade_events(runtime, monkeypatch)
    original_save = InMemoryPlayerInventoryRepository.save

    def fail_after_save(self, inventory):
        result = original_save(self, inventory)
        raise RuntimeError("offer reservation failed")

    monkeypatch.setattr(InMemoryPlayerInventoryRepository, "save", fail_after_save)

    with pytest.raises(RuntimeError, match="offer reservation failed"):
        runtime._player_trade_service.offer(
            _OFFERER,
            target=_TARGET,
            gives_items=(
                {"item_spec_id": _spec_id(runtime, _HERB).value, "quantity": 1},
            ),
            gives_gold=0,
            asks_item_labels=(),
            asks_gold=1,
            current_tick=runtime.current_tick(),
        )

    assert runtime._pending_trade_offer_store.list_all() == ()
    assert runtime._player_inventory_repo.find_by_id(_OFFERER).reserved_item_ids == set()
    assert delivered == []


def test_accept_late_status_failure_rolls_back_both_sides_and_keeps_offer(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """承諾後半の所持金保存失敗は二者の品・所持金・提案・観測を開始前へ戻す。"""
    _give(runtime, _TARGET, _HERB)
    offer = _offer_herb_for_gold(runtime)
    before_gold = tuple(
        runtime._player_status_repo.find_by_id(player_id).gold.value
        for player_id in (_OFFERER, _TARGET)
    )
    delivered = _capture_trade_events(runtime, monkeypatch)
    original_save = InMemoryPlayerStatusRepository.save
    saves = 0

    def fail_second_status_save(self, status):
        nonlocal saves
        result = original_save(self, status)
        saves += 1
        if saves == 2:
            raise RuntimeError("accept status failed")
        return result

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", fail_second_status_save)

    with pytest.raises(RuntimeError, match="accept status failed"):
        runtime._player_trade_service.accept(_TARGET, offerer=_OFFERER)

    assert _held(runtime, _TARGET, _HERB) == 1
    assert _held(runtime, _OFFERER, _HERB) == 0
    assert tuple(
        runtime._player_status_repo.find_by_id(player_id).gold.value
        for player_id in (_OFFERER, _TARGET)
    ) == before_gold
    assert runtime._pending_trade_offer_store.find(offer.offer_id) == offer
    assert delivered == []


def test_decline_release_failure_keeps_offer_reservation_and_skips_observation(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """辞退時の予約解除保存失敗は提案と予約を残し、辞退観測を出さない。"""
    _give(runtime, _OFFERER, _HERB)
    offer = runtime._player_trade_service.offer(
        _OFFERER,
        target=_TARGET,
        gives_items=(
            {"item_spec_id": _spec_id(runtime, _HERB).value, "quantity": 1},
        ),
        gives_gold=0,
        asks_item_labels=(),
        asks_gold=1,
        current_tick=runtime.current_tick(),
    )
    delivered = _capture_trade_events(runtime, monkeypatch)
    original_save = InMemoryPlayerInventoryRepository.save

    def fail_after_save(self, inventory):
        result = original_save(self, inventory)
        raise RuntimeError("decline release failed")

    monkeypatch.setattr(InMemoryPlayerInventoryRepository, "save", fail_after_save)

    with pytest.raises(RuntimeError, match="decline release failed"):
        runtime._player_trade_service.decline(_TARGET, offerer=_OFFERER)

    assert runtime._pending_trade_offer_store.find(offer.offer_id) == offer
    assert len(
        runtime._player_inventory_repo.find_by_id(_OFFERER).reserved_item_ids
    ) == 1
    assert delivered == []
