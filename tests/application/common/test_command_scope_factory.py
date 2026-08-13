"""CommandScopeFactoryがcommandごとに独立したscopeを作る契約を保証する。"""

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory


class _Transaction:
    def __init__(self) -> None:
        self.is_active = False

    def begin(self) -> None:
        self.is_active = True

    def commit(self) -> None:
        self.is_active = False

    def rollback(self) -> None:
        self.is_active = False


class _TransactionFactory:
    def __init__(self) -> None:
        self.created: list[_Transaction] = []

    def create(self) -> _Transaction:
        transaction = _Transaction()
        self.created.append(transaction)
        return transaction


class _ProviderFactory:
    def create(self, context: object, transaction: object) -> object:
        return object()


class _Dispatcher:
    def dispatch(self, event: object, context: object) -> None:
        return


class _Handoff:
    def handoff(self, events: object) -> None:
        return


def test_factory_creates_fresh_transaction_for_each_scope() -> None:
    """createを2回呼ぶと異なるtransactionを持つNEW状態のscopeを返す。"""
    transaction_factory = _TransactionFactory()
    factory = CommandScopeFactory(
        transaction_factory,
        sync_dispatcher=_Dispatcher(),  # type: ignore[arg-type]
        after_commit_handoff=_Handoff(),  # type: ignore[arg-type]
        repository_provider_factory=_ProviderFactory(),  # type: ignore[arg-type]
    )

    first = factory.create()
    second = factory.create()

    assert first is not second
    assert len(transaction_factory.created) == 2
    with first:
        assert transaction_factory.created[0].is_active is True
        assert transaction_factory.created[1].is_active is False
    with second:
        assert transaction_factory.created[1].is_active is True
