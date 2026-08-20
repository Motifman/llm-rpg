.PHONY: test test-cov test-html clean install dev-install help \
	experiment-relay experiment-relay-r1 experiment-relay-r2 experiment-relay-cloud \
	experiment experiment-publish experiment-survival experiment-survival-coop experiment-recall-probe \
	check-no-internal-hostnames build-trace-viewer

# relay_puzzle 実 LLM 実験（docs/running_scenarios.md）
PYTHON ?= $(shell if [ -x venv/bin/python ]; then echo venv/bin/python; else echo python3; fi)
ISSUE154_MAX_TICKS ?= 30
EXPERIMENT_OUTPUT ?= var/experiment_relay_report.md
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
	@echo "  make experiment-relay         - relay_puzzle R1+R2（クラウド既定）"
	@echo "  make experiment-relay-r1      - R1 のみ"
	@echo "  make experiment-relay-r2      - R2 のみ"
	@echo "  make experiment-relay-cloud   - experiment-relay と等価 (名前で参照されているため残す)"
	@echo "  make experiment [EXPERIMENT_PROFILE=belief_goal_full] [OUT=...]"
	@echo "                                - profile に固定した汎用シナリオ実験"
	@echo "  make experiment-publish ...   - experiment + 自動 gist publish"
	@echo "  make experiment-survival OUT=... [EPISODIC=1]"
	@echo "                                - survival_island_v2 専用 (140 tick / workers 4 / publish 既定)"
	@echo "  make experiment-survival-coop OUT=... [EPISODIC=1]"
	@echo "                                - survival_island_v3_coop 専用 (stranded_at_tick=240 / workers 4 / publish 既定)"
	@echo "  make experiment-recall-probe OUT=... [DRY_RUN=1]"
	@echo "                                - Issue #526 不在 2 検証用 (recall_probe_v1 / 15 tick / 1 player)"
	@echo "  make build-trace-viewer RUN_DIR=...  - viewer 3 種 (main + episodic + timeline) を build"

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

