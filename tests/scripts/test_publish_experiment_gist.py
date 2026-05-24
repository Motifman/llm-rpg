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

    def test_既知ファイル名は_prefix_付きに変換される(self) -> None:
        """summary.md → 00_summary.md など、辞書順が論理順になる。"""
        assert _prefixed_name("summary.md") == "00_summary.md"
        assert _prefixed_name("report.md") == "01_report.md"
        assert _prefixed_name("trace.jsonl") == "02_trace.jsonl"
        assert _prefixed_name("trace.html") == "03_trace.html"
        assert _prefixed_name("scenario.json") == "04_scenario.json"

    def test_未知ファイル名は変換されない(self) -> None:
        """マッピングに無い名前は素通り。"""
        assert _prefixed_name("custom.txt") == "custom.txt"


class TestCollectFiles:
    """run_dir からの publish 対象収集。"""

    def test_ファイルがなければ_GistPublishError(self, tmp_path: Path) -> None:
        """空ディレクトリは publish できない (gh がエラーになる前にここで止める)。"""
        with pytest.raises(GistPublishError, match="no files"):
            _collect_files(tmp_path)

    def test_存在しないディレクトリは_FileNotFoundError(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _collect_files(tmp_path / "missing")

    def test_隠しファイルは無視される(self, tmp_path: Path) -> None:
        """ドットファイル (.DS_Store 等) は publish 対象外。"""
        (tmp_path / ".DS_Store").write_text("x")
        (tmp_path / "report.md").write_text("# r")
        files = _collect_files(tmp_path)
        names = [name for _, name in files]
        assert "01_report.md" in names
        assert not any(n.startswith(".") for n in names)

    def test_サブディレクトリは無視される(self, tmp_path: Path) -> None:
        """flat なファイル群だけが対象 (再帰しない)。"""
        (tmp_path / "report.md").write_text("# r")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "ignored.txt").write_text("x")
        files = _collect_files(tmp_path)
        assert len(files) == 1


class TestExtractGistId:
    """gh gist create の出力 URL から id を抜く。"""

    def test_標準的な_URL_から_id_を返す(self) -> None:
        """通常の gist URL から末尾 id を取る。"""
        url = "https://gist.github.com/Motifman/abc123def456"
        assert _extract_gist_id(url) == "abc123def456"

    def test_空文字なら_None(self) -> None:
        assert _extract_gist_id("") is None

    def test_末尾スラッシュも吸収する(self) -> None:
        url = "https://gist.github.com/Motifman/abc123/"
        assert _extract_gist_id(url) == "abc123"


class TestHtmlPreviewUrl:
    """htmlpreview.github.io URL の組み立て。"""

    def test_URL_に_id_と_user_と_ファイル名が入る(self) -> None:
        """組み立てた URL からブラウザで HTML をプレビューできる形にする。"""
        url = _html_preview_url("abc123", "Motifman", "03_trace.html")
        assert "abc123" in url
        assert "Motifman" in url
        assert "03_trace.html" in url
        assert url.startswith("https://htmlpreview.github.io/?")


class TestPublishWithMock:
    """publish() の外部 gh 呼び出しをモックして end-to-end の組み立てを確認。"""

    def test_publish_は_gh_を呼び_URL_を返す(self, tmp_path: Path) -> None:
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
            result = publish(run_dir, description="t", secret=True)

        assert result["gist_url"].endswith("abc123")
        assert result["gist_id"] == "abc123"
        assert "Motifman" in result["html_preview_url"]
        assert "03_trace.html" in result["html_preview_url"]
        # staging ディレクトリは掃除されていること
        assert not (run_dir / "_gist_staging").exists()

    def test_html_が無ければ_html_preview_url_は_None(self, tmp_path: Path) -> None:
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

    def test_secret_既定で_public_フラグ_は_付かない(self, tmp_path: Path) -> None:
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

    def test_public_True_のとき_public_フラグが付く(self, tmp_path: Path) -> None:
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

    def test_gh_が_失敗したら_GistPublishError(self, tmp_path: Path) -> None:
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

    def test_gh_未インストールなら_GistPublishError(self, tmp_path: Path) -> None:
        """gh が PATH にない時は分かりやすいメッセージで止める。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "report.md").write_text("# r")

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("gh: command not found")

        with patch.object(subprocess, "run", side_effect=fake_run):
            with pytest.raises(GistPublishError, match="gh CLI not found"):
                publish(run_dir, secret=True)
