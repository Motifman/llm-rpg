from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from .agent import Agent
from .item import Item


class JobType(Enum):
    """職業タイプ"""
    ADVENTURER = "adventurer"  # 冒険者
    CRAFTSMAN = "craftsman"    # 職人
    MERCHANT = "merchant"      # 商人
    PRODUCER = "producer"      # 一次産業者


@dataclass(frozen=True)
class Recipe:
    """アイテム合成レシピ"""
    recipe_id: str
    name: str
    description: str
    required_materials: Dict[str, int]  # item_id -> required_count
    produced_item_id: str
    produced_count: int = 1
    required_job_level: int = 1
    job_experience_gain: int = 10
    success_rate: float = 1.0  # 成功率（0.0-1.0）
    
    def can_craft(self, agent: "JobAgent") -> bool:
        """レシピを実行可能かチェック"""
        # 職業レベルチェック
        if agent.job_level < self.required_job_level:
            return False
        
        # 材料チェック
        for material_id, required_count in self.required_materials.items():
            if agent.get_item_count(material_id) < required_count:
                return False
        
        return True
    
    def get_missing_materials(self, agent: "JobAgent") -> Dict[str, int]:
        """不足している材料を取得"""
        missing = {}
        for material_id, required_count in self.required_materials.items():
            have_count = agent.get_item_count(material_id)
            if have_count < required_count:
                missing[material_id] = required_count - have_count
        return missing


@dataclass(frozen=True)
class Service:
    """商人が提供するサービス"""
    service_id: str
    name: str
    description: str
    price: int
    required_items: Dict[str, int] = None  # 必要アイテム（材料費）
    duration_minutes: int = 0  # サービス持続時間（分）
    
    def can_provide(self, agent: "JobAgent") -> bool:
        """サービスを提供可能かチェック"""
        if self.required_items:
            for item_id, count in self.required_items.items():
                if agent.get_item_count(item_id) < count:
                    return False
        return True


class JobAgent(Agent):
    """職業を持つエージェントの基底クラス"""
    
    def __init__(self, agent_id: str, name: str, job_type: JobType):
        super().__init__(agent_id, name)
        self.job_type = job_type
        self.job_level = 1
        self.job_experience = 0
        self.job_skills: List[str] = []
        self.known_recipes: List[Recipe] = []
        self.available_services: List[Service] = []
        
        # 職業特有のステータス強化
        self._apply_job_bonuses()
    
    def _apply_job_bonuses(self):
        """職業による初期ボーナスを適用"""
        if self.job_type == JobType.ADVENTURER:
            # 冒険者は戦闘ステータスにボーナス
            self.max_hp += 20
            self.current_hp = self.max_hp
            self.attack += 5
        elif self.job_type == JobType.CRAFTSMAN:
            # 職人は器用さ（MP）にボーナス
            self.max_mp += 20
            self.current_mp = self.max_mp
        elif self.job_type == JobType.MERCHANT:
            # 商人は初期資金にボーナス
            self.money += 100
        elif self.job_type == JobType.PRODUCER:
            # 一次産業者は体力にボーナス
            self.max_hp += 10
            self.current_hp = self.max_hp
            self.defense += 3
    
    def add_job_experience(self, exp: int):
        """職業経験値を追加"""
        self.job_experience += exp
        self._check_level_up()
    
    def _check_level_up(self):
        """レベルアップ判定"""
        required_exp = self.job_level * 100  # レベル × 100 で次のレベル
        if self.job_experience >= required_exp:
            self.job_level += 1
            self.job_experience -= required_exp
            self._apply_level_up_bonus()
    
    def _apply_level_up_bonus(self):
        """レベルアップ時のボーナスを適用"""
        # 基本ステータスアップ
        self.max_hp += 5
        self.max_mp += 3
        
        # 職業別ボーナス
        if self.job_type == JobType.ADVENTURER:
            self.attack += 2
        elif self.job_type == JobType.CRAFTSMAN:
            self.max_mp += 5
        elif self.job_type == JobType.MERCHANT:
            # 商人は交渉力（経験値ボーナス）が上がる
            pass
        elif self.job_type == JobType.PRODUCER:
            self.defense += 1
    
    def learn_recipe(self, recipe: Recipe) -> bool:
        """レシピを覚える"""
        if recipe.required_job_level > self.job_level:
            return False
        
        if recipe in self.known_recipes:
            return False  # 既に知っている
        
        self.known_recipes.append(recipe)
        return True
    
    def add_service(self, service: Service):
        """提供可能サービスを追加"""
        if service not in self.available_services:
            self.available_services.append(service)
    
    def can_craft_recipe(self, recipe_id: str) -> bool:
        """指定レシピを実行可能かチェック"""
        recipe = self.get_recipe_by_id(recipe_id)
        if not recipe:
            return False
        return recipe.can_craft(self)
    
    def get_recipe_by_id(self, recipe_id: str) -> Optional[Recipe]:
        """IDでレシピを取得"""
        for recipe in self.known_recipes:
            if recipe.recipe_id == recipe_id:
                return recipe
        return None
    
    def get_service_by_id(self, service_id: str) -> Optional[Service]:
        """IDでサービスを取得"""
        for service in self.available_services:
            if service.service_id == service_id:
                return service
        return None
    
    def get_job_status_summary(self) -> str:
        """職業ステータスの要約を取得"""
        return (f"職業: {self.job_type.value}, レベル: {self.job_level}, "
                f"経験値: {self.job_experience}, レシピ数: {len(self.known_recipes)}, "
                f"サービス数: {len(self.available_services)}")
    
    def __str__(self):
        base_str = super().__str__()
        return f"Job{base_str[5:-1]}, job_type={self.job_type.value}, job_level={self.job_level})"


