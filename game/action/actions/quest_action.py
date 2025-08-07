from typing import List, Optional, Dict
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.quest.quest_manager import QuestSystem
from game.quest.guild import AdventurerGuild
from game.quest.quest_data import Quest
from game.enums import QuestDifficulty


class QuestGetGuildListResult(ActionResult):
    def __init__(self, success: bool, message: str, guilds: List[Dict]):
        super().__init__(success, message)
        self.guilds = guilds
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            guild_info = []
            for guild in self.guilds:
                guild_info.append(f"ID: {guild['guild_id']}, 名前: {guild['name']}, 所在地: {guild['location']}")
            guilds_text = '\n'.join(guild_info)
            return f"{player_name} はギルド一覧を取得しました\n{guilds_text}"
        else:
            return f"{player_name} はギルド一覧を取得できませんでした\n理由:{self.message}"


class QuestCreateMonsterHuntResult(ActionResult):
    def __init__(self, success: bool, message: str, quest_id: str = None):
        super().__init__(success, message)
        self.quest_id = quest_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はモンスター討伐クエストを作成しました\nクエストID: {self.quest_id}"
        else:
            return f"{player_name} はモンスター討伐クエストを作成できませんでした\n理由:{self.message}"


class QuestCreateItemCollectionResult(ActionResult):
    def __init__(self, success: bool, message: str, quest_id: str = None):
        super().__init__(success, message)
        self.quest_id = quest_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はアイテム収集クエストを作成しました\nクエストID: {self.quest_id}"
        else:
            return f"{player_name} はアイテム収集クエストを作成できませんでした\n理由:{self.message}"


class QuestCreateExplorationResult(ActionResult):
    def __init__(self, success: bool, message: str, quest_id: str = None):
        super().__init__(success, message)
        self.quest_id = quest_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は探索クエストを作成しました\nクエストID: {self.quest_id}"
        else:
            return f"{player_name} は探索クエストを作成できませんでした\n理由:{self.message}"


class QuestGetAvailableQuestsResult(ActionResult):
    def __init__(self, success: bool, message: str, quests: List[Dict]):
        super().__init__(success, message)
        self.quests = quests
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            if not self.quests:
                return f"{player_name} は利用可能なクエストを確認しました\n\t利用可能なクエストはありません"
            quest_info = []
            for quest in self.quests:
                quest_info.append(f"ID: {quest['quest_id']}, 名前: {quest['name']}, 報酬: {quest['reward_money']}G")
            quests_text = '\n'.join(quest_info)
            return f"{player_name} は利用可能なクエストを取得しました\n{quests_text}"
        else:
            return f"{player_name} は利用可能なクエストを取得できませんでした\n理由:{self.message}"


class QuestAcceptQuestResult(ActionResult):
    def __init__(self, success: bool, message: str, quest_id: str):
        super().__init__(success, message)
        self.quest_id = quest_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はクエストを受注しました\n\tクエストID: {self.quest_id}"
        else:
            return f"{player_name} はクエストを受注できませんでした\n\t理由:{self.message}"


class QuestGetActiveQuestResult(ActionResult):
    def __init__(self, success: bool, message: str, active_quest: Optional[Dict]):
        super().__init__(success, message)
        self.active_quest = active_quest
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            if self.active_quest:
                quest_info = f"ID: {self.active_quest['quest_id']}, 名前: {self.active_quest['name']}, 進捗: {self.active_quest['progress']}"
                return f"{player_name} はアクティブなクエストを取得しました\n\t{quest_info}"
            else:
                return f"{player_name} はアクティブなクエストを確認しました\n\tアクティブなクエストはありません"
        else:
            return f"{player_name} はアクティブなクエストを取得できませんでした\n\t理由:{self.message}"


class QuestGetGuildListStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("ギルド一覧確認")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return QuestGetGuildListCommand()


