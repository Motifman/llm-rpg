"""システムプロンプトの記憶の指示が、出ている欄と手段だけを指すことを保証する (#1616)。

記憶の部品を止めた run (`var/runs/mine_v1_007_memo`) で、本文が【関連する記憶】と
「能動想起の手段を試す」を指示し続け、エージェントが無い欄と無いツールを探した。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)


def _build() -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
    )


class TestMemoryGuidanceNamesOnlyWhatIsOffered:
    """記憶の指示が、消した受動想起と能動想起を指さないことを保証する。"""

    def test_the_prompt_never_names_relevant_memories(self) -> None:
        """受動想起【関連する記憶】は #1631 で消したので、本文がその欄の名前を出さない。"""
        prompt = _build()

        assert "関連する記憶" not in prompt

    def test_the_prompt_never_mentions_active_recall(self) -> None:
        """能動想起の道具は #1631 で消したので、本文に「能動想起」が出ない。"""
        prompt = _build()

        assert "能動想起" not in prompt

    def test_the_persona_is_never_a_source_of_past_events(self) -> None:
        """過去の出来事をペルソナから想像で補わない指示と「思い出せない」と伝えてよい指示は残る。"""
        prompt = _build()

        assert "ペルソナから想像で補わず" in prompt
        assert "「思い出せない」と素直に伝える" in prompt


def _build_with_index(*, shown: bool, recall_offered: bool) -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
        episode_index_shown=shown,
        episode_recall_offered=recall_offered,
    )


class TestEpisodeIndexGuidanceNamesOnlyWhatIsOffered:
    """【思い出せる出来事】の読み方の文が、欄と呼び出しのツールのそれぞれの有無に合わせて書き分けられることを保証する (#1623)。"""

    def test_with_both_the_prompt_names_the_section_and_the_tool(self) -> None:
        """欄もツールも出ているとき、目次であることと、本文は episode_recall で読むことを書く。"""
        prompt = _build_with_index(shown=True, recall_offered=True)

        assert "【思い出せる出来事】は、自分が昔の出来事を書き残した記憶の目次である。" in prompt
        assert "本文は `episode_recall` で呼び名を指定して思い出したときだけ読める。" in prompt

    def test_without_the_tool_the_prompt_never_names_it(self) -> None:
        """欄は出ているがツールが出ていないとき、欄の説明だけを書き、ツールの名前を出さない。"""
        prompt = _build_with_index(shown=True, recall_offered=False)

        assert "【思い出せる出来事】" in prompt
        assert "episode_recall" not in prompt

    def test_without_the_section_the_prompt_is_unchanged(self) -> None:
        """欄を出さない設定では、既定のまま組んだプロンプトとバイト単位で同じになる。"""
        assert _build_with_index(shown=False, recall_offered=False) == _build()


def _build_with_memo() -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
        being_memo_enabled=True,
    )


class TestMemoRulesAskWhoToldYou:
    """【メモの書き方】が、人から聞いたことには誰から聞いたかを書くよう指示することを保証する (#1621)。

    確認の run (`var/runs/mine_v1_008_check`) で、4 人とも最初の手番で from の無い heard の
    メモを書いて外された。from の決まりは tool の説明にしか無かった。
    """

    def test_heard_fact_rule_names_who_told_you(self) -> None:
        """メモ帳を有効にすると、【メモの書き方】の分かったことの行が、人から聞いたなら誰から聞いたかも書くよう指示する。"""
        prompt = _build_with_memo()

        assert "人から聞いたなら誰から聞いたかも書く" in prompt
