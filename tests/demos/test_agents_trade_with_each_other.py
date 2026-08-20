"""同席したエージェント同士が、条件つきで品と gold を交換する (経済統合 Phase 2)。

Phase 1 の売買は相手が NPC 商人なので、価格は世界が決めていて交渉が無い。
ここで入るのは**相手も判断する主体**の取引で、「持ちかける → 相手が受けるか
断る」の 2 手番に分かれる。分かれるからこそ、待っている間に差し出したものを
使えてしまうと決済が壊れる (凍結は #1162 で入れた)。

このファイルは 3 つのツールを**実経路 (resolver → executor) で**叩く。
executor だけを直接呼ぶと、resolver の取り違え (ラベル → id の解決) が
そのまま通ってしまう — Phase 1 で実際に 1 件見落としかけた。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


class _Town:
    """市場町に 2 人を立たせ、取引ツールを実経路で叩く。"""

    def __init__(self, directory: pathlib.Path) -> None:
        raw = json.loads(_TOWN.read_text(encoding="utf-8"))
        spawn = raw["players"][0]["spawn_spot"]
        raw["players"].append(
            {
                "id": "tom",
                "name": "トム",
                "spawn_spot": spawn,
                "initial_items": [],
                "initial_gold": 50,
                "persona_prompt": "あなたはトム、この町の荷運び。",
            }
        )
        # 3 人目は取引に関わらない傍観者。第三者に何が見えるかは、
        # 当事者 2 人だけの世界では検証できない。
        raw["players"].append(
            {
                "id": "mina",
                "name": "ミナ",
                "spawn_spot": spawn,
                "initial_items": [],
                "initial_gold": 0,
                "persona_prompt": "あなたはミナ、井戸端で水を汲んでいる。",
            }
        )
        raw["player_trade"] = {"enabled": True}
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

    def spec_id(self, name: str) -> int:
        return next(
            definition.spec_id.value
            for definition in self.runtime.scenario.item_spec_definitions
            if definition.name == name
        )

    def grant(self, player_id: PlayerId, name: str, count: int = 1) -> None:
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )

        grant_item_specs_to_inventory(
            player_id,
            tuple(ItemSpecId.create(self.spec_id(name)) for _ in range(count)),
            self.runtime._item_repo,
            self.runtime._item_spec_repo,
            self.runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

    def gold_of(self, player_id: PlayerId) -> int:
        return self.runtime._player_status_repo.find_by_id(player_id).gold.value

    def counts(self, player_id: PlayerId, name: str) -> int:
        inventory = self.runtime._player_inventory_repo.find_by_id(player_id)
        wanted = self.spec_id(name)
        return sum(
            1
            for _, item_instance_id in inventory.iter_occupied_slots()
            if self.runtime._item_repo.find_by_id(item_instance_id)
            .item_spec.item_spec_id.value
            == wanted
        )

    def move_away(self, player_id: PlayerId) -> None:
        """相手を別の spot へ動かす (同席していない状態を作る)。"""
        graph = self.runtime._spot_graph_repo.find_graph()
        here = graph.get_entity_spot(EntityId.create(int(player_id)))
        elsewhere = graph.neighbor_spot_ids_for_routing(here)[0]
        graph.unplace_entity(EntityId.create(int(player_id)))
        graph.place_entity(EntityId.create(int(player_id)), SpotId.create(elsewhere.value))
        self.runtime._spot_graph_repo.save(graph)

    def offer_via_tool(
        self,
        *,
        gives: Dict[str, Any] | None = None,
        asks: Dict[str, Any] | None = None,
        actor: PlayerId = _LENA,
        partner: str = "トム",
    ):
        return self.call(
            "trade_offer",
            {
                "target_player_label": partner,
                "gives": gives if gives is not None else {"items": [{"item_label": _HERB, "quantity": 2}]},
                "asks": asks if asks is not None else {"gold": 12},
                "inner_thought": "交換したい",
            },
            actor,
        )

    def trade_offer_section(self, player_id: PlayerId) -> str:
        """「自分宛ての取引の申し出:」節だけを取り出す (無ければ空文字)。"""
        lines = self.prompt_of(player_id).splitlines()
        for index, line in enumerate(lines):
            if line.startswith("自分宛ての取引の申し出"):
                body = []
                for following in lines[index + 1 :]:
                    if following and not following.startswith(" "):
                        break
                    body.append(following)
                return "\n".join(body)
        return ""

    def prompt_of(self, player_id: PlayerId) -> str:
        """その人がいま読む prompt 全文 (直近の出来事を含む)。"""
        return self.runtime.build_full_prompt(player_id)["messages"][1]["content"]

    def drain_observations(self, player_id: PlayerId) -> List[Any]:
        """まだ読まれていない観測を取り出す (取り出すと消える)。"""
        return list(self.runtime._obs_buffer.drain(player_id))


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    return _Town(tmp_path)


class TestAnOfferIsMadeAndSettled:
    """持ちかけ → 承諾で、両側のものが実際に入れ替わる。"""

    def test_the_offer_is_accepted_and_both_sides_move(self, town: _Town) -> None:
        """承諾すると、品は受けた側へ、gold は持ちかけた側へ動く。"""
        town.grant(_LENA, _HERB, 2)

        town.offer_via_tool()
        result = town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert result.success is True
        assert town.counts(_TOM, _HERB) == 2
        assert town.counts(_LENA, _HERB) == 0
        assert town.gold_of(_TOM) == 50 - 12
        assert town.gold_of(_LENA) == 12 + 12

    def test_the_offer_is_gone_after_it_settles(self, town: _Town) -> None:
        """成立した提案は返事待ちから外れ、二度は受けられない。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        again = town.call("trade_accept", {"inner_thought": "もう一度"}, _TOM)

        assert again.success is False
        assert again.error_code == "TRADE_NO_OFFER_FOR_YOU"

    def test_items_flow_in_both_directions(self, town: _Town) -> None:
        """品と品の交換もできる (gold を挟まない物々交換)。"""
        town.grant(_LENA, _HERB, 1)
        town.grant(_TOM, _BREAD, 1)

        town.offer_via_tool(
            gives={"items": [{"item_label": _HERB, "quantity": 1}]},
            asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )
        town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert town.counts(_TOM, _HERB) == 1
        assert town.counts(_LENA, _BREAD) == 1


