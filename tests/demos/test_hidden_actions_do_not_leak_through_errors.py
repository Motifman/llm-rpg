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
    hidden_object_interaction_failure_reason,
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
    rt = create_world_runtime(_DRILL)
    # これらの試験は、暗所の物体を見たうえで候補の秘匿だけを検査する。
    # 初期所持への暗黙依存をやめ、公開入口から灯りを確保して従来の前提を作る。
    _move(rt, _MORI, "storage")
    rt.build_observation(PlayerId(_MORI))
    rt.do_interact(PlayerId(_MORI), "emergency_lantern_case", "take_lantern")
    _move(rt, _MORI, "hall")
    return rt


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


def _names_hidden_from(player_index: int) -> list[str]:
    """その人には伏せられている操作の名前を、シナリオの宣言から集める。

    **接尾辞では拾わない。** 最初は ``_pretend`` で終わる名前を集めていたが、
    それは命名の習慣であって仕様ではない。station_drill には ``find_cutter``
    のように ``_pretend`` が付かない伏せた操作もあり、**そちらはテストが
    一切見ていなかった** (claude の指摘)。命名から外れた操作を足した人は、
    テストに何も言われないまま漏らせてしまう。

    **伏せる範囲は見る人ごとに違う。** ``count_supplies`` はアオイには
    自分の手順で、モリには伏せた操作。全員ぶんをまとめて 1 つの集合に
    すると、正しく見えている操作まで「漏れ」と判定してしまう。

    拾うのは ``PLAYER_STATE_IS`` を宣言していて、その人の初期状態が
    満たさない操作。engine が「行為者自身について訊く、伏せる条件」として
    扱っているものと同じ基準にする。
    """
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    state = raw["players"][player_index - 1]["initial_state"]
    hidden: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            name = node.get("action_name")
            if isinstance(name, str):
                for cond in node.get("preconditions") or []:
                    if not isinstance(cond, dict):
                        continue
                    if cond.get("condition_type") != "PLAYER_STATE_IS":
                        continue
                    required = cond.get("required_state") or {}
                    if any(state.get(k) != v for k, v in required.items()):
                        hidden.append(name)
                        break
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    assert hidden, f"player {player_index} に伏せた操作が無いなら何も守れない"
    return hidden


class TestTheRescueListRespectsWhoIsAsking:
    """案内に並ぶのは、その人に見えている操作だけ。"""

    def test_a_crew_member_never_sees_the_fake_version(self, runtime) -> None:
        """クルーの案内に偽装版が 1 つも出ない。

        **run 011 で漏れた形そのもの。** ハギはここから読み取って呼んだ。
        """
        oid = _object_id_with(runtime, "count_supplies")

        listed = list_object_interactions(runtime, oid, player_id=_HAGI)

        for hidden in _names_hidden_from(_HAGI):
            assert hidden not in listed, hidden

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

    def test_forgetting_the_actor_is_impossible(self, runtime) -> None:
        """行為者を渡さずには呼べない。

        当初は「渡し忘れたら空を返す」にしていた。漏らすよりはましだが、
        **空になるのもそれはそれで静かな失敗**で、案内が丸ごと死んだことに
        誰も気づけない (claude の指摘)。必須にすれば即座に落ちる。
        """
        oid = _object_id_with(runtime, "count_supplies")

        with pytest.raises(TypeError):
            list_object_interactions(runtime, oid)


