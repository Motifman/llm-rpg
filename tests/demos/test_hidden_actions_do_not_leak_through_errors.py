"""伏せた操作の名前が、間違えたときの案内から漏れない。

## 片側で消して、隣で教えていた

役割で弾かれる候補は、候補一覧から**行ごと**落としている。「いまできない」に
回すだけでは**その操作が存在すること**が伝わるためで、偽装版 (``_pretend``)
の仕組みはこの隠蔽の上に成り立っている。

その隣で、操作名を間違えたときの案内が全操作をそのまま並べていた。

    このオブジェクトには 'examine' という操作がありません。
    利用可能な操作: log_weather, log_weather_2, log_weather_3, log_weather_pretend

実 run 011 で、この漏れは**実際に使われた**。

    t24 ハギ (クルー) が操作名を間違える
         → 案内に count_supplies_pretend が出る
    t26 ハギが count_supplies_pretend を呼ぶ
    t28 ハギが別のオブジェクトへ check_generator_pretend を呼ぶ

**偽装版という仕組みそのものを学習している。** クルーがこれを知る手段は
本来無い。

## 案内そのものは消さない

一覧を消すと、``examine`` のような発明された名前から正しい名前へ戻る道が
無くなる。実 run 011 では 12 件がこの案内に助けられている。消すのではなく、
**その人に見えている操作だけを並べる**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.executors.interact_helpers import (
    list_object_interactions,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
#: モリ(気象担当) / セナ(配線) / クゼ(インポスター) / アオイ(棚卸し) / ハギ(発電機)
_MORI, _SENA, _KUZE, _AOI, _HAGI = range(1, 6)


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _object_id_with(runtime, action_fragment: str) -> int:
    graph = runtime._spot_graph_repo.find_graph()
    for node in graph.iter_spot_nodes():
        interior = runtime._spot_interior_repo.find_by_spot_id(node.spot_id)
        if interior is None:
            continue
        for obj in interior.objects:
            if any(action_fragment in i.action_name for i in obj.interactions):
                return obj.object_id.value
    raise AssertionError(f"{action_fragment} を持つオブジェクトが無い")


def _move(runtime, player_id: int, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(player_id))
    graph.place_entity(
        EntityId.create(player_id),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _pretend_names() -> list[str]:
    """シナリオが宣言している偽装版の名前。**テストに書き写さない。**"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            name = node.get("action_name")
            if isinstance(name, str) and name.endswith("_pretend"):
                found.append(name)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    assert found, "偽装版が 1 つも宣言されていないなら、この節は何も守れない"
    return found


class TestTheRescueListRespectsWhoIsAsking:
    """案内に並ぶのは、その人に見えている操作だけ。"""

    def test_a_crew_member_never_sees_the_fake_version(self, runtime) -> None:
        """クルーの案内に偽装版が 1 つも出ない。

        **run 011 で漏れた形そのもの。** ハギはここから読み取って呼んだ。
        """
        oid = _object_id_with(runtime, "count_supplies")

        listed = list_object_interactions(runtime, oid, player_id=_HAGI)

        for fake in _pretend_names():
            assert fake not in listed, fake

    def test_the_owner_sees_their_own_steps(self, runtime) -> None:
        """担当者には自分の手順が並ぶ。

        **「常に空」でも上のテストは通る**ので、見える側を必ず一緒に見る。
        案内が空になると、名前を間違えたときに戻る道が消える。
        """
        oid = _object_id_with(runtime, "count_supplies")

        listed = list_object_interactions(runtime, oid, player_id=_AOI)

        assert "count_supplies" in listed

    def test_the_impostor_sees_only_the_fake_version(self, runtime) -> None:
        """インポスターには偽装版だけが並び、本物は並ばない。

        本物が並ぶと、記録に残る手順を踏んでしまう。
        """
        oid = _object_id_with(runtime, "count_supplies")

        listed = list_object_interactions(runtime, oid, player_id=_KUZE)

        assert listed == ["count_supplies_pretend"]

    def test_a_forgotten_actor_leaks_nothing(self, runtime) -> None:
        """行為者を渡し忘れた経路は、何も並べない。

        全部を返すと、**渡し忘れが「たまたま全部見える」として静かに漏れる**。
        案内が空になるほうがまし。
        """
        oid = _object_id_with(runtime, "count_supplies")

        assert list_object_interactions(runtime, oid, player_id=None) == []


