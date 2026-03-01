"""観測まわりのポート（インターフェース）"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class IObservationRecipientResolver(ABC):
    """イベントから観測の配信先プレイヤーID一覧を解決するポート"""

    @abstractmethod
    def resolve(self, event: Any) -> List[PlayerId]:
        """イベントに応じた配信先プレイヤーIDのリストを返す。観測対象外なら空リスト。"""
        pass


class IObservationFormatter(ABC):
    """イベント＋配信先を観測テキスト（プローズ＋構造化）に変換するポート"""

    @abstractmethod
    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[str] = None,
    ) -> Optional[ObservationOutput]:
        """
        指定プレイヤー向けの観測出力を生成する。
        スキップする場合は None を返す。
        attention_level は将来の注意レベル（FULL / FILTER_SOCIAL / IGNORE）用。現状は未使用可。
        """
        pass


class IObservationContextBuffer(ABC):
    """プレイヤーごとの観測を蓄積・取得するポート"""

    @abstractmethod
    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        """指定プレイヤーの観測を1件追加する。"""
        pass

    @abstractmethod
    def get_observations(self, player_id: PlayerId) -> List[ObservationEntry]:
        """指定プレイヤーの蓄積済み観測一覧を返す（順序保持）。"""
        pass

    @abstractmethod
    def drain(self, player_id: PlayerId) -> List[ObservationEntry]:
        """指定プレイヤーの観測を取得し、バッファから削除する。"""
        pass
