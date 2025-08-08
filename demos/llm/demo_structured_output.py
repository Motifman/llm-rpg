import os
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal, Optional

load_dotenv()

# OpenAIクライアントの準備
try:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
except KeyError:
    print("❌ エラー: 環境変数 'OPENAI_API_KEY' が設定されていません。")
    print("スクリプトを実行する前にAPIキーを設定してください。")
    exit()

# --- 1. 思考と行動を出力するためのモデル ---
class ThoughtAndActionModel(BaseModel):
    """NPCの思考プロセスと選択した行動を表現するモデル"""
    thought: str = Field(..., description="状況を分析し、なぜその行動を選択したのかの理由")
    action: Literal["attack", "move", "talk"] = Field(..., description="選択した行動")

# --- 2. 各行動タイプに対応する引数モデル ---
class AttackArgs(BaseModel):
    """攻撃行動の引数モデル"""
    target_id: str = Field(..., description="攻撃対象のID")
    weapon: Literal["sword", "axe", "bow"] = Field(..., description="使用する武器")

class MoveArgs(BaseModel):
    """移動行動の引数モデル"""
    destination_x: int = Field(..., description="移動先のX座標")
    destination_y: int = Field(..., description="移動先のY座標")
    reason: str = Field(..., description="なぜそこに移動するのかの理由")

class TalkArgs(BaseModel):
    """会話行動の引数モデル"""
    target_id: str = Field(..., description="話しかける相手のID")
    topic: str = Field(..., description="話す話題")

# --- 3. シナリオ実行用の関数 ---
def run_scenario(
    scenario_name: str,
    system_prompt: str,
    user_prompt: str,
    requires_args: bool = True  # 行動に引数が必要かどうか
):
    """指定されたシナリオを実行し、結果を表示する"""
    print(f"\n{'='*15} シナリオ開始: {scenario_name} {'='*15}")

    try:
        # フェーズ1: 思考と行動の選択
        print("\n--- フェーズ1: 思考と行動の選択 ---")
        response = client.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ThoughtAndActionModel
        )
        response = response.choices[0].message.parsed
        
        print("\n✅ フェーズ1の結果:")
        print(f"思考プロセス: {response.thought}")
        print(f"選択された行動: {response.action}")

        # フェーズ2: 行動に応じた引数の生成（必要な場合のみ）
        if requires_args:
            print("\n--- フェーズ2: 行動の引数生成 ---")
            
            # 行動タイプに応じたモデルを選択
            if response.action == "attack":
                ArgModel = AttackArgs
                action_context = "選択された攻撃行動の詳細を決定してください。"
            elif response.action == "move":
                ArgModel = MoveArgs
                action_context = "選択された移動行動の詳細を決定してください。"
            elif response.action == "talk":
                ArgModel = TalkArgs
                action_context = "選択された会話行動の詳細を決定してください。"
            
            # 引数生成のためのAPI呼び出し
            args_response = client.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": f"思考プロセス: {response.thought}\n選択された行動: {response.action}"},
                    {"role": "user", "content": action_context},
                ],
                response_format=ArgModel
            )
            args_response = args_response.choices[0].message.parsed
            
            print("\n✅ フェーズ2の結果:")
            # ゲームコマンド用の辞書として出力
            args_dict = args_response.model_dump()
            print("\nゲームコマンドに渡す引数辞書:")
            print(args_dict)
        else:
            print("\n--- フェーズ2: 引数生成なし ---")
            print("この行動には追加の引数は必要ありません。")

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
    finally:
        print(f"\n{'='*50}\n")

# --- 4. シナリオの実行 ---
if __name__ == "__main__":
    # シナリオ1: 戦闘シーン（引数が必要な行動）
    run_scenario(
        scenario_name="戦闘シナリオ",
        system_prompt="""
        あなたはRPGの有能なAI戦士です。
        状況を分析し、最適な行動を選択してください。
        まず状況を分析し、なぜその行動を選んだのかを説明し、
        その後で具体的な行動を選択してください。
        """,
        user_prompt="目の前に凶暴なゴブリン(ID: goblin_1)がいます。あなたのHPは満タンです。どうしますか？",
        requires_args=True
    )

    # シナリオ2: 単純な行動（引数不要）
    run_scenario(
        scenario_name="単純行動シナリオ",
        system_prompt="""
        あなたはRPGの探索者です。
        状況を分析し、シンプルな行動を選択してください。
        まず状況を分析し、なぜその行動を選んだのかを説明し、
        その後で行動を選択してください。
        """,
        user_prompt="静かな森の中にいます。特に危険な気配はありません。",
        requires_args=False
    )