"""station_drill の通気口が、宣言だけで「見られなければ秘密の移動」になることを保証する。

## この試験が守るもの

通気口は engine の機能ではなく、`TELEPORT_ENTITY` に観測文を宣言しただけのもの。
そのため守るべきは 3 つに分かれる。

1. **使える人が絞られていること** — クルーと幽霊には候補にも出ず、直接呼んでも通らない
2. **暗所でも見えること** — 暗い区画のオブジェクトは一覧から消えるので、
   `is_visible_in_dark` が無いと使う側にも見えない (配線箱と同じ罠)
3. **観測が明暗で書き分けられること** — 明るければ誰が出入りしたか分かり、
   暗ければ音だけになる

3 は「移動が秘密になりうる」ことの土台で、本家の読み合いはここに乗っている。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)  # keeper (インポスター)
_AOI = PlayerId(4)
_HAGI = PlayerId(5)
_YURA = PlayerId(6)
_JIN = PlayerId(7)  # keeper (インポスター)
_SAKI = PlayerId(8)
_VENT_KNOWLEDGE = (
    "区画によっては、床に近い壁に通気口の格子がある。あれを通り抜けられるのは、"
    "この観測所の造りを知る者だけだ。自分には開けられない。誰かが通ったと"
    "分かったなら、それはその人物がそういう立場にあるということだ。"
)
_BOARD_VENT_KNOWLEDGE = "通気口の格子は、造りを知る者でなければ開かない。"
_IMPOSTOR_VENT_KNOWLEDGE = (
    "観測室と物資庫の壁の下部にある格子は互いに繋がっていて、そこを通り抜けられる。"
    "通り抜けたところを誰にも見られなければ、その移動には気づかれない。"
    "クルーにはこの格子を開けられない。"
)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _spot(runtime, name: str):
    return runtime.id_mapper.get_int("spot", name)


def _place(runtime, player_id: PlayerId, spot_name: str) -> None:
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId

    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    try:
        graph.unplace_entity(entity)
    except Exception:
        pass
    graph.place_entity(entity, SpotId.create(_spot(runtime, spot_name)))
    # **配置ぶんのイベントをここで捨てる。** 残すと次の interaction の
    # publish_all に相乗りし、「クゼが観測室にやってきた。」が目撃者へ届く。
    # 準備の副産物を本番の観測と混ぜると、漏れの検査が空振りする。
    graph.clear_events()
    runtime._spot_graph_repo.save(graph)


def _vent(runtime, player_id: PlayerId, object_sid: str, action_name: str):
    """実行経路 (SpotInteractionApplicationService) から通気口を使う。"""
    from ai_rpg_world.domain.common.value_object import WorldTick
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
        SpotObjectId,
    )

    return runtime._interaction_service.execute_interaction(
        player_id,
        SpotObjectId.create(runtime.id_mapper.get_int("object", object_sid)),
        action_name,
        current_tick=WorldTick(runtime.current_tick()),
    )


def _current_spot(runtime, player_id: PlayerId) -> int:
    graph = runtime._spot_graph_repo.find_graph()
    return int(graph.get_entity_spot(EntityId.create(int(player_id))))


def _vent_actions_offered_to(runtime, player_id: PlayerId) -> list[str]:
    snapshot = runtime._state_builder.build_snapshot(int(player_id))
    assert snapshot is not None
    return [line for line in snapshot.object_lines if "通気口" in line]


def _vent_prompt_lines(runtime, player_id: PlayerId) -> list[str]:
    """実際の手番プロンプトから通気口の説明行を取り出す。"""
    user_prompt = runtime.build_full_prompt(player_id)["messages"][1]["content"]
    return [line for line in user_prompt.splitlines() if '"通気口"' in line]


def _give_lantern(runtime, player_id: PlayerId) -> None:
    """実効照明の本番経路を通すため、player にシナリオ宣言のランタンを渡す。"""
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

    grant_item_specs_to_inventory(
        player_id,
        (ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "lantern")),),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


class TestOnlyTheImpostorCanVent:
    """通気口はインポスターにだけ差し出され、それ以外には実行もできない。"""

    def test_the_impostor_moves_between_the_two_rooms(self, runtime) -> None:
        """keeper が通気口を使うと、接続を辿らずに物資庫へ移る。"""
        _place(runtime, _KUZE, "observatory")

        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        assert _current_spot(runtime, _KUZE) == _spot(runtime, "storage")

    def test_a_crew_member_is_refused(self, runtime) -> None:
        """クルーが直接呼んでも、役割の前提条件で拒否される。"""
        _place(runtime, _SENA, "observatory")

        with pytest.raises(InteractionNotAllowedException):
            _vent(runtime, _SENA, "observatory_vent", "enter_vent_to_storage")

    def test_the_vent_is_visible_in_the_dark(self, runtime) -> None:
        """灯り無しの観測室でも通気口は一覧に出る (出ないと使えない手になる)。"""
        darken_spot(runtime, "observatory")
        _place(runtime, _KUZE, "observatory")

        assert _vent_actions_offered_to(runtime, _KUZE) != []

    @pytest.mark.parametrize(
        ("spot_name", "hidden_destination"),
        (("observatory", "物資庫"), ("storage", "観測室")),
    )
    def test_crew_see_the_grate_without_being_told_its_destination(
        self, runtime, spot_name: str, hidden_destination: str
    ) -> None:
        """使えないクルーには通気口を見せても、接続先を説明で宣伝しない。"""
        _place(runtime, _SENA, spot_name)

        lines = _vent_prompt_lines(runtime, _SENA)

        assert len(lines) == 1
        assert hidden_destination not in lines[0]
        assert "通気口に潜り込む" not in lines[0]

    @pytest.mark.parametrize(
        ("spot_name", "action_name"),
        (
            ("observatory", "enter_vent_to_storage"),
            ("storage", "enter_vent_to_observatory"),
        ),
    )
    def test_the_impostor_still_sees_the_destination_action(
        self, runtime, spot_name: str, action_name: str
    ) -> None:
        """使える keeper には、説明でなく操作名を通じて接続先を伝える。"""
        _place(runtime, _KUZE, spot_name)

        lines = _vent_prompt_lines(runtime, _KUZE)

        assert len(lines) == 1
        assert action_name in lines[0]

    def test_a_ghost_is_refused(self, runtime) -> None:
        """幽霊にも通気口は使えない (第 1 版は LIVING だけを宣言している)。"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        _place(runtime, _KUZE, "observatory")
        observatory = SpotId.create(_spot(runtime, "observatory"))
        runtime._fallen_body_registry.record(_KUZE, observatory, WorldTick(1))
        runtime._player_outcome_registry.set_outcome(_KUZE, PlayerOutcomeEnum.DEAD)

        with pytest.raises(InteractionNotAllowedException):
            _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")


