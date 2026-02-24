"""ギルド金庫集約（GuildId と 1:1）。Phase 5 で金庫（ゴールド）を管理。倉庫（アイテム）は将来拡張。"""
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.guild.exception.guild_exception import (
    InsufficientGuildBankBalanceException,
)


class GuildBankAggregate(AggregateRoot):
    """ギルド金庫集約（GuildId に 1:1）。残高は Gold 値オブジェクトで表現する。"""

    def __init__(self, guild_id: GuildId, gold: Gold):
        super().__init__()
        self._guild_id = guild_id
        self._gold = gold

    @classmethod
    def create_for_guild(cls, guild_id: GuildId) -> "GuildBankAggregate":
        """新規ギルド用の金庫を作成（残高 0）"""
        return cls(guild_id=guild_id, gold=Gold.create(0))

    @property
    def guild_id(self) -> GuildId:
        return self._guild_id

    @property
    def gold(self) -> Gold:
        return self._gold

    def deposit_gold(self, amount: int, deposited_by: PlayerId) -> None:
        """金庫に入金する。権限チェックはアプリ層で行う。"""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self._gold = self._gold.add(amount)
        self.add_event(
            GuildBankDepositedEvent.create(
                aggregate_id=self._guild_id,
                aggregate_type="GuildBankAggregate",
                amount=amount,
                deposited_by=deposited_by,
            )
        )

    def withdraw_gold(self, amount: int, withdrawn_by: PlayerId) -> None:
        """金庫から出金する。権限チェックはアプリ層で行う。"""
        if amount <= 0:
            raise ValueError("Withdraw amount must be positive")
        if not self._gold.can_subtract(amount):
            raise InsufficientGuildBankBalanceException(
                f"Insufficient guild bank balance: have {self._gold.value}, requested {amount}"
            )
        self._gold = self._gold.subtract(amount)
        self.add_event(
            GuildBankWithdrawnEvent.create(
                aggregate_id=self._guild_id,
                aggregate_type="GuildBankAggregate",
                amount=amount,
                withdrawn_by=withdrawn_by,
            )
        )
