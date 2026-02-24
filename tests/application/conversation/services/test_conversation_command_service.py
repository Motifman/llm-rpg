"""ConversationCommandService のテスト（正常・例外の網羅）"""
import pytest
from unittest.mock import Mock

from ai_rpg_world.application.conversation.services.conversation_command_service import (
    ConversationCommandService,
)
from ai_rpg_world.application.conversation.contracts.commands import (
    StartConversationCommand,
    AdvanceConversationCommand,
    GetCurrentNodeQuery,
)
from ai_rpg_world.application.conversation.exceptions import (
    DialogueTreeNotFoundException,
    DialogueNodeNotFoundException,
    NoActiveSessionException,
    ConversationCommandException,
    ConversationSystemErrorException,
)
from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode
from ai_rpg_world.infrastructure.repository.in_memory_dialogue_tree_repository import (
    InMemoryDialogueTreeRepository,
)


class TestConversationCommandService:
    """ConversationCommandService のテスト"""

    @pytest.fixture
    def dialogue_repo(self):
        repo = InMemoryDialogueTreeRepository()
        node0 = DialogueNode(
            node_id=0,
            text="Hello, adventurer.",
            choices=(("Next", 1),),
            next_node_id=None,
            is_terminal=False,
        )
        node1 = DialogueNode(
            node_id=1,
            text="Thanks! Here's a reward.",
            choices=(),
            next_node_id=None,
            is_terminal=True,
            reward_gold=50,
        )
        repo.register_tree(tree_id=1, entry_node_id=0, nodes={0: node0, 1: node1})
        return repo

    @pytest.fixture
    def event_publisher(self):
        pub = Mock()
        pub.publish = Mock()
        return pub

    @pytest.fixture
    def service(self, dialogue_repo, event_publisher):
        return ConversationCommandService(
            dialogue_tree_repository=dialogue_repo,
            event_publisher=event_publisher,
        )

    def test_start_conversation_success(self, service, event_publisher):
        """会話開始が成功し、セッションとイベントが発行される"""
        cmd = StartConversationCommand(
            player_id=1,
            npc_id_value=100,
            dialogue_tree_id=1,
        )
        result = service.start_conversation(cmd)
        assert result.success is True
        assert result.session is not None
        assert result.session.player_id == 1
        assert result.session.npc_id_value == 100
        assert result.session.current_node.node_id_value == 0
        assert result.session.current_node.text == "Hello, adventurer."
        assert result.session.current_node.choices == (("Next", 1),)
        assert result.session.current_node.is_terminal is False
        event_publisher.publish.assert_called_once()
        call_args = event_publisher.publish.call_args[0][0]
        assert call_args.npc_id_value == 100
        assert call_args.entry_node_id_value == 0

    def test_start_conversation_dialogue_tree_not_found(self, service):
        """存在しない dialogue_tree_id で会話開始すると例外"""
        cmd = StartConversationCommand(
            player_id=1,
            npc_id_value=100,
            dialogue_tree_id=999,
        )
        with pytest.raises(DialogueTreeNotFoundException):
            service.start_conversation(cmd)

    def test_get_current_node_returns_none_when_no_session(self, service):
        """セッションがないとき get_current_node は None"""
        query = GetCurrentNodeQuery(player_id=1, npc_id_value=100)
        assert service.get_current_node(query) is None

    def test_get_current_node_after_start_returns_session(self, service):
        """会話開始後に get_current_node で現在ノードを取得できる"""
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=1)
        )
        query = GetCurrentNodeQuery(player_id=1, npc_id_value=100)
        session = service.get_current_node(query)
        assert session is not None
        assert session.current_node.text == "Hello, adventurer."

    def test_advance_conversation_without_session_raises(self, service):
        """セッションなしで advance すると NoActiveSessionException"""
        cmd = AdvanceConversationCommand(player_id=1, npc_id_value=100)
        with pytest.raises(NoActiveSessionException):
            service.advance_conversation(cmd)

    def test_advance_conversation_by_choice_success(self, service, event_publisher):
        """選択肢で進行し、終端ノードで会話終了・報酬・イベント発行"""
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=1)
        )
        event_publisher.publish.reset_mock()
        cmd = AdvanceConversationCommand(
            player_id=1,
            npc_id_value=100,
            choice_index=0,
        )
        result = service.advance_conversation(cmd)
        assert result.success is True
        assert result.conversation_ended is True
        assert result.session is None
        assert result.rewards_claimed_gold == 50
        event_publisher.publish.assert_called_once()
        call_args = event_publisher.publish.call_args[0][0]
        assert call_args.npc_id_value == 100
        assert call_args.end_node_id_value == 1
        assert call_args.rewards_claimed_gold == 50

    def test_after_end_get_current_node_returns_none(self, service):
        """会話終了後は get_current_node が None"""
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=1)
        )
        service.advance_conversation(
            AdvanceConversationCommand(player_id=1, npc_id_value=100, choice_index=0)
        )
        assert service.get_current_node(GetCurrentNodeQuery(1, 100)) is None

    def test_advance_with_invalid_choice_index_raises(self, service):
        """無効な choice_index で ConversationCommandException"""
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=1)
        )
        with pytest.raises(ConversationCommandException):
            service.advance_conversation(
                AdvanceConversationCommand(
                    player_id=1,
                    npc_id_value=100,
                    choice_index=99,
                )
            )

    def test_advance_next_node_not_in_repository_raises_dialogue_node_not_found(
        self, dialogue_repo, event_publisher
    ):
        """選択肢の指す次ノードがリポジトリに存在しない場合 DialogueNodeNotFoundException"""
        # ノード0のみ登録し、選択肢は存在しないノード99を指す
        repo = InMemoryDialogueTreeRepository()
        node0 = DialogueNode(
            node_id=0,
            text="Choose path.",
            choices=(("To missing", 99),),
            next_node_id=None,
            is_terminal=False,
        )
        repo.register_tree(tree_id=10, entry_node_id=0, nodes={0: node0})
        service = ConversationCommandService(
            dialogue_tree_repository=repo,
            event_publisher=event_publisher,
        )
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=10)
        )
        with pytest.raises(DialogueNodeNotFoundException) as exc_info:
            service.advance_conversation(
                AdvanceConversationCommand(
                    player_id=1,
                    npc_id_value=100,
                    choice_index=0,
                )
            )
        assert "ダイアログノードが見つかりません" in str(exc_info.value)
        assert "tree_id=10" in str(exc_info.value) and "node_id=99" in str(exc_info.value)

    def test_unexpected_exception_wrapped_as_system_error(
        self, dialogue_repo, event_publisher
    ):
        """想定外の例外は ConversationSystemErrorException にラップされる"""
        original_error = RuntimeError("database connection failed")
        dialogue_repo.get_entry_node_id = Mock(side_effect=original_error)
        service = ConversationCommandService(
            dialogue_tree_repository=dialogue_repo,
            event_publisher=event_publisher,
        )
        cmd = StartConversationCommand(
            player_id=1,
            npc_id_value=100,
            dialogue_tree_id=1,
        )
        with pytest.raises(ConversationSystemErrorException) as exc_info:
            service.start_conversation(cmd)
        assert exc_info.value.original_exception is original_error