# === 具体的な職業クラス ===

class CraftsmanAgent(JobAgent):
    """職人エージェント - アイテム合成・強化専門"""
    
    def __init__(self, agent_id: str, name: str, specialty: str = "general"):
        super().__init__(agent_id, name, JobType.CRAFTSMAN)
        self.specialty = specialty  # "blacksmith", "alchemist", "tailor" など
        self.enhancement_success_rate = 0.8  # 強化成功率
        self.crafting_efficiency = 1.0  # 作業効率（経験値倍率）
        
        # 専門分野による追加ボーナス
        self._apply_specialty_bonuses()
    
    def _apply_specialty_bonuses(self):
        """専門分野による追加ボーナス"""
        if self.specialty == "blacksmith":
            self.enhancement_success_rate += 0.1
            self.job_skills.append("武器強化")
            self.job_skills.append("防具作成")
        elif self.specialty == "alchemist":
            self.crafting_efficiency += 0.2
            self.job_skills.append("ポーション調合")
            self.job_skills.append("薬草知識")
        elif self.specialty == "tailor":
            self.job_skills.append("服飾作成")
            self.job_skills.append("装飾品作成")
    
    def craft_item(self, recipe: Recipe, quantity: int = 1) -> Dict[str, Any]:
        """アイテムを合成する"""
        result = {
            "success": False,
            "created_items": [],
            "consumed_materials": {},
            "experience_gained": 0,
            "messages": []
        }
        
        if not recipe.can_craft(self):
            missing = recipe.get_missing_materials(self)
            result["messages"].append(f"材料不足: {missing}")
            return result
        
        # 複数回作成の場合
        for _ in range(quantity):
            # 成功判定
            import random
            if random.random() <= recipe.success_rate:
                # 成功: アイテム作成
                created_item = Item(recipe.produced_item_id, f"{recipe.name}で作成")
                for _ in range(recipe.produced_count):
                    self.add_item(created_item)
                    result["created_items"].append(created_item)
                
                # 経験値獲得
                exp_gain = int(recipe.job_experience_gain * self.crafting_efficiency)
                self.add_job_experience(exp_gain)
                result["experience_gained"] += exp_gain
                
                result["messages"].append(f"{recipe.name}の作成に成功")
            else:
                result["messages"].append(f"{recipe.name}の作成に失敗")
            
            # 材料消費
            for material_id, count in recipe.required_materials.items():
                removed = self.remove_item_by_id(material_id, count)
                result["consumed_materials"][material_id] = result["consumed_materials"].get(material_id, 0) + removed
        
        result["success"] = len(result["created_items"]) > 0
        return result
    
    def enhance_item(self, item_id: str, enhancement_materials: Dict[str, int]) -> Dict[str, Any]:
        """アイテムを強化する"""
        result = {
            "success": False,
            "enhanced_item": None,
            "consumed_materials": {},
            "experience_gained": 0,
            "messages": []
        }
        
        # 対象アイテムチェック
        if not self.has_item(item_id):
            result["messages"].append(f"アイテム {item_id} を所持していません")
            return result
        
        # 強化材料チェック
        for material_id, count in enhancement_materials.items():
            if self.get_item_count(material_id) < count:
                result["messages"].append(f"強化材料 {material_id} が不足")
                return result
        
        # 強化実行
        import random
        if random.random() <= self.enhancement_success_rate:
            # 強化成功: 新しい強化アイテムを作成
            original_item = self.get_item_by_id(item_id)
            enhanced_item = Item(f"{item_id}_enhanced", f"強化された{original_item.description}")
            
            # 元アイテムを削除し、強化アイテムを追加
            self.remove_item_by_id(item_id, 1)
            self.add_item(enhanced_item)
            
            result["enhanced_item"] = enhanced_item
            result["success"] = True
            result["messages"].append(f"{item_id}の強化に成功")
            
            # 経験値獲得
            exp_gain = 20  # 強化の基本経験値
            self.add_job_experience(exp_gain)
            result["experience_gained"] = exp_gain
        else:
            result["messages"].append(f"{item_id}の強化に失敗")
        
        # 強化材料消費
        for material_id, count in enhancement_materials.items():
            removed = self.remove_item_by_id(material_id, count)
            result["consumed_materials"][material_id] = removed
        
        return result


