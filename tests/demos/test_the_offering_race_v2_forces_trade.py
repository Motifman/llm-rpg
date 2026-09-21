"""供物競争 v2 は、取引しなければ 1 歩も進めない形になっている (経済 Phase 4)。

**設計表をそのままテストに置く。** この世界が作ろうとしている力は 3 つ。

| 力 | 構造 |
|---|---|
| 取引の強制 | **自組の産物は自分の祭壇に納められない**。供物は全部敵から来る |
| 交換比の争点 | **供物の内訳が非対称** (東 薬草4+45G / 西 麦束3+60G)。1 対 1 で交換し続けると西が先に納め終わるので、東は割合を動かすか金で買うしかない |
| gold の敵対 | 総量 80G 固定 (蛇口なし) に対し必要 105G。刻限の同数時は納めた金でタイブレーク |

v1 の教訓: 自組の産物を納められると、**取引を回避する行動が最初の 48 tick を
食べる**。実 run でガレンは麦 3 束を全部自分の祭壇に納め、唯一の交渉材料を
自分で消してから「取引材料を作る」ために刈り直していた。v2 は納め口そのものを
外し、最初の一歩から取引が要る形にする。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_RACE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "offering_race_v2.json"
)

_GAREN, _DONA, _SERA, _YUNO = (PlayerId(i) for i in range(1, 5))
_NAME_TO_ID = {"ガレン": _GAREN, "ドナ": _DONA, "セラ": _SERA, "ユノ": _YUNO}

#: 組の設計表。行 = 人、列 = できる採取。
_TEAM_MATRIX: dict[str, dict[str, bool]] = {
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
#: 祭壇が受ける品。**自組の産物は入っていない** (これが v2 の核)。
_ALTAR_ACCEPTS = {"east_altar": "herb", "west_altar": "wheat"}
#: 組が採れる品。
_TEAM_PRODUCE = {"east": "wheat", "west": "herb"}

#: 供物の内訳。**組ごとに違う** — 対称だと 1 対 1 の交換が判定に対して
#: 中立になり、いくら取引しても引き分けのままになる (初版 v2 の欠陥)。
_OFFER = {
    "east": {"material": 4, "gold": 45},
    "west": {"material": 3, "gold": 60},
}
_GOLD_UNIT = 15
_INITIAL_GOLD = 20
_TEAM_SIZE = 2
_PLAYERS = 4


class _Race:
    def __init__(self) -> None:
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        self.runtime = create_world_runtime(str(_RACE))
        self.raw: dict[str, Any] = json.loads(_RACE.read_text(encoding="utf-8"))

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
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

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
        """働きかけを試し、(できたか, 断り文) を返す。

        **「前提を満たさない」と「その操作が無い」の両方を拾う。**
        v2 は自組の産物の納め口そのものを外したので、後者が正常な断り方に
        なる (前提で弾くだけだと「持てば通る」と読まれる)。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
            InteractionNotFoundException,
        )

        try:
            result = self.interact(player_id, object_id, action)
        except (InteractionNotAllowedException, InteractionNotFoundException) as exc:
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

    def fill_offering(self, altar: str, team_players: list[PlayerId]) -> None:
        """供物 (敵の産物 4 つと 45G) を祭壇に納め切る。

        **敵から手に入れる過程は省略して**、テストでは材料を直接持たせる
        (取引が要ることは別のクラスで構造として確かめる)。gold は組の合算
        40G でも 45G に届かないので、ここも直接足して埋める。
        """
        payer = team_players[0]
        side = altar.split("_")[0]
        accepts = _ALTAR_ACCEPTS[altar]
        need = _OFFER[side]
        self.give(payer, accepts, need["material"])
        self.interact(payer, altar, f"offer_{accepts}")
        status = self.runtime._player_status_repo.find_by_id(payer)
        status.earn_gold(need["gold"])
        self.runtime._player_status_repo.save(status)
        for _ in range(need["gold"] // _GOLD_UNIT):
            self.interact(payer, altar, "offer_gold")


#: ループの安全弁。**境界ではない** — 刻限を跨ぐまで回すための余裕で、
#: 判定 tick の境界そのものは `test_the_judgment_compares_enemy_produce_then_gold`
#: が `TICK_LIMIT - 1` として固定する。
_GENEROUS_TICK_BOUND = 200


def _tick_limit(race: _Race) -> int:
    """世界が自分で終わる tick。`max_world_ticks` はループ上限で、これとは別。"""
    return next(
        c["tick_limit"]
        for c in race.raw["game_end_conditions"]["lose"]
        if c["type"] == "TICK_LIMIT"
    )


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


class TestTheTablesCross:
    """設計表どうしが交差している (自組の産物 ≠ 自分の祭壇が受ける品)。

    表を置いただけで拘束していないと、**表と世界がずれても緑のまま**に
    なる。2 つの表が必ず食い違うことを、ここで 1 行にする。
    """

    @pytest.mark.parametrize("side", sorted(_TEAM_PRODUCE))
    def test_your_altar_never_accepts_your_own_produce(self, side: str) -> None:
        assert _TEAM_PRODUCE[side] != _ALTAR_ACCEPTS[f"{side}_altar"]


class TestYourOwnProduceCannotBeOffered:
    """**v2 の核**: 自分の組が採れるものを納める道が、世界に存在しない。

    v1 ではここが開いていたため、実 run で東の組は麦 3 束を自分の祭壇に
    納め (= 唯一の交渉材料を消し)、48 tick を自給自足に費やした。
    """

    @pytest.mark.parametrize("altar", sorted(_ALTAR_ACCEPTS))
    def test_the_altar_has_no_door_for_your_own_produce(
        self, race: _Race, altar: str
    ) -> None:
        """祭壇の操作一覧に、自組の産物の納め口が無い。

        「持っていないから失敗する」ではなく **操作そのものが無い**。
        前提条件で弾くだけだと、持てば通ると読んで手番を溶かす。
        """
        raw_altar = next(
            o
            for s in race.raw["spots"]
            for o in s.get("interior", {}).get("objects", [])
            if o["id"] == altar
        )
        actions = {i["action_name"] for i in raw_altar["interactions"]}
        accepts = _ALTAR_ACCEPTS[altar]
        own = "wheat" if accepts == "herb" else "herb"

        assert f"offer_{accepts}" in actions, "受ける品の納め口が無い (正の対照)"
        assert f"offer_{own}" not in actions
        assert "offer_gold" in actions

    def test_holding_your_own_produce_does_not_help(self, race: _Race) -> None:
        """自組の産物を持っていても、自分の祭壇には納められない。

        宣言 (上のテスト) だけでなく、実経路でも道が無いことを見る。
        """
        race.give(_GAREN, "wheat", 2)

        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotFoundException,
        )

        with pytest.raises(InteractionNotFoundException):
            race.interact(_GAREN, "east_altar", "offer_wheat")

    def test_the_enemy_produce_is_accepted(self, race: _Race) -> None:
        """敵の産物なら納められる (**正の対照**)。"""
        race.give(_GAREN, "herb", 2)

        race.interact(_GAREN, "east_altar", "offer_herb")

        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        interior = race.runtime._spot_interior_repo.find_by_spot_id(
            SpotId.create(race.runtime.id_mapper.get_int("spot", "festival_square"))
        )
        altar = interior.get_object(
            SpotObjectId.create(race.runtime.id_mapper.get_int("object", "east_altar"))
        )
        assert altar.state["herb_offered"] == 2


