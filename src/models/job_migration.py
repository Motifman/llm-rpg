"""
JobシステムからRoleシステムへの移行アダプター

既存のJobAgentベースのシステムを新しいRoleベースのSpotActionシステムに
段階的に移行するためのアダプター層
"""

from typing import Dict, Optional, Any
from .agent import Agent
from .spot_action import Role, Permission
from .job import JobAgent, JobType, CraftsmanAgent, MerchantAgent, ServiceProviderAgent, TraderAgent, ProducerAgent, AdventurerAgent


class JobToRoleMapper:
    """JobSystemからRoleSystemへのマッピングを管理"""
    
    # JobType から Role への基本マッピング
    JOB_TO_ROLE_MAPPING: Dict[JobType, Role] = {
        JobType.ADVENTURER: Role.ADVENTURER,
        JobType.CRAFTSMAN: Role.CRAFTSMAN,
        JobType.MERCHANT: Role.MERCHANT,
        JobType.PRODUCER: Role.FARMER,  # デフォルトとして農家に
    }
    
    # より詳細な職業特化マッピング
    DETAILED_JOB_MAPPING: Dict[str, Role] = {
        # CraftsmanAgent の specialty
        "blacksmith": Role.BLACKSMITH,
        "alchemist": Role.ALCHEMIST,
        "tailor": Role.TAILOR,
        
        # MerchantAgent の business_type
        "trader": Role.TRADER,
        "innkeeper": Role.INNKEEPER,
        "shop_keeper": Role.SHOP_KEEPER,
        
        # ServiceProviderAgent の service_type
        "innkeeper": Role.INNKEEPER,
        "dancer": Role.DANCER,
        "priest": Role.PRIEST,
        
        # TraderAgent の trade_specialty -> 商人系として統一
        "general": Role.MERCHANT,
        "weapons": Role.MERCHANT,
        "potions": Role.MERCHANT,
        "food": Role.MERCHANT,
        
        # ProducerAgent の production_type
        "farmer": Role.FARMER,
        "fisher": Role.FISHER,
        "miner": Role.MINER,
        "woodcutter": Role.WOODCUTTER,
        
        # AdventurerAgent の specialty
        "warrior": Role.ADVENTURER,
    }
    
    @classmethod
    def map_job_agent_to_role(cls, job_agent: JobAgent) -> Role:
        """JobAgentから適切なRoleを特定"""
        
        # 詳細な職業特化マッピングを優先
        if isinstance(job_agent, CraftsmanAgent):
            return cls.DETAILED_JOB_MAPPING.get(job_agent.specialty, Role.CRAFTSMAN)
        elif isinstance(job_agent, MerchantAgent):
            return cls.DETAILED_JOB_MAPPING.get(job_agent.business_type, Role.MERCHANT)
        elif isinstance(job_agent, ServiceProviderAgent):
            return cls.DETAILED_JOB_MAPPING.get(job_agent.service_type, Role.MERCHANT)
        elif isinstance(job_agent, TraderAgent):
            return cls.DETAILED_JOB_MAPPING.get(job_agent.trade_specialty, Role.MERCHANT)
        elif isinstance(job_agent, ProducerAgent):
            return cls.DETAILED_JOB_MAPPING.get(job_agent.production_type, Role.FARMER)
        elif isinstance(job_agent, AdventurerAgent):
            # AdventurerAgentのspecialtyがある場合は確認
            if hasattr(job_agent, 'specialty'):
                return cls.DETAILED_JOB_MAPPING.get(job_agent.specialty, Role.ADVENTURER)
            return Role.ADVENTURER
        
        # 基本的なJobTypeマッピング
        return cls.JOB_TO_ROLE_MAPPING.get(job_agent.job_type, Role.CITIZEN)
    
    @classmethod
    def get_default_permission_for_role(cls, role: Role) -> Permission:
        """Roleに基づくデフォルト権限を取得"""
        permission_mapping = {
            Role.CITIZEN: Permission.CUSTOMER,
            Role.ADVENTURER: Permission.CUSTOMER,
            Role.MERCHANT: Permission.CUSTOMER,
            Role.SHOP_KEEPER: Permission.OWNER,
            Role.TRADER: Permission.CUSTOMER,
            Role.CRAFTSMAN: Permission.CUSTOMER,
            Role.BLACKSMITH: Permission.EMPLOYEE,
            Role.ALCHEMIST: Permission.EMPLOYEE,
            Role.TAILOR: Permission.EMPLOYEE,
            Role.INNKEEPER: Permission.OWNER,
            Role.DANCER: Permission.EMPLOYEE,
            Role.PRIEST: Permission.EMPLOYEE,
            Role.FARMER: Permission.CUSTOMER,
            Role.FISHER: Permission.CUSTOMER,
            Role.MINER: Permission.CUSTOMER,
            Role.WOODCUTTER: Permission.CUSTOMER,
        }
        return permission_mapping.get(role, Permission.CUSTOMER)