class TestTheVentRestrictionIsSharedKnowledge:
    """クルーは通気口を試さず、通った人物を疑うための前提だけを知る。"""

    @pytest.mark.parametrize(
        "player_id", (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI)
    )
    def test_each_crew_member_knows_the_vent_is_not_for_them(
        self, runtime, player_id: PlayerId
    ) -> None:
        """クルー6人の実プロンプトに、非公開の使い手を推理する前提が届く。"""
        messages = runtime.build_full_prompt(player_id)["messages"]
        prompt = "\n".join(message["content"] for message in messages)

        assert _VENT_KNOWLEDGE in prompt
        assert "各室の壁の下部には通気口の格子がある" not in prompt

    def test_no_crew_prompt_names_the_role_that_can_use_the_vent(
        self, runtime
    ) -> None:
        """クルーの実プロンプトは、使い手を一段で特定できる役割名を漏らさない。"""
        for player_id in (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI):
            messages = runtime.build_full_prompt(player_id)["messages"]
            prompt = "\n".join(message["content"] for message in messages)

            assert "管理人" not in prompt, runtime.get_player_name(player_id)
            assert "keeper" not in prompt, runtime.get_player_name(player_id)

    @pytest.mark.parametrize(
        "knowledge", (_VENT_KNOWLEDGE, _BOARD_VENT_KNOWLEDGE)
    )
    def test_the_added_knowledge_does_not_name_the_role(
        self, knowledge: str
    ) -> None:
        """persona と当番表へ足す知識文自体にも、使い手の役割名を書かない。"""
        assert "管理人" not in knowledge
        assert "keeper" not in knowledge

    def test_the_impostor_is_not_told_the_crew_only_limitation(self, runtime) -> None:
        """通気口を使えるクゼには「自分には開けられない」という嘘を渡さない。"""
        messages = runtime.build_full_prompt(_KUZE)["messages"]
        prompt = "\n".join(message["content"] for message in messages)

        assert "自分には開けられない" not in prompt


