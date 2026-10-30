"""採番・名前・表示状態に依存しない SNS の不変識別子。"""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from ai_rpg_world.domain.sns.exception.identity_token_exception import (
    SnsIdentityValidationException,
)


@dataclass(frozen=True)
class SnsIdentityToken:
    """新規作成時に発行し、保存した値を復元時にもそのまま使う。"""

    value: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        try:
            parsed = UUID(hex=self.value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise SnsIdentityValidationException("SNS の識別子は UUID4 の小文字32桁で指定してください") from exc
        if parsed.hex != self.value or parsed.version != 4:
            raise SnsIdentityValidationException("SNS の識別子は UUID4 の小文字32桁で指定してください")
