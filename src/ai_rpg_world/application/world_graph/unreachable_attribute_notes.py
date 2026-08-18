"""永久に扱えない物体に添える注記を組む。

## なぜ engine が組むか

シナリオは条件ごとに ``failure_message`` を書いている。ところがその文面は
**呼んだ人ひとりへの応答**として書かれていて、**一覧に常時出る注記**としては
書かれていない。実際に描画して分かったのは、市場町の文面が

    窯の火加減も捏ね方も分からない。パンを焼けるのは**あの人**だけだ。

となっていることで、常時表示に置くと「あの人」が誰か分からず、しかも焼き手は
2 人いるのに単数で書かれている。**書かれた場所と使う場所がずれた文面の流用**は
`tend_to_player` / `give_item` で踏んだ形と同じなので、ここでは流用しない。

## engine が決め打ちしてよいのは型だけ

出すのは ``<値の呼び名>だけが扱える`` という型で、**呼び名は作者が書いたもの**を
そのまま使う。属性の種類は engine が知らないままにする。

型を ``<呼び名>の仕事`` にしかけて差し戻した。生業なら通るが、``race`` を同じ
経路に通すと「エルフの仕事」になる。**engine が属性の種類を決め打ちすると
嘘になる。**

呼び名が宣言されていなければ ``いまのあなたには扱えない`` に落とす。ここで
「あなたの生業では」と書くと、生業以外の属性で同じ嘘をつく。**世界が名前を
持っていないものを、engine が代わりに名付けない。**
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
    UnreachableRequirement,
)

from .hidden_interaction_filter import failed_actor_hidden_requirements

#: 呼び名が宣言されているときの型。
_ONLY_THEY_CAN_USE_IT = "{value_display_name}だけが扱える"

#: 呼び名が無いときの型。**属性の種類を言わない。**
_NO_NAME_FOR_IT = "いまのあなたには扱えない"


def _note_for(requirement: UnreachableRequirement) -> str:
    name = requirement.value_display_name
    if not name:
        return _NO_NAME_FOR_IT
    return _ONLY_THEY_CAN_USE_IT.format(value_display_name=name)


def unreachable_attribute_notes(
    interactions: Iterable[Any],
    actor_state: Optional[Mapping[str, Any]],
    specs: Optional[PlayerAttributeSpecs],
) -> Tuple[str, ...]:
    """その物体について、**永久に届かない**ことだけを注記にして返す。

    伏せた条件が要求している属性のうち、``PlayerAttributeSpecs`` が
    「変えられない」と宣言しているものだけを拾う。

    **公開されている属性だけを出す。** 伏せた属性 (役割・変装) の要求は
    注記にしない。かつ、伏せた属性が混ざっていても**公開されているぶんは
    そのまま出す**。混在を理由に全部伏せると、公開側の出力が伏せた属性の
    有無で変わり、**そこから伏せた属性の存在が読める**。

    **まだ変えられる要求は返さない。** 「いまは満たしていないが、いずれ
    通る」ものに注記を付けると、伏せた条件の存在が漏れるうえ、注記が
    無いこと自体が正しい情報である状態を壊す。
    """
    if specs is None or not specs.by_name:
        return ()
    notes: list[str] = []
    for interaction in interactions or ():
        for required_state in failed_actor_hidden_requirements(
            interaction, actor_state
        ):
            for requirement in specs.unreachable_requirements(
                required_state, actor_state
            ):
                if not requirement.is_public:
                    continue
                note = _note_for(requirement)
                # 同じ値を要求する action が 2 つある物体で、同じ注記が
                # 2 回並ばないようにする。物体単位の注記なので、何回
                # 要求されたかは読み手にとって情報ではない。
                if note not in notes:
                    notes.append(note)
    return tuple(notes)


__all__ = ["unreachable_attribute_notes"]
