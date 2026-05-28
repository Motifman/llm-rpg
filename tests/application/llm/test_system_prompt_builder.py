"""DefaultSystemPromptBuilder のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
    DEFAULT_SYSTEM_PROMPT_TEMPLATE,
)


class TestDefaultSystemPromptBuilder:
    """DefaultSystemPromptBuilder の正常・例外ケース"""

    @pytest.fixture
    def builder(self):
        return DefaultSystemPromptBuilder()

    @pytest.fixture
    def player_info(self):
        return SystemPromptPlayerInfoDto(
            player_name="冒険者",
            role="adventurer",
            race="human",
            element="fire",
            game_description="MMOの世界で冒険するゲームです。",
        )

    def test_build_includes_player_name_and_game_description(self, builder, player_info):
        """プレイヤー名とゲーム説明が含まれる"""
        text = builder.build(player_info)
        assert "冒険者" in text
        assert "MMOの世界で冒険するゲームです。" in text

    def test_build_includes_role_race_element(self, builder, player_info):
        """役職・種族・属性が含まれる"""
        text = builder.build(player_info)
        assert "adventurer" in text
        assert "human" in text
        assert "fire" in text

    def test_build_includes_action_stance_and_protocol_sections(self, builder, player_info):
        """【行動の構え】と【世界とのやり取りの規約】セクションが含まれる"""
        text = builder.build(player_info)
        assert "【行動の構え】" in text
        assert "【世界とのやり取りの規約】" in text
        assert "ツール" in text

    def test_build_frames_relevant_memories_as_subjective(self, builder, player_info):
        """「関連する記憶」が主観的記憶として読むよう誘導されている"""
        text = builder.build(player_info)
        assert "関連する記憶" in text
        assert "主観的な記憶" in text

    def test_build_empty_game_description_ok(self, builder):
        """game_description が空でも生成される"""
        info = SystemPromptPlayerInfoDto(
            player_name="P",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        text = builder.build(info)
        assert "P" in text

    def test_build_player_info_not_dto_raises_type_error(self, builder):
        """player_info が SystemPromptPlayerInfoDto でないとき TypeError"""
        with pytest.raises(TypeError, match="player_info must be SystemPromptPlayerInfoDto"):
            builder.build("not a dto")  # type: ignore[arg-type]

    def test_custom_template_is_used(self):
        """カスタムテンプレートを渡すとそれが使われる"""
        custom = "Hello {{player_name}} only."
        builder = DefaultSystemPromptBuilder(template=custom)
        info = SystemPromptPlayerInfoDto(
            player_name="Alice",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        text = builder.build(info)
        assert "Hello Alice only." in text

    def test_init_template_not_str_raises_type_error(self):
        """template が str でないとき TypeError"""
        with pytest.raises(TypeError, match="template must be str"):
            DefaultSystemPromptBuilder(template=123)  # type: ignore[arg-type]

    def test_init_unknown_template_variable_raises_value_error(self):
        """typo の {{plyer_name}} が __init__ で ValueError として検出される (Issue #227 後続 MEDIUM-7)。"""
        broken = "Hello {{plyer_name}}"
        with pytest.raises(ValueError, match="plyer_name"):
            DefaultSystemPromptBuilder(template=broken)

    def test_init_multiple_unknown_template_variables_listed(self):
        """複数の未知変数があれば全て ValueError に列挙される。"""
        broken = "{{foo}} and {{bar}}"
        with pytest.raises(ValueError, match="bar.*foo|foo.*bar"):
            DefaultSystemPromptBuilder(template=broken)

    def test_init_no_placeholders_ok(self):
        """変数を 1 つも含まない template は許容 (literal text のみでも OK)。"""
        builder = DefaultSystemPromptBuilder(template="just literal text")
        info = SystemPromptPlayerInfoDto(
            player_name="P", role="r", race="r", element="e", game_description=""
        )
        assert builder.build(info) == "just literal text"

    def test_init_partial_subset_of_known_variables_ok(self):
        """既知変数のサブセットだけを使う template は許容。"""
        builder = DefaultSystemPromptBuilder(template="Hi {{player_name}}, role={{role}}")
        info = SystemPromptPlayerInfoDto(
            player_name="Alice", role="mage", race="r", element="e", game_description=""
        )
        assert builder.build(info) == "Hi Alice, role=mage"

    def test_init_whitespace_inside_placeholders_ok(self):
        """`{{ player_name }}` のように内部空白があっても OK (正規表現が許容)。"""
        builder = DefaultSystemPromptBuilder(template="Hi {{ player_name }}")
        info = SystemPromptPlayerInfoDto(
            player_name="Alice", role="r", race="r", element="e", game_description=""
        )
        # 注: build() は厳密な `{{player_name}}` 形式のみ置換するため、
        # `{{ player_name }}` (空白あり) は文字通り残る。strict 検証は
        # 通過するが、置換挙動の現状仕様を確認する
        result = builder.build(info)
        assert "Alice" not in result  # 空白入りは置換されないため
