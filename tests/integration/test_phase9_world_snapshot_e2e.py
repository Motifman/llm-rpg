"""Phase 9 完成版 E2E テスト: 実 ``EscapeGameRuntime`` で world snapshot 往復 (Issue #470)。

Phase 9 全体 (9-1〜9-4c) で 21 subsystem の world snapshot が揃った。本ファイル
は **実 EscapeGameRuntime を立てて** snapshot → 復元の end-to-end を担保する。

## カバレッジ

- ``test_capture_restore_round_trip_bit_identical``: 実 runtime で capture →
  別 runtime に restore → recapture すると payload が bit-identical
- ``test_post_restore_runtime_can_advance_ticks``: restore 後の runtime が
  ``advance_tick()`` で正常に進む (= resume が機能して crash しない)
- ``test_world_tick_continues_from_restored_value``: snapshot に tick=N が
  保存されていれば、復元後 runtime.current_tick() == N
- ``test_cross_scenario_world_load_fails_fast``: 別 scenario への world
  snapshot 読み込みは即 fail
- ``test_legacy_snapshot_dir_no_world_json_skips_world``: world.json なし
  (= Phase 6 までの旧 snapshot) でも壊れずに skip

## 「30+30=60 tick 等価性」について

LLM 出力は非決定論的なので、bit-identical な run output 比較は原理的に不可能。
代わりに「**snapshot の前後で state が等価**」+「**post-restore で runtime が
正常に進む**」を担保することで、**LLM が決定論なら 60 tick の一気走と同じ
trajectory になる** ことが理屈で保証される (= Phase 8 の決定性 property を
継承)。

## stub LLM の使用

LLM 呼び出しは ``LLM_CLIENT=stub`` で stub クライアントを使う。stub は
deterministic な fixed response を返すので、テスト全体が deterministic に
保たれる。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ai_rpg_world.application.being.experiment_snapshot_session import (
    ExperimentSnapshotSession,
)
from ai_rpg_world.application.being.world_state_snapshot import (
    WorldStateScenarioMismatchError,
)


_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios"
)
_SCENARIO_FILE = "decay_demo.json"


def _build_runtime_session(out_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """``EscapeGameRuntime`` を 1 つ立てて ``ExperimentSnapshotSession`` を返す。

    既存の ``scripts/run_scenario_experiment.py`` の wiring 構築を再現するが、
    完全には呼び出さない (= LLM turn loop は走らせない、scenario 起動のみ)。

    Phase 9-5 code-review HIGH 2 対応: ``os.environ`` 直書きでなく
    ``monkeypatch.setenv`` で test 後に自動 restore する (= test 間干渉防止)。
    """
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    monkeypatch.setenv("LLM_CLIENT", "stub")
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")

    chars_path = out_dir / "characters.json"
    mgr = GameRuntimeManager(
        scenarios_dir=_SCENARIOS_DIR, characters_path=chars_path
    )
    char = mgr.create_character(CharacterCreateRequest(name="e2e-test"))
    world_id = Path(_SCENARIO_FILE).stem
    summary = mgr.create_session(
        SessionCreateRequest(world_id=world_id, character_ids=[char.id])
    )
    state = mgr._sessions[summary.session_id]
    runtime = state.runtime

    # snapshot session を組むためには aux Being stack の初期化が必要
    # (= scripts/run_scenario_experiment.py の経路と同じ)。
    if hasattr(runtime, "_wire_auxiliary_tool_stack"):
        runtime._wire_auxiliary_tool_stack()
    for pid in runtime.get_player_ids():
        provisioning = getattr(runtime, "_aux_being_provisioning", None)
        if provisioning is not None:
            provisioning.ensure_attached(pid)

    from scripts.run_scenario_experiment import (
        _wiring_stub_from_escape_runtime,
    )

    wiring_stub = _wiring_stub_from_escape_runtime(runtime)
    session = ExperimentSnapshotSession(
        wiring_result=wiring_stub,
        snapshot_dir=out_dir / "snapshots",
    )
    # mgr を保持しないと session の終わり際で GC される (= scenario 状態が失われる)
    return runtime, session, mgr


def _normalize_world_json(path: Path) -> dict:
    """captured_at だけ落とした正規化 dict を返す (= 時刻だけ揺らぐので)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("captured_at", None)
    return data


