"""供物競争は、敵と取引しなければ勝てない形になっている (経済 Phase 4、PR 3)。

**設計表をそのままテストに置く。** この世界が作ろうとしている力は 3 つ。

| 力 | 構造 |
|---|---|
| 取引の強制 | 麦は東・薬草は西しか作れず、供物には両方が要る |
| gold の敵対 | 総量 80G 固定 (蛇口なし) に対し必要 45G × 2 = 90G |
| 刻限の圧 | 先に納め切れば即勝ち。刻限では敵の産物の多い組の判定勝ち |

v3.7 の教訓: 需要側に板より安い迂回路が 1 本でも残ると、市場は読まれる
だけで書かれない。この表は「迂回路が無いこと」の宣言でもある。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_RACE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "offering_race_v1.json"
)

_GAREN, _DONA, _SERA, _YUNO = (PlayerId(i) for i in range(1, 5))
_NAME_TO_ID = {"ガレン": _GAREN, "ドナ": _DONA, "セラ": _SERA, "ユノ": _YUNO}

#: 組の設計表。行 = 人、列 = できる採取。
_TEAM_MATRIX: Dict[str, Dict[str, bool]] = {
    "ガレン": {"reap_wheat": True, "gather_herb": False},
    "ドナ":   {"reap_wheat": True, "gather_herb": False},
    "セラ":   {"reap_wheat": False, "gather_herb": True},
    "ユノ":   {"reap_wheat": False, "gather_herb": True},
}

_WORK = {
    "reap_wheat": ("wheat_field", "wheat_rows"),
    "gather_herb": ("herb_slope", "herb_patch"),
}

#: 供物の設計値。シナリオ側と二重に持つのは、シナリオを書き換えたときに
#: 表 (このテスト) との突き合わせで気づくため。
_OFFER_GOLD = 45
_OFFER_MATERIALS = 3
_INITIAL_GOLD = 20
_TEAM_SIZE = 2
_PLAYERS = 4


class _Race:
    def __init__(self) -> None:
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        self.runtime = create_world_runtime(str(_RACE))
        self.raw: Dict[str, Any] = json.loads(_RACE.read_text(encoding="utf-8"))

    def place(self, player_id: PlayerId, string_id: str) -> None:
        graph = self.runtime._spot_graph_repo.find_graph()
        entity = EntityId.create(int(player_id))
        graph.unplace_entity(entity)
        graph.place_entity(
            entity,
            SpotId.create(self.runtime.id_mapper.get_int("spot", string_id)),
        )
        self.runtime._spot_graph_repo.save(graph)

    def give(self, player_id: PlayerId, item_id: str, count: int = 1) -> None:
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        spec_id = self.runtime.id_mapper.get_int("item_spec", item_id)
        grant_item_specs_to_inventory(
            player_id,
            tuple(ItemSpecId.create(spec_id) for _ in range(count)),
            self.runtime._item_repo,
            self.runtime._item_spec_repo,
            self.runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

    def try_work(self, player_id: PlayerId, object_id: str, action: str):
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        try:
            result = self.interact(player_id, object_id, action)
        except InteractionNotAllowedException as exc:
            return False, str(exc)
        return bool(getattr(result, "success", True)), str(
            getattr(result, "message", "")
        )

    def interact(self, player_id: PlayerId, object_id: str, action: str):
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        return self.runtime._interaction_service.execute_interaction(
            player_id,
            SpotObjectId.create(self.runtime.id_mapper.get_int("object", object_id)),
            action,
            current_tick=WorldTick(self.runtime.current_tick()),
        )

    def flags(self) -> frozenset:
        return self.runtime._world_flag_state.as_frozen_set()

    def fill_offering(self, altar: str, team_players: List[PlayerId]) -> None:
        """供物 (材料 3+3 と 45G) を祭壇に納め切る。

        gold は 15G × 3 回。1 人の初期 20G では足りないので 2 人で分担する
        (= 組の合算 40G でも 45G には 5G 足りない現実を、テストでは gold を
        直接足して埋める)。
        """
        payer = team_players[0]
        self.give(payer, "wheat", _OFFER_MATERIALS)
        self.give(payer, "herb", _OFFER_MATERIALS)
        self.interact(payer, altar, "offer_wheat")
        self.interact(payer, altar, "offer_herb")
        status = self.runtime._player_status_repo.find_by_id(payer)
        status.earn_gold(_OFFER_GOLD)
        self.runtime._player_status_repo.save(status)
        for _ in range(_OFFER_GOLD // 15):
            self.interact(payer, altar, "offer_gold")


@pytest.fixture()
def race() -> _Race:
    return _Race()


class TestOnlyYourTeamCanHarvestItsField:
    """採取の組ゲートが、表のとおりに効いている。"""

    @pytest.mark.parametrize("who", sorted(_TEAM_MATRIX))
    @pytest.mark.parametrize("job", sorted(_WORK))
    def test_the_matrix_holds(self, race: _Race, who: str, job: str) -> None:
        """できる人だけができ、できない人は組を理由に断られる。"""
        player_id = _NAME_TO_ID[who]
        spot, target = _WORK[job]
        race.place(player_id, spot)

        did, message = race.try_work(player_id, target, job)

        assert did is _TEAM_MATRIX[who][job], (
            f"{who} が {job} を {'できる' if _TEAM_MATRIX[who][job] else 'できない'} "
            f"はずだが、結果は {did} ({message})"
        )


class TestOnlyYourTeamCanUseYourAltar:
    """祭壇の組ゲート。敵の祭壇には妨害でも間違いでも納められない。"""

    @pytest.mark.parametrize("action", ["offer_wheat", "offer_herb", "offer_gold"])
    def test_the_enemy_altar_refuses(self, race: _Race, action: str) -> None:
        """東の人は西の祭壇のどの納め口も使えない。"""
        race.give(_GAREN, "wheat", 1)
        race.give(_GAREN, "herb", 1)

        did, message = race.try_work(_GAREN, "west_altar", action)

        assert did is False
        assert "西の衆だけ" in message

    def test_your_own_altar_accepts(self, race: _Race) -> None:
        """自分の組の祭壇には納められる (**正の対照**)。"""
        race.give(_GAREN, "wheat", 2)

        race.interact(_GAREN, "east_altar", "offer_wheat")

        interior = race.runtime._spot_interior_repo.find_by_spot_id(
            SpotId.create(race.runtime.id_mapper.get_int("spot", "festival_square"))
        )
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        altar = interior.get_object(
            SpotObjectId.create(race.runtime.id_mapper.get_int("object", "east_altar"))
        )
        assert altar.state["wheat_offered"] == 2


class TestGoldIsAZeroSumWeapon:
    """gold の算術が「敵から稼ぐしかない」を成立させている。

    v3.7 の設計ミス (初期資金だけで gold 条件を満たせた) の再発防止。
    値そのものではなく**関係**で固定する。
    """

    def test_the_design_constants_match_the_scenario(self, race: _Race) -> None:
        """このテストの設計値が、シナリオの宣言と一致している。

        関係のテスト (下 2 件) は設計値どうしの算術なので、シナリオだけを
        書き換えると**表とずれたまま緑になる**。ここで突き合わせて、
        どちらを変えても片方だけの変更が落ちるようにする。
        """
        assert all(p["initial_gold"] == _INITIAL_GOLD for p in race.raw["players"])
        assert len(race.raw["players"]) == _PLAYERS
        east = [p for p in race.raw["players"] if p["initial_state"]["team"] == "east"]
        assert len(east) == _TEAM_SIZE
        complete = next(
            e for e in race.raw["scenario_events"]
            if e["id"] == "east_offering_complete"
        )
        declared = {
            c["state_key"]: c["ticks_offset"]
            for c in complete["conditions"]
            if c["condition_type"] == "OBJECT_STATE_INT_AT_LEAST"
        }
        assert declared == {
            "wheat_offered": _OFFER_MATERIALS,
            "herb_offered": _OFFER_MATERIALS,
            "gold_offered": _OFFER_GOLD,
        }

    def test_both_teams_cannot_complete_on_the_world_supply(
        self, race: _Race
    ) -> None:
        """必要額の合計が、世界の gold 総量を上回る。

        これが崩れると、両組が取引なしで gold 条件を満たせてしまう。
        gold の蛇口 (商人・報酬) が無いことは下のテストが守る。
        """
        world_gold = sum(p["initial_gold"] for p in race.raw["players"])

        assert _OFFER_GOLD * 2 > world_gold

    def test_one_team_cannot_complete_on_its_own_purse(self, race: _Race) -> None:
        """1 組の初期資金では自分の必要額に届かない。

        届いてしまうと、物々交換だけで完走できる (v3.7 の C-1)。
        """
        team_gold = _INITIAL_GOLD * _TEAM_SIZE

        assert team_gold < _OFFER_GOLD

    def test_there_is_no_gold_faucet(self, race: _Race) -> None:
        """商人が居ない (= gold の蛇口が無い)。

        蛇口が 1 つでもあると、総量 80G の算術が崩れる。
        """
        assert not race.raw.get("merchants")

    def test_the_gold_deposit_unit_fits_a_single_purse(self, race: _Race) -> None:
        """1 回の納め額 (15G) が個人の初期資金 (20G) 以下。

        納め口が初期資金より大きいと、稼ぐ前に一度も納められず、
        賽銭箱の音 (目撃情報) が終盤まで消える。
        """
        altar = next(
            o
            for s in race.raw["spots"]
            for o in s.get("interior", {}).get("objects", [])
            if o["id"] == "east_altar"
        )
        gold_action = next(
            i for i in altar["interactions"] if i["action_name"] == "offer_gold"
        )
        amount = next(
            e["parameters"]["amount"]
            for e in gold_action["effects"]
            if e["effect_type"] == "DEPOSIT_GOLD_TO_OBJECT"
        )

        assert amount <= _INITIAL_GOLD
        assert _OFFER_GOLD % amount == 0


class TestTimersDoNotBecomeWeapons:
    """期限の設定が、放置や居座りを武器にさせない。"""

    def test_a_trade_offer_expires_quickly(self, race: _Race) -> None:
        """同席取引の期限が短い (8 tick 以下)。

        敵対世界では「敵からの提案に返事をせず、凍結させたまま座る」が
        合理化する。offerer 側に取り下げ手段が無いので、期限だけが解毒。
        """
        assert race.raw["player_trade"]["offer_expires_in_ticks"] <= 8

    def test_no_board_order_outlives_the_run(self, race: _Race) -> None:
        """掲示板の既定期限が run 長より短く、初期の錨も無い。"""
        assert race.raw["market"]["order_expires_in_ticks"] < 80
        assert race.raw["market"]["initial_orders"] == []


class TestTheAltarKeepsItsSecrets:
    """祭壇の中身は、広場に立っても読めない。"""

    def test_counters_do_not_leak_into_the_prompt(self, race: _Race) -> None:
        """敵 (と味方) のプロンプトに祭壇のカウンタが出ない。

        object.state は既定でスポット描画に全部載る (過去に設定漏れで
        漏洩した回帰がある)。hidden_state_keys の宣言が実際に効いている
        ことを、実プロンプトで確かめる。
        """
        race.give(_GAREN, "wheat", 2)
        race.interact(_GAREN, "east_altar", "offer_wheat")

        context = race.runtime.build_llm_context(_SERA)
        text = context.current_state_text

        assert "東の祭壇" in text, "祭壇そのものは見える (正の対照)"
        assert "wheat_offered" not in text
        assert "herb_offered" not in text
        assert "gold_offered" not in text


class TestTheRaceCanActuallyEnd:
    """勝ち筋 2 つ (納め切り / 判定) と共倒れが、実経路で終わる。"""

    def test_a_full_offering_ends_the_race(self, race: _Race) -> None:
        """供物を納め切ると完了フラグが立ち、世界が終わる。"""
        race.fill_offering("east_altar", [_GAREN, _DONA])

        race.runtime.advance_tick()

        assert "east_offering_complete" in race.flags()
        assert race.runtime.check_game_end().is_ended

    def test_the_judgment_favors_more_enemy_produce(self, race: _Race) -> None:
        """刻限まで納め切りが無ければ、敵の産物の多い組の判定勝ち。

        東が薬草 1 (敵の産物)、西が麦 0 なら、判定は東。
        """
        race.give(_GAREN, "herb", 1)
        race.interact(_GAREN, "east_altar", "offer_herb")

        for _ in range(80):
            if race.runtime.check_game_end().is_ended:
                break
            race.runtime.advance_tick()

        assert "east_judged_win" in race.flags()
        assert "west_judged_win" not in race.flags()

    def test_a_tie_lets_the_festival_die(self, race: _Race) -> None:
        """敵の産物が同数 (0 対 0) なら判定は出ず、刻限で共倒れに終わる。"""
        for _ in range(81):
            if race.runtime.check_game_end().is_ended:
                break
            race.runtime.advance_tick()

        assert race.runtime.check_game_end().is_ended
        assert "east_judged_win" not in race.flags()
        assert "west_judged_win" not in race.flags()


class TestTheToolsOfTradeAreOffered:
    """取引の道具 (手渡し・escrow・掲示板) が実際に LLM へ出る。"""

    def test_the_trade_tools_reach_the_llm(self, race: _Race) -> None:
        """give_item / trade_offer / market_view が払い出しに載る (**正の対照**)。

        宣言 (player_trade / market) を書いても、露出判断の別の理由で
        落ちていれば気付けない。実払い出しまで見る。
        """
        from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
            _WorldLlmWiring,
        )

        class _CaptureClient:
            def __init__(self) -> None:
                self.tools: List[Any] = []

            def invoke(self, messages, tools, tool_choice="required", **kwargs):
                self.tools = tools
                return {"name": "wait", "arguments": {}}

        client = _CaptureClient()
        wiring = _WorldLlmWiring(
            runtime=race.runtime,
            observation_buffer=race.runtime._obs_buffer,
            short_term_memory=race.runtime._short_term_memory,
            llm_client=client,
        )
        wiring.run_phase_a(_GAREN)
        names = {tool["function"]["name"] for tool in client.tools}

        assert {"give_item", "trade_offer", "trade_accept", "trade_decline",
                "market_view", "market_list_item", "market_bid"} <= names
