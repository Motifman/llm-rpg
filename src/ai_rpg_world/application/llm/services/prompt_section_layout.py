"""フェーズごとに、どのセクションをどの順で出すかを 1 か所で決める。

## なぜ表にするか

会議中のプロンプトが探索中とまったく同じだった。使えない接続先やオブジェクト
が並び、「give_item で渡せる」という嘘の案内も出る (実 run 009)。

各ビルダの中で ``is_meeting`` を見る形にはしない。**今日 2 回踏んだ「判断が
散る」形そのもの**だから。

- 死の観測: 到達範囲の判定が strategy ごとに手書きで、発話の経路が漏れた
- ツールの出し分け: 判定が定義側にしか無く、dispatch が見ていなかった

どちらも「1 か所に集めたら直った」。セクションでも同じことをする。
``ToolExposure`` (#922) と同じ形にして、読む人が 2 つ目の流儀を覚えずに済む
ようにする。

## シナリオには宣言させない

「接続先」「オブジェクト」は engine 側の概念で、シナリオがその名前を知ると
**むしろ結合が増える**。シナリオが持つのは部屋やオブジェクトの名前と
description で、どのセクションを出すかは engine の判断。

会議のセクションは、シナリオが ``meeting`` を宣言した世界にしか現れない。
engine が勝手に会議の概念を持ち込むことはない。

## 中身が変わるセクションは、別のビルダにする

同席者行は自由時間では行動つき、会議では名前と生死だけ。**ビルダの中に
分岐を入れない。** 同じ位置に別のビルダを置く。
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Tuple

from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase


class PromptSection(str, Enum):
    """プロンプトに出る節。

    **足したらこの enum に入れる。** 入れ忘れると、どのフェーズの並びにも
    載らず黙って消える。網羅テストが「どこにも割り当てられていない節」を
    落とす。
    """

    CONNECTIONS = "connections"
    OBJECTS = "objects"
    SUB_LOCATIONS = "sub_locations"
    #: 同席者 + その相手にできること。
    ENTITIES_WITH_ACTIONS = "entities_with_actions"
    #: 同席者の名前と生死だけ。会議で「誰に投票できるか」を読むための形。
    ENTITIES_PLAIN = "entities_plain"
    MONSTERS = "monsters"
    #: 現在地に居る NPC 商人と、その品揃え・価格。
    MERCHANTS = "merchants"
    MARKET_BOARD = "market_board"
    #: 行動者本人の所持金。
    GOLD = "gold"
    #: 自分宛てに来ている取引の申し出。
    TRADE_OFFERS = "trade_offers"
    INVENTORY = "inventory"
    GROUND_ITEMS = "ground_items"
    NEEDS = "needs"
    ACTIVE_EFFECTS = "active_effects"
    AGENT_STATUS = "agent_status"


#: 自由時間の並び。従来どおり。
FREE_ROAM_SECTIONS: Tuple[PromptSection, ...] = (
    PromptSection.CONNECTIONS,
    PromptSection.OBJECTS,
    PromptSection.SUB_LOCATIONS,
    PromptSection.ENTITIES_WITH_ACTIONS,
    PromptSection.MONSTERS,
    # 商人と所持金は、その場に在るもの (オブジェクト・同席者) と自分の持ち物の
    # 間に置く。売買は「目の前の商人」と「自分の財布」を突き合わせる判断なので、
    # 2 つが離れていると読み直しが要る。
    PromptSection.MERCHANTS,
    # 市場の掲示板は商人の隣。どちらも「いくらで買えるか」を読む節で、
    # 所持金と突き合わせる判断も同じ。離すと読み直しが要る。
    PromptSection.MARKET_BOARD,
    PromptSection.GOLD,
    # 自分宛ての申し出は、所持金と持ち物の間に置く。「何を求められているか」は
    # 手元の在庫と突き合わせて判断するので、離すと読み直しが要る。
    PromptSection.TRADE_OFFERS,
    PromptSection.INVENTORY,
    PromptSection.GROUND_ITEMS,
    PromptSection.NEEDS,
    PromptSection.ACTIVE_EFFECTS,
    PromptSection.AGENT_STATUS,
)

#: 会議中の並び。
#:
#: 落とすのは **その場で選べない対象**。接続先は移動の列、オブジェクトは
#: interact の対象で、会議中はどちらも出していない (#948 で実行もできない)。
#: 出したままだと「選べるのに必ず失敗する手」が並ぶ (#860 で潰した形)。
#:
#: 地図はシステムプロンプトにあるので、接続先を落としても**空間の推論は
#: 失われない** (#949)。Among Us と同じく、消えるのは操作であって知識ではない。
#:
#: 同席者は残す。**誰に投票できるかを読む唯一の手がかり**で、倒れている人が
#: 誰かもここに出る。ただし行動は付けない。
#:
#: 所持品と身体の状態は残す。会議での主張の材料になる (「ランタンを持って
#: いたのは俺だ」)。
#:
#: **落とす節すべてに理由を書く。** 黙って外すと消えたことに誰も気づけない
#: (claude の指摘。当初 MONSTERS と GROUND_ITEMS が無言で消えていた)。
#:
#: - SUB_LOCATIONS: 移動の一種で、会議中は動けない
#: - MONSTERS: 判断が割れた。軸は「消えるのは操作であって知識ではない」なので
#:   残すほうが筋だが、**会議は招集者の場所に全員を集める**ので、そこに
#:   モンスターが居る状況は「議論どころではない」。この世界には 1 体も
#:   居らず、居る世界で会議を開いた実例もまだ無い。**出す形を決める材料が
#:   無いので、いまは落として run で必要になったら戻す**
#: - GROUND_ITEMS: 同じ理由で判断を保留する。所持品を残した理屈 (主張の材料)
#:   はこちらにも当てはまるので、**戻す可能性が高いのはこちら**
#: - TRADE_OFFERS: 取引ツールも会議中は出ないので、節だけ残すと「見えるのに
#:   手が無い」状態になる。MERCHANTS と同じ理屈で落とす
#: - MARKET_BOARD: 会議中は市場ツールも出ないので、節だけ残すと「見える
#:   のに手が無い」状態になる。MERCHANTS と同じ理屈で落とす
#: - MERCHANTS: 会議中は売買できないので、選べない対象として落とす
#:   (オブジェクトと同じ扱い)。商人が議論の話題になる余地はあるが、
#:   それは記憶と発話の側の話で、いまここで買える一覧を出す理由にはならない
MEETING_SECTIONS: Tuple[PromptSection, ...] = (
    PromptSection.ENTITIES_PLAIN,
    # 所持金は残す。所持品を残した理屈 (会議での主張の材料になる) が
    # そのまま当てはまる (「その金はどこで手に入れた」)。
    PromptSection.GOLD,
    PromptSection.INVENTORY,
    PromptSection.NEEDS,
    PromptSection.ACTIVE_EFFECTS,
    PromptSection.AGENT_STATUS,
)

#: どのフェーズにも出さない節。**理由つきでここに書く。**
#:
#: 空にしておく。載せる場合は「なぜどの並びにも要らないか」を書く。
#: 黙って両方の表から外すと、消えたことに誰も気づけない。
INTENTIONALLY_UNUSED: FrozenSet[PromptSection] = frozenset()


#: フェーズ → その並び。
#:
#: **真偽値で引かない。** ``in_meeting`` のような bool にすると、フェーズが
#: 3 つ目になったときに**黙って自由時間へ縮退する**。GamePhase を直接キーに
#: して、網羅テストで全 enum が載っていることを縛る (codex の指摘)。
SECTIONS_BY_PHASE: Dict[GamePhase, Tuple[PromptSection, ...]] = {
    GamePhase.FREE_ROAM: FREE_ROAM_SECTIONS,
    GamePhase.MEETING: MEETING_SECTIONS,
}


def sections_for(phase: GamePhase) -> Tuple[PromptSection, ...]:
    """そのフェーズで出す節を、出す順に返す。

    知らないフェーズは例外にする。**自由時間へ縮退させると、新しい
    フェーズで使えない対象が並び続けることに誰も気づけない。**
    """
    try:
        return SECTIONS_BY_PHASE[phase]
    except KeyError as exc:
        raise KeyError(
            f"{phase} の並びが prompt_section_layout に登録されていません"
        ) from exc