class TestWhatIsOfferedIsFrozenUntilAnswered:
    """ツール経由で持ちかけた品も、返事がつくまで使えない。"""

    def test_the_offered_item_cannot_be_dropped(self, town: _Town) -> None:
        """持ちかけた品は、返事を待っている間は手放せない。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        result = town.call("drop_item", {"item_label": _HERB, "inner_thought": "置く"})

        assert result.success is False
        assert result.error_code == "ITEM_OFFERED_IN_TRADE"

    def test_declining_unfreezes_it(self, town: _Town) -> None:
        """断られれば凍結は解け、持ちかけた側はまた使える。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        town.call("trade_decline", {"inner_thought": "断る"}, _TOM)
        result = town.call("drop_item", {"item_label": _HERB, "inner_thought": "置く"})

        assert result.success is True

    def test_the_offered_gold_is_not_spendable(self, town: _Town) -> None:
        """持ちかけに出した gold は、返事を待っている間は買い物に使えない。"""
        town.grant(_TOM, _BREAD, 1)
        town.offer_via_tool(
            gives={"gold": 10}, asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )

        # 初期 12G のうち 10G を出しているので、10G のパンは商人から買えない
        graph = town.runtime._spot_graph_repo.find_graph()
        graph.unplace_entity(EntityId.create(int(_LENA)))
        graph.place_entity(
            EntityId.create(int(_LENA)),
            SpotId.create(town.runtime.scenario.merchants[0].spot_id.value),
        )
        town.runtime._spot_graph_repo.save(graph)

        result = town.call(
            "buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is False
        assert result.error_code == "BUY_ITEM_NOT_ENOUGH_GOLD"


class TestAnOfferThatCannotStandIsRefused:
    """成立しえない提案は、持ちかけた瞬間に理由つきで返る。"""

    def test_a_partner_who_walked_away_cannot_settle(self, town: _Town) -> None:
        """持ちかけたあとに相手が離れると、その場では成立しない。

        持ちかけの時点では 2 人とも居るので、離れられるのは返事までの間だけ。
        ここを見ないと、離れた相手と品が瞬間移動で交換されてしまう。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.move_away(_LENA)

        result = town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert result.success is False
        assert result.error_code == "TRADE_PARTNER_NOT_HERE"

    def test_more_than_what_is_owned_cannot_be_offered(self, town: _Town) -> None:
        """持っている数を超える個数は差し出せない。

        1 つも持っていない品は在庫ラベルが解決できずに落ちるので、**個数が
        足りない場合**がこの検査の本番になる。通すと、承諾の瞬間に足りない
        ことが分かり、受けた側の失敗に見える。
        """
        town.grant(_LENA, _HERB, 1)

        result = town.offer_via_tool(
            gives={"items": [{"item_label": _HERB, "quantity": 2}]},
        )

        assert result.success is False
        assert result.error_code == "TRADE_ITEM_NOT_OWNED"

    def test_gold_beyond_the_purse_cannot_be_offered(self, town: _Town) -> None:
        """所持額を超える gold は差し出せない。"""
        result = town.offer_via_tool(
            gives={"gold": 999}, asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )

        assert result.success is False
        assert result.error_code == "TRADE_GOLD_NOT_ENOUGH"

    def test_an_unknown_item_cannot_be_asked_for(self, town: _Town) -> None:
        """この世界に無い品を求める提案は作れない。

        求める側の品は相手の持ち物に依らず名前で指名するので、**存在しない
        名前を弾けるのはここだけ**。通すと、承諾のときに「持っていない」に
        化けて、相手のせいに見える。
        """
        town.grant(_LENA, _HERB, 2)

        result = town.offer_via_tool(
            asks={"items": [{"item_label": "月の欠片", "quantity": 1}]},
        )

        assert result.success is False
        assert result.error_code == "TRADE_UNKNOWN_ITEM"

    def test_the_same_items_cannot_be_promised_to_two_people(self, town: _Town) -> None:
        """1 人に差し出している品を、同時にもう 1 人へは差し出せない。

        二重に約束できると、先に受けた側が持っていき、後の相手には「受けた
        のに何も来ない」が起きる。しかもそれは**相手の行動のせい**に見えて、
        自分の判断の失敗と区別がつかない。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool(partner="トム")

        result = town.offer_via_tool(partner="ミナ")

        assert result.success is False
        assert result.error_code == "TRADE_ITEM_NOT_OWNED"

    def test_the_same_gold_cannot_be_promised_to_two_people(self, town: _Town) -> None:
        """1 人に差し出している gold も、同時にもう 1 人へは差し出せない。"""
        town.grant(_TOM, _BREAD, 1)
        town.grant(_MINA, _BREAD, 1)
        town.offer_via_tool(
            partner="トム",
            gives={"gold": 10},
            asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )

        result = town.offer_via_tool(
            partner="ミナ",
            gives={"gold": 10},
            asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )

        assert result.success is False
        assert result.error_code == "TRADE_GOLD_NOT_ENOUGH"

    def test_a_second_offer_to_the_same_person_is_refused(self, town: _Town) -> None:
        """同じ相手へ返事待ちの提案があるうちは、重ねて持ちかけられない。"""
        town.grant(_LENA, _HERB, 4)
        town.offer_via_tool()

        result = town.offer_via_tool()

        assert result.success is False
        assert result.error_code == "TRADE_DUPLICATE_OFFER"


class TestAnAnswerThatCannotStandIsRefused:
    """受けられない承諾は、その理由が分かる形で返る。"""

    def test_accepting_without_an_offer_fails(self, town: _Town) -> None:
        """自分宛ての提案が無いのに受けようとすると失敗する。"""
        result = town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert result.success is False
        assert result.error_code == "TRADE_NO_OFFER_FOR_YOU"

    def test_accepting_without_what_was_asked_fails(self, town: _Town) -> None:
        """求められたものが手元に無いと、受けられない。

        提案は消えない (集めてから受け直せる)。ここで消すと、相手に断りが
        届いて交渉が終わってしまう。
        """
        town.grant(_LENA, _HERB, 1)
        town.offer_via_tool(
            gives={"items": [{"item_label": _HERB, "quantity": 1}]},
            asks={"items": [{"item_label": _BREAD, "quantity": 1}]},
        )

        result = town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert result.success is False
        assert result.error_code == "TRADE_ASK_NOT_MET"
        assert town.runtime._pending_trade_offer_store.list_for_target(_TOM) != ()

    def test_naming_the_offerer_picks_the_right_offer(self, town: _Town) -> None:
        """相手を名指しすれば、複数の申し出があっても取り違えない。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        result = town.call(
            "trade_accept", {"offerer_player_label": "レナ", "inner_thought": "受ける"}, _TOM,
        )

        assert result.success is True
        assert town.counts(_TOM, _HERB) == 2

    def test_naming_someone_who_did_not_offer_fails(self, town: _Town) -> None:
        """申し出ていない相手を名指しすると、別の提案を受けてしまわずに失敗する。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        result = town.call(
            "trade_accept", {"offerer_player_label": "ミナ", "inner_thought": "受ける"}, _TOM,
        )

        assert result.success is False
        assert result.error_code == "TRADE_NO_OFFER_FOR_YOU"


class TestTheOfferIsVisibleToItsTarget:
    """自分宛ての申し出は、返事をする前に prompt から見える。"""

    def test_the_incoming_offer_appears_with_its_remaining_time(
        self, town: _Town
    ) -> None:
        """受ける側の prompt に、誰から・何と何を・あと何手番かが出る。

        見えなければ「返事をしない」しか選べず、辞退と沈黙が区別できない。
        観測 (直近の出来事) は 1 度読むと流れるので、**返事を待っている間
        ずっと見えている必要がある**。だから現在の状況の節で見る。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        section = town.trade_offer_section(_TOM)

        assert "レナ" in section
        assert _HERB in section
        assert "12" in section
        assert "手番" in section

    def test_the_offer_stays_visible_across_turns(self, town: _Town) -> None:
        """1 手番なにもしなくても、申し出は消えずに見えたままになる。

        直近の出来事だけに出していると、受ける前に流れて「何を求められて
        いたか」が分からなくなる。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.prompt_of(_TOM)  # 1 度読む (観測は流れる)

        assert "レナ" in town.trade_offer_section(_TOM)

    def test_the_offerer_does_not_see_it_as_incoming(self, town: _Town) -> None:
        """持ちかけた側の prompt には、自分の申し出は「自分宛て」として出ない。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        assert town.trade_offer_section(_LENA) == ""

    def test_a_world_without_trade_has_no_such_section(self, town: _Town) -> None:
        """申し出が 1 件も無いうちは、その節ごと prompt に出ない。"""
        assert town.trade_offer_section(_TOM) == ""


class TestWhatOthersSee:
    """交渉は同席の第三者に見え、断りは当事者だけに残る。"""

    def test_an_offer_is_visible_to_a_bystander(self, town: _Town) -> None:
        """その場に居合わせた第三者にも、持ちかけたことが中身つきで見える。

        見えなければ「交渉が起きた世界」を観測できず、誰が誰と何を取引した
        のかを後から追えない。**届いた観測そのもの**を見る — prompt 全文を
        見ると、同席者の名前や品名は別の節にも出ているので、観測が 1 件も
        届いていなくても緑になる (実際そうなっていた)。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        seen = " ".join(e.output.prose for e in town.drain_observations(_MINA))

        assert "レナ" in seen and "トム" in seen and _HERB in seen

    def test_a_settlement_is_visible_to_a_bystander(self, town: _Town) -> None:
        """成立も第三者に見える (誰と誰の間で取引が成ったか)。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.drain_observations(_MINA)  # 持ちかけぶんを空にする
        town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        seen = " ".join(e.output.prose for e in town.drain_observations(_MINA))

        assert "成立" in seen
        assert "レナ" in seen and "トム" in seen

    def test_the_offerer_learns_that_it_was_accepted(self, town: _Town) -> None:
        """持ちかけた側は、受けられたことを観測で知る。

        受けるのは相手の手番なので、持ちかけた側には**観測でしか届かない**。
        届かないと、凍結が解けて品が消えた理由が本人に分からない。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.drain_observations(_LENA)  # 持ちかけぶんを空にする

        town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert "成立" in " ".join(
            e.output.prose for e in town.drain_observations(_LENA)
        )

    def test_the_one_who_answered_is_not_told_twice(self, town: _Town) -> None:
        """返事をした本人には観測が届かない (行動結果と二重になる)。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.drain_observations(_TOM)

        town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)

        assert "成立" not in " ".join(
            e.output.prose for e in town.drain_observations(_TOM)
        )

    def test_a_decline_reaches_only_the_two_parties(self, town: _Town) -> None:
        """断りは当事者だけに届き、その場の第三者には流れない。

        断りまで公開すると、断ること自体の重さが消える。持ちかけた側には
        必ず届く — 届かないと、凍結が解けた理由が本人に分からない。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()
        town.drain_observations(_MINA)  # 持ちかけぶんを空にする

        town.call("trade_decline", {"inner_thought": "断る"}, _TOM)

        assert "断" in " ".join(
            entry.output.prose for entry in town.drain_observations(_LENA)
        )
        assert town.drain_observations(_MINA) == []

    def test_an_offer_wakes_the_person_it_is_made_to(self, town: _Town) -> None:
        """持ちかけられた側は手番が起き、断るか受けるかを選べる。

        起きなければ、相手は期限切れまで気付かない。「返事をしなかった」が
        判断ではなく配線の都合になってしまう。
        """
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        entries = town.drain_observations(_TOM)

        assert any(entry.output.schedules_turn is True for entry in entries)

    def test_an_offer_does_not_wake_a_bystander(self, town: _Town) -> None:
        """第三者は見えるだけで、手番は起きない (交渉のたびに全員が動かない)。"""
        town.grant(_LENA, _HERB, 2)
        town.offer_via_tool()

        entries = town.drain_observations(_MINA)

        assert entries
        assert all(entry.output.schedules_turn is False for entry in entries)
