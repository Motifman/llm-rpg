"""協力アクションの準備状態を管理するレジストリ。

ターン制ゲームでの「準備→実行」パターンを実現する。
エージェントAが PREPARE_ACTION で準備 → worldフラグに記録 →
エージェントBの INTERACT 条件(PREPARED_ACTION)でフラグをチェック。

フラグ形式: ``prepared:{action_id}:{player_id}``
"""

from __future__ import annotations

from typing import FrozenSet

from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState


class PreparedActionRegistry:
    """worldフラグベースの準備アクション管理。"""

    FLAG_PREFIX = "prepared:"

    def __init__(self, world_flag_state: MutableWorldFlagState) -> None:
        self._world_flag_state = world_flag_state

    def prepare(self, player_id: int, action_id: str) -> str:
        """準備アクションを登録し、セットしたフラグ名を返す。

        Raises:
            ValueError: action_id が空またはコロンを含む場合。
        """
        if not action_id.strip():
            raise ValueError("action_id cannot be empty")
        if ":" in action_id:
            raise ValueError("action_id must not contain ':' (used as flag delimiter)")
        flag = self._make_flag(action_id, player_id)
        self._world_flag_state.add(flag)
        return flag

    def cancel(self, player_id: int, action_id: str) -> None:
        """準備アクションをキャンセルする。"""
        flag = self._make_flag(action_id, player_id)
        self._world_flag_state.remove(flag)

    def cancel_all_for_player(self, player_id: int) -> None:
        """指定プレイヤーの全準備アクションをキャンセルする。"""
        prefix = self.FLAG_PREFIX
        suffix = f":{player_id}"
        to_remove = [
            f for f in self._world_flag_state.as_frozen_set()
            if f.startswith(prefix) and f.endswith(suffix)
        ]
        for flag in to_remove:
            self._world_flag_state.remove(flag)

    def consume(self, action_id: str) -> int | None:
        """準備済みアクションを消費し、準備したplayer_idを返す。なければNone。"""
        prefix = f"{self.FLAG_PREFIX}{action_id}:"
        for flag in self._world_flag_state.as_frozen_set():
            if flag.startswith(prefix):
                player_id_str = flag[len(prefix):]
                try:
                    player_id = int(player_id_str)
                    self._world_flag_state.remove(flag)
                    return player_id
                except ValueError:
                    continue
        return None

    @classmethod
    def is_prepared(cls, action_id: str, world_flags: FrozenSet[str]) -> bool:
        """準備済みかどうかをフラグセットから判定する（静的チェック）。"""
        prefix = f"{cls.FLAG_PREFIX}{action_id}:"
        return any(f.startswith(prefix) for f in world_flags)

    @staticmethod
    def _make_flag(action_id: str, player_id: int) -> str:
        return f"prepared:{action_id}:{player_id}"
