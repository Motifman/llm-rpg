"""アイテム操作系 4 tool (use/drop/give/pickup) の end-to-end regression。

過去 3 連続で本番実験まで漏れたアイテム関連バグ:
- 実験 #24 (#343): UNSUPPORTED_TOOL 196 件 (配線漏れ) → #353
- 実験 #25 (#356): INVALID_ARGUMENT 106 件 (resolver gap) → #369
- 実験 #26 (#384): SYSTEM_ERROR 72 件 (`inv.slots` 存在しない属性) → #385
- 実験 #27 (#390): SYSTEM_ERROR 40 件 (`name_resolver.item_name` 存在しない) → 本 PR

これらの **共通の構造** は「unit 単位の mock テストでは pass するが、
LLM-shape の args → wiring → resolver → executor → event publish →
formatter の全経路を 1 通り通すテストが存在しない」。

本ファイルでは **実 runtime (forbidden_library / survival_island_v2 ではなく
最小 scenario でも可)** + **実 LLM stub** + **実 wiring / resolver /
executor / formatter** を組み立てて 4 tool が成功するパスを通す。
mock を使うのは LLM client (stub) と event publisher 観察のみ。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """survival_island_v2 セッションを LLM stub で立ち上げる共有 fixture。"""
    from tests.demos._world_runtime_helpers import create_world_runtime_session
    return create_world_runtime_session(
        monkeypatch, tmp_path, world_id="survival_island_v2",
    )


def _grant(runtime, pid: PlayerId, spec_str_id: str) -> None:
    spec_id = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", spec_str_id))
    grant_item_specs_to_inventory(
        player_id=pid, item_spec_ids=(spec_id,),
        item_repository=runtime._item_repo,
        item_spec_repository=runtime._item_spec_repo,
        player_inventory_repository=runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _teleport(runtime, pid_int: int, spot_str: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    eid = EntityId.create(pid_int)
    try:
        graph.unplace_entity(eid)
    except Exception:
        pass
    spot_int = runtime.id_mapper.get_int("spot", spot_str)
    graph.place_entity(eid, SpotId.create(spot_int))
    runtime._spot_graph_repo.save(graph)


def _player_id(runtime, str_id: str) -> PlayerId:
    for sp in runtime.scenario.player_spawns:
        if sp.string_id == str_id:
            return PlayerId(int(sp.player_id))
    raise AssertionError(f"player {str_id} が scenario に存在しない")


def _owns_spec(runtime, pid: PlayerId, spec_str_id: str) -> bool:
    """`pid` が `spec_str_id` のアイテムを持っているか。

    「inventory が空か」ではなく **その品を持っているか** で見る。シナリオが
    宣言した初期所持品が起動時に配られるようになったため、空を前提にすると
    無関係な持ち物で落ちる (かつては配布漏れで偶然空だった)。
    """
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        collect_owned_item_spec_ids_from_inventory,
    )

    spec_id = ItemSpecId.create(runtime.scenario.id_mapper.get_int("item_spec", spec_str_id))
    inv = runtime._player_inventory_repo.find_by_id(pid)
    assert inv is not None
    return spec_id in collect_owned_item_spec_ids_from_inventory(inv, runtime._item_repo)


class _CapturingTraceRecorder:
    """run_turn が emit した trace payload を確認するための最小 recorder。"""

    def __init__(self) -> None:
        self.events: list[tuple[object, dict]] = []

    def record(self, kind, **payload) -> None:
        self.events.append((kind, payload))


def _label_for_item(runtime, pid: PlayerId, item_spec_str: str) -> str:
    """ada の prompt context から指定 spec のアイテム label (I1/I2/...) を引く。"""
    return _label_for_item_with_spoilage(runtime, pid, item_spec_str)


def _label_for_item_with_spoilage(
    runtime,
    pid: PlayerId,
    item_spec_str: str,
    *,
    is_spoiled: bool = False,
) -> str:
    """指定 spec かつ腐敗状態の item_label を prompt context から引く。"""
    target_spec_id = runtime.id_mapper.get_int("item_spec", item_spec_str)
    prompt = runtime.build_full_prompt(pid)
    ctx = prompt["tool_runtime_context"]
    for label, target in ctx.targets.items():
        if getattr(target, "kind", None) != "inventory_item":
            continue
        # 慣習: item_instance_id field に item_spec_id が入る (DTO コメント)
        if (
            getattr(target, "item_instance_id", None) == target_spec_id
            and getattr(target, "is_spoiled", False) is is_spoiled
        ):
            return label
    raise AssertionError(
        f"{item_spec_str} (spec_id={target_spec_id}, spoiled={is_spoiled}) "
        f"ラベルが見つからない: "
        f"{[(l, t.kind, getattr(t, 'item_instance_id', None), getattr(t, 'is_spoiled', None)) for l, t in ctx.targets.items()]}"
    )


def _set_one_owned_item_spoiled(
    runtime,
    pid: PlayerId,
    item_spec_str: str,
    *,
    is_spoiled: bool,
) -> None:
    """pid が持つ item_spec_str の 1 instance の spoiled state を設定する。"""
    spec_id = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", item_spec_str))
    inv = runtime._player_inventory_repo.find_by_id(pid)
    assert inv is not None
    for _slot_id, iid in inv.iter_occupied_slots():
        item = runtime._item_repo.find_by_id(iid)
        if item is None or item.item_spec.item_spec_id != spec_id:
            continue
        item.merge_state({"spoiled": is_spoiled})
        runtime._item_repo.save(item)
        return
    raise AssertionError(f"{item_spec_str} の所持 instance が見つからない")


def _count_owned_spec_by_spoilage(
    runtime,
    pid: PlayerId,
    item_spec_str: str,
    *,
    is_spoiled: bool,
) -> int:
    """pid が持つ item_spec_str のうち spoiled 状態が一致する個数。"""
    spec_id = ItemSpecId.create(runtime.id_mapper.get_int("item_spec", item_spec_str))
    inv = runtime._player_inventory_repo.find_by_id(pid)
    assert inv is not None
    count = 0
    for _slot_id, iid in inv.iter_occupied_slots():
        item = runtime._item_repo.find_by_id(iid)
        if item is None or item.item_spec.item_spec_id != spec_id:
            continue
        if bool(item.state.get("spoiled")) is is_spoiled:
            count += 1
    return count


def _count_ground_spec_by_spoilage(
    runtime,
    spot_str: str,
    item_spec_str: str,
    *,
    is_spoiled: bool,
) -> int:
    """spot に落ちている item_spec_str のうち spoiled 状態が一致する個数。"""
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId

    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", spot_str))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    assert interior is not None
    spec_id_value = runtime.id_mapper.get_int("item_spec", item_spec_str)
    count = 0
    for ground_item in interior.ground_items:
        if ground_item.item_spec_id.value != spec_id_value:
            continue
        item = runtime._item_repo.find_by_id(ground_item.item_instance_id)
        if item is not None and bool(item.state.get("spoiled")) is is_spoiled:
            count += 1
    return count


# ---------------------------------------------------------------------------
# use_item: 4 連続でバグが出た本丸
# ---------------------------------------------------------------------------
class TestUseItemEndToEnd:
    """use_item の wiring → resolver → executor → event publish → formatter を通す。"""

    def test_success_inventory_removed(self, session) -> None:
        """成功パス: LLM が item_label を指定 → 実 aggregate / event publish /
        formatter まで例外なく通る。**実験 #24-27 の全 4 バグを 1 件でも残せば
        ここで AttributeError or KeyError や False で落ちる**。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        _grant(runtime, ada, "coconut")  # CONSUMABLE
        label = _label_for_item(runtime, ada, "coconut")

        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            "arguments": {"item_label": label, "inner_thought": "食べる"},
        })
        session.llm_wiring.llm_client = stub
        result = session.llm_wiring.run_turn(ada)

        assert result.success is True, (
            f"use_item が失敗: code={result.error_code} msg={result.message[:160]}"
        )
        # inventory から該当アイテムが消えていること
        inv = runtime._player_inventory_repo.find_by_id(ada)
        assert inv is not None
        assert not _owns_spec(runtime, ada, "coconut"), (
            "use_item 成功後も coconut が inventory に残っている"
        )

    def test_returns_item_label_invalid_target_label(self, session) -> None:
        """resolver 経路が壊れていれば INVALID_ARGUMENT (= 実験 #25 の症状) に化ける。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            "arguments": {"item_label": "I99", "inner_thought": "t"},
        })
        session.llm_wiring.llm_client = stub
        result = session.llm_wiring.run_turn(ada)
        assert result.success is False
        assert result.error_code in (
            "INVALID_TARGET_LABEL", "INVALID_TARGET_KIND",
        ), f"unexpected code: {result.error_code} (resolver が動いていない疑い)"

    def test_successful_use_item_runs_observation_pipeline_without_exception(self, session) -> None:
        """**実験 #27 の症状 (`item_name` AttributeError) を直接検知する test**。

        event publisher 経由で formatter が動くため、ConsumableUsedEvent →
        ItemUseObservationFormatter → name_resolver.item_spec_name(...) の
        全 chain を通す。formatter で AttributeError が出れば executor の
        try/except で SYSTEM_ERROR に化けるので result.success=False になる。
        """
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        # 同 spot に noah を置くと他者観測経路 (formatter が走る) が active になる
        _teleport(runtime, int(ada), "shipwreck_beach")
        _teleport(runtime, int(noah), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        label = _label_for_item(runtime, ada, "coconut")

        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            "arguments": {"item_label": label, "inner_thought": "食"},
        })
        session.llm_wiring.llm_client = stub
        result = session.llm_wiring.run_turn(ada)
        assert result.success is True, (
            f"use_item の event publish/formatter で例外: "
            f"code={result.error_code} msg={result.message[:200]}"
        )
        # SYSTEM_ERROR (= AttributeError 等) が出ていないことを明示
        assert result.error_code != "SYSTEM_ERROR"

    def test_use_spoiled_label_consumes_spoiled_item_and_keeps_fresh_item(self, session) -> None:
        """同じ食料の新鮮品と腐敗品を持つとき、腐敗ラベルの use_item は腐敗品を消費する。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        _grant(runtime, ada, "coconut")
        _grant(runtime, ada, "coconut")
        _set_one_owned_item_spoiled(runtime, ada, "coconut", is_spoiled=True)
        spoiled_label = _label_for_item_with_spoilage(
            runtime, ada, "coconut", is_spoiled=True,
        )

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            "arguments": {"item_label": spoiled_label, "inner_thought": "腐った方を食べる"},
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is True, result.message
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=False) == 1
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=True) == 0


