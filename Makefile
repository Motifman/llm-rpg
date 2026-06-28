.PHONY: test test-cov test-html clean install dev-install help \
	web-demo-db web-demo-db-reset web-backend web-frontend-install \
	web-frontend-test web-frontend-build web-frontend \
	asset-pipeline-sync asset-pipeline-sync-rembg asset-pipeline \
	experiment-relay experiment-relay-r1 experiment-relay-r2 experiment-relay-cloud \
	experiment experiment-publish experiment-survival experiment-recall-probe \
	vllm-tunnel vllm-check \
	check-no-internal-hostnames build-trace-viewer

WEB_GAME_DB ?= var/game/ai_rpg_world.db
WEB_MANUAL_PLAYER_IDS ?= 1
ASSET_PIPELINE_DIR := tools/asset_pipeline

# relay_puzzle 実 LLM 実験（docs/running_scenarios.md）
PYTHON ?= $(shell if [ -x venv/bin/python ]; then echo venv/bin/python; else echo python3; fi)
ISSUE154_MAX_TICKS ?= 30
EXPERIMENT_OUTPUT ?= var/experiment_relay_report.md
VLLM_LOCAL_PORT ?= 18001
VLLM_OPENAI_API_BASE ?= http://127.0.0.1:$(VLLM_LOCAL_PORT)/v1
VLLM_SSH_HOST ?= v108-vllm
VLLM_LLM_MODEL ?= openai/gemma-4-31b-it-nvfp4
CLOUD_LLM_MODEL ?= openai/gpt-5-mini

# デフォルトターゲット
help:
	@echo "利用可能なコマンド:"
	@echo "  make install      - 依存関係をインストール"
	@echo "  make dev-install  - 開発用依存関係をインストール"
	@echo "  make test         - テストを実行"
	@echo "  make test-cov     - カバレッジ付きでテストを実行"
	@echo "  make test-html    - HTMLカバレッジレポートを生成"
	@echo "  make clean        - 一時ファイルを削除"
	@echo "  make web-demo-db        - Web viewer 用の最小 SQLite DB を作成"
	@echo "  make web-demo-db-reset  - Web viewer 用 DB を再作成"
	@echo "  make web-backend        - Web viewer backend を起動"
	@echo "  make web-frontend-install - frontend 依存関係をインストール"
	@echo "  make web-frontend-test  - frontend テストを実行"
	@echo "  make web-frontend-build - frontend を build"
	@echo "  make web-frontend       - frontend dev server を起動"
	@echo "  make asset-pipeline-sync       - スプライト用 CLI (tools/asset_pipeline) の依存を同期"
	@echo "  make asset-pipeline-sync-rembg - 同上 + rembg（要時間・容量）"
	@echo "  make asset-pipeline CMD='…'   - 例: make asset-pipeline CMD='split -h'"
	@echo "  make experiment-relay         - relay_puzzle R1+R2（vLLM 既定: :8001 Gemma）"
	@echo "  make experiment-relay-r1      - R1 のみ"
	@echo "  make experiment-relay-r2      - R2 のみ"
	@echo "  make experiment-relay-cloud   - OpenAI クラウド（OPENAI_API_BASE 空）"
	@echo "  make experiment SCENARIO=... MAX_WORLD_TICKS=... [WORKERS=4 EPISODIC=1 IDLE_TICKS=6 OUT=...]"
	@echo "                                  prefix cache 系: [SECTION_ORDER=stable_to_volatile|legacy]"
	@echo "                                                   [MEMORY_KIND=sliding_window|rolling_summary]"
	@echo "                                                   [SCHEDULER_MODE=inline|thread_pool]"
	@echo "                                  OpenRouter: [PROVIDER=Parasail QUANTIZATION=fp8 REQUIRE_PARAMS=1]"
	@echo "                                - 汎用シナリオ実験 (任意 scenario JSON)"
	@echo "  make experiment-publish ...   - experiment + 自動 gist publish"
	@echo "  make experiment-survival OUT=... [EPISODIC=1]"
	@echo "                                - survival_island_v2 専用 (140 tick / workers 4 / publish 既定)"
	@echo "  make experiment-recall-probe OUT=... [DRY_RUN=1]"
	@echo "                                - Issue #526 不在 2 検証用 (recall_probe_v1 / 15 tick / 1 player)"
	@echo "  make build-trace-viewer RUN_DIR=...  - viewer 3 種 (main + episodic + timeline) を build"
	@echo "  make vllm-tunnel              - v108 vLLM 用 SSH トンネル起動 (port $(VLLM_LOCAL_PORT))"
	@echo "  make vllm-check               - トンネル + vLLM 応答確認"

