"""この世界で LLM にどのツールを出すかを 1 か所で決める。

## なぜ集めるか

ツールを出す / 出さないの判断が、**ツール定義を組む場所にしか無かった**。
プロンプト本文の側にはツール名を宣伝する箇所が別にあり、そちらは判断を
見ていない。結果、シナリオが `disabled_tools` で無効化しても

    - "セナ" (倒れて動かない) [持ち物を奪う, 介抱して起こす (tend_to_player)]

のように**行動候補として宣伝され続ける**。エージェントはこれを選び、
存在しないツールを呼ぶ。無効化しないより悪い。

    同じ場所にいるプレイヤー: (倒れていない相手には give_item で…)

こちらも同じ形。宣言が半分しか効いていない状態は、#914 / #917 の死の観測で
2 回踏んだのと同じ穴。

## ここに置くのは「世界ごとに変わらない」判断だけ

判断は 2 段ある。``is_exposed`` が「この世界に在るか」(run 中ずっと同じ)、
``is_available_in_phase`` が「いまのフェーズで出すか」(会議境界で変わる)。

**分けたまま同じファイルに置く。** 別ファイルに散らすと、ツールを 1 つ
足した人が片方だけ見て終わる。混ぜると、プレフィックスキャッシュ
(設計判断 #1) にとって重要な「run 中変わらない」性質が見えなくなる。

| 判断 | run 中の変化 | ここに置くか |
|---|---|---|
| シナリオが無効化した (`disabled_tools`) | 変わらない | 置く |
| 会議機構を宣言していない | 変わらない | 置く |
| 同時行動を宣言していない (`prepare_action`) | 変わらない | 置く |
| いま会議フェーズか | **変わる** | 置く (別のメソッドで) |
| 記憶ツールの実験設定 | 変わらない | 置かない (世界ではなく実験の設定) |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable

#: 同時行動を宣言したシナリオでだけ出すツール。
_SYNCHRONIZED_ACTION_TOOLS = frozenset({"prepare_action"})

#: 商人を宣言したシナリオでだけ出すツール (経済統合 Phase 1)。
#:
#: 宣言の無い世界に売買が並ぶと、対象候補が永久に空なのに毎ターン選択肢へ
#: 載る。会議を宣言しない世界から投票を落とすのと同じ判断。
_ECONOMY_TOOLS = frozenset({"buy_item", "sell_item"})

#: エージェント同士の取引を宣言したシナリオでだけ出すツール (Phase 2)。
#:
#: 商人 (_ECONOMY_TOOLS) とは別の集合にする。商人の居る町でも「人同士の取引は
#: しない」世界はありえるし、逆もある。
_PLAYER_TRADE_TOOLS = frozenset({"trade_offer", "trade_accept", "trade_decline"})

#: 市場を宣言したシナリオでだけ出すツール (Phase 3)。
#:
#: 商人・同席取引とはさらに別の集合にする。3 つは独立に選べる (商人だけ居る町、
#: 人同士の取引だけある集落、板だけがある市場、どれもありえる)。
#:
#: **同席はここで見ない。** 板から離れていてもツールは出したままにする。
#: 出したり消したりすると、エージェントから見て世界の可能性が揺れる。板の
#: 手前まで来ているのに選択肢に無い、という形も生まれる。同席は実行時の失敗
#: (`MARKET_BOARD_NOT_HERE`) として返す — 商人と同じ流儀。
_MARKET_TOOLS = frozenset({
    "market_list_item", "market_buy", "market_reprice", "market_cancel",
    "market_bid", "market_sell",
})

#: 会議機構を宣言したシナリオでだけ出すツール。
#:
#: 「会議フェーズでだけ出す」(`_MEETING_ONLY_TOOLS`) とは軸が違う。
#: `report_body` は自由時間に出るが、会議を持たない世界では出したくない。
#: 2 つを 1 つの集合で兼ねると、report_body をいつ出すかの判断と、そもそも
#: 会議がある世界かの判断が混ざる。
_MEETING_TOOLS = frozenset({"vote", "report_body"})

#: フェーズを問わず出すツール。会議中に残るのはこれだけ。
#:
#: 話す手段が無いと会議そのものが成立しない。listen と wait は「黙って
#: 様子を見る」を潰さないために残す (棄権や保留を選べることは
#: agent_design_principles の「取れる手段の質」に効く)。
#:
#: tend_to_player も共通に置く。倒れている相手を報告すると全員がその場所に
#: 集まる (report_body は報告者と対象の同席を要求する) のに、手当てだけ
#: できない状態になっていた。隣に倒れている人が居るのに助け起こせないのは、
#: #848 で置いた「倒れているだけの相手は蘇生できる」という判断と衝突する。
#: #860 の行ゲートが「同席かつ行動不能な相手が居るときだけ」に絞っている
#: ので、露出は広がらない。
#:
#: 蘇生の無い世界 (`grace_ticks: 0`) は、シナリオが `disabled_tools` で
#: 落とす。engine 側でここから外すと、蘇生のある世界を壊す。
PHASE_COMMON_TOOLS = frozenset({"speak", "listen", "wait", "tend_to_player"})

#: 生死・フェーズ・投票状態を問わず、実際の tools payload の先頭へ置く順序。
#:
#: ``listen`` と ``tend_to_player`` は状態やシナリオで落ちうるため含めない。
#: 状態依存の名前をここへ混ぜると、一つ消えただけで後続の長い定義すべてが
#: プレフィックスキャッシュから外れる。spot / memory という定義元を越えた
#: 最終順序なので、呼び出し側へ同じ列を書き写さない。
ALWAYS_PRESENT_TOOL_ORDER = (
    "wait",
    "speak",
    "memo_add",
    "memo_list",
    "memo_done",
)

#: 常在ブロック以後で、状態により出入りする既知ツールの順序。
_CONDITIONAL_TOOL_ORDER = (
    "listen",
    "travel_to",
    "interact",
    "prepare_action",
    "drop_item",
    "pickup_item",
    "give_item",
    # 人同士の取引は give_item の隣に置く。無償の受け渡しと条件つきの交換は
    # 同じ「相手に物を渡す」系統で、読む側にとって近い位置が自然。
    "trade_offer",
    "trade_accept",
    "trade_decline",
    # 売買は既存ツールの後ろへ足す。既存の相対順を動かすと、payload 先頭から
    # の一致が切れて過去 run と比較できなくなる。
    "buy_item",
    "sell_item",
    # 市場は商人との売買の後ろ。どちらも「品と金を動かす」系統で近い。
    "market_list_item",
    "market_buy",
    "market_bid",
    "market_reprice",
    "market_cancel",
    "market_sell",
    "report_body",
    "vote",
)

_PAYLOAD_TOOL_ORDER = ALWAYS_PRESENT_TOOL_ORDER + _CONDITIONAL_TOOL_ORDER

#: 会議フェーズでだけ出すツール。自由時間では出さない。
#:
#: 共通ブロックには入れない。自由時間に vote が並ぶと「いつでも投票できる」
#: と読め、会議の外で試して失敗し続ける (#860 で潰した形)。
_MEETING_ONLY_TOOLS = frozenset({"vote"})


@dataclass(frozen=True)
class ToolExposure:
    """ツールを出すかどうかの問いに、ここだけで答える。

    問いは 2 つあり、混ぜない。

    - ``is_exposed``: そもそもこの世界に在るか (run 中ずっと同じ)
    - ``split_for_phase``: いまのフェーズと本人の投票状態から、どの
      ブロックに置くか

    静的な世界宣言と、フェーズ・本人ごとに変わる利用可否を同じ入口で合成する。
    個別判定を呼び出し側へ散らすと、実際の LLM payload だけが条件を通らない
    経路が再び生まれる。
    """

    disabled_by_scenario: FrozenSet[str] = frozenset()
    meeting_declared: bool = False
    synchronized_actions_declared: bool = False
    merchants_declared: bool = False
    player_trade_declared: bool = False
    market_declared: bool = False

    @classmethod
    def from_scenario(cls, scenario, *, meeting_declared: bool) -> "ToolExposure":
        """シナリオの宣言から組み立てる。

        ``meeting_declared`` を引数で受けるのは、会議の有効判定が runtime 側の
        設定と合成されているため。シナリオだけからは決まらない。
        """
        disabled = getattr(scenario, "disabled_tools", ()) or ()
        if not isinstance(disabled, (tuple, list, frozenset, set)):
            # loader は必ず tuple を返す。ここに来るのは契約違反なので落とす。
            #
            # 空集合へ黙って縮退させると、**誤った代役を使っているテストが
            # 緑のまま通る**。「宣言したつもりが効いていない」を作るのは
            # この PR が直している穴そのもの。
            raise TypeError(
                "scenario.disabled_tools は tuple / list / set で渡してください: "
                f"{type(disabled).__name__}"
            )
        return cls(
            disabled_by_scenario=frozenset(disabled),
            meeting_declared=bool(meeting_declared),
            synchronized_actions_declared=bool(
                getattr(scenario, "synchronized_action_groups", ()) or ()
            ),
            merchants_declared=bool(getattr(scenario, "merchants", ()) or ()),
            player_trade_declared=bool(
                getattr(scenario, "player_trade_enabled", False)
            ),
            market_declared=getattr(scenario, "market", None) is not None,
        )

    def is_exposed(self, tool_name: str) -> bool:
        """この世界に ``tool_name`` が存在するか。"""
        if tool_name in self.disabled_by_scenario:
            return False
        if tool_name in _MEETING_TOOLS and not self.meeting_declared:
            return False
        if (
            tool_name in _SYNCHRONIZED_ACTION_TOOLS
            and not self.synchronized_actions_declared
        ):
            return False
        if tool_name in _ECONOMY_TOOLS and not self.merchants_declared:
            return False
        if tool_name in _PLAYER_TRADE_TOOLS and not self.player_trade_declared:
            return False
        if tool_name in _MARKET_TOOLS and not self.market_declared:
            return False
        return True

    def filter_names(self, names: Iterable[str]) -> tuple:
        """この世界に在るツール名だけを宣言順で返す。"""
        return tuple(name for name in names if self.is_exposed(name))

    @staticmethod
    def order_for_payload(names: Iterable[str]) -> tuple:
        """定義元を越えて、実際の tools payload に使う安定順を返す。

        既知の順序を先に置き、それ以外は入力順を保つ。新しいツールを追加した
        ときに黙って消さず、状態間で不変な既存ブロックを先頭に維持する。
        """
        original = tuple(names)
        present = frozenset(original)
        ordered = tuple(name for name in _PAYLOAD_TOOL_ORDER if name in present)
        known = frozenset(_PAYLOAD_TOOL_ORDER)
        return ordered + tuple(name for name in original if name not in known)

    def split_for_phase(
        self,
        names: Iterable[str],
        *,
        in_meeting: bool,
        voting_completed: bool,
    ) -> tuple:
        """(共通ブロック, フェーズ固有ブロック) を返す。**通常はこれを使う。**

        2 つの問いを両方通す入口。``is_available_in_phase`` だけを呼ぶと
        **無効化したツールが出る**。名前からは「フェーズで出すか」としか
        読めないので、``is_exposed`` を先に通す必要があると気づけない。

        1 つの宣言が複数箇所へ手書きで反映される、というのがこの仕組みの
        敵なので、同じ形をクラスの内側に作らない。個別メソッドは残すが、
        既定の入口はこちら。
        """
        exposed = [name for name in names if self.is_exposed(name)]
        return (
            tuple(n for n in exposed if self.is_phase_common(n)),
            tuple(
                n
                for n in exposed
                if self.is_available_in_phase(n, in_meeting=in_meeting)
                and not (n == "vote" and voting_completed)
            ),
        )

    @staticmethod
    def is_phase_common(tool_name: str) -> bool:
        """フェーズを問わず出すツールか。"""
        return tool_name in PHASE_COMMON_TOOLS

    @staticmethod
    def is_available_in_phase(tool_name: str, *, in_meeting: bool) -> bool:
        """いまのフェーズで、フェーズ固有ブロックに出すツールか。

        共通ブロックのツールはここでは扱わない。並び順を
        [共通] → [記憶] → [フェーズ固有] に固定してあり、会議境界で
        入れ替わるのは末尾だけにしたい (先頭がプレフィックスキャッシュに
        残る)。共通と固有を 1 つの判定に混ぜると、この並びが崩れる。

        ``memo_add`` などの記憶ツールは実験設定から別経路で追加され、
        ``split_for_phase`` を通らない。そのため、このメソッドが ``False`` を
        返しても、記憶ツールを有効にした実際の会議 payload には残る。
        """
        if ToolExposure.is_phase_common(tool_name):
            return False
        if in_meeting:
            return tool_name in _MEETING_ONLY_TOOLS
        return tool_name not in _MEETING_ONLY_TOOLS
