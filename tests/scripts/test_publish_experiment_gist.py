"""scripts/publish_experiment_gist.py の挙動テスト (Issue #188 Phase 1d publish)。

gh CLI 実行は ``subprocess.run`` をモックして外部依存なしで検証する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.publish_experiment_gist import (  # noqa: E402
    GistPublishError,
    _collect_files,
    _extract_gist_id,
    _html_preview_url,
    _prefixed_name,
    publish,
)


class TestPrefixedName:
    """既知ファイル名は GitHub UI 並び順用 prefix が付く。"""

    def test_file_prefix(self) -> None:
        """summary.md → 00_summary.md など、辞書順が論理順になる。"""
        assert _prefixed_name("summary.md") == "00_summary.md"
        assert _prefixed_name("report.md") == "01_report.md"
        assert _prefixed_name("trace.jsonl") == "02_trace.jsonl"
        assert _prefixed_name("trace.html") == "03_trace.html"
        assert _prefixed_name("scenario.json") == "04_scenario.json"

    def test_unknown_file(self) -> None:
        """マッピングに無い名前は素通り。"""
        assert _prefixed_name("custom.txt") == "custom.txt"


class TestCollectFiles:
    """run_dir からの publish 対象収集。"""

    def test_file_gist_publish_error(self, tmp_path: Path) -> None:
        """空ディレクトリは publish できない (gh がエラーになる前にここで止める)。"""
        with pytest.raises(GistPublishError, match="no files"):
            _collect_files(tmp_path)

    def test_missing_raises_file_not_found_error(self, tmp_path: Path) -> None:
        """存在しないディレクトリは FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            _collect_files(tmp_path / "missing")

    def test_file(self, tmp_path: Path) -> None:
        """ドットファイル (.DS_Store 等) は publish 対象外。"""
        (tmp_path / ".DS_Store").write_text("x")
        (tmp_path / "report.md").write_text("# r")
        files = _collect_files(tmp_path)
        names = [name for _, name in files]
        assert "01_report.md" in names
        assert not any(n.startswith(".") for n in names)

    def test_directory(self, tmp_path: Path) -> None:
        """flat なファイル群だけが対象 (再帰しない)。"""
        (tmp_path / "report.md").write_text("# r")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "ignored.txt").write_text("x")
        files = _collect_files(tmp_path)
        assert len(files) == 1


class TestExtractGistId:
    """gh gist create の出力 URL から id を抜く。"""

    def test_returns_url_id(self) -> None:
        """通常の gist URL から末尾 id を取る。"""
        url = "https://gist.github.com/Motifman/abc123def456"
        assert _extract_gist_id(url) == "abc123def456"

    def test_empty_string_none(self) -> None:
        """空文字なら None。"""
        assert _extract_gist_id("") is None

    def test_last(self) -> None:
        """末尾スラッシュも吸収する。"""
        url = "https://gist.github.com/Motifman/abc123/"
        assert _extract_gist_id(url) == "abc123"


class TestHtmlPreviewUrl:
    """htmlpreview.github.io URL の組み立て。"""

    def test_url_id_user_file(self) -> None:
        """組み立てた URL からブラウザで HTML をプレビューできる形にする。"""
        url = _html_preview_url("abc123", "Motifman", "03_trace.html")
        assert "abc123" in url
        assert "Motifman" in url
        assert "03_trace.html" in url
        assert url.startswith("https://htmlpreview.github.io/?")


