"""売買ツールが実際の世界で成立し、失敗と観測と trace を残すか。

ここは「宣言 → ツール定義 → 露出 → 解決 → 実行 → 観測 → trace」が 1 本に
つながっていることを見る。どこか 1 段が欠けると、シナリオに商人を書いたのに
買えない / 買えたのに誰も気づかない / 買えたのに trace から通貨の流れを
追えない、のいずれかになる。
"""

from __future__ import annotations

import json
import pathlib
import tempfile
from typing import Any, Dict

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_DRILL = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_SENA = PlayerId(2)


def _world(
    *,
    initial_gold: int = 100,
    price: int = 10,
    second_merchant_price: int | None = None,
    disabled_tools: tuple[str, ...] = (),
) -> Any:
    raw: Dict[str, Any] = json.loads(_DRILL.read_text(encoding="utf-8"))
    spawn_spot = raw["players"][0]["spawn_spot"]
    traded = raw["item_specs"][0]["id"]
    raw["merchants"] = [
        {
            "id": "gustav",
            "name": "商人グスタフ",
            "spot": spawn_spot,
            "sells": [{"item_spec": traded, "price": price}],
            "buys": [{"item_spec": traded, "price": max(1, price - 4)}],
        }
    ]
    if second_merchant_price is not None:
        raw["merchants"].append(
            {
                "id": "martha",
                "name": "商人マーサ",
                "spot": spawn_spot,
                "sells": [{"item_spec": traded, "price": second_merchant_price}],
            }
        )
    for player in raw["players"]:
        player["initial_gold"] = initial_gold
    if disabled_tools:
        raw["disabled_tools"] = list(raw.get("disabled_tools", ())) + list(disabled_tools)
    directory = pathlib.Path(tempfile.mkdtemp())
    (directory / "econ.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8",
    )
    return _Session(directory)


class _Session:
    """商人を宣言した世界を、LLM 経路つきで 1 つ立ち上げる。

    resolver → executor の実経路を通すため、tool 呼び出しは stub の LLM に
    返させる。executor だけを直接叩くと、resolver の解決 (品名 → 商人) が
    抜けたままでも緑になる。
    """

    def __init__(self, directory: pathlib.Path) -> None:
        self._manager = GameRuntimeManager(
            scenarios_dir=directory,
            characters_path=directory / "characters.json",
        )
        character = self._manager.create_character(CharacterCreateRequest(name="モリ"))
        summary = self._manager.create_session(
            SessionCreateRequest(world_id="econ", character_ids=[character.id])
        )
        self._state = self._manager._sessions[summary.session_id]

    @property
    def runtime(self) -> Any:
        return self._state.runtime

    def call(self, player_id: PlayerId, tool: str, args: Dict[str, Any]):
        """ツールを 1 回、resolver → executor の実経路で実行する。"""
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": tool, "arguments": args},
        )
        return self._state.llm_wiring.run_turn(player_id)


def _traded_item_name(session: Any) -> str:
    runtime = session.runtime
    spec_id = runtime.scenario.merchants[0].sells[0].item_spec_id
    return next(
        definition.name
        for definition in runtime.scenario.item_spec_definitions
        if definition.spec_id.value == spec_id
    )


def _execute(session: Any, player_id: PlayerId, tool: str, args: Dict[str, Any]):
    """resolver → executor の実経路でツールを 1 回実行する。"""
    return session.call(player_id, tool, args)


def _gold(session: Any, player_id: PlayerId = _MORI) -> int:
    return session.runtime._player_status_repo.find_by_id(player_id).gold.value


def _put_both_at_the_merchant(session: Any) -> None:
    runtime = session.runtime
    graph = runtime._spot_graph_repo.find_graph()
    spot = runtime.scenario.merchants[0].spot_id
    for player_id in (_MORI, _SENA):
        graph.unplace_entity(EntityId.create(int(player_id)))
        graph.place_entity(EntityId.create(int(player_id)), SpotId.create(spot.value))
    runtime._spot_graph_repo.save(graph)


