"""公開SNSの露出・実行・通知・画面・再開が同じWorldRuntimeでつながる。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.being.world_state_snapshot import WorldStateSnapshot, WorldStateSnapshotCoverageError
from ai_rpg_world.application.being.world_state_snapshot_service import WorldStateSnapshotService
from ai_rpg_world.application.being.world_subsystems.public_sns_codec import PublicSnsSubsystemCodec
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.world_llm_turn.wiring import WorldLlmWiring
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.world_runtime import PublicSnsNotSupportedError, create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SUSPENDED = "公開 SNS の世界は、通知を【直近の出来事】に収め直すまで起動時に止めている (#1920)"


def _scenario_path(tmp_path: Path, *, enabled: bool, disabled=(), budget=6000) -> Path:
    raw = json.loads(Path("data/scenarios/station_drill.json").read_text())
    raw.update(
        public_sns_enabled=enabled,
        disabled_tools=list(dict.fromkeys([*raw.get("disabled_tools", []), *disabled])),
        public_sns_push_budget_chars=budget,
    )
    path = tmp_path / f"world-{len(list(tmp_path.iterdir()))}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    return path


def test_public_sns_world_stops_at_startup_with_the_issue_number(tmp_path):
    """公開 SNS を有効にしたシナリオは、起動時に PublicSnsNotSupportedError で止まり、文に直す Issue の番号 (#1920) が出る。"""
    path = _scenario_path(tmp_path, enabled=True)

    with pytest.raises(PublicSnsNotSupportedError, match="#1920"):
        create_world_runtime(path, config=ResolvedLlmRuntimeConfig.for_tests())


@pytest.fixture
def make_runtime(tmp_path):
    def create(*, enabled=True, disabled=(), budget=6000):
        if enabled:
            pytest.skip(_SUSPENDED)
        path = _scenario_path(tmp_path, enabled=enabled, disabled=disabled, budget=budget)
        return create_world_runtime(path, config=ResolvedLlmRuntimeConfig.for_tests())

    return create


def wire(runtime, call):
    return WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(call),
    )


def test_only_two_public_tools_and_disabled_tools_are_enforced(make_runtime):
    """SNS宣言時だけ二つの入口が現れ、個別無効化を実行時にも守る。"""
    absent = make_runtime(enabled=False)
    assert not any(d.name.startswith("sns_") for d in absent.get_tool_definitions(player_id=PlayerId(1)))
    runtime = make_runtime()
    assert {d.name for d in runtime.get_tool_definitions(player_id=PlayerId(1)) if d.name.startswith("sns_")} == {
        "sns_read",
        "sns_publish",
    }
    for name in ("sns_read", "sns_publish"):
        disabled = make_runtime(disabled=(name,))
        assert name not in [d.name for d in disabled.get_tool_definitions(player_id=PlayerId(1))]
        assert name not in disabled.build_full_prompt(PlayerId(1))["messages"][-1]["content"]
        result = wire(
            disabled, {"name": name, "arguments": {"view": "posts", "action": "new", "content": "公開されない"}}
        ).run_turn(PlayerId(1))
        assert not result.success
        assert not disabled._public_sns_data_store.posts


def test_provenance_and_short_receipt_reach_normal_action_store(make_runtime):
    """dataset記録が無効でも実行IDと実際のprovider呼出しIDと当人の手番が残る。"""
    runtime = make_runtime()
    call = {
        "name": "sns_publish",
        "arguments": {"action": "new", "content": "一度だけ公開する本文"},
        "tool_call_id": "provider-real-42",
    }
    wiring = wire(runtime, call)
    result = wiring.run_turn(PlayerId(1))
    assert result.success and not result.should_reschedule
    entry = runtime._action_result_store.get_recent(PlayerId(1), 1)[0]
    source = entry.execution_provenance
    assert source.execution_request_id.startswith("execution-")
    assert source.tool_call_id == "provider-real-42"
    assert source.actor_player_id == 1 and source.actor_turn == 1
    assert source.llm_call_id is None
    assert "一度だけ公開する本文" not in entry.result_summary
    wiring.llm_client.set_tool_call_to_return({"name": "sns_read", "arguments": {"view": "posts"}})
    assert wiring.run_turn(PlayerId(1)).success
    screen = runtime._public_sns_screens.get(1)
    assert screen.provenance.actor_turn == 2
    assert screen.provenance.execution_request_id != source.execution_request_id
    assert screen.provenance.tool_call_id is None


