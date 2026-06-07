"""PR β (実験 #29 後続): 疲労 severe 以上のときに発話 content が朦朧化されること。

- fatigue < 85: blur 適用なし (LLM が渡した content がそのまま speech_service に流れる)
- fatigue >= 85: 語単位で確率的に ``…`` へ伏字化された content が流れる
- player_status_repository が None: blur 機能は無効 (後方互換)
- status read 失敗: 例外は静かに無視し、原文のまま発話する
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.speech_executor import (
    SpeechToolExecutor,
    _apply_speech_blur,
)


class _FakeStatus:
    """``PlayerStatusRepository.find_by_id`` の戻り値 stub。"""

    def __init__(self, fatigue_value: int) -> None:
        self.fatigue_value = fatigue_value


class _FakeStatusRepo:
    def __init__(self, fatigue_value: int) -> None:
        self._status = _FakeStatus(fatigue_value)

    def find_by_id(self, _player_id):
        return self._status


class _RaisingStatusRepo:
    def find_by_id(self, _player_id):
        raise RuntimeError("repo down")


class TestSpeechBlurThreshold:
    """fatigue tier に応じた発話 content の朦朧化挙動。"""

    def test_fatigue_below_threshold_keeps_content_verbatim(self) -> None:
        """fatigue 60 (fatigued tier) は blur 対象外。原文が speak に渡る。"""
        speech_service = MagicMock()
        executor = SpeechToolExecutor(
            speech_service=speech_service,
            player_status_repository=_FakeStatusRepo(60),
            rng=random.Random(1),
        )
        executor._execute_speech(
            player_id=7,
            args={"channel": "say", "content": "枯葉を 探しに 行ってくる"},
        )
        speak_call = speech_service.speak.call_args
        assert speak_call.args[0].content == "枯葉を 探しに 行ってくる"

    def test_fatigue_at_severe_threshold_blurs_content(self) -> None:
        """fatigue 85 (severe tier) で語単位の伏字化が起きる。"""
        speech_service = MagicMock()
        executor = SpeechToolExecutor(
            speech_service=speech_service,
            player_status_repository=_FakeStatusRepo(85),
            rng=random.Random(2),
        )
        executor._execute_speech(
            player_id=7,
            args={"channel": "say", "content": "枯葉を 探しに 行ってくる"},
        )
        blurred = speech_service.speak.call_args.args[0].content
        assert "…" in blurred
        assert blurred != "枯葉を 探しに 行ってくる"

    def test_exhausted_also_blurs(self) -> None:
        """fatigue 100 (exhausted tier) も blur 対象。"""
        speech_service = MagicMock()
        executor = SpeechToolExecutor(
            speech_service=speech_service,
            player_status_repository=_FakeStatusRepo(100),
            rng=random.Random(3),
        )
        executor._execute_speech(
            player_id=7,
            args={"channel": "say", "content": "助けて 助けて"},
        )
        assert "…" in speech_service.speak.call_args.args[0].content


class TestSpeechBlurResilience:
    """blur 機構が壊れていても発話自体は止まらないこと。"""

    def test_missing_status_repo_disables_blur(self) -> None:
        """player_status_repository=None なら原文のまま流れる (後方互換)。"""
        speech_service = MagicMock()
        executor = SpeechToolExecutor(
            speech_service=speech_service,
            player_status_repository=None,
            rng=random.Random(1),
        )
        executor._execute_speech(
            player_id=7,
            args={"channel": "say", "content": "原文"},
        )
        assert speech_service.speak.call_args.args[0].content == "原文"

    def test_status_read_failure_falls_back_to_original_content(self) -> None:
        """status repo が例外を投げても発話は原文で続行する。"""
        speech_service = MagicMock()
        executor = SpeechToolExecutor(
            speech_service=speech_service,
            player_status_repository=_RaisingStatusRepo(),
            rng=random.Random(1),
        )
        executor._execute_speech(
            player_id=7,
            args={"channel": "say", "content": "原文"},
        )
        assert speech_service.speak.call_args.args[0].content == "原文"


class TestApplySpeechBlur:
    """``_apply_speech_blur`` 単体の振る舞い。"""

    def test_all_masked_returns_original(self) -> None:
        """全語が伏字化される seed では空白化を避けて原文を返す。"""
        # mask_rate=0.30 の確率で 1 語以上は残る seed を選ぶのが本来だが、
        # ここは「全 mask → 原文 fallback」を担保するため、固定 rng で
        # 「全部 mask」を強制した代替実装で確認する。
        rng = random.Random()
        rng.random = lambda: 0.0  # 常に mask 側に分岐
        result = _apply_speech_blur("あ い う", rng=rng)
        assert result == "あ い う"

    def test_no_mask_returns_original(self) -> None:
        """rng が常に閾値以上を返すと一切 blur されない。"""
        rng = random.Random()
        rng.random = lambda: 0.99
        assert _apply_speech_blur("こんにちは", rng=rng) == "こんにちは"

    def test_separators_are_preserved(self) -> None:
        """句読点・スペースなどの区切りは語が伏字化されても残る。"""
        rng = random.Random()
        rng.random = lambda: 0.0
        # 全語 mask されても、区切り文字 (、。) は元位置に残る
        assert _apply_speech_blur("ね、いいよ。", rng=rng) == "…、…。"