class TestOnlyYourTeamCanUseYourAltar:
    """祭壇の組ゲート。敵の祭壇には妨害でも間違いでも納められない。"""

    @pytest.mark.parametrize("action", ["offer_wheat", "offer_gold"])
    def test_the_enemy_altar_refuses(self, race: _Race, action: str) -> None:
        """東の人は西の祭壇のどの納め口も使えない。"""
        race.give(_GAREN, "wheat", 1)

        did, message = race.try_work(_GAREN, "west_altar", action)

        assert did is False
        assert "西の衆だけ" in message


class TestGoldIsAZeroSumWeapon:
    """gold の算術が「敵から稼ぐしかない」を成立させている。

    v3.7 の設計ミス (初期資金だけで gold 条件を満たせた) の再発防止。
    値そのものではなく**関係**で固定する。
    """

    def test_the_design_constants_match_the_scenario(self, race: _Race) -> None:
        """このテストの設計値が、シナリオの 4 イベント全部と一致している。

        関係のテスト (下 2 件) は設計値どうしの算術なので、シナリオだけを
        書き換えると**表とずれたまま緑になる**。ここで突き合わせて、
        どちらを変えても片方だけの変更が落ちるようにする。**東側だけを
        見ると、西だけ供物が安い改変が素通りする** (レビューの変異で実証)。

        (`ticks_offset` は OBJECT_STATE_INT_AT_LEAST では閾値の流用。
        45 は tick ではなく gold の額。)
        """
        assert all(p["initial_gold"] == _INITIAL_GOLD for p in race.raw["players"])
        assert len(race.raw["players"]) == _PLAYERS
        east = [p for p in race.raw["players"] if p["initial_state"]["team"] == "east"]
        assert len(east) == _TEAM_SIZE

        for side in ("east", "west"):
            complete = next(
                e for e in race.raw["scenario_events"]
                if e["id"] == f"{side}_offering_complete"
            )
            declared = {
                (c["target_object"], c["state_key"]): c["ticks_offset"]
                for c in complete["conditions"]
                if c["condition_type"] == "OBJECT_STATE_INT_AT_LEAST"
            }
            altar = f"{side}_altar"
            accepts = _ALTAR_ACCEPTS[altar]
            assert declared == {
                (altar, f"{accepts}_offered"): _OFFER[side]["material"],
                (altar, "gold_offered"): _OFFER[side]["gold"],
            }, side

    def test_the_judgment_compares_enemy_produce_then_gold(self, race: _Race) -> None:
        """判定は敵の産物の数で決め、同数なら納めた金でタイブレークする。

        **同数を引き分けのままにすると、1 対 1 の交換が判定に対して中立に
        なり、いくら取引しても共倒れで終わる** (初版 v2 の欠陥)。金の
        タイブレークで、引き分けが吸収状態でなくなる。

        条件は OR(材料で勝ち, AND(材料で負けていない, 金で勝ち)) の形。

        判定 tick は世界の刻限から 1 引いた値で、**刻限を延ばしたら一緒に
        動かないと判定そのものが起きない**。run 長を伸ばす改変で、この対が
        黙って外れるのを止める。
        """
        for side, mine, theirs in (
            ("east", "herb_offered", "wheat_offered"),
            ("west", "wheat_offered", "herb_offered"),
        ):
            event = next(
                e for e in race.raw["scenario_events"]
                if e["id"] == f"{side}_judged_win"
            )
            other = "west" if side == "east" else "east"
            tick = next(
                c["tick"] for c in event["conditions"]
                if c["condition_type"] == "TICK_AT_LEAST"
            )
            assert tick == _tick_limit(race) - 1, side

            branch = next(
                c for c in event["conditions"] if c["condition_type"] == "OR"
            )
            material_win, gold_tiebreak = branch["children"]

            assert (
                material_win["target_object"], material_win["state_key"],
                material_win["other_object"], material_win["other_state_key"],
            ) == (f"{side}_altar", mine, f"{other}_altar", theirs), side

            not_losing, gold_win = gold_tiebreak["children"]
            assert not_losing["condition_type"] == "NOT"
            losing = not_losing["children"][0]
            assert (
                losing["target_object"], losing["state_key"],
            ) == (f"{other}_altar", theirs), side
            assert (
                gold_win["target_object"], gold_win["state_key"],
                gold_win["other_object"], gold_win["other_state_key"],
            ) == (f"{side}_altar", "gold_offered",
                  f"{other}_altar", "gold_offered"), side

    def test_one_for_one_trading_does_not_stay_even(self, race: _Race) -> None:
        """1 対 1 で交換し続けると、西が先に納め終わる。

        **これが v2 の争点**。対称だと k:k のまま永遠に引き分けなので、
        交渉は「するかしないか」で止まる。非対称なら東は割合を動かすか
        金で買うしかなくなり、値付けが観測対象として立ち上がる。
        """
        east, west = _OFFER["east"]["material"], _OFFER["west"]["material"]

        assert east != west, "供物の数が対称だと 1 対 1 交換が中立になる"
        assert west < east, "先に納め切るのは西 (東は割合か金で対抗する)"

    def test_both_teams_cannot_complete_on_the_world_supply(
        self, race: _Race
    ) -> None:
        """必要額の合計が、世界の gold 総量を上回る。

        これが崩れると、両組が取引なしで gold 条件を満たせてしまう。
        gold の蛇口 (商人・報酬) が無いことは下のテストが守る。
        """
        world_gold = sum(p["initial_gold"] for p in race.raw["players"])
        needed = _OFFER["east"]["gold"] + _OFFER["west"]["gold"]

        assert needed > world_gold

    def test_one_team_cannot_complete_on_its_own_purse(self, race: _Race) -> None:
        """1 組の初期資金では自分の必要額に届かない。

        届いてしまうと、物々交換だけで完走できる (v3.7 の C-1)。
        """
        team_gold = _INITIAL_GOLD * _TEAM_SIZE

        assert all(team_gold < need["gold"] for need in _OFFER.values())

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
        assert all(need["gold"] % amount == 0 for need in _OFFER.values())


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
        assert race.raw["market"]["order_expires_in_ticks"] < _tick_limit(race)

    def test_the_deadline_the_agents_are_told_is_the_real_one(
        self, race: _Race
    ) -> None:
        """シナリオ説明文が名乗る刻限が、実際の `TICK_LIMIT` と一致する。

        エージェントは説明文の刻限を読んで計画を立てる。**run 長を伸ばした
        ときに文が置いていかれると、残り時間を実際より短く見積もる。**
        """
        limit = _tick_limit(race)

        assert f"刻限 ({limit} tick)" in race.raw["metadata"]["description"]
        assert race.raw["market"]["initial_orders"] == []


