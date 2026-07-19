"""scripts/_viewer_vendor.py の単体テスト (Issue #188 Phase 1d β)。

実際のネットワーク download は行わない (mock)。SHA256 検証・キャッシュ再利用・
失敗時のエラーメッセージなど制御フローのみ検証する。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts import _viewer_vendor as vendor  # noqa: E402


def _fake_resp(data: bytes):
    """urlopen 互換のダミー context manager。"""
    class _FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return data
    return _FakeResp()


class TestFetchCytoscape:
    """fetch_cytoscape の挙動。"""

    def test_downed_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キャッシュ済みファイルは再 download しない (urlopen 呼ばれない)。"""
        monkeypatch.setenv(vendor._CACHE_DIR_ENV, str(tmp_path))
        content = b"/* cached cytoscape */"
        digest = hashlib.sha256(content).hexdigest()
        cache_file = tmp_path / f"cytoscape-{vendor.CYTOSCAPE_VERSION}.min.js"
        cache_file.write_bytes(content)

        with patch.object(
            vendor, "CYTOSCAPE_SHA256", digest
        ), patch("urllib.request.urlopen") as mock_open:
            asset = vendor.fetch_cytoscape()

        assert asset.content == content.decode("utf-8")
        mock_open.assert_not_called()

    def test_downed_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回は urlopen が呼ばれ、ファイルがキャッシュされる。"""
        monkeypatch.setenv(vendor._CACHE_DIR_ENV, str(tmp_path))
        content = b"/* downloaded cytoscape */"
        digest = hashlib.sha256(content).hexdigest()

        with patch.object(vendor, "CYTOSCAPE_SHA256", digest), patch(
            "urllib.request.urlopen", return_value=_fake_resp(content)
        ):
            asset = vendor.fetch_cytoscape()

        cache_file = tmp_path / f"cytoscape-{vendor.CYTOSCAPE_VERSION}.min.js"
        assert cache_file.exists()
        assert cache_file.read_bytes() == content
        assert asset.content == content.decode("utf-8")

    def test_sha256_matches_vendor_fetch_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """download した内容のハッシュが期待と違うと例外、キャッシュにも書かない。"""
        monkeypatch.setenv(vendor._CACHE_DIR_ENV, str(tmp_path))
        content = b"malicious payload"
        # wrong hash
        with patch.object(vendor, "CYTOSCAPE_SHA256", "0" * 64), patch(
            "urllib.request.urlopen", return_value=_fake_resp(content)
        ):
            with pytest.raises(vendor.VendorFetchError, match="SHA256 mismatch"):
                vendor.fetch_cytoscape()

        cache_file = tmp_path / f"cytoscape-{vendor.CYTOSCAPE_VERSION}.min.js"
        assert not cache_file.exists()

    def test_offline_mode_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``offline=True`` で未キャッシュなら download 試みずエラー。"""
        monkeypatch.setenv(vendor._CACHE_DIR_ENV, str(tmp_path))
        with patch("urllib.request.urlopen") as mock_open:
            with pytest.raises(vendor.VendorFetchError, match="offline"):
                vendor.fetch_cytoscape(offline=True)
        mock_open.assert_not_called()

    def test_downed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SHA 不一致のキャッシュは破棄して download し直す。"""
        monkeypatch.setenv(vendor._CACHE_DIR_ENV, str(tmp_path))
        good_content = b"/* good */"
        good_digest = hashlib.sha256(good_content).hexdigest()
        cache_file = tmp_path / f"cytoscape-{vendor.CYTOSCAPE_VERSION}.min.js"
        cache_file.write_bytes(b"corrupted")

        with patch.object(vendor, "CYTOSCAPE_SHA256", good_digest), patch(
            "urllib.request.urlopen", return_value=_fake_resp(good_content)
        ):
            asset = vendor.fetch_cytoscape()

        assert asset.content == good_content.decode("utf-8")
        assert cache_file.read_bytes() == good_content