class MerchantAgent(JobAgent):
    """商人エージェント - 販売・サービス提供専門"""
    
    def __init__(self, agent_id: str, name: str, business_type: str = "general"):
        super().__init__(agent_id, name, JobType.MERCHANT)
        self.business_type = business_type  # "trader", "innkeeper", "information_broker" など
        self.negotiation_skill = 1.0  # 交渉スキル
        self.shop_reputation = 1.0  # 店の評判
        self.active_shop: Optional[Dict[str, Any]] = None  # 現在の店舗情報
        
        # 業種による追加ボーナス
        self._apply_business_bonuses()
    
    def _apply_business_bonuses(self):
        """業種による追加ボーナス"""
        if self.business_type == "trader":
            self.negotiation_skill += 0.2
            self.job_skills.append("価格交渉")
            self.job_skills.append("商品知識")
        elif self.business_type == "innkeeper":
            self.job_skills.append("宿泊サービス")
            self.job_skills.append("料理提供")
        elif self.business_type == "information_broker":
            self.job_skills.append("情報収集")
            self.job_skills.append("情報販売")
    
    def setup_shop(self, shop_name: str, shop_type: str, offered_items: Dict[str, int], 
                   offered_services: List[str]) -> Dict[str, Any]:
        """店舗を設営する"""
        # 店舗情報を設定
        self.active_shop = {
            "name": shop_name,
            "type": shop_type,
            "offered_items": offered_items.copy(),  # item_id -> price
            "offered_services": offered_services.copy(),
            "location": self.current_spot_id,
            "reputation": self.shop_reputation
        }
        
        return {
            "success": True,
            "shop_info": self.active_shop.copy(),
            "message": f"{shop_name}を{self.current_spot_id}に開店しました"
        }
    
    def provide_service(self, service_id: str, target_agent_id: str, custom_price: Optional[int] = None) -> Dict[str, Any]:
        """サービスを提供する"""
        result = {
            "success": False,
            "service_provided": None,
            "price_charged": 0,
            "experience_gained": 0,
            "messages": []
        }
        
        service = self.get_service_by_id(service_id)
        if not service:
            result["messages"].append(f"サービス {service_id} を提供できません")
            return result
        
        if not service.can_provide(self):
            result["messages"].append(f"サービス {service_id} の提供条件を満たしていません")
            return result
        
        # 価格設定
        final_price = custom_price if custom_price is not None else service.price
        
        # サービス提供
        result["success"] = True
        result["service_provided"] = service
        result["price_charged"] = final_price
        result["messages"].append(f"{service.name}を{target_agent_id}に提供しました")
        
        # 経験値獲得
        exp_gain = 15
        self.add_job_experience(exp_gain)
        result["experience_gained"] = exp_gain
        
        # 材料消費
        if service.required_items:
            for item_id, count in service.required_items.items():
                self.remove_item_by_id(item_id, count)
        
        return result
    
    def negotiate_price(self, original_price: int, agent_reputation: float = 1.0) -> int:
        """価格交渉を行う"""
        # 交渉スキルと相手の評判を考慮して価格を調整
        negotiation_factor = self.negotiation_skill * agent_reputation
        discount_rate = min(0.3, negotiation_factor * 0.1)  # 最大30%割引
        
        final_price = int(original_price * (1 - discount_rate))
        return max(1, final_price)  # 最低1ゴールド


