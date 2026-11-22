"""Being がいま入っている環境。環境が付けた識別子と、表示の名前で持つ (#1928、design_decisions D1928-2)。

Being にとって識別子は中身の分からない札で、同じ環境かを照合するのにだけ使う。同じシナリオの世界が 2 つ同時に立つと
表示の名前は重なるので、見分けるのは識別子にする。誰がどのプレイヤーを動かしているかはゲームの側の対応表が持つので、
Being はゲームのプレイヤーの番号を持たない。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import BeingAttachmentValidationException


def _require_text(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BeingAttachmentValidationException(f"BeingAttachment.{field_name} must be non-blank str, got {value!r}")


@dataclass(frozen=True)
class BeingAttachment:
    """同時に入れる環境は 1 つまで (``Being.attach``)。離れても経験は Being に残る。

    - ``environment_id``: 環境が付けた識別子 (例: ``mine_village_v1#1``)。照合にだけ使う
    - ``environment_name``: 環境の表示の名前 (例: 廃坑の山村)。エピソードに書く名前と同じ
    - ``known_facts``: この世界で知っていること。人柄に混ぜると、別の世界へ持ち越してしまう (D2222)
    """

    environment_id: str
    environment_name: str
    known_facts: str | None = None

    def __post_init__(self) -> None:
        _require_text("environment_id", self.environment_id)
        _require_text("environment_name", self.environment_name)
        if self.known_facts is not None:
            _require_text("known_facts", self.known_facts)


__all__ = ["BeingAttachment"]