class TestTheAltarKeepsItsSecrets:
    """祭壇の中身は、広場に立っても読めない。"""

    @pytest.mark.parametrize(
        "actor,altar,accepts,viewer",
        [(_GAREN, "east_altar", "herb", _SERA), (_SERA, "west_altar", "wheat", _GAREN)],
    )
    def test_counters_do_not_leak_into_the_prompt(
        self, race: _Race, actor, altar: str, accepts: str, viewer
    ) -> None:
        """敵 (と味方) のプロンプトに祭壇のカウンタが出ない。

        object.state は既定でスポット描画に全部載る (過去に設定漏れで
        漏洩した回帰がある)。hidden_state_keys の宣言が実際に効いている
        ことを、実プロンプトで確かめる。
        """
        race.give(actor, accepts, 2)
        race.interact(actor, altar, f"offer_{accepts}")

        text = race.runtime.build_llm_context(viewer).current_state_text

        assert "祭壇" in text, "祭壇そのものは見える (正の対照)"
        assert f"{accepts}_offered" not in text
        assert "gold_offered" not in text


class TestTheFieldsGrowBack:
    """材料は再生する。止まると全 run が共倒れ確定になる。

    再生間隔 4 tick の意図: **材料は潤沢**。自組の産物は自分の祭壇に納められ
    ないので、採れた分はすべて敵に渡す対価になる。窮乏は gold 側 (総量 80 に
    対し必要 105) に寄せ、材料の希少さで競争を作らない設計。

    **run 長を伸ばしても窮乏は緩まない。** gold の総量は run 長と無関係に
    80 で固定なので、材料の収穫回数が増えても取引の必然性は動かない。
    """

    @pytest.mark.parametrize("job", sorted(_WORK))
    def test_a_harvest_depletes_and_returns(self, race: _Race, job: str) -> None:
        """採る → 枯れる → 4 tick 後にまた採れる (**両方の産地で**)。

        東側だけを見ていると、薬草の再生だけを止める改変が素通りする
        (= 世界に薬草が 1 個しか出ず、東の勝利が構造的に不可能になる)。

        reactive_bindings を消しても他のテストは 1 回しか採取しないので
        気づけない (レビューの変異で実証)。世界に材料が各 1 個しか出ない
        run は、宣言した勝ち筋がすべて構造的に不可能になる。
        """
        spot, target = _WORK[job]
        who = next(
            _NAME_TO_ID[name]
            for name, jobs in _TEAM_MATRIX.items()
            if jobs[job]
        )
        race.place(who, spot)
        did, _ = race.try_work(who, target, job)
        assert did is True

        did, message = race.try_work(who, target, job)
        assert did is False
        assert "また" in message

        for _ in range(5):
            race.runtime.advance_tick()

        did, _ = race.try_work(who, target, job)
        assert did is True