class TestTheImpostorsKnowWhatTheVentsEnable:
    """インポスター二人が、実配置と一致する秘密移動を事前に知る。"""

    @pytest.mark.parametrize("player_id", (_KUZE, _JIN))
    def test_each_impostor_system_prompt_explains_the_vent_ability(
        self, runtime, player_id: PlayerId
    ) -> None:
        """二人の system prompt は、二室間を秘密に移動できると伝える。"""
        system = runtime.build_full_prompt(player_id)["messages"][0]["content"]

        assert _IMPOSTOR_VENT_KNOWLEDGE in system

    @pytest.mark.parametrize("player_id", (_MORI, _SENA, _AOI, _HAGI, _YURA))
    def test_crew_system_prompts_do_not_receive_the_impostor_ability(
        self, runtime, player_id: PlayerId
    ) -> None:
        """クルーの既存知識には、クゼだけが知る秘密移動の説明を混ぜない。"""
        system = runtime.build_full_prompt(player_id)["messages"][0]["content"]

        assert _IMPOSTOR_VENT_KNOWLEDGE not in system

    def test_the_impostor_knowledge_does_not_name_the_hidden_role(self) -> None:
        """能力説明は、役割名や肩書きを使って正体を説明しない。"""
        assert "keeper" not in _IMPOSTOR_VENT_KNOWLEDGE
        assert "管理人" not in _IMPOSTOR_VENT_KNOWLEDGE

    def test_the_declared_vents_connect_exactly_the_two_named_rooms(self) -> None:
        """persona が名指す観測室と物資庫だけに通気口があり、互いを結ぶ。"""
        scenario = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        declared_connections: dict[str, str] = {}
        for spot in scenario["spots"]:
            for obj in spot["interior"]["objects"]:
                if obj.get("name") != "通気口":
                    continue
                teleport_effects = [
                    effect
                    for interaction in obj.get("interactions", [])
                    for effect in interaction.get("effects", [])
                    if effect.get("effect_type") == "TELEPORT_ENTITY"
                ]
                assert len(teleport_effects) == 1, obj["id"]
                declared_connections[spot["id"]] = teleport_effects[0][
                    "parameters"
                ]["target_spot"]

        assert declared_connections == {
            "observatory": "storage",
            "storage": "observatory",
        }


class TestWhatTheWitnessesSee:
    """明暗で観測が書き分けられる。ここに本家の読み合いが乗っている。"""

    def _outputs_for(self, runtime, player_id: PlayerId):
        """この player に届いた観測の (prose, structured) を返す。

        **entry の repr を丸ごと文字列にしてはいけない。** structured に残った
        名前まで拾ってしまい、prose で伏せたことを確かめられない (一度やった)。
        """
        return [
            (entry.output.prose, entry.output.structured or {})
            for entry in runtime._obs_buffer.drain(player_id)
        ]

    def test_a_dark_room_only_hears_the_vent(self, runtime) -> None:
        """灯りの無い観測室では、入ったのが誰かは分からず音だけが残る。"""
        darken_spot(runtime, "observatory")
        _place(runtime, _KUZE, "observatory")
        _place(runtime, _MORI, "observatory")

        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        outputs = self._outputs_for(runtime, _MORI)
        assert "ベントが開いて誰かが入った音がした。" in [p for p, _ in outputs]
        # **「ベント」を含む行だけを見てはいけない。** 最初そう書いていて、
        # 同じ interaction が出す SpotObjectInteractedEvent の
        # 「クゼが『通気口に潜り込む』を行った。」を見落とした。移動が匿名でも
        # 別のイベントから名前が漏れる。**届いた全部を見る。**
        #
        # structured も一緒に見る。prose だけ伏せても、structured を読む側
        # (記憶の索引など) が増えた瞬間に漏れる。
        assert "クゼ" not in str(outputs)

    def test_a_lit_room_sees_who_came_out(self, runtime) -> None:
        """灯りのある物資庫では、通気口から出てきたのが誰かまで見える。"""
        _place(runtime, _KUZE, "observatory")
        _place(runtime, _MORI, "storage")
        # 出発側だけを暗くする。同じ移動が
        # **出発と到着で別の文になる**ことも同時に確かめられる。
        darken_spot(runtime, "observatory")

        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        proses = [prose for prose, _ in self._outputs_for(runtime, _MORI)]
        assert "ベントが開いてクゼが中から出てきた。" in proses


