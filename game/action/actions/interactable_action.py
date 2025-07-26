from typing import List, Dict, TYPE_CHECKING
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy
from game.player.player import Player
from game.core.game_context import GameContext

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.object.chest import Chest
    from game.object.interactable import BulletinBoard, Monument


class OpenChestResult(ActionResult):
    def __init__(self, success: bool, message: str, items_details: List[str] = None):
        super().__init__(success, message)
        self.items_details = items_details
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            items_text = '\n\t'.join(self.items_details) if self.items_details else "なし"
            return f"{player_name} は宝箱を開けてアイテムを入手しました\n\t入手したアイテム:\n\t{items_text}"
        else:
            return f"{player_name} は宝箱を開けることに失敗しました\n\t理由:{self.message}"


class OpenChestStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("宝箱を開ける")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        """利用可能なチェストの表示名を返す"""
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return []
        
        available_chests = []
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                available_chests.append(interactable.get_display_name())
        
        return available_chests
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return False
        
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                return True
        return False
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        target_chest_name = kwargs.get('chest_name', None)
        return OpenChestCommand(target_chest_name)


class OpenChestCommand(ActionCommand):
    def __init__(self, target_chest_name: str = None):
        super().__init__("宝箱を開ける")
        self.target_chest_name = target_chest_name
    
    def execute(self, acting_player: Player, game_context: GameContext) -> OpenChestResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot:
            return OpenChestResult(
                success=False,
                message="現在のスポットが見つかりません"
            )
        
        available_chests = []
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                available_chests.append(interactable)
        
        if not available_chests:
            return OpenChestResult(
                success=False,
                message="この場所に開けることができる宝箱はありません",
                items_details=[]
            )
        
        target_chest = None
        if self.target_chest_name:
            for chest in available_chests:
                if chest.get_display_name() == self.target_chest_name:
                    target_chest = chest
                    break
            
            if not target_chest:
                available_names = [chest.get_display_name() for chest in available_chests]
                return OpenChestResult(
                    success=False,
                    message=f"「{self.target_chest_name}」という名前の宝箱は見つかりません。利用可能な宝箱: {', '.join(available_names)}",
                    items_details=[]
                )
        else:
            target_chest = available_chests[0]
        
        if target_chest.is_locked:
            if not target_chest.required_item_id:
                return OpenChestResult(
                    success=False,
                    message="宝箱は鍵でロックされています",
                    items_details=[]
                )
            
            if not acting_player.has_item(target_chest.required_item_id):
                return OpenChestResult(
                    success=False,
                    message=f"宝箱を開けるには「{target_chest.required_item_id}」が必要です",
                    items_details=[]
                )
            
            target_chest.unlock()
            acting_player.remove_item(target_chest.required_item_id)
        
        items = target_chest.open()
        for item in items:
            acting_player.add_item(item)
        
        if items:
            item_details = [str(item) for item in items]
            message = f"「{target_chest.get_display_name()}」を開けてアイテムを入手しました"
        else:
            message = f"「{target_chest.get_display_name()}」を開けましたが、中は空でした"
            item_details = []
        
        return OpenChestResult(
            success=True,
            message=message,
            items_details=item_details
        )


# 掲示板関連のアクション
class WriteBulletinBoardResult(ActionResult):
    def __init__(self, success: bool, message: str, post_content: str = None):
        super().__init__(success, message)
        self.post_content = post_content
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は掲示板に投稿を書き込みました\n\t投稿内容: {self.post_content}"
        else:
            return f"{player_name} は掲示板への投稿に失敗しました\n\t理由: {self.message}"


class ReadBulletinBoardResult(ActionResult):
    def __init__(self, success: bool, message: str, posts: List[str] = None):
        super().__init__(success, message)
        self.posts = posts or []
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            if self.posts:
                posts_text = '\n\t'.join([f"{i+1}. {post}" for i, post in enumerate(self.posts)])
                return f"{player_name} は掲示板を読みました\n\t投稿一覧:\n\t{posts_text}"
            else:
                return f"{player_name} は掲示板を読みました\n\t投稿はありません"
        else:
            return f"{player_name} は掲示板の読み取りに失敗しました\n\t理由: {self.message}"


class WriteBulletinBoardStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("掲示板に書き込む")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        """利用可能な掲示板の表示名を返す"""
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return []
        
        available_boards = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                available_boards.append(interactable.get_display_name())
        
        return available_boards
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return False
        
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                return True
        return False
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        target_board_name = kwargs.get('board_name', None)
        content = kwargs.get('content', '')
        return WriteBulletinBoardCommand(target_board_name, content)