class TestTheHiddenReasonOnlyDescribesTheCurrentRoom:
    """伏せた操作の拒否理由は、行為者の現在地にある物体だけから導く。"""

    def test_an_object_in_another_room_has_no_local_reason(self, runtime) -> None:
        """現在地外の物体 ID を渡しても、その物体の拒否理由を返さない。

        物体 ID は世界内で一意だが、この補助関数の契約は「目の前の対象を
        解決できた後の理由」である。世界全体を探索すると、その契約より広い
        情報を返せてしまう。
        """
        oid = _object_id_with(runtime, "count_supplies")

        reason = hidden_object_interaction_failure_reason(
            runtime, oid, player_id=_MORI
        )

        assert reason == ""

    def test_repository_failure_is_not_downgraded_to_no_reason(
        self, runtime, monkeypatch
    ) -> None:
        """配線障害は伝播し、既知の悪い「利用可能な操作: (なし)」へ退化しない。"""

        def _fail_to_load_graph():
            raise RuntimeError("graph wiring is broken")

        monkeypatch.setattr(
            runtime._spot_graph_repo, "find_graph", _fail_to_load_graph
        )

        with pytest.raises(RuntimeError, match="graph wiring is broken"):
            hidden_object_interaction_failure_reason(
                runtime, 1, player_id=_MORI
            )


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
            short_term_memory=runtime._short_term_memory,
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
            offered_tool_names_at_prompt=frozenset({"interact"}),
        )

        assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
        assert "count_supplies" in result.message
        assert result.remediation is not None
        assert "現在の状況" in result.remediation
        assert not any(
            name in result.remediation for name in ("gather", "search", "examine")
        )
        for hidden in _names_hidden_from(_AOI):
            assert hidden not in result.message, hidden

    def test_an_object_with_only_hidden_steps_returns_the_declared_reason(
        self, runtime
    ) -> None:
        """担当外でも物体は解決し、秘密を漏らさず誤った操作名を否定する。

        run 013 のモリは、目の前にある配線箱へ ``examine`` を試した。しかし
        本人向けの公開操作が 0 件だったため物体ごと候補から落ち、存在するのに
        「この場所に interactable なオブジェクトなし」と返っていた。

        run 022 では宣言済みの拒否理由だけを返したため、存在しない名前を
        「実在するが権限が無い」と誤解して再試行した。秘密の正解は伏せたまま、
        本人が送った名前だけは存在しないと明記する。
        """
        class _StubClient:
            """LLM は呼ばず、本番の引数解決と実行だけを見る。"""

        _move(runtime, _MORI, "corridor")
        ui = runtime.build_llm_context(PlayerId(_MORI))
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_StubClient(),
        )

        result = wiring._execute_tool(
            PlayerId(_MORI),
            "interact",
            {"target_label": "配線箱", "action_name": "examine"},
            ui.tool_runtime_context,
            offered_tool_names_at_prompt=frozenset({"interact"}),
        )

        assert '"配線箱"' in ui.current_state_text
        object_targets = [
            target
            for target in ui.tool_runtime_context.targets.values()
            if target.display_name == "配線箱"
        ]
        assert len(object_targets) == 1
        assert object_targets[0].available_interactions == ()
        assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
        assert "その手順は自分の担当ではない" in result.message
        assert "この対象に 'examine' という名前の操作はありません" in result.message
        assert "interactable なオブジェクトなし" not in result.message
        assert "利用可能な操作" not in result.message
        assert result.remediation is not None
        assert "前提条件" in result.remediation
        assert "表示に無い名前を推測しない" in result.remediation
        for hidden in _names_hidden_from(_MORI):
            assert hidden not in ui.current_state_text, hidden
            assert hidden not in result.message, hidden
            assert hidden not in result.remediation, hidden

    def test_a_dark_hidden_object_returns_the_visibility_reason(self, runtime) -> None:
        """暗所で見えない既知の物体は、不存在ではなく灯り不足として断る。

        担当者のセナが暗い連絡通路で配線箱を指定した run 013 の再現。
        C の担当違いとは別原因なので、別の試験で固定する。
        """
        class _StubClient:
            """LLM は呼ばず、本番の引数解決と失敗文面だけを見る。"""

        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum

        graph = runtime._spot_graph_repo.find_graph()
        graph.update_spot_atmosphere(
            SpotId.create(runtime.id_mapper.get_int("spot", "corridor")),
            lighting=LightingEnum.DARK,
        )
        runtime._spot_graph_repo.save(graph)
        _move(runtime, _SENA, "corridor")
        ui = runtime.build_llm_context(PlayerId(_SENA))
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_StubClient(),
        )

        # 通気口を暗所可にしてから、連絡通路の一覧は空でなくなった。
        # **見えている物があっても、暗さが隠していることは伝わる**必要がある。
        assert "灯りがなければ" in ui.current_state_text
        assert '"配線箱"' not in ui.current_state_text
        assert not any(
            target.display_name == "配線箱"
            for target in ui.tool_runtime_context.targets.values()
        )
        result = wiring._execute_tool(
            PlayerId(_SENA),
            "interact",
            {"target_label": "配線箱", "action_name": "examine"},
            ui.tool_runtime_context,
            offered_tool_names_at_prompt=frozenset({"interact"}),
        )

        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "暗くて見えない" in result.message
        assert "interactable なオブジェクトなし" not in result.message

    def test_an_existing_object_action_is_not_denied_as_nonexistent(
        self, runtime
    ) -> None:
        """実在する操作の前提条件失敗には、名前が無いという誤情報を足さない。"""
        class _StubClient:
            """LLM は呼ばず、本番の物体操作結果だけを見る。"""

        # モリのランタンで配線箱を見えるようにし、最初の工程を飛ばして
        # 実在する tighten_wiring_2 を呼ぶ。名前は正しいが順序の前提だけが違う。
        _move(runtime, _MORI, "corridor")
        _move(runtime, _SENA, "corridor")
        ui = runtime.build_llm_context(PlayerId(_SENA))
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_StubClient(),
        )

        result = wiring._execute_tool(
            PlayerId(_SENA),
            "interact",
            {"target_label": "配線箱", "action_name": "tighten_wiring_2"},
            ui.tool_runtime_context,
            offered_tool_names_at_prompt=frozenset({"interact"}),
        )

        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "存在しない" not in result.message
        assert "という名前の操作はありません" not in result.message

    def test_dim_rejection_does_not_claim_the_room_is_bright(self, runtime) -> None:
        """薄暗い場所での襲撃拒否は、明るさの程度を誤って断定しない。"""
        class _StubClient:
            """LLM は呼ばず、本番の対人操作結果だけを見る。"""

        # 明示した停電を、モリが持つランタンで DARK から DIM にする。
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum

        graph = runtime._spot_graph_repo.find_graph()
        graph.update_spot_atmosphere(
            SpotId.create(runtime.id_mapper.get_int("spot", "machine_room")),
            lighting=LightingEnum.DARK,
        )
        runtime._spot_graph_repo.save(graph)
        for player_id in (_MORI, _KUZE, _HAGI):
            _move(runtime, player_id, "machine_room")
        ui = runtime.build_llm_context(PlayerId(_KUZE))
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_StubClient(),
        )

        result = wiring._execute_tool(
            PlayerId(_KUZE),
            "interact",
            {"target_label": "ハギ", "action_name": "strike_down"},
            ui.tool_runtime_context,
            offered_tool_names_at_prompt=frozenset({"interact"}),
        )

        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "ここは暗がりではない" in result.message
        assert "明るすぎる" not in result.message
        assert "存在しない" not in result.message
        assert "という名前の操作はありません" not in result.message


