#!/usr/bin/env python3
"""実験成果物 (trace.jsonl + trace.html + report.md ...) を gist に publish するヘルパ。

scripts/run_scenario_experiment.py の ``--publish-gist`` から呼ばれる。
単体 CLI としても使える (既に書き出された var/runs/<name>/ を後追い publish)。

設計方針:
    - secret gist (URL を知っている人のみアクセス)
    - 1 実験 = 1 gist (履歴混在を避ける)
    - ファイル順序を表す prefix (00_, 01_, ...) をつけて GitHub UI で読みやすく
    - 終了時に htmlpreview.github.io 経由の HTML プレビュー URL を表示

前提:
    - GitHub CLI (gh) がインストール済みかつ ``gh auth status`` で認証済み
    - ``run_dir`` 配下に少なくとも 1 ファイル存在
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("publish_experiment_gist")

# GitHub UI と htmlpreview 用に明示的に順序づけるファイル名 prefix
_FILENAME_PREFIXES = {
    "summary.md": "00_summary.md",
    "report.md": "01_report.md",
    "trace.jsonl": "02_trace.jsonl",
    "trace.html": "03_trace.html",
    "scenario.json": "04_scenario.json",
    "run_info.md": "05_run_info.md",
    # PR δ (#213): build_trace_viewer.py が生成する Cytoscape inline viewer。
    # ファイル名は 06_ で並び順を後ろにし、htmlpreview ボタンとして強調する想定。
    "viewer.html": "06_viewer.html",
}


class GistPublishError(RuntimeError):
    """gist publish に失敗したとき。"""


def _prefixed_name(original: str) -> str:
    """GitHub UI で並ぶ順序を保つため prefix をつける。未知名はそのまま。"""
    return _FILENAME_PREFIXES.get(original, original)


def _collect_files(run_dir: Path) -> List[Tuple[Path, str]]:
    """publish 対象ファイルを (元 path, gist 内名前) で返す。

    既知ファイルは prefix を付与、それ以外はそのままの名前で gist に入れる。
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir not found: {run_dir}")
    if not run_dir.is_dir():
        raise NotADirectoryError(f"not a directory: {run_dir}")
    files: List[Tuple[Path, str]] = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_file():
            continue
        if child.name.startswith("."):
            continue
        files.append((child, _prefixed_name(child.name)))
    if not files:
        raise GistPublishError(f"no files to publish under {run_dir}")
    return files


def _build_gh_command(
    files: Sequence[Tuple[Path, str]],
    *,
    description: str,
    secret: bool,
) -> List[str]:
    """gh gist create の argv を組み立てる。

    1 つ目の file を positional に、残りは ``--filename`` トリックではなく
    実 path 渡しを並べる。gist 内のファイル名は実 path 名 = prefix 後の名前。
    """
    # gh gist create では各ファイルが gist 内で「そのファイル名」で見える。
    # prefix を反映するため一時 path にコピーする方が確実 (呼び出し側で
    # symlink/コピーを作って渡してもらう想定)。本関数では path をそのまま渡し、
    # 呼び出し側で staging directory に prefix 済みの名前で並べる。
    cmd: List[str] = ["gh", "gist", "create"]
    cmd.extend(["--desc", description])
    if not secret:
        cmd.append("--public")
    for path, _ in files:
        cmd.append(str(path))
    return cmd


def _stage_files(staging_dir: Path, files: Sequence[Tuple[Path, str]]) -> List[Tuple[Path, str]]:
    """gist 内で prefix 済み名前にするため staging ディレクトリにコピーする。"""
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged: List[Tuple[Path, str]] = []
    for src, gist_name in files:
        dst = staging_dir / gist_name
        dst.write_bytes(src.read_bytes())
        staged.append((dst, gist_name))
    return staged