class TestBuyingThroughTheTool:
    """buy_item がツールとして成立し、結果と trace を返す。"""

    def test_buying_succeeds_and_reports_the_remaining_gold(self) -> None:
        """買えたとき、成功として何をいくつ買ったかと残りの所持金を返す。"""
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 2, "inner_thought": "買っておく"},
        )

        assert result.success is True
        assert "商人グスタフ" in result.message
        assert "80G" in result.message
        assert _gold(session) == 80

    def test_the_trace_payload_carries_the_gold_flow(self) -> None:
        """成功した売買は、source と増減を trace payload に残す。

        run 全体の通貨の流入・流出を trace.jsonl だけで集計できるようにする。
        """
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        payload = result.trace_payload
        assert payload["gold_change_source"] == "merchant_buy"
        assert payload["gold_delta"] == -10
        assert payload["gold_after"] == 90
        assert payload["merchant_name"] == "商人グスタフ"
        assert payload["traded_quantity"] == 1
        assert payload["traded_item_name"] == item

    def test_selling_reports_a_positive_gold_delta(self) -> None:
        """売った取引の trace は source が merchant_sell で、増減は正になる。"""
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)
        _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        result = _execute(
            session, _MORI, "sell_item",
            {"item_label": item, "quantity": 1, "inner_thought": "売る"},
        )

        assert result.success is True
        assert result.trace_payload["gold_change_source"] == "merchant_sell"
        assert result.trace_payload["gold_delta"] == 6


class TestLearnableFailures:
    """失敗が原因ごとに分かれ、次の一手が決まる形で返る。"""

    def test_not_enough_gold_names_the_shortfall(self) -> None:
        """所持金が足りないとき、不足額つきで専用の失敗コードを返す。"""
        session = _world(initial_gold=5, price=10)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買いたい"},
        )

        assert result.success is False
        assert result.error_code == "BUY_ITEM_NOT_ENOUGH_GOLD"
        assert "5G 足りません" in result.message
        assert result.remediation

    def test_selling_something_not_owned_is_rejected(self) -> None:
        """持っていない品を売ろうとすると、所持数つきで失敗する。"""
        session = _world(initial_gold=0, price=10)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "sell_item",
            {"item_label": item, "quantity": 1, "inner_thought": "売る"},
        )

        assert result.success is False
        assert result.error_code == "SELL_ITEM_NOT_OWNED"

    def test_an_unknown_item_is_an_item_problem(self) -> None:
        """商人は居るが扱わない品を指定したときは「品の失敗」として返る。

        場所の失敗 (MERCHANT_NOT_AT_SPOT) と区別する。扱う品を添えるので、
        次の一手は商人節を読み直すことに決まる。
        """
        session = _world()

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": "存在しない品", "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is False
        assert result.error_code == "BUY_ITEM_NOT_SOLD_HERE"
        assert "商人グスタフ" in result.message

    def test_trading_away_from_the_merchant_is_a_location_problem(self) -> None:
        """商人の居ない場所からの取引は「場所の失敗」として返る。

        品名の誤り (BUY_ITEM_NOT_SOLD_HERE) と同じコードに畳まない。文面が
        似ていても、次の一手は「移動する」と「品名を読み直す」で違う。trace で
        未発火理由を集計したときも、2 つが混ざると原因を切り分けられない。
        """
        session = _world()
        runtime = session.runtime
        item = _traded_item_name(session)
        graph = runtime._spot_graph_repo.find_graph()
        merchant_spot = runtime.scenario.merchants[0].spot_id
        elsewhere = next(
            node.spot_id for node in graph.iter_spot_nodes()
            if node.spot_id != merchant_spot
        )
        graph.unplace_entity(EntityId.create(int(_MORI)))
        graph.place_entity(EntityId.create(int(_MORI)), SpotId.create(elsewhere.value))
        runtime._spot_graph_repo.save(graph)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is False
        assert result.error_code == "MERCHANT_NOT_AT_SPOT"

    @pytest.mark.parametrize("quantity", [0, -1, 100])
    def test_an_out_of_range_quantity_fails_as_a_quantity_problem(self, quantity: int) -> None:
        """個数が範囲外のとき、金の話ではなく数量の誤りとして失敗する。"""
        session = _world(initial_gold=1000, price=1)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": quantity, "inner_thought": "買う"},
        )

        assert result.success is False
        assert "個数" in result.message

    def test_two_merchants_selling_the_same_item_require_a_choice(self) -> None:
        """同じ品を 2 人が売っているとき、価格を添えて相手の指定を促す。

        engine が最安を勝手に選ばない。どちらと取引するかは価格差のある世界では
        意思決定そのもので、勝手に選ぶと「安い方を選んだ」という判断が
        エージェントの経験から消える。
        """
        session = _world(initial_gold=100, price=10, second_merchant_price=8)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        assert result.success is False
        assert "10G" in result.message and "8G" in result.message
        assert _gold(session) == 100

    def test_naming_the_merchant_resolves_the_ambiguity(self) -> None:
        """merchant_label で相手を指定すれば、その商人の価格で成立する。"""
        session = _world(initial_gold=100, price=10, second_merchant_price=8)
        item = _traded_item_name(session)

        result = _execute(
            session, _MORI, "buy_item",
            {
                "item_label": item,
                "quantity": 1,
                "merchant_label": "商人マーサ",
                "inner_thought": "安い方で買う",
            },
        )

        assert result.success is True
        assert _gold(session) == 92


