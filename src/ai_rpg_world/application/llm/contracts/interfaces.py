"""LLM 向け表示・記憶層のポート（インターフェース）"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.value_object import WorldTick

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    EpisodeMemoryEntry,
    LlmUiContextDto,
    LongTermFactEntry,
    MemoryLawEntry,
    MemoryRetrievalQueryDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
    TodoEntry,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class IHandleStore(ABC):
    """memory_query の output_mode=handle で保持する参照のストア。1 turn 限定。"""

    @abstractmethod
    def put(
        self,
        player_id: PlayerId,
        handle_id: str,
        data: List[Dict[str, Any]],
        expr: str,
    ) -> None:
        """評価結果を handle_id で保存する。"""
        pass

    @abstractmethod
    def get(
        self, player_id: PlayerId, handle_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """handle_id に対応するデータを取得する。存在しなければ None。"""
        pass

    @abstractmethod
    def clear_player(self, player_id: PlayerId) -> None:
        """指定プレイヤーの全 handle を破棄する。ターン開始時に呼ぶ。"""
        pass


class ISlidingWindowMemory(ABC):
    """観測のスライディングウィンドウ記憶。直近 N 件を返す。"""

    @abstractmethod
    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        """指定プレイヤーの観測を 1 件追加する。"""
        pass

    @abstractmethod
    def append_all(
        self, player_id: PlayerId, entries: List[ObservationEntry]
    ) -> List[ObservationEntry]:
        """
        指定プレイヤーに観測を複数件追加する。
        戻り値は今回の追加によりウィンドウから溢れた（捨てられた）観測のリスト。
        """
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]:
        """指定プレイヤーの直近 limit 件の観測を新しい順で返す。"""
        pass


# --- 記憶モジュール（Phase 4）---


class IEpisodeMemoryStore(ABC):
    """エピソード記憶の格納・取得。"""

    @abstractmethod
    def add(self, player_id: PlayerId, entry: EpisodeMemoryEntry) -> None:
        """1 件追加。"""
        pass

    @abstractmethod
    def add_many(
        self, player_id: PlayerId, entries: List[EpisodeMemoryEntry]
    ) -> None:
        """複数件追加。"""
        pass

    @abstractmethod
    def get_recent(
        self,
        player_id: PlayerId,
        limit: int,
        since: Optional[datetime] = None,
    ) -> List[EpisodeMemoryEntry]:
        """新しい順で取得。since は Reflection 用の「直近 N 日」など。"""
        pass

    @abstractmethod
    def find_by_entities_and_actions(
        self,
        player_id: PlayerId,
        entity_ids: Optional[List[str]] = None,
        action_names: Optional[List[str]] = None,
        world_object_ids: Optional[List[int]] = None,
        spot_ids: Optional[List[int]] = None,
        scope_keys: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[EpisodeMemoryEntry]:
        """
        ルールベース検索（コンテキスト・予測検索で使用）。
        world_object_ids / spot_ids は stable id 優先検索用。scope_keys は関係性メモリ用。
        指定時はそちらを優先し、未指定時は entity_ids / action_names のみで検索する。
        """
        pass

    @abstractmethod
    def increment_recall_count(self, player_id: PlayerId, episode_id: str) -> None:
        """検索ヒット時の想起回数を加算。"""
        pass

    @abstractmethod
    def get_important_or_high_recall(
        self,
        player_id: PlayerId,
        since: datetime,
        min_importance: Optional[str] = None,
        min_recall_count: Optional[int] = None,
        limit: int = 20,
    ) -> List[EpisodeMemoryEntry]:
        """Reflection 用: 重要度・想起回数でフィルタしたエピソードを取得。"""
        pass


class IMemoryExtractor(ABC):
    """観測＋直近の行動結果から記憶すべきエピソードを抽出する。"""

    @abstractmethod
    def extract(
        self,
        player_id: PlayerId,
        overflow_observations: List[ObservationEntry],
        action_summary: str,
        result_summary: str,
    ) -> List[EpisodeMemoryEntry]:
        """
        溢れた観測とこのターンの行動結果からエピソード候補を返す。
        run_turn の末尾で 1 回だけ呼ぶ。
        """
        pass


class IPredictiveMemoryRetriever(ABC):
    """
    現在状態と候補行動から、予測に役立つエピソード・長期記憶（事実・法則）を取得する。
    プロンプトの「関連する記憶」に載せる文字列を返す。ヒットしたエピソードの想起回数を更新する。
    query_dto を渡すと DTO 由来の entity/location/actionable/notable を優先検索し、
    current_state_summary の文字面への依存を弱める。
    """

    @abstractmethod
    def retrieve_for_prediction(
        self,
        player_id: PlayerId,
        current_state_summary: str,
        candidate_action_names: List[str],
        episode_limit: int = 5,
        fact_limit: int = 5,
        law_limit: int = 5,
        query_dto: Optional[MemoryRetrievalQueryDto] = None,
    ) -> str:
        """
        現在状態と候補行動名に基づき、関連するエピソード・事実・法則を取得し、
        「関連する記憶」セクション用の 1 本のテキストにフォーマットして返す。
        返す前にヒットしたエピソードの recall_count をインクリメントする。
        query_dto 指定時は entity > location > actionable/notable > action > free_text の順で検索。
        """
        pass


class IReflectionService(ABC):
    """
    重要・高想起エピソードから教訓・法則を抽出し長期記憶に反映する。
    日次または閾値ベースで実行する。
    """

    @abstractmethod
    def run(
        self,
        player_id: PlayerId,
        since: datetime,
        min_importance: Optional[str] = None,
        min_recall_count: Optional[int] = None,
        episode_limit: int = 20,
    ) -> Optional[datetime]:
        """
        指定プレイヤーについて、since 以降の重要・高想起エピソードを取得し、
        教訓・法則を抽出して長期記憶に add/update する。
        戻り値: 今回反映したエピソード群の最大 timestamp。反映が 0 件の場合は None。
        """
        pass


class ILongTermMemoryStore(ABC):
    """長期記憶（事実・教訓と法則・共起）の格納・検索。"""

    @abstractmethod
    def add_fact(self, player_id: PlayerId, content: str) -> str:
        """事実を追加し id を返す。"""
        pass

    @abstractmethod
    def search_facts(
        self,
        player_id: PlayerId,
        keywords: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[LongTermFactEntry]:
        """事実をキーワードで検索。"""
        pass

    @abstractmethod
    def upsert_law(
        self,
        player_id: PlayerId,
        subject: str,
        relation: str,
        target: str,
        delta_strength: float = 1.0,
    ) -> None:
        """法則を追加または同一 (subject, relation, target) で強度を更新。"""
        pass

    @abstractmethod
    def find_laws(
        self,
        player_id: PlayerId,
        subject: Optional[str] = None,
        action_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryLawEntry]:
        """法則を検索。action_name は relation の簡易検索用。"""
        pass


class IActionResultStore(ABC):
    """行動要約＋結果要約の記録。直近 M 件を返す。"""

    @abstractmethod
    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        """1 件の行動結果を追加する。occurred_at は省略時は現在時刻。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ActionResultEntry]:
        """指定プレイヤーの直近 limit 件の行動結果を新しい順で返す。"""
        pass


