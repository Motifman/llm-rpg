from typing import List
from .item import Item, ItemEffect


class Agent:
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        # エージェントの状態
        self.items: List[Item] = []
        self.discovered_info: List[str] = []
        self.current_spot_id: str = ""
        self.experience_points: int = 0
        self.money: int = 0
        
        # RPG基本ステータス（ベース値）
        self.base_max_hp: int = 100
        self.current_hp: int = 100
        self.base_max_mp: int = 50
        self.current_mp: int = 50
        self.base_attack: int = 10
        self.base_defense: int = 5
        self.base_speed: int = 7  # バトルシステム用の素早さ
        
        # 装備システム
        from .weapon import EquipmentSet
        self.equipment: EquipmentSet = EquipmentSet()
        
        # 状態異常システム
        self.status_conditions: List = []  # StatusConditionのリスト
        
        # 会話システム関連
        self.received_messages: List = []  # 受信したメッセージのリスト
        self.conversation_history: List = []  # 会話履歴（全体的な記録）

    # === 装備システム関連 ===
    
    def equip_weapon(self, weapon) -> bool:
        """武器を装備"""
        from .weapon import Weapon
        if not isinstance(weapon, Weapon):
            return False
        
        # アイテムを持っているかチェック
        if not self.has_item(weapon.item_id):
            return False
        
        # 既存の装備を外してインベントリに戻す
        old_weapon = self.equipment.equip_weapon(weapon)
        if old_weapon:
            self.add_item(old_weapon)
        
        # 新しい武器をインベントリから削除
        self.remove_item_by_id(weapon.item_id, 1)
        
        return True
    
    def equip_armor(self, armor) -> bool:
        """防具を装備"""
        from .weapon import Armor
        if not isinstance(armor, Armor):
            return False
        
        # アイテムを持っているかチェック
        if not self.has_item(armor.item_id):
            return False
        
        # 既存の装備を外してインベントリに戻す
        old_armor = self.equipment.equip_armor(armor)
        if old_armor:
            self.add_item(old_armor)
        
        # 新しい防具をインベントリから削除
        self.remove_item_by_id(armor.item_id, 1)
        
        return True
    
    def unequip_weapon(self) -> bool:
        """武器を外す"""
        weapon = self.equipment.unequip_weapon()
        if weapon:
            self.add_item(weapon)
            return True
        return False
    
    def unequip_armor(self, armor_type) -> bool:
        """防具を外す"""
        from .weapon import ArmorType
        armor = self.equipment.unequip_armor(armor_type)
        if armor:
            self.add_item(armor)
            return True
        return False
    
    def get_equipment_summary(self) -> str:
        """装備の要約を取得"""
        return str(self.equipment)

    # === ステータス計算（装備補正付き） ===
    
    @property
    def max_hp(self) -> int:
        """最大HP（装備補正なし、将来拡張用）"""
        return self.base_max_hp
    
    @property
    def max_mp(self) -> int:
        """最大MP（装備補正なし、将来拡張用）"""
        return self.base_max_mp
    
    @property  
    def attack(self) -> int:
        """攻撃力（装備補正付き）"""
        return self.base_attack + self.equipment.get_total_attack_bonus()
    
    @property
    def defense(self) -> int:
        """防御力（装備補正付き）"""
        return self.base_defense + self.equipment.get_total_defense_bonus()
    
    @property
    def speed(self) -> int:
        """素早さ（装備補正付き）"""
        return self.base_speed + self.equipment.get_total_speed_bonus()
    
    def get_critical_rate(self) -> float:
        """クリティカル率を取得"""
        base_critical = 0.05  # ベースクリティカル率5%
        return base_critical + self.equipment.get_total_critical_rate()
    
    def get_evasion_rate(self) -> float:
        """回避率を取得"""
        base_evasion = 0.05  # ベース回避率5%
        return base_evasion + self.equipment.get_total_evasion_rate()

    # === 状態異常システム ===
    
    def add_status_condition(self, condition):
        """状態異常を追加"""
        self.status_conditions.append(condition)
    
    def remove_status_condition(self, effect):
        """特定の状態異常を削除"""
        from .weapon import StatusEffect
        self.status_conditions = [c for c in self.status_conditions if c.effect != effect]
    
    def has_status_condition(self, effect) -> bool:
        """特定の状態異常があるかチェック"""
        from .weapon import StatusEffect
        return any(c.effect == effect for c in self.status_conditions)
    
    def get_status_resistance(self, effect) -> float:
        """状態異常耐性を取得"""
        total_resistance = 0.0
        for armor in self.equipment.get_equipped_armors():
            total_resistance += armor.get_status_resistance(effect)
        return min(total_resistance, 0.95)  # 最大95%
    
    def process_status_effects(self):
        """状態異常の効果を処理（ターン終了時に呼ばれる）"""
        from .weapon import StatusEffect
        
        # 状態異常の効果を適用
        for condition in self.status_conditions[:]:  # コピーを作成して安全にイテレート
            if condition.effect == StatusEffect.POISON:
                # 毒ダメージ
                poison_damage = max(1, condition.value)
                self.current_hp = max(0, self.current_hp - poison_damage)
            
            # ターン数を減らす
            condition.duration -= 1
            
            # 持続時間が終了した状態異常を削除
            if condition.duration <= 0:
                self.status_conditions.remove(condition)
    
    def get_status_summary(self) -> str:
        """状態異常の要約を取得"""
        if not self.status_conditions:
            return "状態異常なし"
        return "状態異常: " + ", ".join(str(c) for c in self.status_conditions)

    # === 既存メソッドの更新（装備補正対応） ===

    def add_item(self, item: Item):
        self.items.append(item)

    def remove_item(self, item: Item):
        self.items.remove(item)
    
    def remove_item_by_id(self, item_id: str, count: int = 1) -> int:
        """IDでアイテムを安全に削除（重複対応）
        
        Args:
            item_id: 削除するアイテムのID
            count: 削除する個数
            
        Returns:
            実際に削除された個数
        """
        removed_count = 0
        items_to_remove = []
        
        for item in self.items:
            if item.item_id == item_id and removed_count < count:
                items_to_remove.append(item)
                removed_count += 1
        
        for item in items_to_remove:
            self.items.remove(item)
        
        return removed_count
    
    # TODO アイテムの所持状況を確認するメソッド、アイテムが重複所持が許さない場合にこれを使用する
    def has_item(self, item_id: str) -> bool:
        return any(item.item_id == item_id for item in self.items)
    
    def get_item_count(self, item_id: str) -> int:
        """特定のアイテムの所持数を取得"""
        return sum(1 for item in self.items if item.item_id == item_id)
    
    def get_items(self) -> List[Item]:
        return self.items
    
    def get_item_by_id(self, item_id: str) -> Item:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None
    
    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        self.current_spot_id = spot_id
    
    # TODO 探索情報を取得するメソッド、探索情報の管理方法は今後変更する可能性がある
    def get_discovered_info(self) -> List[str]:
        return self.discovered_info
    
    def add_discovered_info(self, discovered_info: str):
        self.discovered_info.append(discovered_info)
    
    def get_experience_points(self) -> int:
        return self.experience_points
    
    def add_experience_points(self, experience_points: int):
        self.experience_points += experience_points
        if self.experience_points < 0:
            self.experience_points = 0
    
    def get_money(self) -> int:
        return self.money
    
    def add_money(self, money: int):
        self.money += money
        if self.money < 0:
            self.money = 0
    
    # === RPGステータス管理 ===
    
    def get_hp(self) -> tuple[int, int]:
        """現在HP、最大HPを取得"""
        return self.current_hp, self.max_hp
    
    def get_mp(self) -> tuple[int, int]:
        """現在MP、最大MPを取得"""
        return self.current_mp, self.max_mp
    
    def get_attack(self) -> int:
        """攻撃力を取得（装備補正付き）"""
        return self.attack
    
    def get_defense(self) -> int:
        """防御力を取得（装備補正付き）"""
        return self.defense
    
    def get_speed(self) -> int:
        """素早さを取得（装備補正付き）"""
        return self.speed
    
    def set_hp(self, hp: int):
        """HPを設定（上限・下限チェック付き）"""
        self.current_hp = max(0, min(hp, self.max_hp))
    
    def set_mp(self, mp: int):
        """MPを設定（上限・下限チェック付き）"""
        self.current_mp = max(0, min(mp, self.max_mp))
    
    def set_max_hp(self, max_hp: int):
        """最大HPを設定"""
        if max_hp > 0:
            self.base_max_hp = max_hp
            # 現在HPが最大HPを超えている場合は調整
            if self.current_hp > self.max_hp:
                self.current_hp = self.max_hp
    
    def set_max_mp(self, max_mp: int):
        """最大MPを設定"""
        if max_mp > 0:
            self.base_max_mp = max_mp
            # 現在MPが最大MPを超えている場合は調整
            if self.current_mp > self.max_mp:
                self.current_mp = self.max_mp
    
    def set_base_attack(self, attack: int):
        """ベース攻撃力を設定"""
        self.base_attack = max(0, attack)
    
    def set_base_defense(self, defense: int):
        """ベース防御力を設定"""
        self.base_defense = max(0, defense)
    
    def set_base_speed(self, speed: int):
        """ベース素早さを設定"""
        self.base_speed = max(0, speed)
    
    def apply_item_effect(self, effect: ItemEffect):
        """アイテム効果を適用"""
        # HP/MP変更
        if effect.hp_change != 0:
            new_hp = self.current_hp + effect.hp_change
            self.set_hp(new_hp)
        
        if effect.mp_change != 0:
            new_mp = self.current_mp + effect.mp_change
            self.set_mp(new_mp)
        
        # ステータス変更（ベース値への変更）
        if effect.attack_change != 0:
            new_attack = self.base_attack + effect.attack_change
            self.set_base_attack(new_attack)
        
        if effect.defense_change != 0:
            new_defense = self.base_defense + effect.defense_change
            self.set_base_defense(new_defense)
        
        # 既存のステータス変更
        if effect.money_change != 0:
            self.add_money(effect.money_change)
        
        if effect.experience_change != 0:
            self.add_experience_points(effect.experience_change)
        
        # 一時的効果（将来の拡張用）
        # temporary_effectsは現在は記録のみで、実際の効果は今後実装
    
    def is_alive(self) -> bool:
        """生存判定"""
        return self.current_hp > 0
    
    def get_status_summary(self) -> str:
        """ステータスの要約を取得（装備補正付き）"""
        return (f"HP: {self.current_hp}/{self.max_hp}, "
                f"MP: {self.current_mp}/{self.max_mp}, "
                f"攻撃: {self.attack}, 防御: {self.defense}, 素早さ: {self.speed}, "
                f"所持金: {self.money}, 経験値: {self.experience_points}, "
                f"クリティカル: {self.get_critical_rate():.1%}, 回避: {self.get_evasion_rate():.1%}")
    
    # === 会話システム関連メソッド ===
    
    def receive_message(self, message):
        """メッセージを受信する"""
        self.received_messages.append(message)
        self.conversation_history.append(message)
    
    def get_received_messages(self):
        """受信したメッセージを取得"""
        return self.received_messages.copy()
    
    def clear_received_messages(self):
        """受信済みメッセージをクリア（読み取り済みとしてマーク）"""
        self.received_messages.clear()
    
    def get_conversation_history(self, limit: int = None):
        """会話履歴を取得"""
        if limit is None:
            return self.conversation_history.copy()
        else:
            return self.conversation_history[-limit:] if limit > 0 else []
    
    def get_recent_conversation_context(self, max_messages: int = 10):
        """最近の会話コンテキストを取得（LLM統合準備）"""
        recent_messages = self.get_conversation_history(max_messages)
        context = {
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "current_spot_id": self.current_spot_id,
            "status": self.get_status_summary(),
            "equipment": self.get_equipment_summary(),
            "status_effects": self.get_status_summary(),
            "recent_messages": [msg.to_dict() if hasattr(msg, 'to_dict') else str(msg) for msg in recent_messages],
            "items": [item.item_id for item in self.items],
            "discovered_info": self.discovered_info.copy()
        }
        return context
    
    def has_unread_messages(self) -> bool:
        """未読メッセージがあるかどうか"""
        return len(self.received_messages) > 0

    def __str__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items}, current_spot_id={self.current_spot_id}, experience_points={self.experience_points}, money={self.money})"
    
    def __repr__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items}, current_spot_id={self.current_spot_id}, experience_points={self.experience_points}, money={self.money})"