class TestConversationCommandServiceNonTerminalNoNext:
    """終端でないのに次ノードがない場合のテスト"""

    @pytest.fixture
    def dialogue_repo(self):
        repo = InMemoryDialogueTreeRepository()
        # 終端でないが next_node_id も choices もない不正なノード
        node0 = DialogueNode(
            node_id=0,
            text="Stuck.",
            choices=(),
            next_node_id=None,
            is_terminal=False,
        )
        repo.register_tree(tree_id=20, entry_node_id=0, nodes={0: node0})
        return repo

    @pytest.fixture
    def event_publisher(self):
        pub = Mock()
        pub.publish = Mock()
        return pub

    @pytest.fixture
    def service(self, dialogue_repo, event_publisher):
        return ConversationCommandService(
            dialogue_tree_repository=dialogue_repo,
            event_publisher=event_publisher,
        )

    def test_advance_non_terminal_with_no_next_raises(self, service):
        """終端ノードでないのに次ノードが無い場合 ConversationCommandException"""
        service.start_conversation(
            StartConversationCommand(player_id=1, npc_id_value=100, dialogue_tree_id=20)
        )
        with pytest.raises(ConversationCommandException) as exc_info:
            service.advance_conversation(
                AdvanceConversationCommand(player_id=1, npc_id_value=100)
            )
        assert "終端ノードでないのに次ノードがありません" in str(exc_info.value)


class TestConversationCommandServiceWithNextNode:
    """「次へ」で進むパターンのテスト"""

    @pytest.fixture
    def dialogue_repo(self):
        repo = InMemoryDialogueTreeRepository()
        node0 = DialogueNode(
            node_id=0,
            text="First.",
            choices=(),
            next_node_id=1,
            is_terminal=False,
        )
        node1 = DialogueNode(
            node_id=1,
            text="Second. Bye.",
            choices=(),
            next_node_id=None,
            is_terminal=True,
            reward_gold=10,
        )
        repo.register_tree(tree_id=2, entry_node_id=0, nodes={0: node0, 1: node1})
        return repo

    @pytest.fixture
    def event_publisher(self):
        pub = Mock()
        pub.publish = Mock()
        return pub

    @pytest.fixture
    def service(self, dialogue_repo, event_publisher):
        return ConversationCommandService(
            dialogue_tree_repository=dialogue_repo,
            event_publisher=event_publisher,
        )

    def test_advance_by_next_success(self, service, event_publisher):
        """choice_index なし（次へ）で進み、終端で終了"""
        service.start_conversation(
            StartConversationCommand(player_id=2, npc_id_value=200, dialogue_tree_id=2)
        )
        event_publisher.publish.reset_mock()
        result = service.advance_conversation(
            AdvanceConversationCommand(player_id=2, npc_id_value=200)
        )
        assert result.conversation_ended is True
        assert result.rewards_claimed_gold == 10
        event_publisher.publish.assert_called_once()