class TestTheOnlyIntelligenceChannelWorks:
    """「納める瞬間の目撃」がこの世界唯一の諜報チャネルとして機能する。"""

    @pytest.mark.parametrize(
        "actor,altar,accepts,witness,word",
        [
            (_GAREN, "east_altar", "herb", _SERA, "薬草を納めた"),
            (_SERA, "west_altar", "wheat", _GAREN, "麦束を納めた"),
        ],
    )
    def test_the_enemy_witnesses_the_deposit(
        self, race: _Race, actor, altar: str, accepts: str, witness, word: str
    ) -> None:
        """敵が同じ広場に居れば、納めた行為が観測として届く。

        目撃文を消しても幕 (hidden_state_keys) のテストは緑のままなので、
        ここで配信まで見る (レビューの変異で実証)。数値は漏れない。
        """
        race.runtime._obs_buffer.drain(witness)
        race.give(actor, accepts, 2)

        race.interact(actor, altar, f"offer_{accepts}")

        seen = " ".join(
            e.output.prose for e in race.runtime._obs_buffer.drain(witness)
        )
        assert word in seen
        assert "2" not in seen, "納めた個数は目撃文に漏れない"


class TestTheBoardStandsInTheSquare:
    """掲示板は広場にある (匿名の取引と目撃が同じ場所に集まる)。"""

    def test_board_spot_is_the_square(self, race: _Race) -> None:
        assert race.raw["market"]["board_spot"] == "festival_square"


