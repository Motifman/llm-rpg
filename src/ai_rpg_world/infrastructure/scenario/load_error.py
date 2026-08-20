"""シナリオ読み込みエラー。"""

from __future__ import annotations
SUPPORTED_FORMAT_VERSIONS = ("1.0",)


class ScenarioLoadError(Exception):
    """シナリオ読み込み中のエラー。"""
