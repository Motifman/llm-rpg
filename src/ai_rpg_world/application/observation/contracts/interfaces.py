"""観測まわりのポート（インターフェース）"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

__all__ = [
    "IPlayerAudienceQueryPort",
    "IWorldObjectToPlayerResolver",
    "IRecipientResolutionStrategy",
    "IObservationRecipientResolver",
    "IObservationFormatter",
    "IObservationContextBuffer",
]


class IWorldObjectToPlayerResolver(ABC):
    """WorldObjectId に紐づくプレイヤーIDを解決するポート（観測配信先解決で利用）"""

    @abstractmethod
    def resolve_player_id(self, object_id: WorldObjectId) -> Optional[PlayerId]:
        """WorldObjectId に紐づくプレイヤーIDを返す。プレイヤーでなければ None。"""
        pass


class IRecipientResolutionStrategy(ABC):
    """イベント型ごとの配信先解決戦略。Resolver が supports が True の先頭戦略に委譲する。"""

    @abstractmethod
    def supports(self, event: Any) -> bool:
        """このイベントを扱うかどうか。"""
        pass

    @abstractmethod
    def resolve(self, event: Any) -> List[PlayerId]:
        """配信先プレイヤーIDのリストを返す（重複含み可。Resolver が重複除去する）。"""
        pass


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
        attention_level: Optional[AttentionLevel] = None,
    ) -> Optional[ObservationOutput]:
        """
        指定プレイヤー向けの観測出力を生成する。
        スキップする場合は None を返す。
        attention_level に応じて FILTER_SOCIAL / IGNORE の場合は要約・スキップする。
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