class TestTheAnalystCanReadTheCurtainedCounters:
    """幕の内の数は、エージェントには見えず、分析者には trace で見える。"""

    def test_deposits_carry_state_changes_for_the_trace(self, race: _Race) -> None:
        """納める操作の結果が、カウンタの増分を trace 転記用に運ぶ。

        これが無いと、run の主要測定対象 (供物の進行) を message 文字列
        からの逆算で再生することになる (見落としの型)。
        """
        race.give(_GAREN, "herb", 2)

        result = race.interact(_GAREN, "east_altar", "offer_herb")

        changes = {
            (c["object"], c["state_key"]): (c["before"], c["after"])
            for c in result.object_state_changes
        }
        assert changes[("東の祭壇", "herb_offered")] == (0, 2)


class TestSimultaneousCompletionBreaksEast:
    """同 tick に両組が納め終えたら、宣言順で東が勝つ。

    これは規則としての選択ではなく、scenario_events の評価順 (JSON の
    宣言順) の帰結。恣意的なタイブレークだが、**未文書のまま挙動が変わる**
    ことを防ぐためにここで固定する。変えるなら宣言順を入れ替える。
    """

    def test_east_wins_a_dead_heat(self, race: _Race) -> None:
        race.fill_offering("east_altar", [_GAREN, _DONA])
        race.fill_offering("west_altar", [_SERA, _YUNO])

        race.runtime.advance_tick()

        assert "east_offering_complete" in race.flags()
        assert "west_offering_complete" not in race.flags()


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

        for _ in range(_GENEROUS_TICK_BOUND):
            if race.runtime.check_game_end().is_ended:
                break
            race.runtime.advance_tick()

        assert "east_judged_win" in race.flags()
        assert "west_judged_win" not in race.flags()

    def test_a_tie_lets_the_festival_die(self, race: _Race) -> None:
        """敵の産物が同数 (0 対 0) なら判定は出ず、刻限で共倒れに終わる。"""
        for _ in range(_GENEROUS_TICK_BOUND):
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
                self.tools: list[Any] = []

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