def test_push_has_full_body_and_target_without_forcing_read_or_wake(make_runtime):
    """返信通知は全文と返信先を持ち、そのまま返信できるが自動起床を要求しない。"""
    runtime = make_runtime()
    root = runtime._public_sns_command_service.publish(1, "相談があります")
    reply = runtime._public_sns_command_service.publish(2, "この内容に直接返事をください", root.target_id)
    observations = (
        runtime._obs_buffer.get_observations(PlayerId(1))
        if hasattr(runtime._obs_buffer, "get_observations")
        else runtime._obs_buffer.peek(PlayerId(1))
    )
    notice = next(o for o in observations if o.output.structured.get("type") == "public_sns_notification")
    assert not notice.output.schedules_turn and not notice.output.breaks_movement
    assert "この内容に直接返事をください" in notice.output.prose
    assert reply.target_id in notice.output.prose
    prompt = runtime.build_full_prompt(PlayerId(1))
    assert prompt["messages"][-1]["content"].count("この内容に直接返事をください") == 1
    assert runtime._public_sns_screens.get(1) is None
    result = wire(
        runtime,
        {
            "name": "sns_publish",
            "arguments": {"action": "reply", "target_id": reply.target_id, "content": "読み直さずに返事します"},
        },
    ).run_turn(PlayerId(1))
    assert result.success


def test_failed_read_keeps_screen_and_close_removes_it(make_runtime):
    """別scopeの対象を読んでも最後の成功画面が残り、closeだけで消える。"""
    runtime = make_runtime()
    runtime._public_sns_command_service.publish(1, "保持する本文")
    assert runtime._public_sns_executor.read(2, {"view": "posts"}).success
    before = runtime._public_sns_screens.get(2)
    assert not runtime._public_sns_executor.read(2, {"view": "thread", "target_id": "sns:other:post:missing"}).success
    assert runtime._public_sns_screens.get(2) == before
    assert "保持する本文" in runtime.build_full_prompt(PlayerId(2))["messages"][-1]["content"]
    assert runtime._public_sns_executor.read(2, {"view": "close"}).success
    assert runtime._public_sns_screens.get(2) is None


def test_screen_deduplicates_push_and_builds_do_not_consume_it(make_runtime):
    """画面と通知の本文を重複表示せず、単なる再描画では表示済みにしない。"""
    runtime = make_runtime()
    root = runtime._public_sns_command_service.publish(1, "親投稿")
    reply = runtime._public_sns_command_service.publish(2, "重複させない本文", root.target_id)
    p1 = runtime.build_full_prompt(PlayerId(1))
    p2 = runtime.build_full_prompt(PlayerId(1))
    assert p1["sns_shown_notification_ids"] == p2["sns_shown_notification_ids"]
    assert p1["sns_shown_notification_ids"]
    assert "重複させない本文" in p2["messages"][-1]["content"]
    runtime._public_sns_executor.read(1, {"view": "thread", "target_id": reply.target_id})
    p3 = runtime.build_full_prompt(PlayerId(1))
    assert p3["messages"][-1]["content"].count("重複させない本文") == 1
    wiring = wire(runtime, {"name": "wait", "arguments": {}})
    wiring.run_turn(PlayerId(1))
    assert not runtime._public_sns_projection.capture()["pending"]["1"]


def test_push_budget_is_total_and_overflow_stays_in_inbox(make_runtime):
    """大量通知でも描画合計が設定文字数以下で、未表示分を受信箱から取得できる。"""
    runtime = make_runtime(budget=1000)
    root = runtime._public_sns_command_service.publish(1, "親投稿")
    for index in range(12):
        runtime._public_sns_command_service.publish(2, f"通知{index:02d}" + "文" * 200, root.target_id)
    runtime.build_full_prompt(PlayerId(1))
    entries = runtime._recent_event_store.get_active_timeline(PlayerId(1))
    projected, shown = runtime._public_sns_projection.project(PlayerId(1), entries)
    rendered = runtime._recent_events_formatter.format_unified_entries(projected)
    assert len(rendered) <= 1000
    assert "未表示の通知が" in rendered
    assert len(shown) < 12
    assert len(runtime._public_sns_data_store.sns_notifications) == 12
    assert len(runtime._public_sns_read_service.read_notifications(1, limit=20).items) == 12