# 依存関係のインストール
install:
	pip install -r requirements.txt

# 開発用依存関係のインストール
dev-install: install
	pip install pytest pytest-cov

# 基本的なテスト実行
test:
	pytest

# カバレッジ付きテスト実行
test-cov:
	pytest --cov=src --cov-report=term-missing

# HTMLカバレッジレポート生成
test-html:
	pytest --cov=src --cov-report=html --cov-report=term
	@echo "HTMLレポートが htmlcov/index.html に生成されました"

# 一時ファイルの削除
clean:
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

web-demo-db:
	uv run python -m ai_rpg_world.presentation.web.demo_seed --database $(WEB_GAME_DB)

web-demo-db-reset:
	uv run python -m ai_rpg_world.presentation.web.demo_seed --database $(WEB_GAME_DB) --overwrite

web-backend:
	AI_RPG_WORLD_GAME_DB=$(WEB_GAME_DB) AI_RPG_WORLD_MANUAL_PLAYER_IDS=$(WEB_MANUAL_PLAYER_IDS) uv run python -m ai_rpg_world.presentation.web.server

web-frontend-install:
	cd frontend && npm install --cache .npm-cache

web-frontend-test:
	cd frontend && npm run test

web-frontend-build:
	cd frontend && npm run build

web-frontend:
	cd frontend && npm run dev

# スプライト前処理 CLI（ゲーム本体の pyproject とは別プロジェクト）
asset-pipeline-sync:
	cd $(ASSET_PIPELINE_DIR) && uv sync

asset-pipeline-sync-rembg:
	cd $(ASSET_PIPELINE_DIR) && uv sync --extra rembg

# 使用例: make asset-pipeline CMD="split sheet.png -r 2 -c 2 -o ./out -W 32 -H 48"
asset-pipeline:
	cd $(ASSET_PIPELINE_DIR) && uv run asset-pipeline $(CMD)