class AdventurerAgent(JobAgent):
    """冒険者エージェント - 戦闘・探索専門"""
    
    def __init__(self, agent_id: str, name: str, combat_class: str = "warrior"):
        super().__init__(agent_id, name, JobType.ADVENTURER)
        self.combat_class = combat_class  # "warrior", "mage", "healer", "tank" など
        self.combat_experience = 0
        self.combat_skills: List[str] = []
        
        # クエスト関連の追加属性
        self.current_quest_id: Optional[str] = None
        self.completed_quests: List[str] = []  # 完了したクエストのIDリスト
        self.quest_reputation: int = 0  # クエスト実績による評判
        
        # 戦闘クラスによる追加ボーナス
        self._apply_combat_bonuses()
    
    def _apply_combat_bonuses(self):
        """戦闘クラスによる追加ボーナス"""
        if self.combat_class == "warrior":
            self.attack += 5
            self.combat_skills.append("強攻撃")
            self.job_skills.append("武器熟練")
        elif self.combat_class == "mage":
            self.max_mp += 30
            self.current_mp = self.max_mp
            self.combat_skills.append("魔法攻撃")
            self.job_skills.append("魔法知識")
        elif self.combat_class == "healer":
            self.max_mp += 20
            self.current_mp = self.max_mp
            self.combat_skills.append("回復魔法")
            self.job_skills.append("治癒術")
        elif self.combat_class == "tank":
            self.max_hp += 30
            self.current_hp = self.max_hp
            self.defense += 5
            self.combat_skills.append("防御強化")
            self.job_skills.append("盾技術")
    
    def use_combat_skill(self, skill_name: str, target_id: Optional[str] = None) -> Dict[str, Any]:
        """戦闘スキルを使用する"""
        result = {
            "success": False,
            "skill_used": skill_name,
            "target": target_id,
            "effect": {},
            "mp_consumed": 0,
            "messages": []
        }
        
        if skill_name not in self.combat_skills:
            result["messages"].append(f"スキル {skill_name} を習得していません")
            return result
        
        # スキル別処理
        mp_cost = 0
        if skill_name == "強攻撃":
            mp_cost = 10
            if self.current_mp >= mp_cost:
                result["effect"] = {"damage_multiplier": 1.5}
                result["success"] = True
                result["messages"].append("強攻撃を発動しました")
        elif skill_name == "魔法攻撃":
            mp_cost = 15
            if self.current_mp >= mp_cost:
                result["effect"] = {"magic_damage": self.attack * 1.2}
                result["success"] = True
                result["messages"].append("魔法攻撃を発動しました")
        elif skill_name == "回復魔法":
            mp_cost = 12
            if self.current_mp >= mp_cost:
                result["effect"] = {"heal_amount": 30}
                result["success"] = True
                result["messages"].append("回復魔法を発動しました")
        elif skill_name == "防御強化":
            mp_cost = 8
            if self.current_mp >= mp_cost:
                result["effect"] = {"defense_boost": 5, "duration": 3}
                result["success"] = True
                result["messages"].append("防御力を強化しました")
        
        if result["success"]:
            self.set_mp(self.current_mp - mp_cost)
            result["mp_consumed"] = mp_cost
            
            # 戦闘経験値獲得
            self.combat_experience += 5
            self.add_job_experience(3)
        else:
            result["messages"].append("MPが不足しています")
        
        return result
    
    # === クエスト関連メソッド ===
    
    def accept_quest(self, quest_id: str) -> bool:
        """クエストを受注"""
        if self.current_quest_id is not None:
            return False  # 既にクエストを受注している
        
        self.current_quest_id = quest_id
        return True
    
    def complete_quest(self, quest_id: str) -> bool:
        """クエストを完了"""
        if self.current_quest_id != quest_id:
            return False
        
        self.completed_quests.append(quest_id)
        self.current_quest_id = None
        self.quest_reputation += 10  # 基本評判上昇
        return True
    
    def cancel_quest(self, quest_id: str) -> bool:
        """クエストをキャンセル"""
        if self.current_quest_id != quest_id:
            return False
        
        self.current_quest_id = None
        # 評判に軽微なペナルティ
        self.quest_reputation = max(0, self.quest_reputation - 2)
        return True
    
    def has_active_quest(self) -> bool:
        """アクティブなクエストがあるかチェック"""
        return self.current_quest_id is not None
    
    def get_current_quest_id(self) -> Optional[str]:
        """現在のクエストIDを取得"""
        return self.current_quest_id
    
    def get_completed_quest_count(self) -> int:
        """完了したクエスト数を取得"""
        return len(self.completed_quests)
    
    def get_quest_reputation(self) -> int:
        """クエスト評判を取得"""
        return self.quest_reputation
    
    def can_accept_quest_difficulty(self, difficulty: str) -> bool:
        """指定された危険度のクエストを受注可能かチェック"""
        # 評判に基づく制限（簡易実装）
        difficulty_requirements = {
            "E": 0,
            "D": 10,
            "C": 30,
            "B": 70,
            "A": 150,
            "S": 300
        }
        
        required_rep = difficulty_requirements.get(difficulty, 0)
        return self.quest_reputation >= required_rep
    
    def get_adventurer_summary(self) -> str:
        """冒険者ステータスの要約を取得"""
        base_summary = self.get_job_status_summary()
        quest_summary = (f"アクティブクエスト: {self.current_quest_id or 'なし'}, "
                        f"完了クエスト数: {len(self.completed_quests)}, "
                        f"クエスト評判: {self.quest_reputation}")
        return f"{base_summary}, {quest_summary}"