def test_snapshot_restores_contents_identity_screen_and_execution_source(make_runtime):
    """再開後も投稿ID・人物ID・保持画面・実行出典が一致し、新しい返信が作れる。"""
    runtime = make_runtime()
    wiring = wire(
        runtime,
        {"name": "sns_publish", "arguments": {"action": "new", "content": "保存する本文"}, "tool_call_id": "real-call"},
    )
    assert wiring.run_turn(PlayerId(1)).success
    wiring.llm_client.set_tool_call_to_return({"name": "sns_read", "arguments": {"view": "posts"}})
    wiring.run_turn(PlayerId(2))
    codec = PublicSnsSubsystemCodec()
    data = codec.capture(runtime)
    resumed = make_runtime()
    codec.restore(resumed, data)
    assert codec.capture(resumed) == data
    target = resumed._public_sns_read_service.read_posts(2).items[0].target_id
    assert resumed._public_sns_command_service.publish(2, "再開した返事", target).parent_target_id == target
    before = codec.capture(resumed)
    corrupt = copy.deepcopy(data)
    corrupt["screens"]["screens"][0]["text"] = "x" * 13000
    with pytest.raises(ValueError):
        codec.restore(resumed, corrupt)
    assert codec.capture(resumed) == before


def test_legacy_missing_sns_snapshot_only_allowed_when_disabled(make_runtime):
    """SNS有効worldでは内容欠落を拒み、無効worldの過去snapshotだけ互換を保つ。"""
    service = WorldStateSnapshotService(
        subsystem_codecs=[PublicSnsSubsystemCodec()], expected_subsystem_keys=["public_sns"]
    )
    snapshot = WorldStateSnapshot(source_scenario="world", world_tick=0, subsystems={})
    service.restore(make_runtime(enabled=False), snapshot, current_scenario="world", strict_subsystems=True)
    with pytest.raises(WorldStateSnapshotCoverageError):
        service.restore(make_runtime(), snapshot, current_scenario="world", strict_subsystems=True)


def test_failed_notification_delivery_resumes_before_first_prompt(make_runtime, monkeypatch):
    """確定後の配送失敗を保存して再開し、投稿を増やさず最初のprompt前に一度だけ届ける。"""
    runtime = make_runtime()
    root = runtime._public_sns_command_service.publish(1, "保存済みの親")

    def fail_delivery(*args):
        raise RuntimeError("配信先が一時停止しています")

    monkeypatch.setattr(runtime, "_emit_observation_directly", fail_delivery)
    result = wire(
        runtime,
        {
            "name": "sns_publish",
            "arguments": {"action": "reply", "target_id": root.target_id, "content": "再送される本文"},
            "tool_call_id": "actual-reply-call",
        },
    ).run_turn(PlayerId(2))
    assert result.success and not result.should_reschedule
    assert result.trace_payload["notification_delivery_pending"]
    codec = PublicSnsSubsystemCodec()
    data = codec.capture(runtime)
    resumed = make_runtime()
    codec.restore(resumed, data)
    first = resumed.build_full_prompt(PlayerId(1))
    second = resumed.build_full_prompt(PlayerId(1))
    assert first["messages"][-1]["content"].count("再送される本文") == 1
    assert second["messages"][-1]["content"].count("再送される本文") == 1
    observations = [
        e.payload for e in resumed._recent_event_store.get_active_timeline(PlayerId(1)) if e.kind == "observation"
    ]
    sns = [e for e in observations if e.output.structured.get("type") == "public_sns_notification"]
    assert len(sns) == 1
    assert sns[0].output.structured["execution_provenance"]["tool_call_id"] == "actual-reply-call"
    assert len(resumed._public_sns_data_store.replies) == 1


def test_header_keeps_pending_count_after_observation_ages_out(make_runtime):
    """通知本文が直近履歴から抜けても未表示件数と自分の不変IDが閉じた画面に残る。"""
    runtime = make_runtime()
    runtime._public_sns_projection.note_incoming(1, "aged-out-notice")
    prompt = runtime.build_full_prompt(PlayerId(1))["messages"][-1]["content"]
    assert "未表示通知: 1件" in prompt
    assert "受信箱で確認できます" in prompt
    assert "現在の画面: 閉じています" in prompt
    assert ":user:" in prompt


@pytest.mark.parametrize("budget", [512, 700, 800])
def test_small_budget_keeps_reply_target_and_partial_body_pending(make_runtime, budget):
    """小さい設定でも人物と返信先を表示し、省略された本文を既読扱いにしない。"""
    runtime = make_runtime(budget=budget)
    root = runtime._public_sns_command_service.publish(1, "親")
    reply = runtime._public_sns_command_service.publish(2, "重要な回答本文" + "長" * 272, root.target_id)
    prompt = runtime.build_full_prompt(PlayerId(1))
    text = prompt["messages"][-1]["content"]
    assert reply.target_id in text
    assert reply.author_target_id in text
    assert "重要" in text
    if "本文の続きは受信箱" in text:
        assert not prompt["sns_shown_notification_ids"]
        assert runtime._public_sns_projection.pending_count(1) == 1


