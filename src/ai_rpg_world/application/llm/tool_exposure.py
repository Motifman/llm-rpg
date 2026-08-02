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
    - ``is_phase_common`` / ``is_available_in_phase``: いまのフェーズで
      どのブロックに置くか (会議境界で変わる)

    世界の側の判断だけがインスタンスの状態を要る。フェーズの側はツール名
    だけで決まるので静的メソッドにしてある。**この非対称がそのまま
    「run 中変わらないのはどちらか」を表している。**
    """

    disabled_by_scenario: FrozenSet[str] = frozenset()
    meeting_declared: bool = False
    synchronized_actions_declared: bool = False

    @classmethod
    def from_scenario(cls, scenario, *, meeting_declared: bool) -> "ToolExposure":
        """シナリオの宣言から組み立てる。

        ``meeting_declared`` を引数で受けるのは、会議の有効判定が runtime 側の
        設定と合成されているため。シナリオだけからは決まらない。
        """
        disabled = getattr(scenario, "disabled_tools", ()) or ()
        return cls(
            disabled_by_scenario=frozenset(disabled)
            if isinstance(disabled, (tuple, list, frozenset, set))
            else frozenset(),
            meeting_declared=bool(meeting_declared),
            synchronized_actions_declared=bool(
                getattr(scenario, "synchronized_action_groups", ()) or ()
            ),
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
        return True

    def filter_names(self, names: Iterable[str]) -> tuple:
        """この世界に在るツール名だけを宣言順で返す。"""
        return tuple(name for name in names if self.is_exposed(name))

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
        """
        if ToolExposure.is_phase_common(tool_name):
            return False
        if in_meeting:
            return tool_name in _MEETING_ONLY_TOOLS
        return tool_name not in _MEETING_ONLY_TOOLS
