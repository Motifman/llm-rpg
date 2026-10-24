"""確定後の配送の用途・保証と、受け手の失敗の知らせ先。"""

from collections.abc import Callable
from enum import Enum

from ai_rpg_world.eventing.domain_event import DomainEvent


class DeliveryChannel(str, Enum):
    """commit後handlerの用途を表す。"""

    OBSERVATION = "observation"
    READ_MODEL = "read_model"
    INTEGRATION = "integration"
    AUXILIARY = "auxiliary"


class DeliveryGuarantee(str, Enum):
    """commit後handlerの失敗に必要な配送保証を表す。"""

    DURABLE_RETRY = "durable_retry"
    BEST_EFFORT = "best_effort"


AfterCommitHandler = Callable[[DomainEvent], None]
AfterCommitFailureObserver = Callable[
    [DeliveryChannel, DeliveryGuarantee, DomainEvent, object, Exception],
    None,
]
