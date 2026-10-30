"""廃坑の山村で、名前を知らない相手が画面のどこでも見た目で出ることを保証する (#1581)。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"


def _ids(runtime) -> dict[str, PlayerId]:
    return {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}


def _offer_lines(runtime, player_id: PlayerId) -> list[str]:
    user = runtime.build_full_prompt(player_id)["messages"][1]["content"]
    return [line for line in user.splitlines() if " から: " in line]


class TestTradeOfferFromAStranger:
    """名前を知らない相手からの取引の申し出が、申し出た人の見た目で出ることを保証する。"""

    def _offer(self, runtime, ids) -> None:
        store = runtime._pending_trade_offer_store
        store.put(
            PendingTradeOffer.create(
                offer_id=store.next_offer_id(),
                offerer_player_id=ids["ゲン"],
                target_player_id=ids["ハル"],
                gives=TradeSide(gold=5),
                asks=TradeSide(items=((runtime.id_mapper.get_int("item_spec", "lamp_oil"), 1),)),
                created_tick=0,
                expires_in_ticks=5,
            )
        )

    def test_offer_from_a_stranger_shows_the_appearance(self) -> None:
        """ハルが名前を知らないゲンからの申し出は「煤けた坑夫の上着を着た初老の男」から届き、ゲンの名前は出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids(runtime)
        self._offer(runtime, ids)

        lines = _offer_lines(runtime, ids["ハル"])

        assert lines and all("煤けた坑夫の上着を着た初老の男" in line for line in lines)
        assert all("ゲン" not in line for line in lines)

    def test_offer_from_someone_named_shows_the_name(self) -> None:
        """ハルがゲンに会って名前を知ったあとは、申し出はゲンの名前で届く。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids(runtime)
        acquaintances = runtime._player_acquaintances
        acquaintances.record_meeting(ids["ハル"], "ゲン")
        acquaintances.learn_name(ids["ハル"], ids["ゲン"], how="名乗り")
        self._offer(runtime, ids)

        assert any('"ゲン" から' in line for line in _offer_lines(runtime, ids["ハル"]))
