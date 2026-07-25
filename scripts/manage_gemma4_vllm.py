#!/usr/bin/env python3
"""Gemma 4 vLLM 4レプリカのsystemd常駐・死活監視・安全停止を管理する。

このスクリプトは標準ライブラリだけで動作する。systemdから直接呼ばれるため、
ゲーム本体の仮想環境やimport状態に依存させない。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence


_SLOT_COUNT = 4
_BASE_PORT = 8100
_SERVED_MODEL_NAME = "gemma-4-31b-it"
_TARGET_UNIT = "gemma4-vllm.target"
_SERVICE_UNIT_PATTERN = "gemma4-vllm@{slot}.service"
_SYSTEMD_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1] / "ops" / "systemd" / "user"
)
_DEFAULT_VLLM_ROOT = Path.home() / "gemma4-vllm"
_METRIC_NAMES = (
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
)


class DrainTimeoutError(RuntimeError):
    """要求が残ったまま安全停止の待ち時間を超えた。"""


@dataclass(frozen=True)
class ReplicaSpec:
    """1つのvLLMレプリカに割り当てるGPUとHTTPポート。"""

    slot: int
    gpu_id: int
    port: int

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def api_base(self) -> str:
        return f"{self.origin}/v1"

    @property
    def service_unit(self) -> str:
        return _SERVICE_UNIT_PATTERN.format(slot=self.slot)


@dataclass(frozen=True)
class ReplicaLoad:
    """安全停止判定に使うvLLMの要求数。"""

    running: int
    waiting: int

    @property
    def is_drained(self) -> bool:
        return self.running == 0 and self.waiting == 0


@dataclass(frozen=True)
class HealthResult:
    """1レプリカのsystemd状態とHTTP死活確認結果。"""

    spec: ReplicaSpec
    healthy: bool
    detail: str
    service_active: Optional[bool] = None
    load: Optional[ReplicaLoad] = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "slot": self.spec.slot,
            "gpu_id": self.spec.gpu_id,
            "port": self.spec.port,
            "api_base": self.spec.api_base,
            "healthy": self.healthy,
            "detail": self.detail,
        }
        if self.service_active is not None:
            payload["service_active"] = self.service_active
        if self.load is not None:
            payload["running_requests"] = self.load.running
            payload["waiting_requests"] = self.load.waiting
        return payload


def replica_spec(slot: int) -> ReplicaSpec:
    """GPU枠番号を検証し、GPU番号と専用ポートへ解決する。"""
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or not 0 <= slot < _SLOT_COUNT
    ):
        raise ValueError(f"slot must be in 0..{_SLOT_COUNT - 1}, got {slot!r}")
    return ReplicaSpec(slot=slot, gpu_id=slot, port=_BASE_PORT + slot)


def all_replica_specs() -> tuple[ReplicaSpec, ...]:
    """固定した4レプリカを順序付きで返す。"""
    return tuple(replica_spec(slot) for slot in range(_SLOT_COUNT))


_METRIC_RE = re.compile(
    r"^(?P<name>vllm:num_requests_(?:running|waiting))(?:\{[^}]*\})?\s+"
    r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*$"
)


def parse_vllm_metrics(text: str) -> ReplicaLoad:
    """Prometheus形式から実行中・待機中要求数を抽出する。

    指標欠落を0と解釈すると、壊れたサーバーを「排出完了」と誤認して停止する。
    そのため両指標が存在しない応答は失敗させる。
    """
    values: dict[str, float] = {name: 0.0 for name in _METRIC_NAMES}
    seen: set[str] = set()
    for raw_line in text.splitlines():
        match = _METRIC_RE.match(raw_line.strip())
        if match is None:
            continue
        name = match.group("name")
        values[name] += float(match.group("value"))
        seen.add(name)
    missing = [name for name in _METRIC_NAMES if name not in seen]
    if missing:
        raise ValueError(f"required vLLM metrics are missing: {missing}")
    return ReplicaLoad(
        running=int(values["vllm:num_requests_running"]),
        waiting=int(values["vllm:num_requests_waiting"]),
    )


def _http_get(url: str, *, timeout_seconds: float) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "llm-rpg-gemma4-service-manager/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        return body.decode("utf-8", errors="replace")


def fetch_replica_metrics(
    spec: ReplicaSpec, *, timeout_seconds: float = 5.0
) -> ReplicaLoad:
    """1レプリカの要求数メトリクスを取得する。"""
    return parse_vllm_metrics(
        _http_get(f"{spec.origin}/metrics", timeout_seconds=timeout_seconds)
    )


def probe_replica_health(
    spec: ReplicaSpec, *, timeout_seconds: float = 5.0
) -> HealthResult:
    """HTTP死活確認と提供モデル名の一致を確認する。"""
    try:
        _http_get(f"{spec.origin}/health", timeout_seconds=timeout_seconds)
        models_text = _http_get(
            f"{spec.api_base}/models", timeout_seconds=timeout_seconds
        )
        models = json.loads(models_text)
        model_ids = {
            item.get("id")
            for item in models.get("data", [])
            if isinstance(item, dict)
        }
        if _SERVED_MODEL_NAME not in model_ids:
            return HealthResult(
                spec=spec,
                healthy=False,
                detail=(
                    f"served model {_SERVED_MODEL_NAME!r} is missing: "
                    f"{sorted(str(value) for value in model_ids)}"
                ),
            )
        return HealthResult(spec=spec, healthy=True, detail="ready")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return HealthResult(
            spec=spec,
            healthy=False,
            detail=f"{type(exc).__name__}: {exc}",
        )


def wait_for_replica_ready(
    spec: ReplicaSpec,
    *,
    timeout_seconds: float = 900.0,
    poll_interval_seconds: float = 5.0,
    probe: Callable[[ReplicaSpec], HealthResult] = probe_replica_health,
) -> HealthResult:
    """モデル読み込みとコンパイルが終わり、要求を受けられるまで待つ。"""
    deadline = time.monotonic() + timeout_seconds
    last = HealthResult(spec=spec, healthy=False, detail="not probed")
    while True:
        last = probe(spec)
        if last.healthy:
            return last
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"replica slot={spec.slot} was not ready within "
                f"{timeout_seconds:.1f}s: {last.detail}"
            )
        time.sleep(poll_interval_seconds)


def wait_until_drained(
    *,
    fetch_metrics: Callable[[], str],
    timeout_seconds: float,
    poll_interval_seconds: float = 2.0,
    monotonic_values: Optional[Iterator[float]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ReplicaLoad:
    """実行中・待機中要求が0になるまで待つ。

    ``monotonic_values`` は決定論的な単体試験用。実運用では指定しない。
    """
    clock = monotonic_values if monotonic_values is not None else _monotonic_iterator()
    start = next(clock)
    while True:
        load = parse_vllm_metrics(fetch_metrics())
        if load.is_drained:
            return load
        now = next(clock)
        if now - start >= timeout_seconds:
            raise DrainTimeoutError(
                "vLLM drain timed out: "
                f"running={load.running} waiting={load.waiting} "
                f"timeout={timeout_seconds:.1f}s"
            )
        sleep(poll_interval_seconds)


def _monotonic_iterator() -> Iterator[float]:
    while True:
        yield time.monotonic()


def drain_replica(spec: ReplicaSpec, timeout_seconds: float) -> ReplicaLoad:
    """1レプリカの要求がなくなるまで待つ。"""
    return wait_until_drained(
        fetch_metrics=lambda: _http_get(
            f"{spec.origin}/metrics", timeout_seconds=5.0
        ),
        timeout_seconds=timeout_seconds,
    )


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _service_is_active(spec: ReplicaSpec) -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", spec.service_unit],
        check=False,
    )
    return result.returncode == 0


class ServiceManager:
    """4レプリカのsystemd操作に準備確認と安全停止を付加する。"""

    def __init__(
        self,
        *,
        run_command: Callable[[list[str]], None] = _run_command,
        start_preflight: Callable[[ReplicaSpec], None] = lambda _: None,
        health_probe: Callable[[ReplicaSpec], HealthResult] = wait_for_replica_ready,
        drain_replica: Callable[[ReplicaSpec, float], object] = drain_replica,
        service_is_active: Callable[[ReplicaSpec], bool] = lambda _: True,
    ) -> None:
        self._run_command = run_command
        self._start_preflight = start_preflight
        self._health_probe = health_probe
        self._drain_replica = drain_replica
        self._service_is_active = service_is_active

    def start_all(self) -> list[HealthResult]:
        """4サービスを開始し、全レプリカの準備完了後に成功を返す。"""
        for spec in all_replica_specs():
            self._start_preflight(spec)
        self._run_command(["systemctl", "--user", "start", _TARGET_UNIT])
        results = [self._health_probe(spec) for spec in all_replica_specs()]
        unhealthy = [result for result in results if not result.healthy]
        if unhealthy:
            detail = "; ".join(
                f"slot={result.spec.slot}: {result.detail}" for result in unhealthy
            )
            raise RuntimeError(f"Gemma 4 pool started but is not healthy: {detail}")
        return results

    def stop_all(self, *, drain_timeout_seconds: float) -> None:
        """監視を休止し、稼働中レプリカの要求を排出してから停止する。"""
        self._run_command(
            [
                "systemctl",
                "--user",
                "stop",
                "gemma4-vllm-monitor.timer",
                "gemma4-vllm-monitor.service",
            ]
        )
        try:
            for spec in all_replica_specs():
                if self._service_is_active(spec):
                    self._drain_replica(spec, drain_timeout_seconds)
            self._run_command(["systemctl", "--user", "stop", _TARGET_UNIT])
        finally:
            self._run_command(
                ["systemctl", "--user", "start", "gemma4-vllm-monitor.timer"]
            )


def render_systemd_units(
    *,
    template_dir: Path,
    output_dir: Path,
    repo_root: Path,
    vllm_root: Path,
) -> list[Path]:
    """systemdテンプレートへ現在の絶対パスを埋め込み、ユーザー領域へ出力する。"""
    if not template_dir.is_dir():
        raise FileNotFoundError(f"systemd template directory not found: {template_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        "@REPO_ROOT@": str(repo_root.resolve()),
        "@VLLM_ROOT@": str(vllm_root.resolve()),
    }
    rendered: list[Path] = []
    for source in sorted(template_dir.iterdir()):
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        for marker, value in replacements.items():
            text = text.replace(marker, value)
        unresolved = re.findall(r"@[A-Z_]+@", text)
        if unresolved:
            raise ValueError(f"unresolved placeholders in {source}: {unresolved}")
        destination = output_dir / source.name
        destination.write_text(text, encoding="utf-8")
        rendered.append(destination)
    return rendered


def install_units(*, vllm_root: Path, enable_monitor: bool) -> list[Path]:
    """ユーザーsystemd領域へ定義を導入し、必要なら監視タイマーを有効化する。"""
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = Path.home() / ".config" / "systemd" / "user"
    rendered = render_systemd_units(
        template_dir=_SYSTEMD_TEMPLATE_DIR,
        output_dir=output_dir,
        repo_root=repo_root,
        vllm_root=vllm_root,
    )
    _run_command(["systemctl", "--user", "daemon-reload"])
    if enable_monitor:
        _run_command(
            [
                "systemctl",
                "--user",
                "enable",
                "--now",
                "gemma4-vllm-monitor.timer",
            ]
        )
    return rendered


def _query_gpu_compute_apps(spec: ReplicaSpec) -> str:
    result = subprocess.run(
        [
            "nvidia-smi",
            f"--id={spec.gpu_id}",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def ensure_gpu_is_idle(
    spec: ReplicaSpec,
    *,
    query_compute_apps: Callable[[ReplicaSpec], str] = _query_gpu_compute_apps,
) -> None:
    """対象GPUに既存の計算プロセスがないことを起動前に保証する。"""
    processes = [
        line.strip()
        for line in query_compute_apps(spec).splitlines()
        if line.strip()
    ]
    if processes:
        detail = "; ".join(processes)
        raise RuntimeError(
            f"GPU {spec.gpu_id} is already used by compute processes "
            f"(pid, process_name, used_memory MiB): {detail}"
        )


def _validate_serve_prerequisites(spec: ReplicaSpec, vllm_root: Path) -> Path:
    launcher = vllm_root / "scripts" / "serve_qat_w4a16_replica.sh"
    vllm_binary = vllm_root / "vllm-upstream" / ".venv-fa4" / "bin" / "vllm"
    if not launcher.is_file():
        raise FileNotFoundError(f"replica launcher not found: {launcher}")
    if not os.access(launcher, os.X_OK):
        raise PermissionError(f"replica launcher is not executable: {launcher}")
    if not vllm_binary.is_file():
        raise FileNotFoundError(f"pinned vLLM binary not found: {vllm_binary}")
    if shutil.which("nvidia-smi") is None:
        raise FileNotFoundError("nvidia-smi is not available")
    ensure_gpu_is_idle(spec)
    if _port_is_open(spec.port):
        raise RuntimeError(
            f"port {spec.port} is already in use before starting slot={spec.slot}"
        )
    return launcher


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def serve_replica(slot: int, *, vllm_root: Path) -> None:
    """systemdのメインプロセスとして指定GPUのvLLMへ置き換わる。"""
    spec = replica_spec(slot)
    launcher = _validate_serve_prerequisites(spec, vllm_root)
    environment = os.environ.copy()
    environment.update(
        {
            "GPU_ID": str(spec.gpu_id),
            "PORT": str(spec.port),
            "HOST": "127.0.0.1",
            "VLLM_ROOT": str(vllm_root / "vllm-upstream"),
        }
    )
    os.execve(str(launcher), [str(launcher)], environment)


def service_statuses() -> list[HealthResult]:
    """systemd状態、HTTP死活、現在要求数を4レプリカ分返す。"""
    results: list[HealthResult] = []
    for spec in all_replica_specs():
        active = _service_is_active(spec)
        if not active:
            results.append(
                HealthResult(
                    spec=spec,
                    healthy=False,
                    detail="service inactive",
                    service_active=False,
                )
            )
            continue
        health = probe_replica_health(spec)
        load: Optional[ReplicaLoad] = None
        detail = health.detail
        if health.healthy:
            try:
                load = fetch_replica_metrics(spec)
            except (OSError, ValueError) as exc:
                detail = f"health ready but metrics failed: {type(exc).__name__}: {exc}"
        results.append(
            HealthResult(
                spec=spec,
                healthy=health.healthy and load is not None,
                detail=detail,
                service_active=True,
                load=load,
            )
        )
    return results


def _monitor_state_dir() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(runtime_dir) if runtime_dir else Path(f"/run/user/{os.getuid()}")
    return root / "gemma4-vllm-monitor"


def monitor_active_replicas(*, restart_after: int) -> list[dict[str, object]]:
    """連続死活失敗を数え、閾値到達時だけ該当レプリカを再起動する。"""
    if restart_after <= 0:
        raise ValueError("restart_after must be greater than 0")
    state_dir = _monitor_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, object]] = []
    for spec in all_replica_specs():
        counter_path = state_dir / f"slot-{spec.slot}.failures"
        if not _service_is_active(spec):
            counter_path.unlink(missing_ok=True)
            events.append(
                {"event": "health_skip", "slot": spec.slot, "reason": "inactive"}
            )
            continue
        result = probe_replica_health(spec)
        if result.healthy:
            counter_path.unlink(missing_ok=True)
            events.append({"event": "health_ok", "slot": spec.slot})
            continue
        failures = _read_failure_count(counter_path) + 1
        counter_path.write_text(f"{failures}\n", encoding="utf-8")
        event: dict[str, object] = {
            "event": "health_failed",
            "slot": spec.slot,
            "failures": failures,
            "detail": result.detail,
        }
        if failures >= restart_after:
            _run_command(
                ["systemctl", "--user", "restart", spec.service_unit]
            )
            counter_path.unlink(missing_ok=True)
            event["event"] = "health_restart"
        events.append(event)
    return events


def _read_failure_count(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gemma 4 vLLM 4レプリカのユーザーsystemdサービスを管理する。"
    )
    parser.add_argument(
        "--vllm-root",
        type=Path,
        default=Path(os.environ.get("GEMMA4_VLLM_ROOT", _DEFAULT_VLLM_ROOT)),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="ユーザーsystemd定義を導入する")
    install.add_argument("--no-enable-monitor", action="store_true")

    subparsers.add_parser("start", help="4レプリカを開始し準備完了まで待つ")
    stop = subparsers.add_parser("stop", help="要求排出後に4レプリカを停止する")
    stop.add_argument("--drain-timeout", type=float, default=600.0)
    subparsers.add_parser("status", help="4レプリカの状態をJSONで表示する")

    serve = subparsers.add_parser("serve-replica", help=argparse.SUPPRESS)
    serve.add_argument("--slot", type=int, required=True)
    ready = subparsers.add_parser("wait-ready", help=argparse.SUPPRESS)
    ready.add_argument("--slot", type=int, required=True)
    ready.add_argument("--timeout", type=float, default=900.0)
    monitor = subparsers.add_parser("monitor", help=argparse.SUPPRESS)
    monitor.add_argument("--restart-after", type=int, default=3)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "install":
            paths = install_units(
                vllm_root=args.vllm_root,
                enable_monitor=not args.no_enable_monitor,
            )
            _print_json(
                {
                    "event": "systemd_units_installed",
                    "paths": [str(path) for path in paths],
                    "monitor_enabled": not args.no_enable_monitor,
                }
            )
            return 0
        if args.command == "serve-replica":
            serve_replica(args.slot, vllm_root=args.vllm_root)
            return 0
        if args.command == "wait-ready":
            result = wait_for_replica_ready(
                replica_spec(args.slot), timeout_seconds=args.timeout
            )
            _print_json({"event": "replica_ready", **result.to_dict()})
            return 0
        if args.command == "monitor":
            for event in monitor_active_replicas(
                restart_after=args.restart_after
            ):
                _print_json(event)
            return 0
        if args.command == "status":
            results = service_statuses()
            _print_json(
                {
                    "event": "pool_status",
                    "healthy": all(result.healthy for result in results),
                    "replicas": [result.to_dict() for result in results],
                }
            )
            return 0 if all(result.healthy for result in results) else 1

        manager = ServiceManager(
            start_preflight=lambda spec: _validate_serve_prerequisites(
                spec, args.vllm_root
            ),
            service_is_active=_service_is_active,
        )
        if args.command == "start":
            results = manager.start_all()
            _print_json(
                {
                    "event": "pool_ready",
                    "replicas": [result.to_dict() for result in results],
                }
            )
            return 0
        if args.command == "stop":
            manager.stop_all(drain_timeout_seconds=args.drain_timeout)
            _print_json({"event": "pool_stopped"})
            return 0
    except (
        DrainTimeoutError,
        FileNotFoundError,
        PermissionError,
        RuntimeError,
        TimeoutError,
        subprocess.CalledProcessError,
        urllib.error.URLError,
        ValueError,
    ) as exc:
        _print_json(
            {
                "event": "operation_failed",
                "command": args.command,
                "error_type": type(exc).__name__,
                "detail": str(exc),
            }
        )
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
