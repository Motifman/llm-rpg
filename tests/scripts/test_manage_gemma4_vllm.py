"""Gemma 4 vLLM 常駐サービスの開始・監視・安全停止の仕様を保証する。"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

import scripts.manage_gemma4_vllm as manager_module
from scripts.manage_gemma4_vllm import (
    DrainTimeoutError,
    HealthResult,
    ServiceManager,
    ensure_gpu_is_idle,
    parse_vllm_metrics,
    render_systemd_units,
    replica_spec,
    wait_until_drained,
)


class TestReplicaSpec:
    """GPU 枠 0〜3を専用GPUと8100〜8103番へ一意に対応させる。"""

    @pytest.mark.parametrize(
        ("slot", "gpu_id", "port"),
        [(0, 0, 8100), (1, 1, 8101), (2, 2, 8102), (3, 3, 8103)],
    )
    def test_valid_slot_maps_to_same_gpu_and_port(
        self, slot: int, gpu_id: int, port: int
    ) -> None:
        """有効な枠番号は同番号のGPUと8100+枠番号のポートへ解決される。"""
        spec = replica_spec(slot)

        assert spec.slot == slot
        assert spec.gpu_id == gpu_id
        assert spec.port == port
        assert spec.api_base == f"http://127.0.0.1:{port}/v1"

    @pytest.mark.parametrize("slot", [-1, 4, 99])
    def test_invalid_slot_fails_before_process_start(self, slot: int) -> None:
        """範囲外の枠番号は別GPUを誤使用せず起動前に失敗する。"""
        with pytest.raises(ValueError, match="0..3"):
            replica_spec(slot)


class TestGpuExclusivity:
    """vLLM起動前に対象GPU上の既存計算を検出し、実験同士の競合を防ぐ。"""

    def test_occupied_gpu_fails_with_process_detail(self) -> None:
        """対象GPUに別プロセスがいればPIDと使用量を示して起動を拒否する。"""
        output = "2746305, /opt/venv/bin/python, 1662\n"

        with pytest.raises(RuntimeError, match="2746305.*1662"):
            ensure_gpu_is_idle(
                replica_spec(0),
                query_compute_apps=lambda _: output,
            )

    def test_empty_gpu_allows_replica_start(self) -> None:
        """対象GPUの計算プロセス一覧が空なら起動前検査を通過する。"""
        ensure_gpu_is_idle(replica_spec(0), query_compute_apps=lambda _: "")


class TestMetrics:
    """vLLMのメトリクスから安全停止に必要な実行中・待機中要求数を得る。"""

    def test_running_and_waiting_requests_are_summed_across_labels(self) -> None:
        """複数ラベルの要求数は合算され、一件でも残れば停止可能と判定しない。"""
        metrics = """
