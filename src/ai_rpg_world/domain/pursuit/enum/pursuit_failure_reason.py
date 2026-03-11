from enum import Enum


class PursuitFailureReason(Enum):
    """追跡失敗の構造化理由。"""

    TARGET_MISSING = "target_missing"
    PATH_UNREACHABLE = "path_unreachable"
    VISION_LOST_AT_LAST_KNOWN = "vision_lost_at_last_known"