# relay_puzzle 実 LLM 実験（docs/running_scenarios.md）
#
# 以前はローカル vLLM を既定にしていたが、vLLM 運用をやめたのでクラウドを
# 既定にした。別のエンドポイントで走らせたい場合は OPENAI_API_BASE と
# LLM_MODEL をシェルから渡す。
#
# experiment-relay-cloud は既定が変わって等価になったが、docs や履歴から
# 名前で参照されているので残す。
experiment-relay:
	@mkdir -p var
	OPENAI_API_BASE= LLM_MODEL=$(CLOUD_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R1_default,R2_pure \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

experiment-relay-r1:
	@mkdir -p var
	OPENAI_API_BASE= LLM_MODEL=$(CLOUD_LLM_MODEL) \
	ISSUE154_MAX_TICKS=$(ISSUE154_MAX_TICKS) ISSUE154_RUNS=R1_default \
	$(PYTHON) scripts/run_relay_puzzle_experiment.py -o $(EXPERIMENT_OUTPUT)

experiment-relay-r2:
	@mkdir -p var
	OPENAI_API_BASE= LLM_MODEL=$(CLOUD_LLM_MODEL) \
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
#   make experiment EXPERIMENT_PROFILE=belief_goal_full OUT=var/runs/foo-001
#   make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-smoke
#   make experiment EXPERIMENT_PROFILE=ablation_base SCENARIO=data/scenarios/foo.json
#
# 引数 (= make 変数):
#   EXPERIMENT_PROFILE
#                   data/experiment_profiles/<name>.json を読む。
#                   実験フラグ・LLM 設定はここだけに置く。
#   EXPERIMENT_CONFIG
#                   profile ではなく任意 JSON ファイルを読む。
#   SCENARIO        profile の scenario を一時的に上書きするパス。
#   MAX_WORLD_TICKS world_tick がこの値に達したらループ終了 (既定 30)。
#                   旧名 MAX_TICKS は外側 iteration 回数だったが #404 P1 で
#                   意味論を world tick 基準に統一した。
#   OUT             出力ディレクトリ (省略時 var/runs/<scenario>-<timestamp>)
#   PUBLISH         1 で gist 自動 publish (= --publish-gist)
#   OPENAI_API_KEY  実 LLM 接続用の秘密情報。profile には書かない。
MAX_WORLD_TICKS ?=
EXPERIMENT_PROFILE ?= belief_goal_full
EXPERIMENT_CONFIG ?=
experiment:
	@if [ -n "$(EXPERIMENT_PROFILE)" ] && [ -n "$(EXPERIMENT_CONFIG)" ]; then \
		echo "EXPERIMENT_PROFILE and EXPERIMENT_CONFIG are mutually exclusive"; \
		exit 2; \
	fi
	@mkdir -p var/runs
	@echo "[experiment] profile=$(EXPERIMENT_PROFILE) config=$(EXPERIMENT_CONFIG)"
	uv run python scripts/run_scenario_experiment.py \
		$(if $(EXPERIMENT_PROFILE),--profile $(EXPERIMENT_PROFILE),) \
		$(if $(EXPERIMENT_CONFIG),--experiment-config $(EXPERIMENT_CONFIG),) \
		$(if $(SCENARIO),--scenario $(SCENARIO),) \
		$(if $(MAX_WORLD_TICKS),--max-world-ticks $(MAX_WORLD_TICKS),) \
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

# survival_island_v3_coop 専用のショートカット。
# このシナリオは「漂流確定 (stranded)」が data/scenarios/survival_island_v3_coop.json の
# stranded_at_tick=240 で設計されている (estimated_ticks も 240)。M7 実走で
# --max-world-ticks 200 を指定してしまい、200 で打ち切られ stranded 判定が
# 一度も発火しなかった (協調が破綻したかどうかを観測できなかった) 反省を
# 踏まえ、v3_coop はこのショートカット経由で 240 を既定にして再発を防ぐ。
# 他シナリオ (survival_island_v2 / decay_demo 等) の既定値には影響しない。
#
# 使い方:
#   make experiment-survival-coop OUT=var/runs/m7_coop_r1
#   make experiment-survival-coop OUT=var/runs/m7_coop_r1_episodic EPISODIC=1
#
# 上書き可能な変数 (省略時の coop 既定値):
#   MAX_WORLD_TICKS=240 (= stranded_at_tick)  WORKERS=4  PUBLISH=1
#   EPISODIC は未指定 (= OFF)。1 で ON_FULL。
#   SECTION_ORDER / MEMORY_KIND / SCHEDULER_MODE / PROVIDER /
#   QUANTIZATION / REQUIRE_PARAMS も同様に上位 experiment target へ素通し。
COOP_MAX_WORLD_TICKS ?= 240
COOP_WORKERS ?= 4
COOP_PUBLISH ?= 1
experiment-survival-coop:
	$(MAKE) experiment \
		SCENARIO=data/scenarios/survival_island_v3_coop.json \
		MAX_WORLD_TICKS=$(COOP_MAX_WORLD_TICKS) \
		WORKERS=$(COOP_WORKERS) \
		OUT=$(OUT) \
		EPISODIC=$(EPISODIC) \
		IDLE_TICKS=$(IDLE_TICKS) \
		SECTION_ORDER=$(SECTION_ORDER) \
		MEMORY_KIND=$(MEMORY_KIND) \
		SCHEDULER_MODE=$(SCHEDULER_MODE) \
		PROVIDER=$(PROVIDER) \
		QUANTIZATION=$(QUANTIZATION) \
		REQUIRE_PARAMS=$(REQUIRE_PARAMS) \
		PUBLISH=$(COOP_PUBLISH)

# Issue #526 後続: 能動 recall (memory_recall_episodes) 検証用の小規模実験。
# 1 player + 15 tick + 過去 episode 強制注入 + scripted NPC「シキ」の質問 3 つ。
#
# 使い方:
#   make experiment-recall-probe OUT=var/runs/recall_probe_001
#   make experiment-recall-probe DRY_RUN=1 OUT=/tmp/dryrun   # LLM 呼ばずに構造確認
#
# 既定: K run 設定 (rolling_summary / thread_pool / stable_to_volatile) +
#       DeepInfra fp4 / deepseek-v4-flash。OPENAI_API_KEY が要る。
#
# 引数:
#   RECALL_PROBE_SCENARIO 既定 data/scenarios/recall_probe_v1.json
#                         v2 (中立 objective + passive 痩せ) を使うときは
#                         data/scenarios/recall_probe_v2.json
RECALL_PROBE_SCENARIO ?= data/scenarios/recall_probe_v1.json
experiment-recall-probe:
	@mkdir -p var/runs
	uv run python scripts/run_recall_probe_experiment.py \
		--scenario $(RECALL_PROBE_SCENARIO) \
		$(if $(RECALL_PROBE_MODE),--mode $(RECALL_PROBE_MODE),) \
		$(if $(RECALL_PROBE_MAX_TICKS),--max-world-ticks $(RECALL_PROBE_MAX_TICKS),) \
		$(if $(DRY_RUN),--no-llm,) \
		$(if $(OUT),--out $(OUT),)

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
	@$(PYTHON) scripts/build_prompt_viewer.py $(RUN_DIR) || true
