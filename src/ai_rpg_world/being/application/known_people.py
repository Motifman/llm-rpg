"""Being が知っている人を、プロンプトの【知っている人】の文に描く。"""

from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.being.domain.acquaintance import Acquaintance


def render_known_people(
    acquaintances: Iterable[Acquaintance], *, environment_name: str
) -> str:
    """描くのは、知ったときに決まって変わらない名前と関係の注記だけ。

    会った回数のように会うたびに変わるものを描くと、毎ターンのメッセージの
    この節から後ろのキャッシュが、会うたびに切れる。名前を知らずに会った相手は
    名前を描けないので並べない。
    """
    return "\n".join(
        f"- {a.name}（{a.relation_note}）" if a.relation_note else f"- {a.name}"
        for a in acquaintances
        if a.environment_name == environment_name and a.knows_name
    )


__all__ = ["render_known_people"]
