from typing import Dict
from game.enums import Role, Permission


class ActionPermissionChecker:
    def __init__(self, spot_id: str):
        self.spot_id = spot_id
        self.role_permissions: Dict[Role, Permission] = {
            Role.CITIZEN: Permission.CUSTOMER,
            Role.ADVENTURER: Permission.CUSTOMER,
        }
        self.agent_permissions: Dict[str, Permission] = {}
    
    def set_role_permission(self, role: Role, permission: Permission):
        self.role_permissions[role] = permission
    
    def set_agent_permission(self, agent_id: str, permission: Permission):
        self.agent_permissions[agent_id] = permission
    
    def get_agent_permission(self, agent) -> Permission:
        if hasattr(agent, 'agent_id') and agent.agent_id in self.agent_permissions:
            return self.agent_permissions[agent.agent_id]
        
        if hasattr(agent, 'role') and agent.role in self.role_permissions:
            return self.role_permissions[agent.role]
        
        return Permission.GUEST
    
    def check_permission(self, agent, required_permission: Permission) -> bool:
        agent_permission = self.get_agent_permission(agent)
        
        permission_levels = {
            Permission.DENIED: 0,
            Permission.GUEST: 1,
            Permission.CUSTOMER: 2,
            Permission.MEMBER: 3,
            Permission.EMPLOYEE: 4,
            Permission.OWNER: 5
        }
        
        agent_level = permission_levels.get(agent_permission, 0)
        required_level = permission_levels.get(required_permission, 5)
        
        return agent_level >= required_level