class WriteBulletinBoardCommand(ActionCommand):
    def __init__(self, target_board_name: str = None, content: str = ''):
        super().__init__("掲示板に書き込む")
        self.target_board_name = target_board_name
        self.content = content
    
    def execute(self, acting_player: Player, game_context: GameContext) -> WriteBulletinBoardResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot:
            return WriteBulletinBoardResult(
                success=False,
                message="現在のスポットが見つかりません"
            )
        
        available_boards = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                available_boards.append(interactable)
        
        if not available_boards:
            return WriteBulletinBoardResult(
                success=False,
                message="この場所に掲示板はありません"
            )
        
        target_board = None
        if self.target_board_name:
            for board in available_boards:
                if board.get_display_name() == self.target_board_name:
                    target_board = board
                    break
            
            if not target_board:
                available_names = [board.get_display_name() for board in available_boards]
                return WriteBulletinBoardResult(
                    success=False,
                    message=f"「{self.target_board_name}」という名前の掲示板は見つかりません。利用可能な掲示板: {', '.join(available_names)}"
                )
        else:
            target_board = available_boards[0]
        
        if not self.content or not self.content.strip():
            return WriteBulletinBoardResult(
                success=False,
                message="投稿内容が空です"
            )
        
        success = target_board.write_post(self.content)
        if success:
            message = f"「{target_board.get_display_name()}」に投稿を書き込みました"
            if target_board.is_full():
                message += "（古い投稿が削除されました）"
        else:
            message = "投稿の書き込みに失敗しました"
        
        return WriteBulletinBoardResult(
            success=success,
            message=message,
            post_content=self.content.strip()
        )


class ReadBulletinBoardStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("掲示板を読む")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        """利用可能な掲示板の表示名を返す"""
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return []
        
        available_boards = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                available_boards.append(interactable.get_display_name())
        
        return available_boards
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return False
        
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                return True
        return False
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        target_board_name = kwargs.get('board_name', None)
        return ReadBulletinBoardCommand(target_board_name)


class ReadBulletinBoardCommand(ActionCommand):
    def __init__(self, target_board_name: str = None):
        super().__init__("掲示板を読む")
        self.target_board_name = target_board_name
    
    def execute(self, acting_player: Player, game_context: GameContext) -> ReadBulletinBoardResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot:
            return ReadBulletinBoardResult(
                success=False,
                message="現在のスポットが見つかりません"
            )
        
        available_boards = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import BulletinBoard
            if isinstance(interactable, BulletinBoard):
                available_boards.append(interactable)
        
        if not available_boards:
            return ReadBulletinBoardResult(
                success=False,
                message="この場所に掲示板はありません"
            )
        
        target_board = None
        if self.target_board_name:
            for board in available_boards:
                if board.get_display_name() == self.target_board_name:
                    target_board = board
                    break
            
            if not target_board:
                available_names = [board.get_display_name() for board in available_boards]
                return ReadBulletinBoardResult(
                    success=False,
                    message=f"「{self.target_board_name}」という名前の掲示板は見つかりません。利用可能な掲示板: {', '.join(available_names)}"
                )
        else:
            target_board = available_boards[0]
        
        posts = target_board.read_posts()
        message = f"「{target_board.get_display_name()}」の内容を読み取りました"
        
        return ReadBulletinBoardResult(
            success=True,
            message=message,
            posts=posts
        )


# 石碑関連のアクション
class ReadMonumentResult(ActionResult):
    def __init__(self, success: bool, message: str, historical_text: str = None):
        super().__init__(success, message)
        self.historical_text = historical_text
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は石碑を読みました\n\t石碑の内容:\n\t{self.historical_text}"
        else:
            return f"{player_name} は石碑の読み取りに失敗しました\n\t理由: {self.message}"


class ReadMonumentStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("石碑を読む")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        """利用可能な石碑の表示名を返す"""
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return []
        
        available_monuments = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import Monument
            if isinstance(interactable, Monument):
                available_monuments.append(interactable.get_display_name())
        
        return available_monuments
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return False
        
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import Monument
            if isinstance(interactable, Monument):
                return True
        return False
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        target_monument_name = kwargs.get('monument_name', None)
        return ReadMonumentCommand(target_monument_name)


class ReadMonumentCommand(ActionCommand):
    def __init__(self, target_monument_name: str = None):
        super().__init__("石碑を読む")
        self.target_monument_name = target_monument_name
    
    def execute(self, acting_player: Player, game_context: GameContext) -> ReadMonumentResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot:
            return ReadMonumentResult(
                success=False,
                message="現在のスポットが見つかりません"
            )
        
        available_monuments = []
        for interactable in current_spot.get_all_interactables():
            from game.object.interactable import Monument
            if isinstance(interactable, Monument):
                available_monuments.append(interactable)
        
        if not available_monuments:
            return ReadMonumentResult(
                success=False,
                message="この場所に石碑はありません"
            )
        
        target_monument = None
        if self.target_monument_name:
            for monument in available_monuments:
                if monument.get_display_name() == self.target_monument_name:
                    target_monument = monument
                    break
            
            if not target_monument:
                available_names = [monument.get_display_name() for monument in available_monuments]
                return ReadMonumentResult(
                    success=False,
                    message=f"「{self.target_monument_name}」という名前の石碑は見つかりません。利用可能な石碑: {', '.join(available_names)}"
                )
        else:
            target_monument = available_monuments[0]
        
        historical_text = target_monument.read_historical_text()
        message = f"「{target_monument.get_display_name()}」の内容を読み取りました"
        
        return ReadMonumentResult(
            success=True,
            message=message,
            historical_text=historical_text
        )