class TestOthersSeeTheTrade:
    """同席の第三者に取引が観測される。"""

    def test_a_bystander_observes_the_purchase(self) -> None:
        """同じ場所に居る別のプレイヤーの直近の出来事に、取引の一文が届く。

        現在の状況にある「商人:」節には商人名も品名も常に出ているので、
        **そちらではなく直近の出来事の本文を見る**。節の方を見ると、観測が
        1 件も届いていなくてもこのテストは緑になる。
        """
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)
        _put_both_at_the_merchant(session)

        _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        prompt = session.runtime.build_full_prompt(_SENA)["messages"][1]["content"]
        assert f"モリが商人グスタフから{item}を1つ買った。" in prompt

    def test_selling_is_observed_as_selling(self) -> None:
        """売った取引は「売った」として届く (買いと文面が入れ替わらない)。"""
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)
        _put_both_at_the_merchant(session)
        _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )
        session.runtime.build_full_prompt(_SENA)

        _execute(
            session, _MORI, "sell_item",
            {"item_label": item, "quantity": 1, "inner_thought": "売る"},
        )

        prompt = session.runtime.build_full_prompt(_SENA)["messages"][1]["content"]
        assert f"モリが商人グスタフに{item}を1つ売った。" in prompt

    def test_the_buyer_does_not_observe_their_own_purchase(self) -> None:
        """本人には観測として流さない (ツール結果と二重にならないようにする)。

        **本人の手番を回さずに確かめる。** ツール経由で買わせると、本人の
        観測はその手番の prompt 構築で汲み出されてしまい、配信されていても
        後から見ると空になる。それでは配信先を間違えても緑になる。
        """
        session = _world(initial_gold=100, price=10)
        _put_both_at_the_merchant(session)
        runtime = session.runtime
        merchant = runtime.scenario.merchants[0]

        runtime._merchant_trade_service.buy(
            _MORI,
            merchant_id=merchant.merchant_id,
            item_spec_id=merchant.sells[0].item_spec_id,
            quantity=1,
        )

        actor_entries = runtime._obs_buffer.drain(_MORI)
        bystander_entries = runtime._obs_buffer.drain(_SENA)
        assert not [
            entry for entry in actor_entries
            if entry.output.structured.get("type") == "player_traded_with_merchant"
        ]
        assert [
            entry for entry in bystander_entries
            if entry.output.structured.get("type") == "player_traded_with_merchant"
        ]

    def test_the_trade_does_not_wake_the_bystander(self) -> None:
        """取引の観測は同席者の手番を起こさない (相手は NPC で、次の一手も変わらない)。"""
        session = _world(initial_gold=100, price=10)
        item = _traded_item_name(session)
        _put_both_at_the_merchant(session)

        _execute(
            session, _MORI, "buy_item",
            {"item_label": item, "quantity": 1, "inner_thought": "買う"},
        )

        entries = session.runtime._obs_buffer.drain(_SENA)
        assert entries
        assert all(entry.output.schedules_turn is False for entry in entries)


class TestTheToolsFollowTheWorldDeclaration:
    """売買ツールが、宣言のある世界にだけ、宣言どおりに出る。"""

    def test_both_tools_are_offered_where_merchants_exist(self) -> None:
        """商人を宣言した世界では、買いと売りの両方が LLM に渡る一覧に出る。"""
        session = _world()

        names = [
            definition.name
            for definition in session.runtime.get_tool_definitions(for_every_player=True)
        ]

        assert "buy_item" in names
        assert "sell_item" in names

    def test_a_scenario_can_drop_only_buying(self) -> None:
        """disabled_tools で買いだけ落とすと、売りは残る。

        「売れるが買えない世界」(換金所だけの町など) を engine を触らずに
        書けることを保証する。
        """
        session = _world(disabled_tools=("buy_item",))

        names = [
            definition.name
            for definition in session.runtime.get_tool_definitions(for_every_player=True)
        ]

        assert "buy_item" not in names
        assert "sell_item" in names

    def test_a_dropped_tool_is_not_advertised_in_the_prompt(self) -> None:
        """落としたツールの名前が、プロンプト本文にも出ない。"""
        session = _world(disabled_tools=("buy_item",))

        observation = session.runtime.build_observation(_MORI)

        assert "buy_item" not in observation