class ITodoStore(ABC):
    """TODO の格納・取得。LLM が管理するタスクリスト用。"""

    @abstractmethod
    def add(self, player_id: PlayerId, content: str) -> str:
        """TODO を追加し、todo_id を返す。"""
        pass

    @abstractmethod
    def list_uncompleted(self, player_id: PlayerId) -> List[TodoEntry]:
        """未完了の TODO を追加日時の新しい順で返す。"""
        pass

    @abstractmethod
    def complete(self, player_id: PlayerId, todo_id: str) -> bool:
        """指定した TODO を完了にする。存在しない id の場合は False。"""
        pass

    @abstractmethod
    def remove(self, player_id: PlayerId, todo_id: str) -> bool:
        """指定した TODO を削除する。存在しない id の場合は False。"""
        pass


class IWorkingMemoryStore(ABC):
    """作業メモ（仮説・中間結論）の格納・取得。セッション寄りの短期記憶。"""

    @abstractmethod
    def append(self, player_id: PlayerId, text: str) -> None:
        """テキストを追加する。"""
        pass

    @abstractmethod
    def get_recent(self, player_id: PlayerId, limit: int) -> List[str]:
        """直近 limit 件を新しい順で返す。"""
        pass

    @abstractmethod
    def clear(self, player_id: PlayerId) -> None:
        """指定プレイヤーの作業メモをクリアする。"""
        pass


class ICurrentStateFormatter(ABC):
    """PlayerCurrentStateDto を現在状態のプロンプト用テキストに変換する。"""

    @abstractmethod
    def format(self, dto: PlayerCurrentStateDto) -> str:
        """現在状態の 1 本のテキストを返す。"""
        pass


class ILlmUiContextBuilder(ABC):
    """現在状態テキストに一時ラベル付きUIを重ね、内部用 runtime context を組み立てる。"""

    @abstractmethod
    def build(
        self,
        current_state_text: str,
        current_state: Optional[PlayerCurrentStateDto],
    ) -> LlmUiContextDto:
        """LLM向け現在状態テキストと tool runtime context を返す。"""
        pass


class IRecentEventsFormatter(ABC):
    """観測リストと行動結果リストを「直近の出来事」テキストに変換する。"""

    @abstractmethod
    def format(
        self,
        observations: List[ObservationEntry],
        action_results: List[ActionResultEntry],
    ) -> str:
        """観測と行動結果を時刻でマージした直近の出来事テキストを返す。"""
        pass


class IContextFormatStrategy(ABC):
    """現在状態・直近の出来事・関連記憶を 1 本のコンテキスト文字列にフォーマットする。"""

    @abstractmethod
    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str,
    ) -> str:
        """3 つのセクションを結合したコンテキスト文字列を返す。"""
        pass


