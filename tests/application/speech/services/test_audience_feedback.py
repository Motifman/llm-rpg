"""``audience_feedback`` の単体テスト (Issue #269 第17回 ②④)。

speaker に返すフィードバック文面が:
- 「届く範囲です」のような可能性語を使わない (発話後の事実報告)
- clarity 内訳 (CLEAR / MUFFLED / FAINT) を内訳として見せる
- 全員 FAINT のときは「内容は伝わっていない」を強調する
- 0 audience では channel ごとに次手の選択肢を提示する
"""

from __future__ import annotations

from ai_rpg_world.application.speech.services.audience_feedback import (
    audience_summary_text,
    zero_audience_text,
)
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceMember,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum


def _member(pid: int, clarity: SoundClarityEnum) -> SpeechAudienceMember:
    return SpeechAudienceMember(player_id=PlayerId.create(pid), clarity=clarity)


class TestZeroAudienceText:
    """audience 0 のときの channel-aware フィードバック。"""

    def test_say_zero_does_not_use_possibility_wording(self) -> None:
        """「届きます」のような可能性語ではなく、事実 + 次手を返す。"""
        text = zero_audience_text(SpeechChannel.SAY)
        # 旧文面の「say は ... のみに届きます」表現が消えていること
        assert "のみに届きます" not in text
        # 事実: 範囲内に他のプレイヤーはいなかった
        assert "他のプレイヤーがいませんでした" in text or "他のプレイヤーは" in text
        # 次手として shout を提案
        assert "shout" in text

    def test_shout_zero_does_not_imply_content_delivered(self) -> None:
        """shout 0 は「届きます」ではなく聞こえる範囲に人がいない事実を述べる。"""
        text = zero_audience_text(SpeechChannel.SHOUT)
        assert "範囲まで届きます" not in text
        assert "誰にも届きませんでした" in text

    def test_whisper_zero_suggests_other_channels(self) -> None:
        """whisper 0 は say/shout への切替案内を含む。"""
        text = zero_audience_text(SpeechChannel.WHISPER)
        assert "誰にも届きませんでした" in text
        assert "say" in text and "shout" in text


class TestAudienceSummaryText:
    """audience 1+ のときの clarity 内訳フィードバック。"""

    def test_uses_past_tense_for_delivery(self) -> None:
        """「届く範囲です」ではなく「届きました」を使う (発話後の事実)。"""
        members = [_member(2, SoundClarityEnum.CLEAR)]
        text = audience_summary_text(SpeechChannel.SAY, members)
        assert "届く範囲です" not in text
        assert "届きました" in text

    def test_clarity_breakdown_uses_label_form(self) -> None:
        """Issue #276 後続: 「内訳: 明瞭=A / ぼんやり=M / かすか=F」のラベル形式。

        旧 "くぐもって遠くから聞こえた N 名" のような従属節形式は N=1 で
        日本語が破綻するため、固定のラベル風内訳に変えた。
        "くぐもり" 表現は日常語の "ぼんやり" に置き換える。
        """
        members = [
            _member(2, SoundClarityEnum.CLEAR),
            _member(3, SoundClarityEnum.MUFFLED),
            _member(4, SoundClarityEnum.MUFFLED),
            _member(5, SoundClarityEnum.FAINT),
        ]
        text = audience_summary_text(SpeechChannel.SHOUT, members)
        # 「あなたの声は 4 名に届きました。」が骨子
        assert "あなたの声は 4 名に届きました" in text
        # ラベル形式
        assert "明瞭=1" in text
        assert "ぼんやり=2" in text
        assert "かすか=1" in text
        # 旧ラベル「くぐもり」は使わない (くぐも… が混じらない)
        assert "くぐも" not in text
        # かすか > 0 のときは内容が伝わっていないことを補足
        assert "内容は伝わっていない" in text

    def test_clarity_label_omits_note_when_no_faint(self) -> None:
        """かすか=0 のときは「内容は伝わっていない」補足を付けない。"""
        members = [
            _member(2, SoundClarityEnum.CLEAR),
            _member(3, SoundClarityEnum.MUFFLED),
        ]
        text = audience_summary_text(SpeechChannel.SHOUT, members)
        assert "明瞭=1" in text
        assert "ぼんやり=1" in text
        assert "かすか=0" in text
        assert "内容は伝わっていない" not in text

    def test_all_faint_warns_content_not_delivered(self) -> None:
        """全員 FAINT のときは「内容は伝わっていない」を強調し、shout / 接近を提案。"""
        members = [
            _member(2, SoundClarityEnum.FAINT),
            _member(3, SoundClarityEnum.FAINT),
        ]
        text = audience_summary_text(SpeechChannel.SAY, members)
        assert "内容は伝わっていません" in text
        assert "2 名" in text
        # 提案
        assert "shout" in text or "近づいて" in text

    def test_zero_audience_delegates_to_zero_text(self) -> None:
        """0 名で呼ばれたら zero_audience_text と同じ内容を返す。"""
        text_say = audience_summary_text(SpeechChannel.SAY, [])
        assert text_say == zero_audience_text(SpeechChannel.SAY)

    def test_whisper_audience_is_simple(self) -> None:
        """WHISPER は常に同 spot 1 名なので CLEAR 確定。シンプルな文面でよい。"""
        members = [_member(2, SoundClarityEnum.CLEAR)]
        text = audience_summary_text(SpeechChannel.WHISPER, members)
        assert "囁きが届きました" in text

    def test_single_listener_grammar_is_natural(self) -> None:
        """N=1 でも日本語が破綻しないことの回帰テスト
        (旧 "1 名に届きました（くぐもって遠くから聞こえた 1 名）" の不自然さ対策)。
        """
        members = [_member(2, SoundClarityEnum.MUFFLED)]
        text = audience_summary_text(SpeechChannel.SAY, members)
        # 旧形式の従属節は出ない
        assert "（くぐもって遠くから聞こえた 1 名）" not in text
        # 新形式: 1 名に届きました。内訳: 明瞭=0 / ぼんやり=1 / かすか=0
        assert "あなたの声は 1 名に届きました" in text
        assert "明瞭=0" in text
        assert "ぼんやり=1" in text
        assert "かすか=0" in text
