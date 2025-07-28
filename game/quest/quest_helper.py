from game.quest.quest_data import Quest, QuestCondition, QuestType, QuestDifficulty
from datetime import datetime, timedelta


def create_monster_hunt_quest(quest_id: str, name: str, description: str,
                             monster_id: str, monster_count: int,
                             difficulty: QuestDifficulty, client_id: str, guild_id: str,
                             reward_money: int, deadline_hours: int = 72) -> Quest:
    """モンスター討伐クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.MONSTER_HUNT,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 討伐条件を追加
    condition = QuestCondition(
        condition_type="kill_monster",
        target=monster_id,
        required_count=monster_count,
        description=f"{monster_id}を{monster_count}体討伐"
    )
    quest.conditions.append(condition)
    
    return quest


def create_item_collection_quest(quest_id: str, name: str, description: str,
                                item_id: str, item_count: int,
                                difficulty: QuestDifficulty, client_id: str, guild_id: str,
                                reward_money: int, deadline_hours: int = 48) -> Quest:
    """アイテム収集クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.ITEM_COLLECTION,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 収集条件を追加
    condition = QuestCondition(
        condition_type="collect_item",
        target=item_id,
        required_count=item_count,
        description=f"{item_id}を{item_count}個収集"
    )
    quest.conditions.append(condition)
    
    return quest


def create_exploration_quest(quest_id: str, name: str, description: str,
                           target_spot_id: str,
                           difficulty: QuestDifficulty, client_id: str, guild_id: str,
                           reward_money: int, deadline_hours: int = 24) -> Quest:
    """探索クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.EXPLORATION,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 探索条件を追加
    condition = QuestCondition(
        condition_type="reach_location",
        target=target_spot_id,
        required_count=1,
        description=f"{target_spot_id}を探索"
    )
    quest.conditions.append(condition)
    
    return quest 