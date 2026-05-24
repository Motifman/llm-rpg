"""trace viewer 用の外部 JS ベンダーの取得・キャッシュ・検証 (Issue #188 Phase 1d β)。

trace viewer は外部 CDN を参照しない単一 HTML として配布したい
(htmlpreview.github.io が CDN をブロックする問題を避けるため)。
そのため Cytoscape.js の中身を HTML に **inline 埋め込み** する。

本モジュールは:
    1. ユーザーキャッシュ (``~/.cache/llm-rpg-viewer/``) に vendor ファイルがあるか確認
    2. なければ pin した URL から download
    3. SHA256 をハードコード値と照合 (供給チェーン攻撃対策)
    4. 内容を str で返す

設計判断:
    - vendor ファイルは git にコミットしない (バイナリ近い、~400KB)
    - 初回 build 時のみ download 発生。以後はキャッシュ
    - SHA256 不一致なら即エラー (silent な脆弱性導入を防ぐ)
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# 採用バージョン: 3.30.4 (2024-11 リリースの安定版、Mermaid と違って CDN 経由
# のロード問題は無いが念のため pin)。
CYTOSCAPE_VERSION = "3.30.4"
CYTOSCAPE_URL = (
    f"https://unpkg.com/cytoscape@{CYTOSCAPE_VERSION}/dist/cytoscape.min.js"
)
# 公式 unpkg の minified を一度手動で取得し、検証した SHA256。
# 更新時は新しい値を手で確認して上書きする。
CYTOSCAPE_SHA256 = "1bb5340e549511e111b31e5684872c949ad33d40ea5dba0ad8e7d90c62c7b3b9"

_CACHE_DIR_ENV = "LLM_RPG_VIEWER_VENDOR_CACHE"
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "llm-rpg-viewer"


class VendorFetchError(RuntimeError):
    """vendor 取得 / 検証失敗。"""


@dataclass(frozen=True)
class VendorAsset:
    """1 つの inline 対象 JS の取得済みデータ。"""

    name: str
    version: str
    content: str
    sha256: str


def cache_dir() -> Path:
    """vendor キャッシュ用のディレクトリパス (環境変数で override 可)。"""
    override = os.environ.get(_CACHE_DIR_ENV)
    if override:
        return Path(override)
    return _DEFAULT_CACHE_DIR


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_or_download(
    *,
    cache_path: Path,
    url: str,
    expected_sha256: str,
    timeout: float = 30.0,
) -> bytes:
    """キャッシュにあれば読む、無ければダウンロードしてキャッシュへ保存。

    どちらの経路でも SHA256 を ``expected_sha256`` と照合する。
    """
    if cache_path.exists():
        data = cache_path.read_bytes()
        if _sha256_hex(data) == expected_sha256:
            return data
        # ハッシュが合わない → 破損 or 古いキャッシュ。捨てて落とし直す
        logger.warning(
            "cached vendor file %s has unexpected SHA256, re-downloading",
            cache_path,
        )
        try:
            cache_path.unlink()
        except OSError:
            pass

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading vendor: %s", url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except Exception as e:
        raise VendorFetchError(
            f"failed to download vendor from {url}: {e}\n"
            f"manual fallback: download the file with curl/wget and place at {cache_path}"
        ) from e

    actual = _sha256_hex(data)
    if actual != expected_sha256:
        # 不一致なら絶対に書き込まない (供給チェーン攻撃の可能性)
        raise VendorFetchError(
            f"SHA256 mismatch for {url}\n"
            f"  expected: {expected_sha256}\n"
            f"  actual:   {actual}\n"
            f"If you intentionally upgraded the version, update CYTOSCAPE_SHA256 in "
            f"scripts/_viewer_vendor.py after verifying the source."
        )

    cache_path.write_bytes(data)
    return data


def fetch_cytoscape(*, offline: bool = False) -> VendorAsset:
    """Cytoscape.js minified を取得 (キャッシュ + SHA256 検証)。

    Args:
        offline: True にすると download を試みず、キャッシュにあれば返す、
            なければ ``VendorFetchError``。CI 環境などネットアクセス禁止用。
    """
    cache_path = cache_dir() / f"cytoscape-{CYTOSCAPE_VERSION}.min.js"
    if offline and not cache_path.exists():
        raise VendorFetchError(
            f"offline mode: vendor not cached at {cache_path}. "
            f"Run once online to populate the cache."
        )
    data = _read_or_download(
        cache_path=cache_path,
        url=CYTOSCAPE_URL,
        expected_sha256=CYTOSCAPE_SHA256,
    )
    return VendorAsset(
        name="cytoscape",
        version=CYTOSCAPE_VERSION,
        content=data.decode("utf-8"),
        sha256=CYTOSCAPE_SHA256,
    )


__all__ = [
    "CYTOSCAPE_VERSION",
    "CYTOSCAPE_URL",
    "CYTOSCAPE_SHA256",
    "VendorAsset",
    "VendorFetchError",
    "cache_dir",
    "fetch_cytoscape",
]