class QuestGetGuildListCommand(ActionCommand):
    def __init__(self):
        super().__init__("ギルド一覧確認")

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestGetGuildListResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestGetGuildListResult(False, "QuestSystemが利用できません", [])
        
        try:
            guilds = quest_system.get_all_guilds()
            guild_list = []
            for guild in guilds:
                guild_list.append({
                    'guild_id': guild.guild_id,
                    'name': guild.name,
                    'location': guild.location_spot_id
                })
            return QuestGetGuildListResult(True, f"{len(guild_list)}個のギルドを取得しました", guild_list)
        except Exception as e:
            return QuestGetGuildListResult(False, f"ギルド一覧の取得に失敗しました: {e}", [])


class QuestCreateMonsterHuntStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("モンスタークエスト依頼")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="guild_id",
                description="クエストを依頼するギルドIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="name",
                description="クエスト名を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="description",
                description="クエストの説明を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="monster_id",
                description="討伐対象のモンスターIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="monster_count",
                description="討伐数を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="difficulty",
                description="クエストの危険度を選択してください",
                candidates=["E", "D", "C", "B", "A", "S"]
            ),
            ArgumentInfo(
                name="reward_money",
                description="報酬金額を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="deadline_hours",
                description="期限（時間）を入力してください（デフォルト: 72時間）",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None

    def build_action_command(self, acting_player: Player, game_context: GameContext, guild_id: str, name: str, description: str, monster_id: str, monster_count: str, difficulty: str, reward_money: str, deadline_hours: str = "72") -> ActionCommand:
        try:
            monster_count_int = int(monster_count)
            reward_money_int = int(reward_money)
            deadline_hours_int = int(deadline_hours)
            difficulty_enum = QuestDifficulty(difficulty)
        except ValueError:
            # デフォルト値を使用
            monster_count_int = 1
            reward_money_int = 100
            deadline_hours_int = 72
            difficulty_enum = QuestDifficulty.E
        
        return QuestCreateMonsterHuntCommand(guild_id, name, description, monster_id, monster_count_int, difficulty_enum, reward_money_int, deadline_hours_int)


class QuestCreateMonsterHuntCommand(ActionCommand):
    def __init__(self, guild_id: str, name: str, description: str, monster_id: str, monster_count: int, difficulty: QuestDifficulty, reward_money: int, deadline_hours: int):
        super().__init__("モンスタークエスト依頼")
        self.guild_id = guild_id
        self.name = name
        self.description = description
        self.monster_id = monster_id
        self.monster_count = monster_count
        self.difficulty = difficulty
        self.reward_money = reward_money
        self.deadline_hours = deadline_hours

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestCreateMonsterHuntResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestCreateMonsterHuntResult(False, "QuestSystemが利用できません")
        
        try:
            # ギルドの存在確認
            guild = quest_system.get_guild(self.guild_id)
            if not guild:
                return QuestCreateMonsterHuntResult(False, f"ギルド {self.guild_id} が存在しません")
            
            # クエスト作成
            quest = quest_system.create_monster_hunt_quest_for_guild(
                self.guild_id, self.name, self.description,
                self.monster_id, self.monster_count,
                self.difficulty, acting_player.get_player_id(),
                self.reward_money, self.deadline_hours
            )
            
            # クエストをギルドに投稿
            success, message = quest_system.post_quest_to_guild(self.guild_id, quest, acting_player)
            if success:
                return QuestCreateMonsterHuntResult(True, "モンスター討伐クエストを作成しました", quest.quest_id)
            else:
                return QuestCreateMonsterHuntResult(False, message)
        except Exception as e:
            return QuestCreateMonsterHuntResult(False, f"クエスト作成中にエラーが発生しました: {e}")


class QuestCreateItemCollectionStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("アイテムクエスト依頼")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="guild_id",
                description="クエストを依頼するギルドIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="name",
                description="クエスト名を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="description",
                description="クエストの説明を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="item_id",
                description="収集対象のアイテムIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="item_count",
                description="収集数を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="difficulty",
                description="クエストの危険度を選択してください",
                candidates=["E", "D", "C", "B", "A", "S"]
            ),
            ArgumentInfo(
                name="reward_money",
                description="報酬金額を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="deadline_hours",
                description="期限（時間）を入力してください（デフォルト: 48時間）",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None

    def build_action_command(self, acting_player: Player, game_context: GameContext, guild_id: str, name: str, description: str, item_id: str, item_count: str, difficulty: str, reward_money: str, deadline_hours: str = "48") -> ActionCommand:
        try:
            item_count_int = int(item_count)
            reward_money_int = int(reward_money)
            deadline_hours_int = int(deadline_hours)
            difficulty_enum = QuestDifficulty(difficulty)
        except ValueError:
            # デフォルト値を使用
            item_count_int = 1
            reward_money_int = 100
            deadline_hours_int = 48
            difficulty_enum = QuestDifficulty.E
        
        return QuestCreateItemCollectionCommand(guild_id, name, description, item_id, item_count_int, difficulty_enum, reward_money_int, deadline_hours_int)


class QuestCreateItemCollectionCommand(ActionCommand):
    def __init__(self, guild_id: str, name: str, description: str, item_id: str, item_count: int, difficulty: QuestDifficulty, reward_money: int, deadline_hours: int):
        super().__init__("アイテムクエスト依頼")
        self.guild_id = guild_id
        self.name = name
        self.description = description
        self.item_id = item_id
        self.item_count = item_count
        self.difficulty = difficulty
        self.reward_money = reward_money
        self.deadline_hours = deadline_hours

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestCreateItemCollectionResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestCreateItemCollectionResult(False, "QuestSystemが利用できません")
        
        try:
            # ギルドの存在確認
            guild = quest_system.get_guild(self.guild_id)
            if not guild:
                return QuestCreateItemCollectionResult(False, f"ギルド {self.guild_id} が存在しません")
            
            # クエスト作成
            quest = quest_system.create_item_collection_quest_for_guild(
                self.guild_id, self.name, self.description,
                self.item_id, self.item_count,
                self.difficulty, acting_player.get_player_id(),
                self.reward_money, self.deadline_hours
            )
            
            # クエストをギルドに投稿
            success, message = quest_system.post_quest_to_guild(self.guild_id, quest, acting_player)
            if success:
                return QuestCreateItemCollectionResult(True, "アイテム収集クエストを作成しました", quest.quest_id)
            else:
                return QuestCreateItemCollectionResult(False, message)
        except Exception as e:
            return QuestCreateItemCollectionResult(False, f"クエスト作成中にエラーが発生しました: {e}")


class QuestCreateExplorationStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("探索クエスト依頼")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="guild_id",
                description="クエストを依頼するギルドIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="name",
                description="クエスト名を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="description",
                description="クエストの説明を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="target_spot_id",
                description="探索対象の場所IDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="difficulty",
                description="クエストの危険度を選択してください",
                candidates=["E", "D", "C", "B", "A", "S"]
            ),
            ArgumentInfo(
                name="reward_money",
                description="報酬金額を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="deadline_hours",
                description="期限（時間）を入力してください（デフォルト: 24時間）",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None

    def build_action_command(self, acting_player: Player, game_context: GameContext, guild_id: str, name: str, description: str, target_spot_id: str, difficulty: str, reward_money: str, deadline_hours: str = "24") -> ActionCommand:
        try:
            reward_money_int = int(reward_money)
            deadline_hours_int = int(deadline_hours)
            difficulty_enum = QuestDifficulty(difficulty)
        except ValueError:
            # デフォルト値を使用
            reward_money_int = 100
            deadline_hours_int = 24
            difficulty_enum = QuestDifficulty.E
        
        return QuestCreateExplorationCommand(guild_id, name, description, target_spot_id, difficulty_enum, reward_money_int, deadline_hours_int)


class QuestCreateExplorationCommand(ActionCommand):
    def __init__(self, guild_id: str, name: str, description: str, target_spot_id: str, difficulty: QuestDifficulty, reward_money: int, deadline_hours: int):
        super().__init__("探索クエスト依頼")
        self.guild_id = guild_id
        self.name = name
        self.description = description
        self.target_spot_id = target_spot_id
        self.difficulty = difficulty
        self.reward_money = reward_money
        self.deadline_hours = deadline_hours

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestCreateExplorationResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestCreateExplorationResult(False, "QuestSystemが利用できません")
        
        try:
            # ギルドの存在確認
            guild = quest_system.get_guild(self.guild_id)
            if not guild:
                return QuestCreateExplorationResult(False, f"ギルド {self.guild_id} が存在しません")
            
            # クエスト作成
            quest = quest_system.create_exploration_quest_for_guild(
                self.guild_id, self.name, self.description,
                self.target_spot_id, self.difficulty,
                acting_player.get_player_id(), self.reward_money, self.deadline_hours
            )
            
            # クエストをギルドに投稿
            success, message = quest_system.post_quest_to_guild(self.guild_id, quest, acting_player)
            if success:
                return QuestCreateExplorationResult(True, "探索クエストを作成しました", quest.quest_id)
            else:
                return QuestCreateExplorationResult(False, message)
        except Exception as e:
            return QuestCreateExplorationResult(False, f"クエスト作成中にエラーが発生しました: {e}")


class QuestGetAvailableQuestsStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("利用可能クエスト取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return QuestGetAvailableQuestsCommand()


class QuestGetAvailableQuestsCommand(ActionCommand):
    def __init__(self):
        super().__init__("利用可能クエスト取得")

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestGetAvailableQuestsResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestGetAvailableQuestsResult(False, "QuestSystemが利用できません", [])
        
        try:
            player_id = acting_player.get_player_id()
            available_quests = quest_system.get_available_quests(player_id)
            
            quest_list = []
            for quest in available_quests:
                quest_list.append({
                    'quest_id': quest.quest_id,
                    'name': quest.name,
                    'reward_money': quest.reward_money
                })
            
            return QuestGetAvailableQuestsResult(True, f"{len(quest_list)}個の利用可能クエストを取得しました", quest_list)
        except Exception as e:
            return QuestGetAvailableQuestsResult(False, f"利用可能クエストの取得に失敗しました: {e}", [])


class QuestAcceptQuestStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("クエスト受注")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="quest_id",
                description="受注するクエストIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None

    def build_action_command(self, acting_player: Player, game_context: GameContext, quest_id: str) -> ActionCommand:
        return QuestAcceptQuestCommand(quest_id)


class QuestAcceptQuestCommand(ActionCommand):
    def __init__(self, quest_id: str):
        super().__init__("クエスト受注")
        self.quest_id = quest_id

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestAcceptQuestResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestAcceptQuestResult(False, "QuestSystemが利用できません", self.quest_id)
        
        try:
            player_id = acting_player.get_player_id()
            success, message = quest_system.accept_quest(player_id, self.quest_id)
            if success:
                return QuestAcceptQuestResult(True, "クエストを受注しました", self.quest_id)
            else:
                return QuestAcceptQuestResult(False, message, self.quest_id)
        except Exception as e:
            return QuestAcceptQuestResult(False, f"クエスト受注中にエラーが発生しました: {e}", self.quest_id)


class QuestGetActiveQuestStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("アクティブクエスト取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # QuestSystemが利用可能かチェック
        quest_system = game_context.get_quest_system()
        return quest_system is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return QuestGetActiveQuestCommand()


class QuestGetActiveQuestCommand(ActionCommand):
    def __init__(self):
        super().__init__("アクティブクエスト取得")

    def execute(self, acting_player: Player, game_context: GameContext) -> QuestGetActiveQuestResult:
        quest_system = game_context.get_quest_system()
        if not quest_system:
            return QuestGetActiveQuestResult(False, "QuestSystemが利用できません", None)
        
        try:
            player_id = acting_player.get_player_id()
            active_quest = quest_system.get_active_quest(player_id)
            
            if active_quest:
                # 進捗情報を取得
                progress_info = []
                for condition in active_quest.conditions:
                    progress_info.append(f"{condition.description}: {condition.current_count}/{condition.required_count}")
                progress_text = ", ".join(progress_info)
                
                quest_info = {
                    'quest_id': active_quest.quest_id,
                    'name': active_quest.name,
                    'progress': progress_text
                }
                return QuestGetActiveQuestResult(True, "アクティブなクエストを取得しました", quest_info)
            else:
                return QuestGetActiveQuestResult(True, "アクティブなクエストはありません", None)
        except Exception as e:
            return QuestGetActiveQuestResult(False, f"アクティブクエストの取得に失敗しました: {e}", None) 