class TestTheMessageTheAgentActuallyReads:
    """エージェントが実際に受け取る文面に、伏せた名前が入らない。"""

    def test_a_wrong_name_gets_help_without_the_secret(self, runtime) -> None:
        """存在しない操作名を呼ぶと、自分の手順だけが案内される。

        ヘルパ単体ではなく **executor が組む文面** を見る。ここを見ないと、
        絞ったのに文面を組む側が別経路で全部並べていても気づけない。
        """
        class _StubClient:
            """LLM は呼ばない。文面の組み立てだけを見る。"""

        # 本番と同じ経路で target_label を解決させる。ここを省くと、
        # **絞ったつもりの一覧を別経路が組んでいても気づけない。**
        # 棚卸し帳は物資庫にある。暗いので灯り持ちを同行させる (暗いままだと
        # オブジェクトが見えず、target_label がそもそも出ない)。
        _move(runtime, _AOI, "storage")
        _move(runtime, _MORI, "storage")
        ui = runtime.build_llm_context(PlayerId(_AOI))
        context = ui.tool_runtime_context
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            llm_client=_StubClient(),
        )
        label = next(
            key for key, value in context.targets.items() if "棚卸し帳" in str(value)
        )
        result = wiring._execute_tool(
            PlayerId(_AOI),
            "interact",
            {"target_label": label, "action_name": "examine"},
            context,
        )

        assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
        assert "count_supplies" in result.message
        for fake in _pretend_names():
            assert fake not in result.message, fake


class TestTheCandidateRowsStillHide:
    """候補一覧側の隠蔽は、判断を移しても変わらない。"""

    def test_a_crew_member_sees_no_fake_row(self, runtime) -> None:
        """クルーの候補一覧に偽装版が出ない。

        判断を共通の場所へ移したので、**移し漏れをここで捕まえる**。
        """
        view = runtime.build_observation(_AOI)

        for fake in _pretend_names():
            assert fake not in view, fake

    def test_the_impostor_still_gets_a_row_to_use(self, runtime) -> None:
        """インポスターの候補一覧には偽装版が出る。

        **「全員から隠す」でも上のテストは通る**ので、出る側を一緒に見る。
        """
        view = runtime.build_observation(_KUZE)

        assert any(fake in view for fake in _pretend_names())


class TestTheOlderStringRowsHideToo:
    """後方互換の文字列行にも、伏せた操作が入らない。

    ``SpotGraphPlayerSnapshotDto.object_lines`` は「formatter のフォールバック
    用」として残っている 3 つの文字列行のひとつ。**いま読み手が 1 つも無い**
    (``.object_lines`` を参照するコードはリポジトリ全体で 0 件)。

    それでも絞る。復活させた人が、隣の DTO 側だけ直っている状態を踏まない
    ようにするため。**読み手が無いぶん、変異テストでは捕まらない。** だから
    ここで DTO を直接見る。

    3 つの文字列行そのものは、消すのが筋。別の PR に分ける。
    """

    def test_the_fallback_rows_skip_the_fake_version(self, runtime) -> None:
        """クルーの文字列行に偽装版が出ない。"""
        _move(runtime, _AOI, "storage")
        _move(runtime, _MORI, "storage")

        snapshot = runtime._state_builder.build_snapshot(_AOI)
        rows = "\n".join(snapshot.object_lines)

        assert "count_supplies" in rows, "行そのものが空なら何も守れない"
        for fake in _pretend_names():
            assert fake not in rows, fake