# ---------------------------------------------------------------------------
# drop_item: PR #385 で resolver 経由になった
# ---------------------------------------------------------------------------
class TestDropItemEndToEnd:
    def test_drop_success_inventory_ground(self, session) -> None:
        """drop 成功で inventory から消え ground に移る。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        label = _label_for_item(runtime, ada, "coconut")

        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            "arguments": {"item_label": label, "inner_thought": "捨てる"},
        })
        session.llm_wiring.llm_client = stub
        result = session.llm_wiring.run_turn(ada)
        assert result.success is True, (
            f"drop_item 失敗: {result.error_code} {result.message[:120]}"
        )

    def test_drop_same_named_item_twice_resolves_slot_at_execution_time(self, session) -> None:
        """同名アイテムを2個持つとき、古い item_label を使う連続 drop でも毎回 slot を引き直す。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        _grant(runtime, ada, "coconut")
        item_label = _label_for_item(runtime, ada, "coconut")

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            "arguments": {"item_label": item_label, "inner_thought": "1個置く"},
        })
        first = session.llm_wiring.run_turn(ada)
        assert first.success is True, first.message

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            "arguments": {"item_label": item_label, "inner_thought": "もう1個置く"},
        })
        second = session.llm_wiring.run_turn(ada)
        assert second.success is True, second.message
        assert not _owns_spec(runtime, ada, "coconut")

    def test_drop_spoiled_label_drops_spoiled_item_and_keeps_fresh_item(self, session) -> None:
        """同じ食料の新鮮品と腐敗品を持つとき、腐敗ラベルの drop_item は腐敗品を地面へ置く。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        spot = "shipwreck_beach"
        _teleport(runtime, int(ada), spot)
        _grant(runtime, ada, "coconut")
        _grant(runtime, ada, "coconut")
        _set_one_owned_item_spoiled(runtime, ada, "coconut", is_spoiled=True)
        spoiled_label = _label_for_item_with_spoilage(
            runtime, ada, "coconut", is_spoiled=True,
        )

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            "arguments": {"item_label": spoiled_label, "inner_thought": "腐った方を捨てる"},
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is True, result.message
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=False) == 1
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=True) == 0
        assert _count_ground_spec_by_spoilage(runtime, spot, "coconut", is_spoiled=True) == 1


# ---------------------------------------------------------------------------
# give_item: 同 spot の player に渡す
# ---------------------------------------------------------------------------
class TestGiveItemEndToEnd:
    def _player_target_label(self, runtime, actor: PlayerId, target_pid: PlayerId) -> str:
        """actor の prompt context から target_pid の player label を引く。"""
        prompt = runtime.build_full_prompt(actor)
        ctx = prompt["tool_runtime_context"]
        for label, target in ctx.targets.items():
            if (
                getattr(target, "kind", None) == "spot_graph_player"
                and getattr(target, "player_id", None) == int(target_pid)
            ):
                return label
        raise AssertionError(f"player_id={int(target_pid)} の label が見つからない")

    def test_give_success_target_player(self, session) -> None:
        """give 成功で対象 player に所有が移る。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _teleport(runtime, int(noah), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        item_label = _label_for_item(runtime, ada, "coconut")

        target_player_label = self._player_target_label(runtime, ada, noah)

        # PR-α (Y_after_pr639_640 後続): give_item は batch-always に統合。
        # 単発でも ``gives: [...]`` 配列で渡す (要素数 1)。
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [
                    {
                        "item_label": item_label,
                        "target_player_label": target_player_label,
                    },
                ],
                "inner_thought": "渡す",
            },
        })
        session.llm_wiring.llm_client = stub
        result = session.llm_wiring.run_turn(ada)
        assert result.success is True, (
            f"give_item 失敗: {result.error_code} {result.message[:160]}"
        )
        # noah の inventory に coconut が入っている
        assert _owns_spec(runtime, noah, "coconut")
        # ada の inventory から消えている
        assert not _owns_spec(runtime, ada, "coconut")

    def test_give_same_named_items_to_three_players_resolves_slot_for_each_entry(self, session) -> None:
        """同名アイテム x3 を1回の give_item で3人へ配ると、各 entry で slot を引き直して全件成功する。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        rio = _player_id(runtime, "rio")
        kai = _player_id(runtime, "kai")
        for pid in (ada, noah, rio, kai):
            _teleport(runtime, int(pid), "shipwreck_beach")
        for _ in range(3):
            _grant(runtime, ada, "coconut")
        item_label = _label_for_item(runtime, ada, "coconut")
        labels = [
            self._player_target_label(runtime, ada, noah),
            self._player_target_label(runtime, ada, rio),
            self._player_target_label(runtime, ada, kai),
        ]

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [
                    {"item_label": item_label, "target_player_label": labels[0]},
                    {"item_label": item_label, "target_player_label": labels[1]},
                    {"item_label": item_label, "target_player_label": labels[2]},
                ],
                "inner_thought": "全員に分ける",
            },
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is True, result.message
        assert "NG" not in result.message
        assert result.trace_payload == {
            "give_item_total_count": 3,
            "give_item_success_count": 3,
            "give_item_failure_count": 0,
            # 個数を扱えるようにしたので、頼んだ数と動いた数も残る。
            "give_item_requested_quantity": 3,
            "give_item_moved_quantity": 3,
            "give_item_partial_failure": False,
        }
        assert not _owns_spec(runtime, ada, "coconut")
        assert _owns_spec(runtime, noah, "coconut")
        assert _owns_spec(runtime, rio, "coconut")
        assert _owns_spec(runtime, kai, "coconut")

    def test_give_more_targets_than_owned_items_reports_partial_failure_without_slot_instruction(self, session) -> None:
        """所持数を超えて同名アイテムを配ると、配れた分は成功し超過分だけ失敗として trace に残る。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        rio = _player_id(runtime, "rio")
        kai = _player_id(runtime, "kai")
        for pid in (ada, noah, rio, kai):
            _teleport(runtime, int(pid), "shipwreck_beach")
        for _ in range(2):
            _grant(runtime, ada, "coconut")
        recorder = _CapturingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        item_label = _label_for_item(runtime, ada, "coconut")
        labels = [
            self._player_target_label(runtime, ada, noah),
            self._player_target_label(runtime, ada, rio),
            self._player_target_label(runtime, ada, kai),
        ]

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [
                    {"item_label": item_label, "target_player_label": labels[0]},
                    {"item_label": item_label, "target_player_label": labels[1]},
                    {"item_label": item_label, "target_player_label": labels[2]},
                ],
                "inner_thought": "足りる分だけ分ける",
            },
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is True
        assert result.trace_payload == {
            "give_item_total_count": 3,
            "give_item_success_count": 2,
            "give_item_failure_count": 1,
            "give_item_requested_quantity": 3,
            "give_item_moved_quantity": 2,
            "give_item_partial_failure": True,
        }
        action_result_events = [
            payload
            for kind, payload in recorder.events
            if str(kind) == "action_result" and payload.get("tool") == TOOL_NAME_SPOT_GRAPH_GIVE_ITEM
        ]
        assert action_result_events
        assert action_result_events[-1]["give_item_success_count"] == 2
        assert action_result_events[-1]["give_item_failure_count"] == 1
        assert action_result_events[-1]["give_item_partial_failure"] is True
        assert "NG" in result.message
        assert "スロット" not in result.message
        assert "スロット番号を指定" not in result.message
        assert not _owns_spec(runtime, ada, "coconut")
        assert _owns_spec(runtime, noah, "coconut")
        assert _owns_spec(runtime, rio, "coconut")
        assert not _owns_spec(runtime, kai, "coconut")

    def test_give_fresh_label_transfers_fresh_item_and_keeps_spoiled_item(self, session) -> None:
        """同じ食料の新鮮品と腐敗品を持つとき、新鮮ラベルの give_item は新鮮品を渡す。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        for pid in (ada, noah):
            _teleport(runtime, int(pid), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        _grant(runtime, ada, "coconut")
        _set_one_owned_item_spoiled(runtime, ada, "coconut", is_spoiled=True)
        fresh_label = _label_for_item_with_spoilage(
            runtime, ada, "coconut", is_spoiled=False,
        )
        target_player_label = self._player_target_label(runtime, ada, noah)

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [{
                    "item_label": fresh_label,
                    "target_player_label": target_player_label,
                }],
                "inner_thought": "新鮮な方を渡す",
            },
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is True, result.message
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=False) == 0
        assert _count_owned_spec_by_spoilage(runtime, ada, "coconut", is_spoiled=True) == 1
        assert _count_owned_spec_by_spoilage(runtime, noah, "coconut", is_spoiled=False) == 1
        assert _count_owned_spec_by_spoilage(runtime, noah, "coconut", is_spoiled=True) == 0

    def test_give_dead_target_returns_learnable_failure(self, session) -> None:
        """死亡済みの相手へ give_item すると、日本語理由を返して所有は移らない。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _teleport(runtime, int(noah), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        runtime._player_outcome_registry.set_outcome(noah, PlayerOutcomeEnum.DEAD)
        item_label = _label_for_item(runtime, ada, "coconut")
        target_player_label = self._player_target_label(runtime, ada, noah)

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [
                    {
                        "item_label": item_label,
                        "target_player_label": target_player_label,
                    },
                ],
            },
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_DEAD"
        assert "死亡しており受け取れない" in result.message
        assert _owns_spec(runtime, ada, "coconut"), "拒否されたのに ada から消えている"
        assert not _owns_spec(runtime, noah, "coconut"), "拒否されたのに noah へ移っている"

    def test_give_down_target_returns_learnable_failure(self, session) -> None:
        """倒れている相手へ give_item すると、日本語理由を返して所有は移らない。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _teleport(runtime, int(noah), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        status = runtime._player_status_repo.find_by_id(noah)
        status.apply_damage(999)
        runtime._player_status_repo.save(status)
        item_label = _label_for_item(runtime, ada, "coconut")
        target_player_label = self._player_target_label(runtime, ada, noah)

        session.llm_wiring.llm_client = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            "arguments": {
                "gives": [
                    {
                        "item_label": item_label,
                        "target_player_label": target_player_label,
                    },
                ],
            },
        })

        result = session.llm_wiring.run_turn(ada)

        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_DOWN"
        assert "倒れていて受け取れない" in result.message
        assert _owns_spec(runtime, ada, "coconut"), "拒否されたのに ada から消えている"
        assert not _owns_spec(runtime, noah, "coconut"), "拒否されたのに noah へ移っている"


# ---------------------------------------------------------------------------
# pickup_item: 地面 → inventory
# ---------------------------------------------------------------------------
class TestPickupItemEndToEnd:
    def test_drop_pickup_round_trips(self, session) -> None:
        """drop → pickup の往復で resolver / executor / inventory が整合する。"""
        runtime = session.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _teleport(runtime, int(ada), "shipwreck_beach")
        _teleport(runtime, int(noah), "shipwreck_beach")
        _grant(runtime, ada, "coconut")
        label = _label_for_item(runtime, ada, "coconut")

        # ada が drop
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            "arguments": {"item_label": label, "inner_thought": "落とす"},
        })
        session.llm_wiring.llm_client = stub
        drop_result = session.llm_wiring.run_turn(ada)
        assert drop_result.success is True

        # noah が pickup する。地面アイテムの label を noah の context から探す
        prompt = runtime.build_full_prompt(noah)
        ctx = prompt["tool_runtime_context"]
        ground_label = None
        for label_n, target in ctx.targets.items():
            if getattr(target, "kind", None) == "ground_item":
                ground_label = label_n
                break
        assert ground_label is not None, "地面に drop されたアイテムが noah の context に出ない"
        stub2 = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            "arguments": {"ground_item_label": ground_label, "inner_thought": "拾う"},
        })
        session.llm_wiring.llm_client = stub2
        pickup_result = session.llm_wiring.run_turn(noah)
        assert pickup_result.success is True, (
            f"pickup 失敗: {pickup_result.error_code} {pickup_result.message[:120]}"
        )


# ---------------------------------------------------------------------------
# 静的検査 (silent bug の再発防止)
# ---------------------------------------------------------------------------
class TestNameResolverMethodNames:
    """name_resolver の typo regression 防止。実験 #27 の `item_name` 同型バグを
    formatter ファイル全体で再発させない。"""

    def test_calls_all_formatter_name_resolver_method(self) -> None:
        """formatter 群が `name_resolver.<method>(...)` で呼ぶ method 名が、
        実 `ObservationNameResolver` の public method として存在することを
        全件チェックする。
        """
        import re
        import inspect
        from ai_rpg_world.application.observation.services.formatters.name_resolver import (
            ObservationNameResolver,
        )

        # public method 名 (アンダースコア始まりでないもの) を列挙
        valid_methods = {
            name for name, _ in inspect.getmembers(
                ObservationNameResolver, predicate=inspect.isfunction,
            )
            if not name.startswith("_")
        }

        formatters_dir = (
            Path(__file__).resolve().parents[2]
            / "src/ai_rpg_world/application/observation/services/formatters"
        )
        pattern = re.compile(r"name_resolver\.([a-zA-Z_][a-zA-Z_0-9]*)\s*\(")
        offenders: list[tuple[Path, int, str]] = []
        for py in formatters_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), start=1):
                # コメント行はスキップ (typo を残しているだけのレビュー対象等)
                if line.lstrip().startswith("#"):
                    continue
                for m in pattern.finditer(line):
                    method = m.group(1)
                    if method not in valid_methods:
                        offenders.append((py, i, method))
        assert not offenders, (
            "name_resolver に存在しない method を呼んでいる formatter が "
            "残っている (実験 #27 と同型のバグ):\n" +
            "\n".join(
                f"  {o[0].name}:{o[1]} → name_resolver.{o[2]}() (未定義)"
                for o in offenders
            )
        )

    def test_inv_aggregate_method_typo_regression(self) -> None:
        """executor が `inv.<method>(...)` で呼ぶ method 名が、実
        PlayerInventoryAggregate の public method (or property) として
        存在することを確認する。実験 #26 の `inv.slots` バグ同型を防ぐ。"""
        import re
        import inspect
        from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
            PlayerInventoryAggregate,
        )

        valid_members = {
            name for name, _ in inspect.getmembers(PlayerInventoryAggregate)
            if not name.startswith("_") or name == "_inventory_slots"
        }

        executor_src = (
            Path(__file__).resolve().parents[2]
            / "src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py"
        )
        text = executor_src.read_text(encoding="utf-8")
        # `inv.<method>` or `inv.<attr>` を pickup (コメント以外)
        pattern = re.compile(r"\binv\.([a-zA-Z_][a-zA-Z_0-9]*)")
        offenders: list[tuple[int, str]] = []
        for i, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for m in pattern.finditer(line):
                name = m.group(1)
                if name not in valid_members:
                    offenders.append((i, name))
        assert not offenders, (
            "PlayerInventoryAggregate に存在しない member を executor が "
            "呼んでいる (実験 #26 と同型のバグ):\n" +
            "\n".join(f"  spot_graph_tool_executor.py:{i} → inv.{n}" for i, n in offenders)
        )
