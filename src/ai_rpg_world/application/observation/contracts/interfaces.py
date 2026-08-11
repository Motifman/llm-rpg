"""観測まわりのポート（インターフェース）

## ``ToolRuntimeContextDto`` を実行時に import しない理由

このファイルは観測層の **入口の型定義** で、``application.llm`` の実装より内側に
ある。にもかかわらず ``ToolRuntimeContextDto`` を実行時に import すると、
``application/llm/__init__.py`` が services 一式を読み込み、そこから
``prompt_builder_config`` 経由でこのファイルへ戻ってくる循環になる。

    observation/contracts/interfaces.py
      → llm/contracts/dtos → llm/__init__.py → llm/services/prompt_builder.py
        → llm/services/prompt_builder_config.py → ここへ戻る

結果、**観測層だけを単独で import できなかった**。フルスイートでは import 順が
揃って隠れるので、``pytest tests/application/observation`` が 1 件も走らない状態が
長く残っていた。

この名前は型注釈にしか使わないので ``TYPE_CHECKING`` 下へ移し、注釈は
``from __future__ import annotations`` で遅延評価にする。実行時に評価する箇所は
無い (``get_type_hints`` の利用はリポジトリ全体で 0 件)。

依存の向き自体を直す (この DTO を中立な場所へ移す / ``llm/__init__.py`` が
services を再輸出するのをやめる) 方が筋は通るが、影響範囲が広いので分けた。
``tests/application/observation/test_modules_import_standalone.py`` が、
戻ってきたら落とす。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)

if TYPE_CHECKING:  # pragma: no cover - 型検査時のみ
    from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
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
    def append(
        self,
        player_id: PlayerId,
        entry: ObservationEntry,
        *,
        runtime_context: Optional[ToolRuntimeContextDto] = None,
    ) -> None:
        """指定プレイヤーの観測を1件追加する。

        runtime_context は観測時点の ToolRuntime 断片。trace 記録のみが利用し、
        既定の in-memory バッファ実装は無視する。
        """
        pass

    @abstractmethod
    def get_observations(self, player_id: PlayerId) -> List[ObservationEntry]:
        """指定プレイヤーの蓄積済み観測一覧を返す（順序保持）。"""
        pass

    @abstractmethod
    def drain(self, player_id: PlayerId) -> List[ObservationEntry]:
        """指定プレイヤーの観測を取得し、バッファから削除する。"""
        pass