class TestPublishWithMock:
    """publish() の外部 gh 呼び出しをモックして end-to-end の組み立てを確認。"""

    def test_returns_publish_gh_url(self, tmp_path: Path) -> None:
        """gh gist create / gh api user の両方が呼ばれ結果が返る。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "trace.jsonl").write_text('{"k":1}\n')
        (run_dir / "trace.html").write_text("<html></html>")

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/abc123\n"
                stub.stderr = ""
            elif cmd[:2] == ["gh", "api"]:
                stub.stdout = "Motifman\n"
                stub.stderr = ""
            else:
                raise AssertionError(f"unexpected cmd: {cmd}")
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = publish(run_dir, description="t", secret=True, build_viewer=False)

        assert result["gist_url"].endswith("abc123")
        assert result["gist_id"] == "abc123"
        assert "Motifman" in result["html_preview_url"]
        assert "03_trace.html" in result["html_preview_url"]
        # staging ディレクトリは掃除されていること
        assert not (run_dir / "_gist_staging").exists()

    def test_html_preview_url_none(self, tmp_path: Path) -> None:
        """HTML ファイルが run_dir に無い場合は html_preview_url キーが None。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/no-html\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = publish(run_dir, secret=True)

        assert result["html_preview_url"] is None

    def test_secret_default_public(self, tmp_path: Path) -> None:
        """secret=True (既定) のとき --public が cmd に出ない。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        captured: list = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stdout = "https://gist.github.com/u/x\n"
            stub.stderr = ""
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            publish(run_dir, secret=True)

        # 最初の gh コマンドが gist create で --public が無いこと
        create_cmd = next(c for c in captured if c[:3] == ["gh", "gist", "create"])
        assert "--public" not in create_cmd

    def test_public_true_public(self, tmp_path: Path) -> None:
        """secret=False (公開) のとき --public フラグが追加される。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        captured: list = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stdout = "https://gist.github.com/u/x\n"
            stub.stderr = ""
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            publish(run_dir, secret=False)

        create_cmd = next(c for c in captured if c[:3] == ["gh", "gist", "create"])
        assert "--public" in create_cmd

    def test_gh_failure_gist_publish_error(self, tmp_path: Path) -> None:
        """gh CLI が非 0 終了したら GistPublishError に詰めて投げる。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, stderr="auth required"
            )

        with patch.object(subprocess, "run", side_effect=fake_run):
            with pytest.raises(GistPublishError, match="gh command failed"):
                publish(run_dir, secret=True)

    def test_gh_gist_publish_error(self, tmp_path: Path) -> None:
        """gh が PATH にない時は分かりやすいメッセージで止める。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("gh: command not found")

        with patch.object(subprocess, "run", side_effect=fake_run):
            with pytest.raises(GistPublishError, match="gh CLI not found"):
                publish(run_dir, secret=True)


