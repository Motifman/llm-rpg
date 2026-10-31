"""BeingProvisioningService — プレイヤーを動かす Being を用意する application service。

## 責務

- プレイヤーを動かしている Being がいれば何もしない (= idempotent)
- いなければ、決定論的な BeingId の Being を作るか、既にある Being を移して、このプレイヤーを動かさせる
- 誰がどのプレイヤーを動かしているかは、ゲームの側の対応表 (``PlayerBeings``) に書く (#1928、design_decisions D1928)

## 決定論的 BeingId 命名

``f"being_w{world_id.value}_p{player_id.value}"`` を仮の命名規約として使う。
run を跨いで同じ player_id が出てきたら同じ BeingId に決まる (= 永続化と再開で identity が連続する)。

## 人柄

新しく作る Being の人柄は ``persona`` で渡す。起動時はシナリオのプレイヤーの名前から作って渡す
(design_decisions D1469-1)。渡されなければ名前だけを ``agent_{player_id}`` にし、一人称などは決めない。

## Thread safety

本 service は単一スレッドの LLM ターン実行を前提とする。並行 ``ensure_attached``
は race するので、必要なら呼び出し側で lock を取ること。
"""

from __future__ import annotations

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingProvisioningService:
    """``player_beings`` の世界のプレイヤーに、Being を用意する idempotent な service。"""

    def __init__(self, being_repository: BeingRepository, player_beings: PlayerBeings) -> None:
        if not isinstance(being_repository, BeingRepository):
            raise TypeError(f"being_repository must be BeingRepository, got {type(being_repository).__name__}")
        if not isinstance(player_beings, PlayerBeings):
            raise TypeError(f"player_beings must be PlayerBeings, got {type(player_beings).__name__}")
        self._repo = being_repository
        self._player_beings = player_beings

    @property
    def default_world_id(self) -> WorldId:
        return self._player_beings.world_id

    def ensure_attached(self, player_id: PlayerId, *, persona: Persona | None = None) -> BeingId:
        """プレイヤーを動かす Being がいることを保証し、その ID を返す。

        - 対応表にもう Being がいれば、その ID を返す
        - いなければ ``being_w{world}_p{player}`` の Being を、無ければ作り、あれば (ほかのプレイヤーを動かしていても)
          このプレイヤーに移して動かさせる (``Being.move_to``、``PlayerBeings.drive``)
        - ``persona`` は新しく作るときだけ使う。既にある Being の人柄は変えない
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError(f"player_id must be PlayerId, got {type(player_id).__name__}")
        if persona is not None and not isinstance(persona, Persona):
            raise TypeError(f"persona must be Persona or None, got {type(persona).__name__}")

        driving = self._player_beings.being_of(player_id)
        if driving is not None:
            return driving

        world_id = self._player_beings.world_id
        being_id = self._derive_being_id(world_id, player_id)
        attachment = BeingAttachment(world_id=world_id.value, player_id=player_id.value)
        # find_by_id は毎回新しいインスタンスを返すので、変えたら必ず save する。
        being = self._repo.find_by_id(being_id)
        if being is None:
            being = Being(
                being_id=being_id,
                persona=persona or Persona(name=f"agent_{player_id.value}"),
                attachment=attachment,
            )
        else:
            being.move_to(attachment)
        self._player_beings.drive(player_id, being_id)
        self._repo.save(being)
        return being_id

    @staticmethod
    def _derive_being_id(world_id: WorldId, player_id: PlayerId) -> BeingId:
        """決定論的 BeingId 命名規約 (= ``being_w<world>_p<player>``)。"""
        return BeingId(f"being_w{world_id.value}_p{player_id.value}")


__all__ = ["BeingProvisioningService"]