class TestTheCandidateRowsStillHide:
    """候補一覧側の隠蔽は、判断を移しても変わらない。"""

    def test_a_crew_member_sees_no_fake_row(self, runtime) -> None:
        """クルーの候補一覧に偽装版が出ない。

        判断を共通の場所へ移したので、**移し漏れをここで捕まえる**。
        """
        # 棚卸し帳は物資庫。暗いので灯り持ちを同行させる。**この移動が
        # 無いと、対象がそもそも視界に無いまま「漏れていない」が通る。**
        _move(runtime, _AOI, "storage")
        _move(runtime, _MORI, "storage")
        view = runtime.build_observation(_AOI)

        assert "count_supplies" in view, "行そのものが空なら何も守れない"
        for hidden in _names_hidden_from(_AOI):
            assert hidden not in view, hidden

    def test_the_impostor_still_gets_a_row_to_use(self, runtime) -> None:
        """インポスターの候補一覧には偽装版が出る。

        **「全員から隠す」でも上のテストは通る**ので、出る側を一緒に見る。
        """
        _move(runtime, _KUZE, "storage")
        _move(runtime, _MORI, "storage")
        view = runtime.build_observation(_KUZE)

        assert "count_supplies_pretend" in view


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
        for hidden in _names_hidden_from(_AOI):
            assert hidden not in rows, hidden