class TestViewerIntegration:
    """PR δ: viewer.html 同梱機構。"""

    def test_returns_viewer_html_viewer_preview_url(self, tmp_path: Path) -> None:
        """run_dir に viewer.html があれば gist に含まれ、viewer URL が出る。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "viewer.html").write_text("<html>viewer</html>")
        (run_dir / "trace.html").write_text("<html>trace</html>")

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/xyz\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            # build_viewer=False: 既存 viewer.html を使う (再 build しない)
            result = publish(run_dir, secret=True, build_viewer=False)

        assert "06_viewer.html" in result["viewer_preview_url"]
        # 旧 trace.html も legacy として参照可能
        assert "03_trace.html" in result["legacy_preview_url"]
        # 後方互換: html_preview_url は viewer (primary) を指す
        assert "06_viewer.html" in result["html_preview_url"]

    def test_viewer_html_legacy_none(self, tmp_path: Path) -> None:
        """viewer.html のみで trace.html (Mermaid 版) が無い場合、legacy は None。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "viewer.html").write_text("<html>viewer</html>")

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/y\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = publish(run_dir, secret=True, build_viewer=False)

        assert result["viewer_preview_url"] is not None
        assert "06_viewer.html" in result["viewer_preview_url"]
        assert result["legacy_preview_url"] is None

    def test_missing_viewer_and_trace_html_return_none_paths(self, tmp_path: Path) -> None:
        """HTML 1 つも無ければ viewer / legacy / html すべて None。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/z\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = publish(run_dir, secret=True, build_viewer=False)

        assert result["viewer_preview_url"] is None
        assert result["legacy_preview_url"] is None
        assert result["html_preview_url"] is None


class TestEpisodicTimelinePreviewUrls:
    """``#404`` 後続: episodic.html / timeline.html の htmlpreview wrap URL。

    旧実装ではこれらが publish 結果に含まれず、ユーザは gist 上の raw URL を
    直接踏んで text/plain 表示でソースコードが見えてしまっていた
    (実験 #29 OFF feedback)。
    """

    def _fake_run(self, gist_url: str):
        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = f"{gist_url}\n"
            else:
                stub.stdout = "Motifman\n"
            return stub
        return fake_run

    def test_returns_episodic_html_episodic_preview_url(
        self, tmp_path: Path
    ) -> None:
        """episodichtml があれば episodicpreviewurl が返る。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "viewer.html").write_text("<html>v</html>")
        (run_dir / "episodic.html").write_text("<html>ep</html>")

        with patch.object(
            subprocess, "run",
            side_effect=self._fake_run("https://gist.github.com/Motifman/aaa"),
        ):
            result = publish(run_dir, secret=True, build_viewer=False)

        assert result["episodic_preview_url"] is not None
        assert "htmlpreview.github.io" in result["episodic_preview_url"]
        assert "episodic.html" in result["episodic_preview_url"]

    def test_returns_timeline_html_timeline_preview_url(
        self, tmp_path: Path
    ) -> None:
        """timelinehtml があれば timelinepreviewurl が返る。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "viewer.html").write_text("<html>v</html>")
        (run_dir / "timeline.html").write_text("<html>tl</html>")

        with patch.object(
            subprocess, "run",
            side_effect=self._fake_run("https://gist.github.com/Motifman/bbb"),
        ):
            result = publish(run_dir, secret=True, build_viewer=False)

        assert result["timeline_preview_url"] is not None
        assert "htmlpreview.github.io" in result["timeline_preview_url"]
        assert "timeline.html" in result["timeline_preview_url"]

    def test_episodic_timeline_none(self, tmp_path: Path) -> None:
        """gist 内に該当 HTML が無ければ None (壊れない後方互換)。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        (run_dir / "viewer.html").write_text("<html>v</html>")

        with patch.object(
            subprocess, "run",
            side_effect=self._fake_run("https://gist.github.com/Motifman/ccc"),
        ):
            result = publish(run_dir, secret=True, build_viewer=False)

        assert result["episodic_preview_url"] is None
        assert result["timeline_preview_url"] is None

    def test_build_viewer_true_trace_jsonl_viewer(
        self, tmp_path: Path
    ) -> None:
        """build_viewer=True かつ trace.jsonl があれば publish 前に viewer.html を build。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        # trace.jsonl だけ用意 (viewer.html は未生成)
        from ai_rpg_world.application.trace.recorder import JsonlTraceRecorder
        from ai_rpg_world.application.trace.events import TraceEventKind

        with JsonlTraceRecorder(run_dir / "trace.jsonl") as rec:
            rec.record(TraceEventKind.RUN_START)
            rec.record(TraceEventKind.RUN_END, outcome="WIN")

        # build_trace_viewer.fetch_cytoscape をモック
        from scripts._viewer_vendor import VendorAsset
        fake_asset = VendorAsset(
            name="cytoscape",
            version="0.0.0-test",
            content="/* fake */ var cytoscape = function() {};",
            sha256="0" * 64,
        )

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/built\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        from scripts import build_trace_viewer

        with patch.object(build_trace_viewer, "fetch_cytoscape", return_value=fake_asset):
            with patch.object(subprocess, "run", side_effect=fake_run):
                result = publish(run_dir, secret=True, build_viewer=True)

        assert (run_dir / "viewer.html").exists()
        assert "06_viewer.html" in result["viewer_preview_url"]

    def test_build_viewer_true_cytoscape_failure_publish_line(
        self, tmp_path: Path
    ) -> None:
        """ネット越し取得が失敗しても publish 全体は止まらない (trace.html の代替がある想定)。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")
        from ai_rpg_world.application.trace.recorder import JsonlTraceRecorder
        from ai_rpg_world.application.trace.events import TraceEventKind

        with JsonlTraceRecorder(run_dir / "trace.jsonl") as rec:
            rec.record(TraceEventKind.RUN_START)

        from scripts._viewer_vendor import VendorFetchError

        def fake_run(cmd, **kwargs):
            stub = subprocess.CompletedProcess(args=cmd, returncode=0)
            stub.stderr = ""
            if cmd[:3] == ["gh", "gist", "create"]:
                stub.stdout = "https://gist.github.com/Motifman/noffer\n"
            else:
                stub.stdout = "Motifman\n"
            return stub

        from scripts import build_trace_viewer

        def raise_fetch(*a, **kw):
            raise VendorFetchError("offline")

        with patch.object(build_trace_viewer, "fetch_cytoscape", side_effect=raise_fetch):
            with patch.object(subprocess, "run", side_effect=fake_run):
                result = publish(run_dir, secret=True, build_viewer=True)

        # publish は成功 (gist URL がある)、viewer は生成されなかった
        assert result["gist_url"].endswith("noffer")
        assert not (run_dir / "viewer.html").exists()
        assert result["viewer_preview_url"] is None
