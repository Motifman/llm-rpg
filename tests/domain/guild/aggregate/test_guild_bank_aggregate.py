"""GuildBankAggregate の残高・入出金通知・拒否後の不変条件を保証する。"""
import pytest

from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
)
from ai_rpg_world.domain.guild.exception.guild_exception import (
    InsufficientGuildBankBalanceException,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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

        @pytest.mark.parametrize("guild_id", [GuildId(1), GuildId(17)])
        def test_deposit_gold_success(self, bank, player_id, guild_id):
            """入金すると残高が増え、対象ギルド・金額・入金者が一致する通知が1件発行される。"""
            bank.deposit_gold(100, player_id)
            assert bank.gold.value == 100
            events = bank.get_events()
            assert len(events) == 1
            assert isinstance(events[0], GuildBankDepositedEvent)
            assert events[0].aggregate_id == guild_id
            assert events[0].amount == 100
            assert events[0].deposited_by == player_id

        def test_deposit_gold_multiple_times(self, bank, player_id):
            """複数回入金すると残高が累積すること"""
            bank.deposit_gold(50, player_id)
            bank.clear_events()
            bank.deposit_gold(30, player_id)
            assert bank.gold.value == 80

        @pytest.mark.parametrize("initial_deposit", [0, 100])
        def test_deposit_gold_zero_amount_raises(self, bank, player_id, initial_deposit):
            """入金額0は ValueError で拒否され、残高と未発行通知は空・非空のどちらでも変わらない。"""
            if initial_deposit:
                bank.deposit_gold(initial_deposit, player_id)
            gold_before = bank.gold
            events_before = bank.get_events()
            with pytest.raises(ValueError, match="Deposit amount must be positive"):
                bank.deposit_gold(0, player_id)
            assert bank.gold == gold_before
            assert bank.get_events() == events_before

        @pytest.mark.parametrize("initial_deposit", [0, 100])
        def test_deposit_gold_negative_amount_raises(self, bank, player_id, initial_deposit):
            """負の入金額は ValueError で拒否され、残高と未発行通知は空・非空のどちらでも変わらない。"""
            if initial_deposit:
                bank.deposit_gold(initial_deposit, player_id)
            gold_before = bank.gold
            events_before = bank.get_events()
            with pytest.raises(ValueError, match="Deposit amount must be positive"):
                bank.deposit_gold(-1, player_id)
            assert bank.gold == gold_before
            assert bank.get_events() == events_before

    class TestWithdrawGold:
        """withdraw_gold のテスト"""

        @pytest.mark.parametrize("guild_id", [GuildId(1), GuildId(17)])
        def test_withdraw_gold_success(self, bank, player_id, guild_id):
            """出金すると残高が減り、対象ギルド・金額・出金者が一致する通知が1件発行される。"""
            bank.deposit_gold(200, player_id)
            bank.clear_events()
            bank.withdraw_gold(50, player_id)
            assert bank.gold.value == 150
            events = bank.get_events()
            assert len(events) == 1
            assert isinstance(events[0], GuildBankWithdrawnEvent)
            assert events[0].aggregate_id == guild_id
            assert events[0].amount == 50
            assert events[0].withdrawn_by == player_id

        def test_withdraw_gold_all_balance(self, bank, player_id):
            """残高全額出金できること"""
            bank.deposit_gold(100, player_id)
            bank.clear_events()
            bank.withdraw_gold(100, player_id)
            assert bank.gold.value == 0

        def test_withdraw_gold_insufficient_balance_raises(self, bank, player_id):
            """残高不足は現在額と要求額を示す専用例外で拒否され、残高と未発行通知は変わらない。"""
            bank.deposit_gold(50, player_id)
            gold_before = bank.gold
            events_before = bank.get_events()
            with pytest.raises(InsufficientGuildBankBalanceException) as exc_info:
                bank.withdraw_gold(100, player_id)
            assert "have 50" in str(exc_info.value)
            assert "requested 100" in str(exc_info.value)
            assert bank.gold == gold_before
            assert bank.get_events() == events_before

        @pytest.mark.parametrize("with_history", [False, True])
        def test_withdraw_gold_zero_balance_raises(self, bank, player_id, with_history):
            """残高0からの出金は専用例外で拒否され、取引履歴の有無によらず残高と未発行通知を保つ。"""
            if with_history:
                bank.deposit_gold(50, player_id)
                bank.withdraw_gold(50, player_id)
            events_before = bank.get_events()
            with pytest.raises(InsufficientGuildBankBalanceException):
                bank.withdraw_gold(1, player_id)
            assert bank.gold.value == 0
            assert bank.get_events() == events_before

        def test_withdraw_gold_zero_amount_raises(self, bank, player_id):
            """出金額0は ValueError で拒否され、残高100と既存の入金通知は変わらない。"""
            bank.deposit_gold(100, player_id)
            gold_before = bank.gold
            events_before = bank.get_events()
            with pytest.raises(ValueError, match="Withdraw amount must be positive"):
                bank.withdraw_gold(0, player_id)
            assert bank.gold == gold_before
            assert bank.get_events() == events_before

        def test_withdraw_gold_negative_amount_raises(self, bank, player_id):
            """負の出金額は ValueError で拒否され、残高100と既存の入金通知は変わらない。"""
            bank.deposit_gold(100, player_id)
            gold_before = bank.gold
            events_before = bank.get_events()
            with pytest.raises(ValueError, match="Withdraw amount must be positive"):
                bank.withdraw_gold(-1, player_id)
            assert bank.gold == gold_before
            assert bank.get_events() == events_before