# relay_puzzle 実 LLM 実験 — 要 vLLM または OPENAI_API_KEY
experiment-relay:
	@mkdir -p var
	OPENAI_API_BASE=$(VLLM_OPENAI_API_BASE) OPENAI_API_KEY= LLM_MODEL=$(VLLM_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R1_default,R2_pure \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

experiment-relay-r1:
	@mkdir -p var
	OPENAI_API_BASE=$(VLLM_OPENAI_API_BASE) OPENAI_API_KEY= LLM_MODEL=$(VLLM_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R1_default \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

experiment-relay-r2:
	@mkdir -p var
	OPENAI_API_BASE=$(VLLM_OPENAI_API_BASE) OPENAI_API_KEY= LLM_MODEL=$(VLLM_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R2_pure \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

experiment-relay-cloud:
	@mkdir -p var
	OPENAI_API_BASE= LLM_MODEL=$(CLOUD_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R1_default,R2_pure \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

# 汎用シナリオ実験 (Issue #188 Phase 1d) — 任意 scenario JSON で実行し
# trace.jsonl + report.md + trace.html を出力する。
#
# 使い方:
#   make experiment SCENARIO=data/scenarios/survival_island_v2.json
#   make experiment SCENARIO=data/scenarios/foo.json MAX_WORLD_TICKS=140 OUT=var/runs/foo-001 WORKERS=4
#   make experiment SCENARIO=... EPISODIC=1   # episodic memory pipeline 有効
#   make experiment SCENARIO=... SECTION_ORDER=stable_to_volatile MEMORY_KIND=rolling_summary
#   make experiment SCENARIO=... PROVIDER=Parasail QUANTIZATION=fp8  # OpenRouter routing
#
# 引数 (= make 変数):
#   SCENARIO        実行するシナリオ JSON のパス (必須)
#   MAX_WORLD_TICKS world_tick がこの値に達したらループ終了 (既定 30)。
#                   旧名 MAX_TICKS は外側 iteration 回数だったが #404 P1 で
#                   意味論を world tick 基準に統一した。
#   OUT             出力ディレクトリ (省略時 var/runs/<scenario>-<timestamp>)
#   WORKERS         LLM Phase A 並列ワーカー数 (既定 1。実験は 4 推奨)
#   EPISODIC        1 で episodic memory 有効 (= LLM_EPISODIC_ENABLED=1)
#   IDLE_TICKS      per-agent idle timer の沈黙上限 tick (既定 6)
#   PUBLISH         1 で gist 自動 publish (= --publish-gist)
#
# 記憶 / prefix cache 系 (実 LLM 実験で prefix cache 効果を見るための切替):
#   SECTION_ORDER   stable_to_volatile | legacy (= PROMPT_SECTION_ORDER)。
#                   未指定なら default (stable_to_volatile)。Phase 0 の
#                   reorder OFF/ON 比較に使う。
#   MEMORY_KIND     sliding_window | rolling_summary (= SHORT_TERM_MEMORY_KIND)。
#                   未指定なら default (sliding_window)。rolling_summary は
#                   Phase 2 の L4 mid summary 経路。
#                   **注意**: 短縮形 ``rolling`` / ``sliding`` は無効値で
#                   sliding_window に fallback するため必ず完全名を使うこと。
#   SCHEDULER_MODE  inline | thread_pool (= SHORT_TERM_MEMORY_SCHEDULER_MODE)。
#                   rolling 時の L4 生成タスクを非同期にするか。未指定なら inline。
#
# OpenRouter provider routing (実 LLM 実験で provider/quant を固定):
#   PROVIDER        provider 名 (例: DeepInfra / Parasail / Venice)。指定時は
#                   OPENROUTER_PROVIDER として渡り allow_fallbacks=False が付く。
#   QUANTIZATION    fp8 / fp4 / bf16 等 (= OPENROUTER_QUANTIZATION)。同 provider
#                   内で variant を絞るとき。例: DeepInfra fp8 (turbo=fp4 を回避)。
#   REQUIRE_PARAMS  1 で OPENROUTER_REQUIRE_PARAMS=true。リクエスト param 全対応
#                   provider のみに限定 (tools / response_format を要求するとき)。
#
# その他の env (litellm 接続):
#   OPENAI_API_BASE / LLM_MODEL / OPENAI_API_KEY
MAX_WORLD_TICKS ?= 30
WORKERS ?= 1
# #346 Step 3 / #404: per-agent idle timer (heartbeat 沈黙上限) tick 数。
# 既定 6 = 「event 駆動で active なら heartbeat は出ず、丸 6 tick 何もなければ
# 1 回起こす」。0 / 未指定 = 既定 (6) を使う。沈黙を強めたい実験では 12 / 24
# に上げる。
IDLE_TICKS ?=
# 実 LLM 実験のデフォルト model / provider。run 同士の prompt prefix cache を
# 共有させるため、未指定なら必ず同じ model + provider に固定する。openrouter
# は同じ model 名でも複数 provider (DeepSeek 本家 / DeepInfra / Parasail /
# 他) にルーティングし、provider が変わると cache が共有されない。default を
# 明示することで「あの run と同じ条件か」を疑う必要をなくす。
# 別 provider で実験したい場合は呼び出し側で LLM_MODEL=... PROVIDER=... を
# 上書きする。0 byte の cache hit に悩んだら、まず stdout の
# `[run] openrouter routing: provider=...` を確認すること。
LLM_MODEL ?= openrouter/deepseek/deepseek-v4-flash
PROVIDER ?= DeepSeek
# 受動 episodic recall の「賢く使う」拡張をデフォルト ON にする (Issue #526
# 段階 2-3 / PR-C)。EPISODIC=1 で受動 recall そのものを有効化したときに、
# 以下 3 機構も併せて動く。受動 recall が OFF なら何も影響しない。
#   - RECALL_HABITUATION: 直近 N tick 採用した episode の score を一時的に
#     下げる慣化 (= 同じ記憶が連続して上に出続けるのを防ぐ)
#   - RECALL_SLOT: working memory スロット (= 想起した記憶を数 tick 保持)
#   - AFTERGLOW: 採用されなかった候補の「ぼんやり覚えてる」インデックス
# これらは Y_recall_layer (= 旧 cache hit 63.7% 取れていた run) のときも
# 全部 ON だった。EPISODIC と一緒にこれら 3 つを忘れないようデフォルト 1。
# 個別に OFF にしたい場合は RECALL_HABITUATION=0 のように 0 を渡す。
RECALL_HABITUATION ?= 1
RECALL_SLOT ?= 1
AFTERGLOW ?= 1
experiment:
	@if [ -z "$(SCENARIO)" ]; then \
		echo "SCENARIO is required. e.g. make experiment SCENARIO=data/scenarios/survival_island_v2.json"; \
		exit 2; \
	fi
	@mkdir -p var/runs
	@echo "[experiment] LLM_MODEL=$(LLM_MODEL) PROVIDER=$(PROVIDER) (default; 上書きは LLM_MODEL=... PROVIDER=...)"
	LLM_MODEL=$(LLM_MODEL) \
	LLM_TURN_PARALLEL_WORKERS=$(WORKERS) \
	$(if $(EPISODIC),LLM_EPISODIC_ENABLED=1,) \
	LLM_EPISODIC_RECALL_HABITUATION_ENABLED=$(RECALL_HABITUATION) \
	LLM_EPISODIC_RECALL_SLOT_ENABLED=$(RECALL_SLOT) \
	LLM_AFTERGLOW_ENABLED=$(AFTERGLOW) \
	$(if $(IDLE_TICKS),LLM_IDLE_TIMEOUT_TICKS=$(IDLE_TICKS),) \
	$(if $(SECTION_ORDER),PROMPT_SECTION_ORDER=$(SECTION_ORDER),) \
	$(if $(MEMORY_KIND),SHORT_TERM_MEMORY_KIND=$(MEMORY_KIND),) \
	$(if $(SCHEDULER_MODE),SHORT_TERM_MEMORY_SCHEDULER_MODE=$(SCHEDULER_MODE),) \
	OPENROUTER_PROVIDER=$(PROVIDER) \
	$(if $(QUANTIZATION),OPENROUTER_QUANTIZATION=$(QUANTIZATION),) \
	$(if $(REQUIRE_PARAMS),OPENROUTER_REQUIRE_PARAMS=true,) \
	$(PYTHON) scripts/run_scenario_experiment.py \
		--scenario $(SCENARIO) \
		--max-world-ticks $(MAX_WORLD_TICKS) \
		$(if $(OUT),--out $(OUT),) \
		$(if $(PUBLISH),--publish-gist,) \
		$(if $(SNAPSHOT_SAVE_DIR),--snapshot-save-dir $(SNAPSHOT_SAVE_DIR),$(if $(OUT),--snapshot-save-dir $(OUT)/snapshots,)) \
		$(if $(SNAPSHOT_LOAD_DIR),--snapshot-load-dir $(SNAPSHOT_LOAD_DIR),)

# Phase 6 (Issue #470): 実験 run の Being snapshot を OUT 配下の snapshots/ に
# 自動保存する shortcut。次回 run-resume で読み込める。
# 使い方:
#   make experiment-with-snapshot SCENARIO=... OUT=var/runs/foo
#   # OUT/snapshots/being_w1_p1.json などが書き出される
experiment-with-snapshot:
	@if [ -z "$(OUT)" ]; then \
		echo "OUT is required for experiment-with-snapshot. e.g. make experiment-with-snapshot SCENARIO=... OUT=var/runs/foo"; \
		exit 2; \
	fi
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) \
		MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		WORKERS=$(WORKERS) \
		EPISODIC=$(EPISODIC) \
		IDLE_TICKS=$(IDLE_TICKS) \
		SECTION_ORDER=$(SECTION_ORDER) \
		MEMORY_KIND=$(MEMORY_KIND) \
		SCHEDULER_MODE=$(SCHEDULER_MODE) \
		PROVIDER=$(PROVIDER) \
		QUANTIZATION=$(QUANTIZATION) \
		REQUIRE_PARAMS=$(REQUIRE_PARAMS) \
		PUBLISH=$(PUBLISH) \
		SNAPSHOT_SAVE_DIR=$(OUT)/snapshots

# Phase 6: 別の OUT で同じ scenario を再開する shortcut。
# 使い方:
#   make experiment-resume SCENARIO=... OUT=var/runs/foo_resume \
#     SNAPSHOT_LOAD_DIR=var/runs/foo/snapshots
experiment-resume:
	@if [ -z "$(SNAPSHOT_LOAD_DIR)" ]; then \
		echo "SNAPSHOT_LOAD_DIR is required. e.g. make experiment-resume SCENARIO=... OUT=... SNAPSHOT_LOAD_DIR=var/runs/prev/snapshots"; \
		exit 2; \
	fi
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) \
		MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		WORKERS=$(WORKERS) \
		EPISODIC=$(EPISODIC) \
		IDLE_TICKS=$(IDLE_TICKS) \
		SECTION_ORDER=$(SECTION_ORDER) \
		MEMORY_KIND=$(MEMORY_KIND) \
		SCHEDULER_MODE=$(SCHEDULER_MODE) \
		PROVIDER=$(PROVIDER) \
		QUANTIZATION=$(QUANTIZATION) \
		REQUIRE_PARAMS=$(REQUIRE_PARAMS) \
		PUBLISH=$(PUBLISH) \
		SNAPSHOT_LOAD_DIR=$(SNAPSHOT_LOAD_DIR) \
		SNAPSHOT_SAVE_DIR=$(if $(OUT),$(OUT)/snapshots,)

# experiment + secret gist 自動 publish (PUBLISH=1 と同等)
experiment-publish:
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) OUT=$(OUT) \
		WORKERS=$(WORKERS) EPISODIC=$(EPISODIC) IDLE_TICKS=$(IDLE_TICKS) \
		SECTION_ORDER=$(SECTION_ORDER) MEMORY_KIND=$(MEMORY_KIND) \
		SCHEDULER_MODE=$(SCHEDULER_MODE) \
		PROVIDER=$(PROVIDER) QUANTIZATION=$(QUANTIZATION) \
		REQUIRE_PARAMS=$(REQUIRE_PARAMS) \
		PUBLISH=1

# survival_island_v2 専用のショートカット。
# 4 player + 14 day (= 140 driver tick) + parallel workers=4 + 自動 publish を
# デフォルトに固定して、何度も同じパラメータを打ち直す煩雑さを解消する。
# EPISODIC のみ切り替えて OFF / ON_FULL の 2 run を回すのが定例。
#
# 使い方:
#   make experiment-survival OUT=var/runs/issue390_exp27_off_r1
#   make experiment-survival OUT=var/runs/issue390_exp27_on_full_r1 EPISODIC=1
#   # prefix cache A/B (vLLM / 第30回相当):
#   make experiment-survival OUT=var/runs/exp30_A SECTION_ORDER=legacy MEMORY_KIND=sliding
#   make experiment-survival OUT=var/runs/exp30_C SECTION_ORDER=stable_to_volatile MEMORY_KIND=rolling_summary
#
# 上書き可能な変数 (省略時の survival 既定値):
#   MAX_WORLD_TICKS=140  WORKERS=4  PUBLISH=1
#   EPISODIC は未指定 (= OFF)。1 で ON_FULL。
#   SECTION_ORDER / MEMORY_KIND / SCHEDULER_MODE / PROVIDER /
#   QUANTIZATION / REQUIRE_PARAMS も同様に上位 experiment target へ素通し。
SURVIVAL_MAX_WORLD_TICKS ?= 140
SURVIVAL_WORKERS ?= 4
SURVIVAL_PUBLISH ?= 1
experiment-survival:
	$(MAKE) experiment \
		SCENARIO=data/scenarios/survival_island_v2.json \
		MAX_WORLD_TICKS=$(SURVIVAL_MAX_WORLD_TICKS) \
		WORKERS=$(SURVIVAL_WORKERS) \
		OUT=$(OUT) \
		EPISODIC=$(EPISODIC) \
		IDLE_TICKS=$(IDLE_TICKS) \
		SECTION_ORDER=$(SECTION_ORDER) \
		MEMORY_KIND=$(MEMORY_KIND) \
		SCHEDULER_MODE=$(SCHEDULER_MODE) \
		PROVIDER=$(PROVIDER) \
		QUANTIZATION=$(QUANTIZATION) \
		REQUIRE_PARAMS=$(REQUIRE_PARAMS) \
		PUBLISH=$(SURVIVAL_PUBLISH)

# Issue #526 後続: 能動 recall (memory_recall_episodes) 検証用の小規模実験。
# 1 player + 15 tick + 過去 episode 強制注入 + scripted NPC「シキ」の質問 3 つ。
#
# 使い方:
#   make experiment-recall-probe OUT=var/runs/recall_probe_001
#   make experiment-recall-probe DRY_RUN=1 OUT=/tmp/dryrun   # LLM 呼ばずに構造確認
#
# 既定: K run 設定 (rolling_summary / thread_pool / stable_to_volatile) +
#       DeepInfra fp4 / deepseek-v4-flash。OPENROUTER_API_KEY が要る。
#
# 環境変数で上書き可能:
#   RECALL_PROBE_MODEL    既定 openrouter/deepseek/deepseek-v4-flash
#   RECALL_PROBE_PROVIDER 既定 DeepInfra
#   RECALL_PROBE_QUANT    既定 fp4
#   RECALL_PROBE_SCENARIO 既定 data/scenarios/recall_probe_v1.json
#                         v2 (中立 objective + passive 痩せ) を使うときは
#                         data/scenarios/recall_probe_v2.json
RECALL_PROBE_MODEL ?= openrouter/deepseek/deepseek-v4-flash
RECALL_PROBE_PROVIDER ?= DeepInfra
RECALL_PROBE_QUANT ?= fp4
RECALL_PROBE_SCENARIO ?= data/scenarios/recall_probe_v1.json
experiment-recall-probe:
	@mkdir -p var/runs
	LLM_CLIENT=$(if $(DRY_RUN),stub,litellm) \
	LLM_MODEL=$(RECALL_PROBE_MODEL) \
	OPENROUTER_PROVIDER=$(RECALL_PROBE_PROVIDER) \
	OPENROUTER_QUANTIZATION=$(RECALL_PROBE_QUANT) \
	OPENROUTER_REQUIRE_PARAMS=true \
	LLM_EPISODIC_ENABLED=1 \
	SHORT_TERM_MEMORY_KIND=rolling_summary \
	SHORT_TERM_MEMORY_SCHEDULER_MODE=thread_pool \
	PROMPT_SECTION_ORDER=stable_to_volatile \
	LLM_IDLE_TIMEOUT_TICKS=1 \
	LLM_TURN_PARALLEL_WORKERS=1 \
	SPOT_GRAPH_TICK_LOOP_ENABLED=false \
	uv run python scripts/run_recall_probe_experiment.py \
		--scenario $(RECALL_PROBE_SCENARIO) \
		$(if $(RECALL_PROBE_MODE),--mode $(RECALL_PROBE_MODE),) \
		$(if $(RECALL_PROBE_MAX_TICKS),--max-world-ticks $(RECALL_PROBE_MAX_TICKS),) \
		$(if $(DRY_RUN),--no-llm,) \
		$(if $(OUT),--out $(OUT),)

# vLLM への SSH トンネル (~/.ssh/config の Host エイリアス、既定 v108-vllm)
# 実 FQDN は本リポジトリには書かない。docs/security_hosts_policy.md 参照。
vllm-tunnel:
	@./scripts/ensure_vllm_tunnel.sh

vllm-check:
	@./scripts/ensure_vllm_tunnel.sh --check

# 内部ホスト名 / 組織 FQDN の混入チェック (docs/security_hosts_policy.md)
check-no-internal-hostnames:
	@./scripts/check_no_internal_hostnames.sh

# Trace viewer の生成 (Issue #188 Phase 1d β + #389 で Phase 3 追加)
# main viewer (viewer.html) に加えて、エピソード記憶 (episodic.html) と
# プレイヤー × tick (timeline.html) の追加 viewer も併せて build する。
# 使い方: make build-trace-viewer RUN_DIR=var/runs/foo
build-trace-viewer:
	@if [ -z "$(RUN_DIR)" ]; then \
		echo "RUN_DIR is required. e.g. make build-trace-viewer RUN_DIR=var/runs/foo"; \
		exit 2; \
	fi
	$(PYTHON) scripts/build_trace_viewer.py $(RUN_DIR)
	@$(PYTHON) scripts/build_episodic_viewer.py $(RUN_DIR) || true
	@$(PYTHON) scripts/build_timeline_viewer.py $(RUN_DIR) || true