def test_failed_read_exposes_request_source_without_relabeling_old_screen(make_runtime):
    """失敗要求と成功画面の出典を分け、最終promptで旧画面保持と取得条件を明示する。"""
    runtime = make_runtime()
    runtime._public_sns_command_service.publish(1, "保持対象の本文")
    wiring = wire(runtime, {"name": "sns_read", "arguments": {"view": "posts"}, "tool_call_id": "successful-read"})
    assert wiring.run_turn(PlayerId(2)).success
    screen_source = runtime._public_sns_screens.get(2).provenance
    text = runtime.build_full_prompt(PlayerId(2))["messages"][-1]["content"]
    assert "新しく取得した内容" in text
    assert "表示条件: 公開され、現在閲覧できる内容のみ" in text
    assert "続き: なし" in text
    wiring.llm_client.set_tool_call_to_return(
        {"name": "sns_read", "arguments": {"view": "thread", "target_id": "missing"}, "tool_call_id": "failed-read"}
    )
    result = wiring.run_turn(PlayerId(2))
    assert not result.success
    assert result.trace_payload["sns_request"]["status"] == "failed_retained"
    assert result.trace_payload["sns_request"]["provenance"]["tool_call_id"] == "failed-read"
    assert result.trace_payload["retained_screen_provenance"]["tool_call_id"] == "successful-read"
    assert runtime._public_sns_screens.get(2).provenance == screen_source
    text = runtime.build_full_prompt(PlayerId(2))["messages"][-1]["content"]
    assert "閲覧要求は失敗" in text
    assert "以前に取得した画面を保持" in text
    assert text.count("保持対象の本文") == 1


def test_missing_world_file_fails_closed_in_actual_snapshot_session(make_runtime, tmp_path):
    """実際の再開入口でもworld.json欠落を拒み、既存SNS識別子を空worldへ結び直さない。"""
    from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

    from ai_rpg_world.application.being.experiment_snapshot_session import ExperimentSnapshotSession

    runtime = make_runtime()
    runtime._wire_being_stack()
    session = ExperimentSnapshotSession(
        wiring_result=_wiring_stub_from_world_runtime(runtime), snapshot_dir=tmp_path / "snapshot"
    )
    with pytest.raises(WorldStateSnapshotCoverageError):
        session.restore_world_from_dir(runtime, tmp_path / "missing", current_scenario="world")
    disabled = make_runtime(enabled=False)
    disabled._wire_being_stack()
    legacy = ExperimentSnapshotSession(
        wiring_result=_wiring_stub_from_world_runtime(disabled), snapshot_dir=tmp_path / "legacy"
    )
    assert legacy.restore_world_from_dir(disabled, tmp_path / "missing", current_scenario="world") is None


def test_invalid_enum_types_are_ordinary_errors_and_keep_screen(make_runtime):
    """列挙引数の配列やオブジェクトは例外にならず、通常の入力失敗として返る。"""
    runtime = make_runtime()
    runtime._public_sns_executor.read(1, {"view": "posts"})
    screen = runtime._public_sns_screens.get(1)
    assert runtime._public_sns_executor.read(1, {"view": []}).error_code == "SNS_INVALID_REQUEST"
    assert (
        runtime._public_sns_executor.publish(1, {"action": {}, "content": "本文"}).error_code == "SNS_INVALID_REQUEST"
    )
    assert runtime._public_sns_screens.get(1) == screen


def test_disabled_sns_declaration_keeps_existing_prompt_bytes(make_runtime, tmp_path):
    """SNSを宣言しない世界とfalseの世界は、既存の本文と道具定義が同一になる。"""
    raw = json.loads(Path("data/scenarios/station_drill.json").read_text())
    path = tmp_path / "without-sns.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    absent = create_world_runtime(path, config=ResolvedLlmRuntimeConfig.for_tests())
    disabled = make_runtime(enabled=False)
    assert absent.build_full_prompt(PlayerId(1))["messages"] == disabled.build_full_prompt(PlayerId(1))["messages"]
    assert absent.get_tool_definitions(player_id=PlayerId(1)) == disabled.get_tool_definitions(player_id=PlayerId(1))


def test_failed_llm_request_does_not_consume_notification_body(make_runtime):
    """モデルの呼出しが失敗した場合、次の判断にも未表示本文を残す。"""
    runtime = make_runtime()
    root = runtime._public_sns_command_service.publish(1, "親投稿")
    runtime._public_sns_command_service.publish(2, "失敗後も届く本文", root.target_id)
    wiring = wire(runtime, None)
    wiring.llm_client.set_exception_to_raise(RuntimeError("一時的な呼出し失敗"))
    assert not wiring.run_turn(PlayerId(1)).success
    assert runtime._public_sns_projection.pending_count(1) == 1
    assert "失敗後も届く本文" in runtime.build_full_prompt(PlayerId(1))["messages"][-1]["content"]