class TestE2ECaptureRestoreRoundTrip:
    """Phase 9 完成のテスト: 21 subsystem 全て round-trip で bit-identical。"""

    def test_capture_restore_round_trip_bit_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """src で capture → dst で restore → recapture が bit-identical。

        これにより全 21 subsystem の codec が正しく往復することを担保。
        """
        # --- src 環境
        src_dir = tmp_path / "src"
        src_runtime, src_session, _src_mgr = _build_runtime_session(src_dir, monkeypatch)
        src_session.capture_world(
            src_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(src_runtime.current_tick()),
        )
        src_world_data = _normalize_world_json(
            src_dir / "snapshots" / "world.json"
        )

        # --- dst 環境 (= fresh runtime)
        dst_dir = tmp_path / "dst"
        dst_runtime, dst_session, _dst_mgr = _build_runtime_session(dst_dir, monkeypatch)
        # まず src で取った snapshot を dst の snapshots/ に配置
        (dst_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        (dst_dir / "snapshots" / "world.json").write_text(
            (src_dir / "snapshots" / "world.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        # restore
        dst_session.restore_world_from_dir(
            dst_runtime,
            dst_dir / "snapshots",
            current_scenario=Path(_SCENARIO_FILE).stem,
        )
        # recapture
        dst_session.capture_world(
            dst_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(dst_runtime.current_tick()),
        )
        dst_world_data = _normalize_world_json(
            dst_dir / "snapshots" / "world.json"
        )

        # bit-identical (captured_at 除く) ことを assert
        assert src_world_data == dst_world_data, (
            "snapshot round-trip が bit-identical でない。"
            "subsystem codec のいずれかで非対称な変換が起きている可能性。"
        )

    def test_subsystems_に_全_21_が乗る(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Phase 9 完成版で世界状態 snapshot に 21 subsystem が含まれる。"""
        runtime, session, _mgr = _build_runtime_session(tmp_path, monkeypatch)
        session.capture_world(
            runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(runtime.current_tick()),
        )
        data = json.loads(
            (tmp_path / "snapshots" / "world.json").read_text(encoding="utf-8")
        )
        expected_subsystems = {
            # Phase 9-2
            "world_tick",
            "player_position",
            "player_vitals",
            "player_needs",
            # Phase 9-2b
            "player_inventory",
            "player_growth",
            "player_state_dict",
            # Phase 9-3
            "world_flags",
            "scenario_event_progress",
            "exploration_progress",
            # Phase 9-3b
            "spot_interior",
            "item_instance",
            # Phase 9-4a
            "player_active_effects",
            "player_attention_level",
            "player_pursuit_state",
            "player_spot_navigation_state",
            # Phase 9-4b
            "weather",
            "day_night",
            # Phase 9-4c
            "sliding_window",
            "observation_buffer",
            "action_result_store",
        }
        assert set(data["subsystems"].keys()) == expected_subsystems
        assert len(data["subsystems"]) == 21

    def test_round_trip_with_mutated_non_initial_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**non-trivial** な live state で round-trip が bit-identical。

        code-review HIGH 1 対応: 初期状態だけの round-trip だと codec が
        「空 default を黙って補完」するバグを見逃す。複数 subsystem を
        意図的に non-initial な状態に置いてから capture → restore →
        recapture を比較する。

        mutate する subsystem:
        - world_tick (= advance_tick で進める)
        - player_vitals (= HP を private に直書きで減らす)
        - player_state_dict (= scenario flag を入れる)
        - world_flags (= flag を追加)
        - sliding_window (= 観測を 1 件 append)
        - action_result_store (= action result を 1 件 append)
        """
        from datetime import datetime, timezone

        from ai_rpg_world.application.llm.contracts.dtos import (
            ActionResultEntry,
        )
        from ai_rpg_world.application.observation.contracts.dtos import (
            ObservationEntry,
            ObservationOutput,
        )

        src_dir = tmp_path / "src"
        src_runtime, src_session, _mgr = _build_runtime_session(
            src_dir, monkeypatch
        )

        # === mutate phase ===
        # 1. world_tick: advance を 4 回 (= 0 でない値にする)
        for _ in range(4):
            src_runtime.advance_tick()

        # 2. player_vitals: HP を 100 → 73 に
        from ai_rpg_world.domain.player.value_object.hp import Hp

        pid_list = list(src_runtime.get_player_ids())
        first_pid = pid_list[0]
        agg = src_runtime._player_status_repo.find_by_id(first_pid)
        agg._hp = Hp(value=73, max_hp=agg._hp.max_hp)
        src_runtime._player_status_repo.save(agg)

        # 3. player_state_dict: scenario flag を入れる
        agg = src_runtime._player_status_repo.find_by_id(first_pid)
        agg._state["e2e_marker"] = "set_in_src"
        src_runtime._player_status_repo.save(agg)

        # 4. world_flags: flag 追加
        src_runtime._world_flag_state.add("e2e_e_world_flag")

        # 5. sliding_window: 観測 1 件 append
        ts = datetime(2026, 6, 14, 9, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=ts,
            output=ObservationOutput(
                prose="e2e mutate marker",
                structured={"kind": "e2e_test_marker"},
                observation_category="self_only",
                schedules_turn=False,
                breaks_movement=False,
            ),
            game_time_label="Day 1 morning",
        )
        src_runtime._sliding_window.append(first_pid, obs)

        # 6. action_result_store: action result 1 件
        ar = ActionResultEntry(
            occurred_at=ts,
            action_summary="walked_to_armory",
            result_summary="arrived",
            success=True,
            tool_name="walk",
            occurred_tick=int(src_runtime.current_tick()),
        )
        src_runtime._action_result_store._store[int(first_pid.value)] = [ar]

        # === capture ===
        src_session.capture_world(
            src_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(src_runtime.current_tick()),
        )
        src_world_data = _normalize_world_json(
            src_dir / "snapshots" / "world.json"
        )

        # sanity: mutate した内容が実際に snapshot に乗っているか確認
        subsystems = src_world_data["subsystems"]
        assert src_world_data["world_tick"] > 0  # tick が進んだ
        vitals_entry = next(
            e
            for e in subsystems["player_vitals"]["entries"]
            if e["player_id"] == int(first_pid.value)
        )
        assert vitals_entry["hp_value"] == 73
        sd_entry = next(
            e
            for e in subsystems["player_state_dict"]["entries"]
            if e["player_id"] == int(first_pid.value)
        )
        assert sd_entry["state"].get("e2e_marker") == "set_in_src"
        assert "e2e_e_world_flag" in subsystems["world_flags"]["flags"]
        sw_entries = subsystems["sliding_window"]["entries"]
        sw_player_entry = next(
            (e for e in sw_entries if e["player_id"] == int(first_pid.value)),
            None,
        )
        assert sw_player_entry is not None
        assert any(
            "e2e mutate marker" in entry["output"]["prose"]
            for entry in sw_player_entry["entries"]
        )
        ar_entries = subsystems["action_result_store"]["entries"]
        ar_player_entry = next(
            (e for e in ar_entries if e["player_id"] == int(first_pid.value)),
            None,
        )
        assert ar_player_entry is not None
        assert any(
            entry["action_summary"] == "walked_to_armory"
            for entry in ar_player_entry["entries"]
        )

        # === restore + recapture (= bit-identical 確認) ===
        dst_dir = tmp_path / "dst"
        dst_runtime, dst_session, _dst_mgr = _build_runtime_session(
            dst_dir, monkeypatch
        )
        (dst_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        (dst_dir / "snapshots" / "world.json").write_text(
            (src_dir / "snapshots" / "world.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        dst_session.restore_world_from_dir(
            dst_runtime,
            dst_dir / "snapshots",
            current_scenario=Path(_SCENARIO_FILE).stem,
        )
        dst_session.capture_world(
            dst_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(dst_runtime.current_tick()),
        )
        dst_world_data = _normalize_world_json(
            dst_dir / "snapshots" / "world.json"
        )
        assert src_world_data == dst_world_data, (
            "non-trivial state での round-trip が bit-identical でない。"
            "live state を扱う codec が非対称な変換をしている可能性。"
        )


class TestE2EPostRestoreRuntime:
    """restore 後の runtime が正常に動作 = resume が crash しない。"""

    def test_post_restore_runtime_can_advance_ticks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """restore 後の runtime で ``advance_tick()`` が無事に進むことを確認。

        これが crash すると resume したつもりが「runtime が壊れていて続行
        不能」になる。本 test は **「resume が機能する」最後の守り**。
        """
        # src で snapshot を取り、dst で restore
        src_runtime, src_session, _src_mgr = _build_runtime_session(
            tmp_path / "src"
        , monkeypatch)
        src_session.capture_world(
            src_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=int(src_runtime.current_tick()),
        )

        dst_dir = tmp_path / "dst"
        dst_runtime, dst_session, _dst_mgr = _build_runtime_session(dst_dir, monkeypatch)
        (dst_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        (dst_dir / "snapshots" / "world.json").write_text(
            (tmp_path / "src" / "snapshots" / "world.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        dst_session.restore_world_from_dir(
            dst_runtime,
            dst_dir / "snapshots",
            current_scenario=Path(_SCENARIO_FILE).stem,
        )

        # restore 後に advance_tick を 3 回呼んで crash しないことを確認
        initial_tick = int(dst_runtime.current_tick())
        for _ in range(3):
            dst_runtime.advance_tick()
        assert int(dst_runtime.current_tick()) == initial_tick + 3

    def test_world_tick_continues_from_restored_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """snapshot に world_tick=N が保存されたら、restore 後 current_tick == N。

        Phase 9-2 で導入した ``set_current_tick`` が機能していることを担保。
        scenario の「30 tick の続きから」を成立させる土台。
        """
        # src で tick を進める
        src_runtime, src_session, _src_mgr = _build_runtime_session(
            tmp_path / "src"
        , monkeypatch)
        for _ in range(5):
            src_runtime.advance_tick()
        src_tick = int(src_runtime.current_tick())
        assert src_tick >= 5  # スポット遷移で more 進む可能性あり

        src_session.capture_world(
            src_runtime,
            source_scenario=Path(_SCENARIO_FILE).stem,
            world_tick=src_tick,
        )

        # dst で restore して tick が src_tick に揃うことを確認
        dst_dir = tmp_path / "dst"
        dst_runtime, dst_session, _dst_mgr = _build_runtime_session(dst_dir, monkeypatch)
        assert int(dst_runtime.current_tick()) == 0  # 初期状態
        (dst_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        (dst_dir / "snapshots" / "world.json").write_text(
            (tmp_path / "src" / "snapshots" / "world.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        dst_session.restore_world_from_dir(
            dst_runtime,
            dst_dir / "snapshots",
            current_scenario=Path(_SCENARIO_FILE).stem,
        )
        assert int(dst_runtime.current_tick()) == src_tick, (
            f"world_tick が src={src_tick} に対し dst={int(dst_runtime.current_tick())} "
            f"= WorldTickSubsystemCodec.restore が機能していない"
        )


class TestE2EFailFast:
    """scenario mismatch / 後方互換のテスト。"""

    def test_cross_scenario_world_load_fails_fast(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """別 scenario への world snapshot 読み込みは ``WorldStateScenarioMismatchError``。

        MEDIUM 2 対応 (code-review): ``source_scenario`` は実在する scenario
        名 (= ``decay_demo`` / ``regrowth_demo``) で検証する。将来
        ``capture_world`` 側で scenario の実在検証が入っても test が崩れない。
        """
        runtime, session, _mgr = _build_runtime_session(tmp_path / "src", monkeypatch)
        session.capture_world(
            runtime,
            source_scenario="decay_demo",  # 実 runtime と一致 (= 正常 save)
            world_tick=int(runtime.current_tick()),
        )
        # 別 scenario (= regrowth_demo) で load 試行
        dst_runtime, dst_session, _dst_mgr = _build_runtime_session(
            tmp_path / "dst", monkeypatch
        )
        dst_dir = tmp_path / "dst" / "snapshots"
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "world.json").write_text(
            (tmp_path / "src" / "snapshots" / "world.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        with pytest.raises(WorldStateScenarioMismatchError, match="decay_demo"):
            dst_session.restore_world_from_dir(
                dst_runtime,
                dst_dir,
                current_scenario="regrowth_demo",
            )

    def test_legacy_snapshot_dir_no_world_json_skips_world(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """world.json なし (= Phase 6 までの旧 snapshot) でも restore は no-op で動く。"""
        runtime, session, _mgr = _build_runtime_session(tmp_path, monkeypatch)
        legacy_dir = tmp_path / "legacy_no_world"
        legacy_dir.mkdir()
        # world.json なしの dir に対する restore → ``None`` で no-op
        result = session.restore_world_from_dir(
            runtime, legacy_dir, current_scenario=Path(_SCENARIO_FILE).stem
        )
        assert result is None