class TestTheSameLeakOnThePersonSide:
    """人を対象にした案内でも、伏せた操作の名前が漏れない。

    物体側と**同じ穴が 90 行下に開いていた** (claude の指摘)。同席者の行では
    役割で正しく落としているのに、その隣の案内が宣言の全件を並べていた。

        人を対象にした 'talk' という操作はありません。
        人に対して使える操作: strike_down, loot_from_downed

    クルーが操作名を 1 回打ち間違えるだけで「人を殺す手段がこの世界にある」
    と分かってしまう。``talk`` / ``ask`` のような名前の発明は物体側より
    起きやすい。

    「識別子が要るから絞れない」と注記されていたが、理由になっていない。
    **絞った識別子**を返せばよい。
    """

    def _typo_message(self, runtime, viewer: int, target: str = "モリ") -> str:
        class _StubClient:
            """LLM は呼ばない。文面の組み立てだけを見る。"""

        ui = runtime.build_llm_context(PlayerId(viewer))
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_StubClient(),
        )
        label = next(
            key
            for key, value in ui.tool_runtime_context.targets.items()
            if target in str(value)
        )
        return wiring._execute_tool(
            PlayerId(viewer),
            "interact",
            {"target_label": label, "action_name": "talk"},
            ui.tool_runtime_context,
            offered_tool_names_at_prompt=frozenset({"interact"}),
        ).message

    def test_a_crew_member_never_learns_of_the_kill(self, runtime) -> None:
        """クルーの案内に襲う手の名前が出ない。"""
        message = self._typo_message(runtime, _AOI)

        for hidden in _names_hidden_from(_AOI):
            assert hidden not in message, hidden

    def test_the_impostor_still_gets_told(self, runtime) -> None:
        """インポスターの案内には襲う手が出る。

        **「全員から隠す」でも上のテストは通る**ので、出る側を一緒に見る。
        隠しすぎると、インポスターが自分の手段を思い出せなくなる。
        """
        message = self._typo_message(runtime, _KUZE)

        assert "strike_down" in message

    def test_the_targets_secret_never_filters_the_list(self, runtime) -> None:
        """相手の伏せた役割で、一覧の中身が変わらない。

        ``strike_down`` は相手が crew であることも要求する。**これを行為者の
        state で判定しかけて、インポスターからも消してしまった。** 相手に
        ついて訊く条件で絞ると、**誰がどちら側かが一覧から読めてしまう**。

        クルー 2 人を相手にした場合と、インポスターを相手にした場合で、
        インポスターに見える一覧が変わらないことを確かめる。
        """
        seen = {
            name: self._typo_message(runtime, _KUZE, name).split("使える操作: ")[-1]
            for name in ("モリ", "セナ", "アオイ")
        }

        assert len(set(seen.values())) == 1, seen
        assert "strike_down" in next(iter(seen.values()))


class TestEveryHiddenConditionIsDeliberatelyClassified:
    """伏せる条件が「誰について訊いているか」を、全件ぶん決めてある。"""

    def test_no_hidden_condition_is_left_unclassified(self) -> None:
        """伏せる条件はすべて、行為者向きか相手向きかが決まっている。

        行為者の state で判定してよいのは**行為者について訊く条件だけ**。
        相手について訊く条件で絞ると、相手の伏せた役割で一覧の中身が変わり、
        **誰がどちら側かが読めてしまう**。

        分類漏れがあると、新しい条件が既定でどちらかに倒れて静かに壊れる。
        ここで全件を突き合わせる。
        """
        from ai_rpg_world.application.world_graph.hidden_interaction_filter import (
            _ACTOR_SCOPED_HIDDEN,
        )
        from ai_rpg_world.domain.world_graph.enum.interaction_condition_visibility import (  # noqa: E501
            CONDITION_VISIBILITY,
            ConditionVisibility,
        )

        hidden = {
            ctype
            for ctype, visibility in CONDITION_VISIBILITY.items()
            if visibility is ConditionVisibility.HIDDEN
        }
        # 相手について訊く条件は名前で見分けられる。ここに漏れがあれば
        # 分類の見直しが要る。
        target_scoped = {c for c in hidden if c.value.startswith("TARGET_")}

        assert _ACTOR_SCOPED_HIDDEN <= hidden
        assert not (_ACTOR_SCOPED_HIDDEN & target_scoped), (
            "相手について訊く条件を、行為者の state で判定してはいけない"
        )
        assert hidden - target_scoped == _ACTOR_SCOPED_HIDDEN, (
            "行為者について訊く伏せた条件が増えている。"
            f"未分類: {hidden - target_scoped - _ACTOR_SCOPED_HIDDEN}"
        )