class ISystemPromptBuilder(ABC):
    """プレイヤー情報 DTO からシステムプロンプト文字列を生成する。"""

    @abstractmethod
    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        """システムプロンプト文字列を返す。"""
        pass


class IPromptBuilder(ABC):
    """1 ターン分のプロンプト（OpenAI 互換 messages）を組み立てる。"""

    @abstractmethod
    def build(
        self,
        player_id: PlayerId,
        action_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        OpenAI 互換の辞書を返す。
        {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}], "tools": [], "tool_choice": "required"}
        action_instruction は user 末尾に付与する行動選択の説明。省略時はデフォルト文言。
        """
        pass


# --- ツール利用可否・ツール一覧（ToolAvailabilityContext = PlayerCurrentStateDto） ---


class IAvailabilityResolver(ABC):
    """あるツールが現在のコンテキストで利用可能かどうかを判定する。"""

    @abstractmethod
    def is_available(
        self, context: Optional[PlayerCurrentStateDto]
    ) -> bool:
        """context でこのツールを提示するか。未配置時は context が None のことがある。"""
        pass


class IGameToolRegistry(ABC):
    """全ツール定義の登録・取得。"""

    @abstractmethod
    def register(
        self,
        definition: ToolDefinitionDto,
        resolver: IAvailabilityResolver,
    ) -> None:
        """ツール定義とその利用可否リゾルバを登録する。"""
        pass

    @abstractmethod
    def get_definitions_with_resolvers(
        self,
    ) -> List[Tuple[ToolDefinitionDto, "IAvailabilityResolver"]]:
        """登録済みの (ToolDefinitionDto, IAvailabilityResolver) のリストを返す。"""
        pass


class IAvailableToolsProvider(ABC):
    """現在状況から利用可能なツールのリスト（OpenAI tools 形式）を返す。"""

    @abstractmethod
    def get_available_tools(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> List[Dict[str, Any]]:
        """context に応じて利用可能なツールだけを OpenAI の tools 形式で返す。"""
        pass


class IToolArgumentResolver(ABC):
    """LLM の UI 用引数を、アプリケーション層へ渡す canonical args に解決する。"""

    @abstractmethod
    def resolve(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """tool 名・UI引数・runtime context から canonical args を返す。"""
        pass


# --- LLM ターン駆動（スケジュール＋実行） ---


class ILLMPlayerResolver(ABC):
    """プレイヤーが LLM 制御かどうかを判定するポート。"""

    @abstractmethod
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        """指定プレイヤーが LLM 制御なら True。"""
        pass


class ILlmTurnTrigger(ABC):
    """LLM ターンのスケジュールと一括実行のポート。観測到着時に schedule_turn、ループ/ティックで run_scheduled_turns を呼ぶ。"""

    @abstractmethod
    def schedule_turn(self, player_id: PlayerId) -> None:
        """指定プレイヤーのターン実行を 1 回スケジュールする（重複は 1 回にまとまる）。"""
        pass

    @abstractmethod
    def run_scheduled_turns(self) -> None:
        """スケジュール済みの全プレイヤーについて run_turn を 1 回ずつ実行し、キューをクリアする。"""
        pass


class IReflectionStatePort(ABC):
    """
    Reflection の実行境界（cursor）を保持するポート。
    次フェーズで永続化する場合はこのインターフェースを実装した永続化層に差し替える。
    """

    @abstractmethod
    def get_last_reflection_game_day(self, player_id: PlayerId) -> Optional[int]:
        """最終 Reflection 成功時の in-game day。None は未実行。"""
        pass

    @abstractmethod
    def get_reflection_cursor(self, player_id: PlayerId) -> Optional[datetime]:
        """
        Reflection の since に渡す cursor。
        この時刻以降のエピソードが対象。wall clock ではなく「反映済み境界」の意味。
        None は全期間を対象。
        """
        pass

    @abstractmethod
    def mark_reflection_success(
        self, player_id: PlayerId, game_day: int, cursor: datetime
    ) -> None:
        """Reflection 成功時に呼ぶ。game_day と cursor を記録。"""
        pass


class IReflectionRunner(ABC):
    """
    in-game day 境界や一定 tick ごとに Reflection を実行するランナーのポート。
    WorldSimulationApplicationService の tick 後に呼び出される。
    """

    @abstractmethod
    def run_after_tick(self, current_tick: "WorldTick") -> None:
        """
        ティック後処理。game day が変わった場合などに、
        LLM 制御プレイヤー向けに Reflection を実行する。
        """
        pass


# --- LLM API 抽象化 ---


class ILLMClient(ABC):
    """LLM API 呼び出しのポート。messages + tools を送り、1 つの tool_call を受け取る。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        """
        1 回の LLM 呼び出しを行い、tool_call があればそれを返す。
        戻り値: {"name": str, "arguments": dict} または tool_call が無い場合 None。
        """
        pass