class TestRecentVentTrace:
    """目撃者がいない通気口移動も、明るい場所では後から物理的な痕跡として読める。"""

    @pytest.mark.parametrize(
        ("spot_name", "object_sid", "action_name"),
        (
            ("observatory", "observatory_vent", "enter_vent_to_storage"),
            ("storage", "storage_vent", "enter_vent_to_observatory"),
        ),
    )
    def test_recent_use_leaves_a_visible_trace_in_a_lit_room(
        self,
        runtime,
        spot_name: str,
        object_sid: str,
        action_name: str,
    ) -> None:
        """両側の通気口は、使用直後に灯りを持つ同室者へ埃の乱れを表示する。"""
        _place(runtime, _KUZE, spot_name)
        _place(runtime, _SENA, spot_name)
        _give_lantern(runtime, _SENA)

        _vent(runtime, _KUZE, object_sid, action_name)

        lines = _vent_prompt_lines(runtime, _SENA)
        assert len(lines) == 1
        assert "格子の縁の埃が乱れている" in lines[0]

    def test_recent_use_does_not_reveal_a_visual_trace_in_the_dark(
        self, runtime
    ) -> None:
        """通気口自体が暗所で見えても、灯りが無ければ埃の乱れは読めない。"""
        darken_spot(runtime, "observatory")
        _place(runtime, _KUZE, "observatory")
        _place(runtime, _SENA, "observatory")

        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        lines = _vent_prompt_lines(runtime, _SENA)
        assert len(lines) == 1
        assert "格子の縁の埃が乱れている" not in lines[0]

    def test_trace_disappears_after_five_ticks(self, runtime) -> None:
        """使用から5手番を超えた痕跡は、灯りがあっても物体行から消える。"""
        _place(runtime, _KUZE, "observatory")
        _place(runtime, _SENA, "observatory")
        _give_lantern(runtime, _SENA)
        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        for _ in range(6):
            runtime.advance_tick()

        lines = _vent_prompt_lines(runtime, _SENA)
        assert len(lines) == 1
        assert "格子の縁の埃が乱れている" not in lines[0]

    def test_unused_vent_has_no_trace(self, runtime) -> None:
        """一度も使われていない通気口は、明るくても痕跡を捏造しない。"""
        _place(runtime, _SENA, "observatory")
        _give_lantern(runtime, _SENA)

        lines = _vent_prompt_lines(runtime, _SENA)
        assert len(lines) == 1
        assert "格子の縁の埃が乱れている" not in lines[0]

    def test_recorded_tick_never_leaks_into_the_prompt(self, runtime) -> None:
        """痕跡を導出しても、hidden な key と記録した生の手番は物体行へ出さない。"""
        _place(runtime, _KUZE, "observatory")
        _place(runtime, _SENA, "observatory")
        _give_lantern(runtime, _SENA)
        recorded_tick = runtime.current_tick()

        _vent(runtime, _KUZE, "observatory_vent", "enter_vent_to_storage")

        lines = _vent_prompt_lines(runtime, _SENA)
        assert len(lines) == 1
        assert "格子の縁の埃が乱れている" in lines[0]
        assert "opened_at_tick" not in lines[0]
        assert str(recorded_tick) not in lines[0]


class TestDarknessStillAnnouncesItself:
    """暗所可のオブジェクトが 1 つあっても、「灯りが要る」は消えない。

    通気口を暗所可にしたことで、観測室の一覧が空でなくなった。ヒントが
    「一覧が空のときだけ」出る作りだと、**配線箱が暗さで隠れていることを
    誰も知らせなくなる。**

    同じ失敗は既に一度起きている。builder のコメントに「実 run 010 でハギは
    『照明が落ちてるから、もっと調べないと見つからないのか』と推測し、explore と
    listen に手番を溶かした」と残っている。
    """

    def _object_section(self, runtime, player_id: PlayerId) -> str:
        text = runtime.build_llm_context(player_id).current_state_text
        start = text.index("オブジェクト:")
        rest = text[start:]
        end = rest.find("\n同じ場所")
        return rest if end < 0 else rest[:end]

    def test_a_dark_room_with_a_visible_object_still_asks_for_a_light(
        self, runtime
    ) -> None:
        """通気口だけ見える観測室でも、灯りが要ることは伝わる。"""
        darken_spot(runtime, "observatory")
        _place(runtime, _SENA, "observatory")

        section = self._object_section(runtime, _SENA)

        assert "通気口" in section
        assert "配線箱" not in section
        assert "灯りがなければ" in section
