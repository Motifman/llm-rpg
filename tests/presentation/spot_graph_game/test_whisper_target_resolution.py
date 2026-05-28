"""Issue #269 第17回 R2: whisper の target_label を空 / 名前直書き で失敗していた
パターンを resolve する挙動。

runtime_manager._resolve_whisper_target は state を持たない pure な lookup なので、
最小限の target dict + namedtuple 風オブジェクトで挙動を検証する。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _EscapeGameLlmWiring,
)


def _player_target(label: str, *, display_name: str, player_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        label=label,
        kind="spot_graph_player",
        display_name=display_name,
        player_id=player_id,
    )


def _make_targets() -> Dict[str, Any]:
    return {
        "P1": _player_target("P1", display_name="リン", player_id=2),
        "P2": _player_target("P2", display_name="カイト", player_id=1),
    }


class _Manager(_EscapeGameLlmWiring):
    """テスト用に __init__ をスキップした manager。

    ``_resolve_whisper_target`` は self を一切参照しないので、空インスタンス
    で safe に呼び出せる。
    """

    def __init__(self) -> None:  # noqa: D401
        pass


class TestResolveWhisperTarget:
    """whisper target_label の lenient 解決。"""

    def test_label_直接_でヒットする(self) -> None:
        """既存の "P1" 経路は回帰しない。"""
        m = _Manager()
        target = m._resolve_whisper_target("P1", _make_targets())
        assert target is not None
        assert target.player_id == 2

    def test_プレイヤー名直書きで解決される(self) -> None:
        """Issue #269 観察: LLM が target_label に "リン" と名前を直書き
        してくるパターンを名前 (display_name) フォールバックで吸収する。"""
        m = _Manager()
        target = m._resolve_whisper_target("リン", _make_targets())
        assert target is not None
        assert target.player_id == 2

    def test_別の名前でも対応する_player_id_に解決される(self) -> None:
        m = _Manager()
        target = m._resolve_whisper_target("カイト", _make_targets())
        assert target is not None
        assert target.player_id == 1

    def test_空文字は_None(self) -> None:
        """空 target_label は None (executor 側 / 呼び出し側で INVALID_WHISPER)。"""
        m = _Manager()
        assert m._resolve_whisper_target("", _make_targets()) is None

    def test_存在しないラベル_名前は_None(self) -> None:
        m = _Manager()
        assert m._resolve_whisper_target("存在しない人", _make_targets()) is None

    def test_候補抽出経由で_P1_括弧つきを解決できる(self) -> None:
        """\"P1 (リン)\" のような prompt 行貼り付けも吸収する。"""
        m = _Manager()
        target = m._resolve_whisper_target("P1 (リン)", _make_targets())
        assert target is not None
        assert target.player_id == 2
