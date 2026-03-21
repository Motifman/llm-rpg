"""ゲーム内 SNS モード（アプリ起動メタファ）のセッション状態。

永続化は行わずプロセス内の dict で player_id ごとに ON/OFF を保持する。
LLM ツール sns_enter / sns_logout と PlayerCurrentStateDto の is_sns_mode_active の参照点を共有する。
"""


class SnsModeSessionService:
    """SNS モード ON/OFF をセッションとして保持するアプリケーションサービス。"""

    def __init__(self) -> None:
        self._active_by_player: dict[int, bool] = {}

    def is_sns_mode_active(self, player_id: int) -> bool:
        return self._active_by_player.get(player_id, False)

    def enter_sns_mode(self, player_id: int) -> None:
        self._active_by_player[player_id] = True

    def exit_sns_mode(self, player_id: int) -> None:
        self._active_by_player[player_id] = False


__all__ = ["SnsModeSessionService"]
