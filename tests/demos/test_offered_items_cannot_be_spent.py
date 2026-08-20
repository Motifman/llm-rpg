"""取引に出したものは、返事がつくまで使えない (経済統合 Phase 2)。

凍結しないと、承諾した側から見て「受けたのに何も来なかった」が起きる。失敗が
**相手の行動に依存して**発生するので、流れた取引が「判断の失敗」なのか
「タイミングの不運」なのか切り分けられない。交渉そのものを観測したい Phase 2
では、決済の不確実性が観測を汚す。

消費経路は 4 つ (use / drop / give / sell) と gold で、**経路ごとに 1 件ずつ
固定する**。1 つの経路の検査を外したら、その経路のテストだけが落ちる形にして
ある。
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_TOWN = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
)
_LENA = PlayerId(1)
_HERB = "薬草"


class _Town:
    """市場町を立ち上げ、ツールを実経路 (resolver → executor) で叩く。"""

    def __init__(self, directory: pathlib.Path) -> None:
        raw = json.loads(_TOWN.read_text(encoding="utf-8"))
        # 取引の相手役を 1 人足す。凍結の検証には相手の実在が要る
        # (提案は二人の間の状態なので)。
        raw["players"].append(
            {
                "id": "tom",
                "name": "トム",
                "spawn_spot": raw["players"][0]["spawn_spot"],
                "initial_items": [],
                "initial_gold": 50,
                "persona_prompt": "あなたはトム、この町の荷運び。",
            }
        )
        raw["player_trade"] = {"enabled": True}
        # 市場町は 1 人の世界なので give_item を落としている。ここでは相手を
        # 足したので、渡す経路も検査対象に戻す。
        raw["disabled_tools"] = [
            name for name in raw.get("disabled_tools", []) if name != "give_item"
        ]
        (directory / "market_town_v1.json").write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8",
        )
        manager = GameRuntimeManager(
            scenarios_dir=directory, characters_path=directory / "characters.json",
        )
        character = manager.create_character(CharacterCreateRequest(name="レナ"))
        summary = manager.create_session(
            SessionCreateRequest(world_id="market_town_v1", character_ids=[character.id])
        )
        self._state = manager._sessions[summary.session_id]

    @property
    def runtime(self) -> Any:
        return self._state.runtime

    def call(self, tool: str, args: Dict[str, Any], player_id: PlayerId = _LENA):
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": tool, "arguments": args},
        )
        return self._state.llm_wiring.run_turn(player_id)

    def grant_herb(self, count: int = 1) -> int:
        """薬草を持たせ、その item_spec_id を返す。"""
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

        spec_id = next(
            definition.spec_id.value
            for definition in self.runtime.scenario.item_spec_definitions
            if definition.name == _HERB
        )
        grant_item_specs_to_inventory(
            _LENA,
            tuple(ItemSpecId.create(spec_id) for _ in range(count)),
            self.runtime._item_repo,
            self.runtime._item_spec_repo,
            self.runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        return spec_id

    def offer(self, *, gives: TradeSide, asks: TradeSide) -> PendingTradeOffer:
        """レナからトムへの提案を 1 件作り、凍結する。

        ツールはまだ無いので、集約と凍結サービスを直接使う。ツール経由の
        経路はツール PR で確かめる。
        """
        store = self.runtime._pending_trade_offer_store
        offer = PendingTradeOffer.create(
            offer_id=store.next_offer_id(),
            offerer_player_id=_LENA,
            target_player_id=PlayerId(2),
            gives=gives,
            asks=asks,
            created_tick=self.runtime.current_tick(),
            expires_in_ticks=10,
        )
        store.put(offer)
        self.runtime._trade_freeze_service.freeze_offer(offer)
        return offer

    def move_to_merchant(self) -> None:
        graph = self.runtime._spot_graph_repo.find_graph()
        spot = self.runtime.scenario.merchants[0].spot_id
        graph.unplace_entity(EntityId.create(int(_LENA)))
        graph.place_entity(EntityId.create(int(_LENA)), SpotId.create(spot.value))
        self.runtime._spot_graph_repo.save(graph)


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    return _Town(tmp_path)


class TestEachSpendingPathRefusesFrozenItems:
    """4 つの消費経路が、提案に出した品を受け付けない。"""

    def test_it_cannot_be_used(self, town: _Town) -> None:
        """提案に出した品は使えない。"""
        town.grant_herb()
        town.offer(gives=TradeSide(items=((_spec(town), 1),)), asks=TradeSide(gold=6))

        result = town.call("use_item", {"item_label": _HERB, "inner_thought": "食べる"})

        assert result.success is False
        assert result.error_code == "ITEM_OFFERED_IN_TRADE"

    def test_it_cannot_be_dropped(self, town: _Town) -> None:
        """提案に出した品は置けない。"""
        town.grant_herb()
        town.offer(gives=TradeSide(items=((_spec(town), 1),)), asks=TradeSide(gold=6))

        result = town.call("drop_item", {"item_label": _HERB, "inner_thought": "置く"})

        assert result.success is False
        assert result.error_code == "ITEM_OFFERED_IN_TRADE"

    def test_it_cannot_be_given_away(self, town: _Town) -> None:
        """提案に出した品は他人へ渡せない。"""
        town.grant_herb()
        town.offer(gives=TradeSide(items=((_spec(town), 1),)), asks=TradeSide(gold=6))

        result = town.call(
            "give_item",
            {
                "gives": [{"item_label": _HERB, "target_player_label": "トム"}],
                "inner_thought": "渡す",
            },
        )

        assert result.success is False
        assert result.error_code == "ITEM_OFFERED_IN_TRADE"

    def test_it_cannot_be_sold_to_the_merchant(self, town: _Town) -> None:
        """提案に出した品は商人へ売れない。理由も凍結だと分かる文面で返る。"""
        town.grant_herb()
        town.offer(gives=TradeSide(items=((_spec(town), 1),)), asks=TradeSide(gold=6))
        town.move_to_merchant()

        result = town.call(
            "sell_item", {"item_label": _HERB, "quantity": 1, "inner_thought": "売る"},
        )

        assert result.success is False
        assert result.error_code == "SELL_ITEM_NOT_OWNED"
        assert "取引の提案に出している" in result.message


class TestFrozenGoldCannotBeSpent:
    """提案に出した gold は買い物に使えない。"""

    def test_buying_uses_the_available_balance(self, town: _Town) -> None:
        """所持額ではなく、凍結を差し引いた額で判定される。

        案 Q (凍結額を集約に持たず、提案から導出する) の弱点は「使う側が
        関数を通し忘れても落ちない」こと。gold を使う唯一のツールである
        buy_item で固定する。
        """
        town.offer(
            gives=TradeSide(gold=10),
            asks=TradeSide(items=((_spec(town), 1),)),
        )
        town.move_to_merchant()

        result = town.call(
            "buy_item",
            {"item_label": "焼きたてのパン", "quantity": 1, "inner_thought": "買う"},
        )

        # 初期所持金 12G のうち 10G を提案に出しているので、10G のパンは買えない
        assert result.success is False
        assert result.error_code == "BUY_ITEM_NOT_ENOUGH_GOLD"
        assert "取引の提案に出している" in result.message

    def test_the_rest_of_the_purse_still_works(self, town: _Town) -> None:
        """凍結していないぶんは、これまでどおり使える。"""
        town.offer(
            gives=TradeSide(gold=2),
            asks=TradeSide(items=((_spec(town), 1),)),
        )
        town.move_to_merchant()

        result = town.call(
            "buy_item",
            {"item_label": "焼きたてのパン", "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is True


class TestReleasingTheOfferUnfreezes:
    """返事がつけば、凍結は解ける。"""

    def test_an_unfrozen_item_can_be_used_again(self, town: _Town) -> None:
        """提案が終われば、出していた品はまた使える。"""
        town.grant_herb()
        offer = town.offer(gives=TradeSide(items=((_spec(town), 1),)), asks=TradeSide(gold=6))

        town.runtime._pending_trade_offer_store.put(offer.decline())
        town.runtime._trade_freeze_service.release_offer(offer)

        result = town.call("drop_item", {"item_label": _HERB, "inner_thought": "置く"})

        assert result.success is True

    def test_unfrozen_gold_can_be_spent_again(self, town: _Town) -> None:
        """提案が終われば、出していた gold もまた使える。"""
        offer = town.offer(
            gives=TradeSide(gold=10), asks=TradeSide(items=((_spec(town), 1),)),
        )
        town.move_to_merchant()

        town.runtime._pending_trade_offer_store.put(offer.expire())
        town.runtime._trade_freeze_service.release_offer(offer)

        result = town.call(
            "buy_item",
            {"item_label": "焼きたてのパン", "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is True


def _spec(town: _Town) -> int:
    """薬草の item_spec_id。"""
    return next(
        definition.spec_id.value
        for definition in town.runtime.scenario.item_spec_definitions
        if definition.name == _HERB
    )