class TestTheWorldOnlyOffersToolsItCanUse:
    """この世界で使えない道具は出さず、敵対を成立させる道具は落とさない。"""

    def test_the_disabled_set_is_exactly_what_we_expect(self, race: _Race) -> None:
        """無効化するツールの集合を固定する。

        **`attack` が黙って復活したら run の意味が変わる** (敵対 2 組の世界で
        暴力が使えるかは別の実験)。集合そのものを見るので、増えても減っても
        落ちる。
        """
        assert set(race.raw["disabled_tools"]) == {
            "attack", "explore", "listen", "tend_to_player", "drop_item",
        }

    def test_the_tools_that_make_trading_possible_are_kept(
        self, race: _Race
    ) -> None:
        """取引の道具は落とさない (**正の対照**)。"""
        disabled = set(race.raw["disabled_tools"])

        assert not (
            {"give_item", "trade_offer", "market_list_item", "market_bid"}
            & disabled
        )


class TestGoldIsSpentIntoTheAltarForever:
    """祭壇に入った gold は流通から消え、両組の到達可能額を削る。"""

    def test_offering_gold_shrinks_what_anyone_can_still_reach(
        self, race: _Race
    ) -> None:
        """両組が納めるほど、残る流通では誰も必要額に届かなくなる。

        **この世界の詰み条件**。開幕に全員が納めると流通が枯れて両組とも
        納め切りが不可能になるので、gold の納め口には「まず敵の産物を
        1 つ納めてから」の歯止めを置いてある (下のクラス)。
        """
        world = _INITIAL_GOLD * _PLAYERS
        spent_each_side = _GOLD_UNIT * 2  # 各組が 2 回ずつ納めた時点
        remaining_world = world - spent_each_side * 2
        still_needed = sum(
            need["gold"] - spent_each_side for need in _OFFER.values()
        )

        assert remaining_world < still_needed, (
            "納めた gold が流通から消える性質が失われている"
        )


class TestGoldComesAfterTheOffering:
    """賽銭は供物のあと。金だけ先に納めて自分の首を絞める道を閉じる。"""

    def test_gold_is_refused_before_any_material(self, race: _Race) -> None:
        """敵の産物を 1 つも納めていないと、gold を納められない。

        **移動も交渉もなく tick 0 に撃てる一手**だったので、全員がやると
        流通が枯れて両組とも詰む。取引の後にしか進めない形に揃える。
        """
        did, message = race.try_work(_GAREN, "east_altar", "offer_gold")

        assert did is False
        assert "供物のあと" in message

    def test_gold_is_accepted_after_the_first_material(self, race: _Race) -> None:
        """敵の産物を 1 つ納めた後なら、gold を納められる (**正の対照**)。"""
        race.give(_GAREN, "herb", 1)
        race.interact(_GAREN, "east_altar", "offer_herb")

        did, _ = race.try_work(_GAREN, "east_altar", "offer_gold")

        assert did is True
