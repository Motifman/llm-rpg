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

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)  # keeper (インポスター)


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
    # publish_all に相乗りし、「クゼが連絡通路にやってきた。」が目撃者へ届く。
    # 準備の副産物を本番の観測と混ぜると、漏れの検査が空振りする。
    graph.clear_events()
    runtime._spot_graph_repo.save(graph)


def _vent(runtime, player_id: PlayerId, object_sid: str, action_name: str):
    """実行経路 (SpotInteractionApplicationService) から通気口を使う。"""
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
        SpotObjectId,
    )

    return runtime._interaction_service.execute_interaction(
        player_id,
        SpotObjectId.create(runtime.id_mapper.get_int("object", object_sid)),
        action_name,
    )


def _current_spot(runtime, player_id: PlayerId) -> int:
    graph = runtime._spot_graph_repo.find_graph()
    return int(graph.get_entity_spot(EntityId.create(int(player_id))))


def _vent_actions_offered_to(runtime, player_id: PlayerId) -> list[str]:
    snapshot = runtime._state_builder.build_snapshot(int(player_id))
    assert snapshot is not None
    return [line for line in snapshot.object_lines if "通気口" in line]


class TestOnlyTheImpostorCanVent:
    """通気口はインポスターにだけ差し出され、それ以外には実行もできない。"""

    def test_the_impostor_moves_between_the_two_rooms(self, runtime) -> None:
        """keeper が通気口を使うと、接続を辿らずに機関室へ移る。"""
        _place(runtime, _KUZE, "corridor")

        _vent(runtime, _KUZE, "corridor_vent", "enter_vent_to_machine_room")

        assert _current_spot(runtime, _KUZE) == _spot(runtime, "machine_room")

    def test_a_crew_member_is_refused(self, runtime) -> None:
        """クルーが直接呼んでも、役割の前提条件で拒否される。"""
        _place(runtime, _SENA, "corridor")

        with pytest.raises(InteractionNotAllowedException):
            _vent(runtime, _SENA, "corridor_vent", "enter_vent_to_machine_room")

    def test_the_vent_is_visible_in_the_dark(self, runtime) -> None:
        """灯り無しの連絡通路でも通気口は一覧に出る (出ないと使えない手になる)。"""
        _place(runtime, _KUZE, "corridor")

        assert _vent_actions_offered_to(runtime, _KUZE) != []

    def test_a_ghost_is_refused(self, runtime) -> None:
        """幽霊にも通気口は使えない (第 1 版は LIVING だけを宣言している)。"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        _place(runtime, _KUZE, "corridor")
        corridor = SpotId.create(_spot(runtime, "corridor"))
        runtime._fallen_body_registry.record(_KUZE, corridor, WorldTick(1))
        runtime._player_outcome_registry.set_outcome(_KUZE, PlayerOutcomeEnum.DEAD)

        with pytest.raises(InteractionNotAllowedException):
            _vent(runtime, _KUZE, "corridor_vent", "enter_vent_to_machine_room")


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
        """灯りの無い連絡通路では、入ったのが誰かは分からず音だけが残る。"""
        _place(runtime, _KUZE, "corridor")
        _place(runtime, _MORI, "corridor")

        _vent(runtime, _KUZE, "corridor_vent", "enter_vent_to_machine_room")

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
        """灯りのある機関室では、通気口から出てきたのが誰かまで見える。"""
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )

        _place(runtime, _KUZE, "corridor")
        _place(runtime, _MORI, "machine_room")
        # 到着側だけを明るくする。出発側は暗いままなので、同じ移動が
        # **出発と到着で別の文になる**ことも同時に確かめられる。
        grant_item_specs_to_inventory(
            _MORI,
            (ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "lantern")),),
            runtime._item_repo,
            runtime._item_spec_repo,
            runtime._player_inventory_repo,
        )

        _vent(runtime, _KUZE, "corridor_vent", "enter_vent_to_machine_room")

        proses = [prose for prose, _ in self._outputs_for(runtime, _MORI)]
        assert "ベントが開いてクゼが中から出てきた。" in proses


class TestDarknessStillAnnouncesItself:
    """暗所可のオブジェクトが 1 つあっても、「灯りが要る」は消えない。

    通気口を暗所可にしたことで、連絡通路の一覧が空でなくなった。ヒントが
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
        """通気口だけ見える連絡通路でも、灯りが要ることは伝わる。"""
        _place(runtime, _SENA, "corridor")

        section = self._object_section(runtime, _SENA)

        assert "通気口" in section
        assert "配線箱" not in section
        assert "灯りがなければ" in section
