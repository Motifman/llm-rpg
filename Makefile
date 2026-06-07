.PHONY: test test-cov test-html clean install dev-install help \
	web-demo-db web-demo-db-reset web-backend web-frontend-install \
	web-frontend-test web-frontend-build web-frontend \
	asset-pipeline-sync asset-pipeline-sync-rembg asset-pipeline \
	experiment-relay experiment-relay-r1 experiment-relay-r2 experiment-relay-cloud \
	experiment experiment-publish experiment-survival vllm-tunnel vllm-check \
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
	@echo "  make experiment SCENARIO=... MAX_TICKS=... [WORKERS=4 EPISODIC=1 IDLE_TICKS=6 OUT=...]"
	@echo "                                - 汎用シナリオ実験 (任意 scenario JSON)"
	@echo "  make experiment-publish ...   - experiment + 自動 gist publish"
	@echo "  make experiment-survival OUT=... [EPISODIC=1]"
	@echo "                                - survival_island_v2 専用 (140 tick / workers 4 / publish 既定)"
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
#   make experiment SCENARIO=data/scenarios/foo.json MAX_TICKS=140 OUT=var/runs/foo-001 WORKERS=4
#   make experiment SCENARIO=... EPISODIC=1   # episodic memory pipeline 有効
#
# 引数 (= make 変数):
#   SCENARIO       実行するシナリオ JSON のパス (必須)
#   MAX_TICKS      外側ループ回数 (既定 30)
#   OUT            出力ディレクトリ (省略時 var/runs/<scenario>-<timestamp>)
#   WORKERS        LLM Phase A 並列ワーカー数 (既定 1。実験は 4 推奨)
#   EPISODIC       1 で episodic memory 有効 (= LLM_EPISODIC_ENABLED=1)
#   PUBLISH        1 で gist 自動 publish (= --publish-gist)
#
# その他の env (litellm 接続):
#   OPENAI_API_BASE / LLM_MODEL / OPENAI_API_KEY
MAX_TICKS ?= 30
WORKERS ?= 1
# #346 Step 3 / #404: per-agent idle timer (heartbeat 沈黙上限) tick 数。
# 既定 6 = 「event 駆動で active なら heartbeat は出ず、丸 6 tick 何もなければ
# 1 回起こす」。0 / 未指定 = 既定 (6) を使う。沈黙を強めたい実験では 12 / 24
# に上げる。
IDLE_TICKS ?=
experiment:
	@if [ -z "$(SCENARIO)" ]; then \
		echo "SCENARIO is required. e.g. make experiment SCENARIO=data/scenarios/survival_island_v2.json"; \
		exit 2; \
	fi
	@mkdir -p var/runs
	LLM_TURN_PARALLEL_WORKERS=$(WORKERS) \
	$(if $(EPISODIC),LLM_EPISODIC_ENABLED=1,) \
	$(if $(IDLE_TICKS),LLM_IDLE_TIMEOUT_TICKS=$(IDLE_TICKS),) \
	$(PYTHON) scripts/run_scenario_experiment.py \
		--scenario $(SCENARIO) \
		--max-ticks $(MAX_TICKS) \
		$(if $(OUT),--out $(OUT),) \
		$(if $(PUBLISH),--publish-gist,)

# experiment + secret gist 自動 publish (PUBLISH=1 と同等)
experiment-publish:
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) MAX_TICKS=$(MAX_TICKS) OUT=$(OUT) \
		WORKERS=$(WORKERS) EPISODIC=$(EPISODIC) IDLE_TICKS=$(IDLE_TICKS) PUBLISH=1

# survival_island_v2 専用のショートカット。
# 4 player + 14 day (= 140 driver tick) + parallel workers=4 + 自動 publish を
# デフォルトに固定して、何度も同じパラメータを打ち直す煩雑さを解消する。
# EPISODIC のみ切り替えて OFF / ON_FULL の 2 run を回すのが定例。
#
# 使い方:
#   make experiment-survival OUT=var/runs/issue390_exp27_off_r1
#   make experiment-survival OUT=var/runs/issue390_exp27_on_full_r1 EPISODIC=1
#
# 上書き可能な変数 (省略時の survival 既定値):
#   MAX_TICKS=140  WORKERS=4  PUBLISH=1
#   EPISODIC は未指定 (= OFF)。1 で ON_FULL。
SURVIVAL_MAX_TICKS ?= 140
SURVIVAL_WORKERS ?= 4
SURVIVAL_PUBLISH ?= 1
experiment-survival:
	$(MAKE) experiment \
		SCENARIO=data/scenarios/survival_island_v2.json \
		MAX_TICKS=$(SURVIVAL_MAX_TICKS) \
		WORKERS=$(SURVIVAL_WORKERS) \
		OUT=$(OUT) \
		EPISODIC=$(EPISODIC) \
		IDLE_TICKS=$(IDLE_TICKS) \
		PUBLISH=$(SURVIVAL_PUBLISH)

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
