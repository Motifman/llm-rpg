"""反復失敗の証拠が、エージェントの語彙で書かれていることを保証する。

## なぜこの試験が要るか

``StructuredFailureEvidenceTranscriber`` は反復失敗を意味記憶の証拠に転記する。
以前はその本文に **error_code をそのまま埋めていた**。

    「interact」が「INTERACTION_PRECONDITION_FAILED」を3回反復した。

``INTERACTION_PRECONDITION_FAILED`` はエージェントの語彙ではない。実 run の
``belief_consolidation`` を読むと、統合を判断する LLM がこの証拠を

    「システムエラーの繰り返しであり、学習すべき内容ではない。」
    「システムエラーによる失敗で、学習すべき行動指針が得られない」

と書いて捨てていた。**4 run で独立に同じ判断が出ている。** 反復した失敗こそ
学ぶ価値があるのに、内部識別子のせいで機械的なノイズとして捨てられていた。

CLAUDE.md の「プロンプト本文にツール名を書くときは必ず露出判断を通す」と同じ形
で、**内部の識別子がエージェントの読む面へ漏れている**。

## この試験が見ないこと

**統合 LLM が実際に捨てなくなったかは見ない。** LLM を呼ぶ検証は不安定でコストが
高い。ここは「生の識別子が本文へ出ない」ことだけを保証し、効果は実 run の
``belief_consolidation`` を後から読んで確かめる。
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
import pytest
from ai_rpg_world.application.llm.services.failure_repeat_phrasing import _REPEATED_FAILURE_PHRASING, describe_repeated_failure
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import InMemoryBeliefEvidenceBufferStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.llm.services.structured_failure_evidence_transcriber import StructuredFailureEvidenceTranscriber
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
_INTERNAL_IDENTIFIER = re.compile('[A-Z][A-Z_]{5,}')
_CODES_SEEN_IN_RUNS = ('INTERACTION_PRECONDITION_FAILED', 'INVALID_TARGET_LABEL')

def _episode(occurred_at: datetime) -> SubjectiveEpisode:
    return SubjectiveEpisode(episode_id='ep-1', player_id=1, being_id=BeingId('being_w1_p1'), occurred_at=occurred_at, game_time_label=None, source=EpisodeSource(event_ids=('evt-1',)), location=EpisodeLocation(), action=EpisodeAction(tool_name='interact'), who=(), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted=None, cues=())

def _transcribe(error_code: str, *, tool_name: str='interact', count: int=3) -> str:
    """転記を 1 件走らせて、積まれた証拠の本文を返す。"""
    buffer_store = InMemoryBeliefEvidenceBufferStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_id = BeingId('being_w1_p1')
    episode_store.put_by_being(being_id, _episode(datetime.now(timezone.utc)))
    transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)
    evidence = transcriber.record_if_triggered(being_id, tool_name=tool_name, error_code=error_code, count=count)
    assert evidence is not None, 'episode があるのに証拠が積まれていません'
    return evidence.text

class TestEvidenceTextHidesInternalIdentifiers:
    """証拠の本文に error_code のような内部識別子が出ない。"""

    @pytest.mark.parametrize('error_code', _CODES_SEEN_IN_RUNS)
    def test_codes_seen_in_real_runs_do_not_leak(self, error_code: str) -> None:
        """実 run で証拠になった code が、本文にそのまま出ない。

        以前は「interact」が「INTERACTION_PRECONDITION_FAILED」を3回反復した。
        という形で漏れていた。
        """
        text = _transcribe(error_code)
        assert error_code not in text, f'error_code が本文へ漏れています: {text}'

    @pytest.mark.parametrize('error_code', sorted(_REPEATED_FAILURE_PHRASING))
    def test_no_phrasing_contains_an_internal_identifier(self, error_code: str) -> None:
        """対応表のどの言い換えにも、英大文字の識別子が入っていない。

        言い換えを足す人が、うっかり code を本文へ書き写すのを止める。
        """
        text = _transcribe(error_code)
        found = _INTERNAL_IDENTIFIER.findall(text)
        assert not found, f'内部識別子らしい並びが本文にあります: {found} / {text}'

    def test_an_unmapped_code_falls_back_without_leaking(self) -> None:
        """対応表に無い code は、code を出さない汎用文へ倒れる。

        対応表を全 code 分そろえるのは重い (error_code のリテラルは 67 種類
        散在していて集中 enum が無い)。だから **漏らさないことだけは確実に**
        させる。粒度が粗くても、語彙が通じる方がよい。
        """
        text = _transcribe('ZZZ_NO_SUCH_ERROR_CODE')
        assert 'ZZZ_NO_SUCH_ERROR_CODE' not in text
        assert not _INTERNAL_IDENTIFIER.findall(text), text

class TestEvidenceTextStillCarriesTheFacts:
    """語彙を変えても、学習に要る事実は落とさない。"""

    def test_the_tool_name_is_kept(self) -> None:
        """どのツールで起きたかは残す。

        cue が ``tool:<name>`` なので、本文からツールが消えると照合できない。
        """
        text = _transcribe('INTERACTION_PRECONDITION_FAILED', tool_name='travel_to')
        assert 'travel_to' in text

    def test_the_repeat_count_is_kept(self) -> None:
        """何回続いたかは残す。1 回の失敗と反復は意味が違う。"""
        text = _transcribe('INTERACTION_PRECONDITION_FAILED', count=5)
        assert '5' in text

    def test_the_reason_is_described_in_plain_japanese(self) -> None:
        """何に阻まれたかが日本語で読める。

        「同じ失敗が続いた」だけでは、次の手を選ぶ手がかりにならない。
        前提条件の不足なら「前提」と分かる言い方にする。
        """
        text = _transcribe('INTERACTION_PRECONDITION_FAILED')
        assert '前提' in text

class TestPhrasingTableCoversWhatRunsProduce:
    """実 run で出た code は、対応表に載っている。"""

    @pytest.mark.parametrize('error_code', _CODES_SEEN_IN_RUNS)
    def test_codes_seen_in_runs_have_a_phrasing(self, error_code: str) -> None:
        """実測で証拠になった code に、専用の言い換えがある。

        fallback でも漏れはしないが、粒度が粗くなって学習の手がかりが減る。
        実際に出ている code は個別に書く。
        """
        assert error_code in _REPEATED_FAILURE_PHRASING

    def test_describe_is_stable_for_the_same_input(self) -> None:
        """同じ入力なら同じ文になる (プレフィックスキャッシュを壊さない)。"""
        first = describe_repeated_failure(tool_name='interact', error_code='INVALID_TARGET_LABEL', count=3)
        second = describe_repeated_failure(tool_name='interact', error_code='INVALID_TARGET_LABEL', count=3)
        assert first == second
