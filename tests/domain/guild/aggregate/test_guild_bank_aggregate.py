"""GuildBankAggregate のドメインテスト。正常・例外の両方を網羅する。"""
import pytest

from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
)
from ai_rpg_world.domain.guild.exception.guild_exception import (
    InsufficientGuildBankBalanceException,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.gold import Gold


class TestGuildBankAggregate:
    """GuildBankAggregate のテスト"""

    @pytest.fixture
    def guild_id(self) -> GuildId:
        return GuildId(1)

    @pytest.fixture
    def player_id(self) -> PlayerId:
        return PlayerId(1)

    @pytest.fixture
    def bank(self, guild_id) -> GuildBankAggregate:
        return GuildBankAggregate.create_for_guild(guild_id)

    class TestCreateForGuild:
        """create_for_guild のテスト"""

        def test_create_for_guild_success(self, guild_id):
            """新規ギルド用の金庫が残高0で作成されること"""
            bank = GuildBankAggregate.create_for_guild(guild_id)
            assert bank.guild_id == guild_id
            assert bank.gold.value == 0
            assert isinstance(bank.gold, Gold)

    class TestDepositGold:
        """deposit_gold のテスト"""

        def test_deposit_gold_success(self, bank, player_id):
            """入金すると残高が増加し、イベントが発行されること"""
            bank.deposit_gold(100, player_id)
            assert bank.gold.value == 100
            events = bank.get_events()
            assert len(events) == 1
            assert isinstance(events[0], GuildBankDepositedEvent)
            assert events[0].amount == 100
            assert events[0].deposited_by == player_id

        def test_deposit_gold_multiple_times(self, bank, player_id):
            """複数回入金すると残高が累積すること"""
            bank.deposit_gold(50, player_id)
            bank.clear_events()
            bank.deposit_gold(30, player_id)
            assert bank.gold.value == 80

        def test_deposit_gold_zero_amount_raises(self, bank, player_id):
            """入金額0では ValueError が発生すること"""
            with pytest.raises(ValueError, match="Deposit amount must be positive"):
                bank.deposit_gold(0, player_id)

        def test_deposit_gold_negative_amount_raises(self, bank, player_id):
            """負の入金額では ValueError が発生すること"""
            with pytest.raises(ValueError, match="Deposit amount must be positive"):
                bank.deposit_gold(-1, player_id)

    class TestWithdrawGold:
        """withdraw_gold のテスト"""

        def test_withdraw_gold_success(self, bank, player_id):
            """出金すると残高が減少し、イベントが発行されること"""
            bank.deposit_gold(200, player_id)
            bank.clear_events()
            bank.withdraw_gold(50, player_id)
            assert bank.gold.value == 150
            events = bank.get_events()
            assert len(events) == 1
            assert isinstance(events[0], GuildBankWithdrawnEvent)
            assert events[0].amount == 50
            assert events[0].withdrawn_by == player_id

        def test_withdraw_gold_all_balance(self, bank, player_id):
            """残高全額出金できること"""
            bank.deposit_gold(100, player_id)
            bank.clear_events()
            bank.withdraw_gold(100, player_id)
            assert bank.gold.value == 0

        def test_withdraw_gold_insufficient_balance_raises(self, bank, player_id):
            """残高不足では InsufficientGuildBankBalanceException が発生すること"""
            bank.deposit_gold(50, player_id)
            with pytest.raises(InsufficientGuildBankBalanceException) as exc_info:
                bank.withdraw_gold(100, player_id)
            assert "have 50" in str(exc_info.value)
            assert "requested 100" in str(exc_info.value)

        def test_withdraw_gold_zero_balance_raises(self, bank, player_id):
            """残高0の状態で出金すると InsufficientGuildBankBalanceException が発生すること"""
            with pytest.raises(InsufficientGuildBankBalanceException):
                bank.withdraw_gold(1, player_id)

        def test_withdraw_gold_zero_amount_raises(self, bank, player_id):
            """出金額0では ValueError が発生すること"""
            bank.deposit_gold(100, player_id)
            with pytest.raises(ValueError, match="Withdraw amount must be positive"):
                bank.withdraw_gold(0, player_id)

        def test_withdraw_gold_negative_amount_raises(self, bank, player_id):
            """負の出金額では ValueError が発生すること"""
            bank.deposit_gold(100, player_id)
            with pytest.raises(ValueError, match="Withdraw amount must be positive"):
                bank.withdraw_gold(-1, player_id)