class ProducerAgent(JobAgent):
    """一次産業者エージェント - 資源採集・生産専門"""
    
    def __init__(self, agent_id: str, name: str, production_type: str = "farmer"):
        super().__init__(agent_id, name, JobType.PRODUCER)
        self.production_type = production_type  # "farmer", "fisher", "miner", "woodcutter" など
        self.production_efficiency = 1.0  # 生産効率
        self.gathering_tools: List[str] = []  # 採集道具
        
        # 生産タイプによる追加ボーナス
        self._apply_production_bonuses()
    
    def _apply_production_bonuses(self):
        """生産タイプによる追加ボーナス"""
        if self.production_type == "farmer":
            self.job_skills.append("農業知識")
            self.job_skills.append("土壌管理")
            self.gathering_tools.append("hoe")  # クワ
        elif self.production_type == "fisher":
            self.job_skills.append("釣り技術")
            self.job_skills.append("魚の知識")
            self.gathering_tools.append("fishing_rod")  # 釣り竿
        elif self.production_type == "miner":
            self.defense += 2  # 鉱山は危険なので防御力アップ
            self.job_skills.append("鉱物知識")
            self.job_skills.append("採掘技術")
            self.gathering_tools.append("pickaxe")  # ツルハシ
        elif self.production_type == "woodcutter":
            self.attack += 2  # 斧での戦闘も可能
            self.job_skills.append("木材知識")
            self.job_skills.append("森林管理")
            self.gathering_tools.append("axe")  # 斧
    
    def gather_resource(self, resource_type: str, tool_item_id: Optional[str] = None, 
                       duration_minutes: int = 60) -> Dict[str, Any]:
        """資源を採集する"""
        result = {
            "success": False,
            "gathered_items": [],
            "tool_durability": 0,
            "experience_gained": 0,
            "messages": []
        }
        
        # 道具チェック
        if tool_item_id and not self.has_item(tool_item_id):
            result["messages"].append(f"道具 {tool_item_id} を所持していません")
            return result
        
        # 採集効率の計算
        efficiency = self.production_efficiency
        if tool_item_id and tool_item_id in self.gathering_tools:
            efficiency *= 1.5  # 適切な道具使用でボーナス
        
        # 採集実行
        import random
        base_yield = duration_minutes // 15  # 15分で1個基準
        actual_yield = int(base_yield * efficiency * (0.8 + random.random() * 0.4))  # ±20%の変動
        
        # アイテム生成
        resource_item = Item(resource_type, f"採集した{resource_type}")
        for _ in range(max(1, actual_yield)):
            self.add_item(resource_item)
            result["gathered_items"].append(resource_item)
        
        result["success"] = True
        result["messages"].append(f"{resource_type}を{len(result['gathered_items'])}個採集しました")
        
        # 経験値獲得
        exp_gain = duration_minutes // 10  # 10分で1経験値
        self.add_job_experience(exp_gain)
        result["experience_gained"] = exp_gain
        
        return result
    
    def process_material(self, raw_material_id: str, processed_item_id: str, 
                        quantity: int = 1) -> Dict[str, Any]:
        """材料を加工する"""
        result = {
            "success": False,
            "processed_items": [],
            "consumed_materials": 0,
            "experience_gained": 0,
            "messages": []
        }
        
        # 材料チェック
        if self.get_item_count(raw_material_id) < quantity:
            result["messages"].append(f"材料 {raw_material_id} が不足")
            return result
        
        # 加工実行
        processed_item = Item(processed_item_id, f"{raw_material_id}から加工")
        for _ in range(quantity):
            # 材料消費
            self.remove_item_by_id(raw_material_id, 1)
            result["consumed_materials"] += 1
            
            # 加工品作成
            self.add_item(processed_item)
            result["processed_items"].append(processed_item)
        
        result["success"] = True
        result["messages"].append(f"{processed_item_id}を{quantity}個加工しました")
        
        # 経験値獲得
        exp_gain = quantity * 2
        self.add_job_experience(exp_gain)
        result["experience_gained"] = exp_gain
        
        return result 