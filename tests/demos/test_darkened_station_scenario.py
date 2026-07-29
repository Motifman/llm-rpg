"""質感確認シナリオ `darkened_station` が意図どおりに動くことを保証する。

設計 doc (docs/memory_system/interpersonal_interaction_design.md) の PR 8。
役割ゲート・暗所限定・秘匿・戦利品・目覚めの申し送りは、それぞれ単体では
固めてある。**組み合わせて初めて出る破綻**があるので、シナリオを 1 本
書いて筋書きどおりに歩かせる。

実際に LLM に遊ばせる run は別途行う。ここで固定するのは「シナリオ作者が
書いたとおりに機能が噛み合うか」であって、エージェントが賢く振る舞うかでは
ない。LLM を呼ばないので毎回のテストで回せる。
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
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "darkened_station.json"
)

# シナリオの players 宣言順に 1 から振られる。
_MORI = PlayerId(1)   # crew, ランタン持ち
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper (襲える側)
_AOI = PlayerId(4)    # crew, 灯りを持たない


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _spot_of(runtime, string_id: str):
    return runtime.id_mapper.get_int("spot", string_id)


def _move(runtime, player_id: PlayerId, spot_string_id: str) -> None:
    """テスト用に player を任意の spot へ置き直す (移動 tool を経由しない)。"""
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId

    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(_spot_of(runtime, spot_string_id)))
    runtime._spot_graph_repo.save(graph)


def _gather_cutter(runtime, player_id: PlayerId) -> None:
    """物資庫で解体用カッターを手に入れる。"""
    _move(runtime, player_id, "storage")
    runtime.do_interact(player_id, "supply_shelf", "find_cutter")


def _interpersonal_observations(runtime, player_id: PlayerId) -> str:
    return "\n".join(
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "player_interacted_with_player"
    )


def _is_down(runtime, player_id: PlayerId) -> bool:
    return bool(runtime._player_status_repo.find_by_id(player_id).is_down)


def _strike_until_down(runtime, actor: PlayerId, target: PlayerId) -> int:
    """倒れるまで襲う。一撃では倒れない (襲撃回数を返す)。

    一撃で倒す設計にすると、倒れた本人は観測の宛先から外れるので
    ``notify_target`` が永久に届かない。生き延びた被害者が疑いの起点に
    なるほうがシナリオとして機能する。
    """
    for attempt in range(1, 6):
        runtime.do_interact_with_player(actor, target, "strike_down")
        if _is_down(runtime, target):
            return attempt
    raise AssertionError("襲い続けても倒れない")


class TestRoleGate:
    """役割で行為者を絞れている。"""

    def test_crew_cannot_strike_at_all(self, runtime) -> None:
        """crew は暗所でカッターを持っていても襲えない。

        場所と道具が揃っても、役割が違えば成立しない。役割ゲートが
        他の条件の裏に隠れていないことを確認する。
        """
        _gather_cutter(runtime, _MORI)
        _move(runtime, _SENA, "storage")

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_MORI, _SENA, "strike_down")

        assert "あなたにそんな真似はできない" in str(exc_info.value)
        assert not _is_down(runtime, _SENA)


class TestDarknessGate:
    """暗い場所でだけ襲える。"""

    def test_bright_hall_refuses_the_strike(self, runtime) -> None:
        """明るい集会室では襲えない。"""
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert "明るすぎる" in str(exc_info.value)

    def test_dark_storage_allows_the_strike(self, runtime) -> None:
        """暗い物資庫では成立し、相手が倒れる。"""
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _SENA, "storage")

        assert _strike_until_down(runtime, _KUZE, _SENA) > 1, (
            "一撃で倒れると、被害者に何も届かないまま終わる"
        )

    def test_a_lantern_bearer_makes_the_room_unsafe_for_the_killer(
        self, runtime
    ) -> None:
        """ランタンを持った第三者が同席すると、暗所でも襲えなくなる。

        「灯りを絶やさないこと」がそのまま身の安全になる、という
        シナリオの中心的な駆け引きが成立していることを確認する。
        判定が spot の静的な明るさではなく実効照明であることに依存する。
        """
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _SENA, "storage")
        _move(runtime, _MORI, "storage")  # ランタン持ち

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert "明るすぎる" in str(exc_info.value)
        assert not _is_down(runtime, _SENA)

    def test_cutting_the_hall_light_opens_the_hall_up(self, runtime) -> None:
        """発電室のレバーで集会室を暗くすると、そこでも襲えるようになる。

        暗所は最初から決まっているのではなく、行為で作れる。照明条件が
        動的であることの確認 (静的な atmosphere を見ていたら通らない)。
        """
        _move(runtime, _MORI, "radio_room")  # ランタン持ちを集会室から離す
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _KUZE, "generator_room")
        runtime.do_interact(_KUZE, "breaker_panel", "cut_hall_light")

        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")
        _strike_until_down(runtime, _KUZE, _SENA)

        assert _is_down(runtime, _SENA)

    def test_restoring_the_light_closes_it_again(self, runtime) -> None:
        """照明を戻せば、集会室はまた安全になる。"""
        _move(runtime, _MORI, "radio_room")  # ランタンの影響を除いて照明だけを見る
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _KUZE, "generator_room")
        runtime.do_interact(_KUZE, "breaker_panel", "cut_hall_light")
        runtime.do_interact(_KUZE, "breaker_panel", "restore_hall_light")

        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")


class TestCovertness:
    """襲撃が第三者に漏れず、被害者にだけ匿名で届く。"""

    def test_victim_is_told_something_happened(self, runtime) -> None:
        """倒される瞬間、被害者本人には衝撃が届く。"""
        _move(runtime, _MORI, "radio_room")
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _KUZE, "generator_room")
        runtime.do_interact(_KUZE, "breaker_panel", "cut_hall_light")
        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert "闇の中で強い衝撃を受けた" in _interpersonal_observations(runtime, _SENA)

    def test_victim_is_not_told_who(self, runtime) -> None:
        """被害者は犯人の名前を知らない。

        名前が出ると、襲撃が失敗した瞬間に犯人が確定してしまい、
        秘匿役職として成立しなくなる。
        """
        _move(runtime, _MORI, "radio_room")
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _KUZE, "generator_room")
        runtime.do_interact(_KUZE, "breaker_panel", "cut_hall_light")
        _move(runtime, _KUZE, "hall")
        _move(runtime, _SENA, "hall")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert "クゼ" not in _interpersonal_observations(runtime, _SENA)

    def test_bystander_in_the_dark_sees_nothing(self, runtime) -> None:
        """暗闇に居合わせた第三者には、襲撃が届かない。

        立会人は灯りを持たないアオイにする。ランタン持ちが同席していると
        そもそも襲撃自体が成立しない (それは別テストで固定済み)。
        """
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _SENA, "storage")
        _move(runtime, _AOI, "storage")

        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

        assert _interpersonal_observations(runtime, _AOI).strip() == ""


class TestLootingLeavesATrace:
    """倒れた相手から奪った跡は、目覚めたときに本人が読める。"""

    def test_taken_item_moves_to_the_killer(self, runtime) -> None:
        """倒れた相手が持っていた真空管を奪える。"""
        _move(runtime, _SENA, "storage")
        runtime.do_interact(_SENA, "supply_shelf", "find_part")
        _gather_cutter(runtime, _KUZE)
        _strike_until_down(runtime, _KUZE, _SENA)

        runtime.do_interact_with_player(
            _KUZE, _SENA, "loot_from_downed", interaction_parameters={"item": "送信機の真空管"}
        )

        assert _owns(runtime, _KUZE, "radio_part")
        assert not _owns(runtime, _SENA, "radio_part")

    def test_the_victim_learns_of_it_on_waking(self, runtime) -> None:
        """目を覚ました被害者は「荷を探られた形跡」を読める。

        倒れている間の観測は本人に配信されない (ターンが回らないため)。
        それでも荷が減った理由が永久に分からないままでは、社会的な反応が
        起こしようがない。
        """
        _move(runtime, _SENA, "storage")
        runtime.do_interact(_SENA, "supply_shelf", "find_part")
        _gather_cutter(runtime, _KUZE)
        _strike_until_down(runtime, _KUZE, _SENA)
        runtime.do_interact_with_player(
            _KUZE, _SENA, "loot_from_downed", interaction_parameters={"item": "送信機の真空管"}
        )

        incidents = runtime._downed_incident_log.peek(_SENA)

        assert incidents, "倒れている間にされたことが記録されていない"
        assert any("持ち物を奪う" in text for text in incidents)

    def test_the_felling_blow_is_not_in_that_log(self, runtime) -> None:
        """倒した一撃そのものは申し送りに入らない。

        襲われた瞬間は本人に届いている (匿名の衝撃)。目覚めの申し送りにも
        入れると、同じ一撃が二度語られる。
        """
        _gather_cutter(runtime, _KUZE)
        _move(runtime, _SENA, "storage")

        _strike_until_down(runtime, _KUZE, _SENA)

        assert runtime._downed_incident_log.peek(_SENA) == ()


class TestRescueNeedsTwo:
    """救難信号は一人では送れない。"""

    def test_alone_the_transmitter_cannot_be_keyed(self, runtime) -> None:
        """修理できても、一人では送信できない。

        keeper が誰か一人を隔離すれば勝ち筋が止まる、という緊張の源。
        """
        _move(runtime, _SENA, "storage")
        runtime.do_interact(_SENA, "supply_shelf", "find_part")
        _move(runtime, _SENA, "radio_room")
        runtime.do_interact(_SENA, "transmitter", "repair")

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact(_SENA, "transmitter", "send_distress")

        assert "一人では" in str(exc_info.value)

    def test_two_crew_can_send_it(self, runtime) -> None:
        """二人揃えば送信でき、勝利フラグが立つ。"""
        _move(runtime, _SENA, "storage")
        runtime.do_interact(_SENA, "supply_shelf", "find_part")
        _move(runtime, _SENA, "radio_room")
        runtime.do_interact(_SENA, "transmitter", "repair")
        _move(runtime, _MORI, "radio_room")

        runtime.do_interact(_SENA, "transmitter", "send_distress")

        assert "distress_sent" in runtime._world_flag_state.as_frozen_set()


def _owns(runtime, player_id: PlayerId, item_string_id: str) -> bool:
    """その player が指定の item spec を 1 つ以上持っているか。"""
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        collect_owned_item_spec_ids_from_inventory,
    )

    spec_int = runtime.id_mapper.get_int("item_spec", item_string_id)
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    owned = collect_owned_item_spec_ids_from_inventory(
        inventory, runtime._item_repo
    )
    return any(int(spec_id) == spec_int for spec_id in owned)
