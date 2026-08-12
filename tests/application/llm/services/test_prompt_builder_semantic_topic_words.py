"""prompt builder が semantic passive recall 用の日本語 topic 語を現在状態から抽出する。"""

from types import SimpleNamespace

from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType

from ai_rpg_world.application.llm.services.prompt_builder import (
    _gather_semantic_topic_words_for_recall,
)


class TestPromptBuilderSemanticTopicWords:
    """現在状態 DTO から、ID ではなく prompt に出る日本語語彙を集める。"""

    def test_extracts_spot_object_inventory_and_need_words(self) -> None:
        """現在地名・見えている物・所持品・高い空腹から topic 語を作る。

        欲求の手がかりは `need_states` (値オブジェクト) から出る。`need_lines` を
        併記してあるのは、**表示文が残っていても判定には使われない**ことを示すため
        (系統2 で文字列の再パースを廃止した)。
        """
        state = SimpleNamespace(
            current_spot_name="山麓",
            area_names=["山岳"],
            visible_objects=[SimpleNamespace(display_name="石積みの目印")],
            inventory_items=[SimpleNamespace(display_name="火打ち石")],
            spot_graph_snapshot=SimpleNamespace(
                current_spot_name="山麓",
                objects=(SimpleNamespace(name="古い焚き火跡"),),
                inventory_items=(SimpleNamespace(name="流木"),),
                ground_items=(SimpleNamespace(name="枯れ葉"),),
                nearby_entities=(SimpleNamespace(display_name="エイダ"),),
                monsters_at_spot=(SimpleNamespace(display_name="大型カニ"),),
                # 系統2: 想起の手がかりは**表示文ではなく欲求の値**から決める。
                # 以前はここに need_lines の文字列を置き、prompt_builder が
                # 「空腹で始まり、高い or 危険 を含むか」で判定していた。tier の
                # 言い回しを変えると手がかりが黙って消える形だった。
                need_states=(
                    AgentNeed(need_type=NeedType.HUNGER, value=72, max_value=100),
                    AgentNeed(need_type=NeedType.FATIGUE, value=0, max_value=100),
                ),
                need_lines=("空腹: 高い（72/100）", "疲労: 問題なし（0/100）"),
            ),
        )
        words = _gather_semantic_topic_words_for_recall(state)
        assert "山麓" in words
        assert "石積みの目印" in words
        assert "火打ち石" in words
        assert "古い焚き火跡" in words
        assert "流木" in words
        assert "空腹" in words
        assert "食料" in words
        assert "疲労" not in words

    def test_returns_empty_when_current_state_is_missing(self) -> None:
        """現在状態 DTO が無いときは topic 語を足さず、従来の relevance=0 側へ倒す。"""
        assert _gather_semantic_topic_words_for_recall(None) == []
