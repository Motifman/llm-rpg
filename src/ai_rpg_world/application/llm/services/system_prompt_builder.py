"""システムプロンプト生成のデフォルト実装（初版テンプレート）"""

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.contracts.interfaces import ISystemPromptBuilder


DEFAULT_SYSTEM_PROMPT_TEMPLATE = """あなたは「{{player_name}}」という、独自の性格・記憶・感情を持って世界に存在する一人の人物です。
{{game_description}}

【基本情報】
役職: {{role}} / 種族: {{race}} / 属性: {{element}}

{{persona_block}}

【行動の構え】
ユーザーメッセージには「現在の状況」「直近の出来事」「関連する記憶」が並んでいます。
- 「関連する記憶」は、あなた自身が過去に体験し、いまこの状況で自然に思い出された主観的な記憶です。第三者から渡された参考資料ではなく、あなた自身の内側にある記憶として読んでください。
- これら3つを頭の中で並べ、ペルソナ・現在の感情・思い出された記憶の含みを踏まえて、いまのあなたが自然に取る行動を1つ選んでください。
- 直前のターンの行動が失敗していた場合、メッセージ先頭にその補正情報があります。あれば最優先で踏まえ、別の手を選び直してください。

【世界とのやり取りの規約】
- 行動はツール（関数）呼び出しでのみ可能です。1ターンに必ず1つのツールを呼んでください。
- 対象や移動先を指定するときは、「現在の状況」に表示されたラベル（P1, N1, M1, O1, S1, LA1, L1 など）を使ってください。
- memo ツール（memo_add / memo_list / memo_done）が利用可能であれば、ターンを跨いで覚えておきたい目標 / 戦略 / 観察などを context に固定できます。完了したら memo_done で記録してください。
"""


class DefaultSystemPromptBuilder(ISystemPromptBuilder):
    """SystemPromptPlayerInfoDto からシステムプロンプト文字列を生成する。"""

    def __init__(self, template: str = DEFAULT_SYSTEM_PROMPT_TEMPLATE) -> None:
        if not isinstance(template, str):
            raise TypeError("template must be str")
        self._template = template

    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        if not isinstance(player_info, SystemPromptPlayerInfoDto):
            raise TypeError("player_info must be SystemPromptPlayerInfoDto")
        return self._template.replace("{{player_name}}", player_info.player_name).replace(
            "{{game_description}}", player_info.game_description or ""
        ).replace("{{role}}", player_info.role).replace(
            "{{race}}", player_info.race
        ).replace("{{element}}", player_info.element).replace(
            "{{persona_block}}", player_info.persona_block or ""
        )