def _run_gh(cmd: Sequence[str]) -> str:
    """gh CLI を実行し標準出力を返す。失敗時は GistPublishError。"""
    logger.debug("running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            list(cmd),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise GistPublishError(
            "gh CLI not found. Install: https://cli.github.com/"
        ) from e
    except subprocess.CalledProcessError as e:
        raise GistPublishError(
            f"gh command failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    return result.stdout.strip()


def _extract_gist_id(url: str) -> Optional[str]:
    """gh gist create の出力 URL から gist id を抜く。"""
    url = url.strip()
    if not url:
        return None
    # https://gist.github.com/<user>/<id> 形式を想定
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    candidate = parts[-1]
    if not candidate:
        return None
    return candidate


def _html_preview_url(gist_id: str, user: str, html_filename: str) -> str:
    """htmlpreview.github.io 経由のレンダリング URL を組み立てる。"""
    raw_base = f"https://gist.githubusercontent.com/{user}/{gist_id}/raw"
    return f"https://htmlpreview.github.io/?{raw_base}/{html_filename}"


def _resolve_gh_user() -> Optional[str]:
    """``gh api user`` で login 名を取得 (htmlpreview URL に必要)。失敗時は None。"""
    try:
        out = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    name = out.stdout.strip()
    return name or None


def _maybe_build_viewer(run_dir: Path) -> Optional[Path]:
    """run_dir 内に trace.jsonl があり viewer.html が無ければ build を試みる。

    PR δ (#213): publish 時に viewer.html を自動同梱する。Cytoscape 取得 (初回)
    のためのネット越し依存があるため、失敗時は警告のみで publish は続行する
    (trace.html が既にあるので可視化手段はゼロにならない)。

    Returns:
        生成 / 既存の viewer.html パス。生成できなかったら None。
    """
    viewer_path = run_dir / "viewer.html"
    trace_path = run_dir / "trace.jsonl"
    if viewer_path.exists():
        return viewer_path
    if not trace_path.exists():
        return None
    try:
        # import を関数内に閉じ込めて、build_trace_viewer 依存を publish 単体
        # ユースケース (viewer 無しの run dir) から外しておく
        from scripts.build_trace_viewer import (  # noqa: WPS433
            fetch_cytoscape,
            load_scenario_topology,
            render_viewer_html,
        )
        from ai_rpg_world.application.trace.recorder import (  # noqa: WPS433
            load_trace_events,
        )
    except Exception as e:
        logger.warning("failed to import build_trace_viewer dependencies: %s", e)
        return None
    try:
        asset = fetch_cytoscape()
    except Exception as e:
        # Cytoscape 取得 (ネット) 失敗。trace.html だけで諦める
        logger.warning(
            "skipping viewer.html build (Cytoscape fetch failed): %s", e
        )
        return None
    try:
        events = list(load_trace_events(trace_path))
        topology = load_scenario_topology(run_dir / "scenario.json")
        html_str = render_viewer_html(
            title=run_dir.name,
            events=events,
            scenario_topology=topology,
            cytoscape_js_src=asset.content,
        )
        viewer_path.write_text(html_str, encoding="utf-8")
    except Exception as e:
        logger.warning("failed to build viewer.html: %s", e)
        return None

    # Phase 3 (実験 #26 user feedback): 追加 viewer 2 種を併せて生成する。
    # 失敗しても publish は続行 (main viewer はある)。
    try:
        from scripts.build_episodic_viewer import (  # noqa: WPS433
            aggregate_episodes,
            load_events as _load_episodic_events,
        )
        from scripts.build_episodic_viewer import render_html as _render_episodic
        episodic_events = _load_episodic_events(trace_path)
        episodes = aggregate_episodes(episodic_events)
        if episodes:
            (run_dir / "episodic.html").write_text(
                _render_episodic(episodes, run_dir.name), encoding="utf-8",
            )
    except Exception as e:
        logger.warning("failed to build episodic.html: %s", e)
    try:
        from scripts.build_timeline_viewer import (  # noqa: WPS433
            load_events as _load_timeline_events,
        )
        from scripts.build_timeline_viewer import render_html as _render_timeline
        timeline_events = _load_timeline_events(trace_path)
        (run_dir / "timeline.html").write_text(
            _render_timeline(timeline_events, run_dir.name), encoding="utf-8",
        )
    except Exception as e:
        logger.warning("failed to build timeline.html: %s", e)

    return viewer_path


def publish(
    run_dir: Path,
    *,
    description: Optional[str] = None,
    secret: bool = True,
    build_viewer: bool = True,
) -> dict:
    """run_dir の中身を 1 つの gist として publish する。

    Args:
        build_viewer: True (既定) なら publish 直前に viewer.html を build (既存なら
            上書きしない)。Cytoscape を取得できない環境 (offline / 認証付き proxy 等)
            では black warning して publish は続行する。

    Returns: ``{"gist_url", "gist_id", "html_preview_url", "viewer_preview_url"}``
    """
    if build_viewer:
        _maybe_build_viewer(run_dir)

    files = _collect_files(run_dir)
    desc = description or f"llm-rpg experiment run: {run_dir.name}"

    staging = run_dir / "_gist_staging"
    try:
        staged = _stage_files(staging, files)
        cmd = _build_gh_command(staged, description=desc, secret=secret)
        gist_url = _run_gh(cmd)
    finally:
        # staging を残してもよいが、毎回掃除しておく方が事故が少ない
        if staging.exists():
            for child in staging.iterdir():
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass

    gist_id = _extract_gist_id(gist_url)
    html_files = [name for _, name in files if name.endswith(".html")]
    user = _resolve_gh_user() if gist_id and html_files else None
    # viewer.html (新 viewer) と trace.html (Mermaid 旧 viewer) を分けて URL 化
    # gist 内ファイル名は prefixed なので "06_viewer.html" / "03_trace.html" を探す
    viewer_files = [n for n in html_files if "viewer" in n]
    legacy_files = [n for n in html_files if "viewer" not in n]
    primary_html = (viewer_files or legacy_files or [None])[0]
    legacy_html = (legacy_files or [None])[0] if viewer_files else None
    html_preview_url = (
        _html_preview_url(gist_id, user, primary_html)
        if gist_id and user and primary_html
        else None
    )
    viewer_preview_url = (
        _html_preview_url(gist_id, user, viewer_files[0])
        if gist_id and user and viewer_files
        else None
    )
    legacy_preview_url = (
        _html_preview_url(gist_id, user, legacy_html)
        if gist_id and user and legacy_html
        else None
    )
    return {
        "gist_url": gist_url,
        "gist_id": gist_id,
        # 後方互換: 既存のテスト/呼び出しは html_preview_url を見る
        "html_preview_url": html_preview_url,
        # 新 viewer の URL (推奨)。viewer.html を含む gist でだけ非 None
        "viewer_preview_url": viewer_preview_url,
        # 旧 Mermaid trace.html の URL。両方ある場合に役立つ
        "legacy_preview_url": legacy_preview_url,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish an experiment run directory to a secret gist"
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Directory containing trace.jsonl / report.md / trace.html etc.",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Gist description (default: llm-rpg experiment run: <dirname>)",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Create a public gist instead of secret (default secret)",
    )
    parser.add_argument(
        "--no-build-viewer",
        action="store_true",
        help="Skip auto-building viewer.html from trace.jsonl + scenario.json",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = publish(
            args.run_dir,
            description=args.description,
            secret=not args.public,
            build_viewer=not args.no_build_viewer,
        )
    except GistPublishError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    print(f"[gist] {result['gist_url']}")
    # PR δ: viewer.html (interactive Cytoscape playback) を最優先で出す。
    # 旧 Mermaid trace.html も一緒に gist にあるなら別行で出す。
    if result.get("viewer_preview_url"):
        print(f"[viewer] {result['viewer_preview_url']}")
        if result.get("legacy_preview_url"):
            print(f"[legacy-html] {result['legacy_preview_url']}")
    elif result.get("html_preview_url"):
        print(f"[html] {result['html_preview_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
