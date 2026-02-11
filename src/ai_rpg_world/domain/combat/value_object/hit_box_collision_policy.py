from enum import Enum


class TargetCollisionPolicy(Enum):
    """ターゲットに衝突した際のHitBox挙動"""
    KEEP_ACTIVE = "keep_active"
    DEACTIVATE = "deactivate"


class ObstacleCollisionPolicy(Enum):
    """障害物に衝突した際のHitBox挙動"""
    PASS_THROUGH = "pass_through"
    DEACTIVATE = "deactivate"