# HELP vllm:num_requests_running Number of requests currently running on GPU.
vllm:num_requests_running{engine="0",model_name="gemma-4-31b-it"} 2.0
vllm:num_requests_running{engine="1",model_name="gemma-4-31b-it"} 1.0
vllm:num_requests_waiting{engine="0",model_name="gemma-4-31b-it"} 4.0
"""

        load = parse_vllm_metrics(metrics)

        assert load.running == 3
        assert load.waiting == 4
        assert not load.is_drained

    def test_missing_required_gauges_is_not_silently_treated_as_idle(self) -> None:
        """必要な指標が欠けた応答は空いていると誤認せず明示的に失敗する。"""
        with pytest.raises(ValueError, match="num_requests_running"):
            parse_vllm_metrics("vllm:prompt_tokens_total 42\n")


class TestDrain:
    """正常停止は全要求が完了するまで待ち、上限超過を明示する。"""

    def test_busy_replica_is_polled_until_all_requests_finish(self) -> None:
        """実行中・待機中要求が0になる前には停止処理へ進まない。"""
        responses = iter(
            [
                "vllm:num_requests_running 1\nvllm:num_requests_waiting 2\n",
                "vllm:num_requests_running 0\nvllm:num_requests_waiting 0\n",
            ]
        )
        sleeps: list[float] = []

        load = wait_until_drained(
            fetch_metrics=lambda: next(responses),
            timeout_seconds=10,
            poll_interval_seconds=0.25,
            monotonic_values=iter([0.0, 0.1]),
            sleep=sleeps.append,
        )

        assert load.is_drained
        assert sleeps == [0.25]

    def test_busy_replica_past_deadline_raises_with_load_detail(self) -> None:
        """停止待ち上限を超えたら要求数を含む例外を投げ、強制停止へ縮退しない。"""
        metrics = "vllm:num_requests_running 2\nvllm:num_requests_waiting 3\n"

        with pytest.raises(DrainTimeoutError, match="running=2 waiting=3"):
            wait_until_drained(
                fetch_metrics=lambda: metrics,
                timeout_seconds=1,
                poll_interval_seconds=0,
                monotonic_values=iter([0.0, 1.1]),
                sleep=lambda _: None,
            )


class TestServiceManager:
    """サービス操作は開始後の準備確認と停止前の排出確認を必須にする。"""

    def test_start_waits_for_all_four_replicas_to_be_ready(self) -> None:
        """一括開始はsystemd起動だけで成功扱いにせず4台の準備完了を確認する。"""
        commands: list[list[str]] = []
        preflighted: list[int] = []
        probed: list[int] = []
        manager = ServiceManager(
            run_command=lambda command: commands.append(command),
            start_preflight=lambda spec: preflighted.append(spec.slot),
            health_probe=lambda spec: (
                probed.append(spec.slot)
                or HealthResult(spec=spec, healthy=True, detail="ready")
            ),
        )

        manager.start_all()

        assert commands == [
            ["systemctl", "--user", "start", "gemma4-vllm.target"]
        ]
        assert preflighted == [0, 1, 2, 3]
        assert probed == [0, 1, 2, 3]

    def test_start_preflight_failure_does_not_start_any_service(self) -> None:
        """1枠でも事前検査に失敗したらtargetを起動せず直ちに失敗する。"""
        commands: list[list[str]] = []
        manager = ServiceManager(
            run_command=lambda command: commands.append(command),
            start_preflight=lambda spec: (
                (_ for _ in ()).throw(RuntimeError("GPU busy"))
                if spec.slot == 1
                else None
            ),
        )

        with pytest.raises(RuntimeError, match="GPU busy"):
            manager.start_all()

        assert commands == []

    def test_stop_drains_every_active_replica_before_stopping_target(self) -> None:
        """一括停止は監視を休止し、4台の要求排出後にtargetを停止して監視を戻す。"""
        commands: list[list[str]] = []
        drained: list[int] = []
        manager = ServiceManager(
            run_command=lambda command: commands.append(command),
            health_probe=lambda spec: HealthResult(
                spec=spec, healthy=True, detail="ready"
            ),
            drain_replica=lambda spec, _: drained.append(spec.slot),
        )

        manager.stop_all(drain_timeout_seconds=30)

        assert drained == [0, 1, 2, 3]
        assert commands == [
            [
                "systemctl",
                "--user",
                "stop",
                "gemma4-vllm-monitor.timer",
                "gemma4-vllm-monitor.service",
            ],
            ["systemctl", "--user", "stop", "gemma4-vllm.target"],
            ["systemctl", "--user", "start", "gemma4-vllm-monitor.timer"],
        ]

    def test_stop_restores_monitor_when_drain_fails(self) -> None:
        """要求排出が失敗してpoolを維持するときも、休止した死活監視を必ず戻す。"""
        commands: list[list[str]] = []
        manager = ServiceManager(
            run_command=lambda command: commands.append(command),
            drain_replica=lambda *_: (_ for _ in ()).throw(
                DrainTimeoutError("still busy")
            ),
        )

        with pytest.raises(DrainTimeoutError, match="still busy"):
            manager.stop_all(drain_timeout_seconds=30)

        assert ["systemctl", "--user", "stop", "gemma4-vllm.target"] not in commands
        assert commands[-1] == [
            "systemctl",
            "--user",
            "start",
            "gemma4-vllm-monitor.timer",
        ]


class TestSystemdUnits:
    """配布用systemd定義が端末非依存・異常時再起動・一括停止を備える。"""

    def test_rendered_units_have_no_placeholders_and_reference_current_paths(
        self, tmp_path: Path
    ) -> None:
        """導入時にリポジトリとvLLM環境の絶対パスが定義へ固定される。"""
        template_dir = Path("ops/systemd/user")
        output_dir = tmp_path / "systemd"

        rendered = render_systemd_units(
            template_dir=template_dir,
            output_dir=output_dir,
            repo_root=Path("/work/llm-rpg"),
            vllm_root=Path("/models/gemma4-vllm"),
        )

        assert rendered
        service = (output_dir / "gemma4-vllm@.service").read_text(encoding="utf-8")
        assert "@REPO_ROOT@" not in service
        assert "@VLLM_ROOT@" not in service
        assert "/work/llm-rpg/scripts/manage_gemma4_vllm.py" in service
        assert "GEMMA4_VLLM_ROOT=/models/gemma4-vllm" in service
        assert "Restart=on-failure" in service
        assert "KillMode=control-group" in service

    def test_target_groups_exactly_four_replicas(self, tmp_path: Path) -> None:
        """一括targetはGPU 0〜3の4サービスだけを起動対象にする。"""
        output_dir = tmp_path / "systemd"
        render_systemd_units(
            template_dir=Path("ops/systemd/user"),
            output_dir=output_dir,
            repo_root=Path("/work/llm-rpg"),
            vllm_root=Path("/models/gemma4-vllm"),
        )

        target = (output_dir / "gemma4-vllm.target").read_text(encoding="utf-8")
        assert (
            "Wants=gemma4-vllm@0.service gemma4-vllm@1.service "
            "gemma4-vllm@2.service gemma4-vllm@3.service"
        ) in target

    def test_rendered_units_pass_systemd_verification(self, tmp_path: Path) -> None:
        """導入後の4定義はsystemd自身の構文・依存関係検査を通過する。"""
        analyzer = shutil.which("systemd-analyze")
        if analyzer is None:
            pytest.skip("systemd-analyze is not installed")
        output_dir = tmp_path / "systemd"
        paths = render_systemd_units(
            template_dir=Path("ops/systemd/user"),
            output_dir=output_dir,
            repo_root=Path("/work/llm-rpg"),
            vllm_root=Path("/models/gemma4-vllm"),
        )

        result = subprocess.run(
            [analyzer, "--user", "verify", *(str(path) for path in paths)],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr


class TestHealthMonitor:
    """一時的な起動遅延では再起動せず、連続した死活失敗だけを復旧する。"""

    def test_replica_restarts_only_after_three_consecutive_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同じ稼働中レプリカが3回連続で失敗した時点で一度だけ再起動する。"""
        commands: list[list[str]] = []
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.setattr(manager_module, "_service_is_active", lambda _: True)
        monkeypatch.setattr(
            manager_module,
            "probe_replica_health",
            lambda spec: HealthResult(
                spec=spec, healthy=False, detail="health timeout"
            ),
        )
        monkeypatch.setattr(
            manager_module, "_run_command", lambda command: commands.append(command)
        )

        first = manager_module.monitor_active_replicas(restart_after=3)
        second = manager_module.monitor_active_replicas(restart_after=3)
        third = manager_module.monitor_active_replicas(restart_after=3)

        assert all(event["event"] == "health_failed" for event in first)
        assert all(event["event"] == "health_failed" for event in second)
        assert all(event["event"] == "health_restart" for event in third)
        assert commands == [
            ["systemctl", "--user", "restart", f"gemma4-vllm@{slot}.service"]
            for slot in range(4)
        ]
