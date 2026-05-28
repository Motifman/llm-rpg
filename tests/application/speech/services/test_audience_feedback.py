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

    def test_clarity_breakdown_is_shown(self) -> None:
        """CLEAR / MUFFLED / FAINT の各人数が内訳として並ぶ。"""
        members = [
            _member(2, SoundClarityEnum.CLEAR),
            _member(3, SoundClarityEnum.MUFFLED),
            _member(4, SoundClarityEnum.MUFFLED),
            _member(5, SoundClarityEnum.FAINT),
        ]
        text = audience_summary_text(SpeechChannel.SHOUT, members)
        assert "4 名" in text  # 合計
        assert "明瞭に聞こえた 1 名" in text
        assert "くぐもって遠くから聞こえた 2 名" in text
        # FAINT は「内容は伝わっていない」を明示
        assert "内容は伝わっていない" in text and "1 名" in text

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

    def test_skips_zero_categories(self) -> None:
        """0 名のカテゴリ (CLEAR / MUFFLED / FAINT のうち該当なし) は内訳に
        含めない (情報量はそのまま、ノイズだけ減る)。"""
        members = [
            _member(2, SoundClarityEnum.CLEAR),
            _member(3, SoundClarityEnum.CLEAR),
        ]
        text = audience_summary_text(SpeechChannel.SAY, members)
        assert "2 名" in text
        assert "明瞭に聞こえた 2 名" in text
        assert "くぐもって" not in text
        assert "かすか" not in text