class JobAgentAdapter:
    """JobAgentを新システムに適応させるアダプター"""
    
    def __init__(self, job_agent: JobAgent):
        self.job_agent = job_agent
        self._mapped_role = JobToRoleMapper.map_job_agent_to_role(job_agent)
        self._default_permission = JobToRoleMapper.get_default_permission_for_role(self._mapped_role)
    
    def get_adapted_agent(self) -> Agent:
        """JobAgentを新しいAgentクラスに変換"""
        # 新しいAgentを作成
        new_agent = Agent(
            agent_id=self.job_agent.agent_id,
            name=self.job_agent.name,
            role=self._mapped_role
        )
        
        # 基本ステータスを移行
        new_agent.money = self.job_agent.money
        new_agent.items = self.job_agent.items.copy()
        new_agent.discovered_info = self.job_agent.discovered_info.copy()
        new_agent.current_spot_id = self.job_agent.current_spot_id
        new_agent.experience_points = self.job_agent.experience_points
        
        # HP/MP系ステータスを移行
        new_agent.base_max_hp = self.job_agent.base_max_hp
        new_agent.current_hp = self.job_agent.current_hp
        new_agent.base_max_mp = self.job_agent.base_max_mp
        new_agent.current_mp = self.job_agent.current_mp
        new_agent.base_attack = self.job_agent.base_attack
        new_agent.base_defense = self.job_agent.base_defense
        new_agent.base_speed = self.job_agent.base_speed
        
        # 装備・状態異常を移行
        if hasattr(self.job_agent, 'equipment'):
            new_agent.equipment = self.job_agent.equipment
        if hasattr(self.job_agent, 'status_conditions'):
            new_agent.status_conditions = self.job_agent.status_conditions.copy()
        if hasattr(self.job_agent, 'received_messages'):
            new_agent.received_messages = self.job_agent.received_messages.copy()
        if hasattr(self.job_agent, 'conversation_history'):
            new_agent.conversation_history = self.job_agent.conversation_history.copy()
        
        return new_agent
    
    def get_role(self) -> Role:
        """マッピングされたRoleを取得"""
        return self._mapped_role
    
    def get_default_permission(self) -> Permission:
        """デフォルト権限を取得"""
        return self._default_permission
    
    def get_job_skills_summary(self) -> Dict[str, Any]:
        """Job固有のスキル情報を取得（互換性維持用）"""
        summary = {
            "job_type": str(self.job_agent.job_type),
            "job_level": self.job_agent.job_level,
            "job_experience": self.job_agent.job_experience,
            "job_skills": self.job_agent.job_skills.copy(),
            "mapped_role": self._mapped_role.value,
            "default_permission": self._default_permission.value
        }
        
        # 職業固有の詳細情報
        if isinstance(self.job_agent, CraftsmanAgent):
            summary.update({
                "specialty": self.job_agent.specialty,
                "enhancement_success_rate": self.job_agent.enhancement_success_rate,
                "crafting_efficiency": self.job_agent.crafting_efficiency,
                "known_recipes": len(self.job_agent.known_recipes)
            })
        elif isinstance(self.job_agent, MerchantAgent):
            summary.update({
                "business_type": self.job_agent.business_type,
                "negotiation_skill": self.job_agent.negotiation_skill,
                "shop_reputation": self.job_agent.shop_reputation,
                "has_active_shop": self.job_agent.active_shop is not None
            })
        elif isinstance(self.job_agent, ServiceProviderAgent):
            summary.update({
                "service_type": self.job_agent.service_type,
                "service_quality": self.job_agent.service_quality,
                "customer_satisfaction": self.job_agent.customer_satisfaction,
                "active_guests": len(self.job_agent.active_guests)
            })
        elif isinstance(self.job_agent, TraderAgent):
            summary.update({
                "trade_specialty": self.job_agent.trade_specialty,
                "negotiation_skill": self.job_agent.negotiation_skill,
                "inventory_items": len(self.job_agent.shop_inventory),
                "sales_records": len(self.job_agent.sales_record)
            })
        elif isinstance(self.job_agent, ProducerAgent):
            summary.update({
                "production_type": self.job_agent.production_type,
                "production_efficiency": self.job_agent.production_efficiency,
                "gathering_tools": self.job_agent.gathering_tools.copy()
            })
        
        return summary


class WorldJobMigrationHelper:
    """WorldクラスでのJobシステム移行を支援"""
    
    def __init__(self, world):
        self.world = world
        self.job_adapters: Dict[str, JobAgentAdapter] = {}
    
    def register_job_agent_for_migration(self, agent_id: str):
        """JobAgentを移行対象として登録"""
        agent = self.world.get_agent(agent_id)
        if isinstance(agent, JobAgent):
            self.job_adapters[agent_id] = JobAgentAdapter(agent)
            return True
        return False
    
    def migrate_agent_to_role_system(self, agent_id: str) -> Optional[Agent]:
        """指定されたエージェントをRoleシステムに移行"""
        if agent_id not in self.job_adapters:
            # まだ登録されていない場合は自動登録を試行
            if not self.register_job_agent_for_migration(agent_id):
                return None
        
        adapter = self.job_adapters[agent_id]
        new_agent = adapter.get_adapted_agent()
        
        # Worldのエージェントを置換
        self.world.agents[agent_id] = new_agent
        
        return new_agent
    
    def migrate_all_job_agents(self) -> Dict[str, Agent]:
        """全てのJobAgentをRoleシステムに移行"""
        migrated_agents = {}
        
        for agent_id, agent in self.world.agents.items():
            if isinstance(agent, JobAgent):
                new_agent = self.migrate_agent_to_role_system(agent_id)
                if new_agent:
                    migrated_agents[agent_id] = new_agent
        
        return migrated_agents
    
    def get_migration_summary(self) -> Dict[str, Any]:
        """移行状況のサマリーを取得"""
        total_agents = len(self.world.agents)
        job_agents = sum(1 for agent in self.world.agents.values() if isinstance(agent, JobAgent))
        role_agents = total_agents - job_agents
        registered_for_migration = len(self.job_adapters)
        
        return {
            "total_agents": total_agents,
            "job_agents": job_agents,
            "role_agents": role_agents,
            "registered_for_migration": registered_for_migration,
            "migration_adapters": {
                agent_id: adapter.get_job_skills_summary() 
                for agent_id, adapter in self.job_adapters.items()
            }
        } 