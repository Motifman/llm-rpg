# LLM プロンプト保存と Hugging Face データセット化の設計

## 目的

実験 run の各 LLM 呼び出しについて、実際に LLM に送ったプロンプト、ツール定義、
LLM の出力、実行結果、メトリクスを後から学習・分析に使える形で保存する。
加えて、litellm に渡した request kwargs と provider response 全体を保存し、
system prompt / toolset の参照を戻せば、確率的要素を除いて同じ LLM request を
再送できる形式にする。
最終成果物は Hugging Face `datasets` の `load_dataset()` で読める構成にする。

この文書は設計のみを扱う。実装は、レビュー後に別 PR で行う。

## 現状の事実

- プロンプト全文は `PromptBuilder.build()` の中で存在する。
  - `system_content` は `system_prompt_builder.build(player_info)` で生成される。
  - `user_content` は現在状態、記憶、直近の出来事、指示などを結合して生成される。
  - 返り値には `messages`、`tools`、`tool_choice`、`current_state_snapshot`、
    `current_beliefs_snapshot`、`persona_snapshot` が入る。
  - 参照: `src/ai_rpg_world/application/llm/services/prompt_builder.py:1155`
    から `:1179`。
- 現在 trace に残るのは prompt 全文ではなく、section ごとの文字数だけである。
  - `PROMPT_SECTION_BREAKDOWN` は `system_chars` / `user_content_chars` /
    `tools_chars` 等を記録する。
  - 参照: `src/ai_rpg_world/application/llm/services/prompt_builder.py:748`
    から `:803`。
- 実 LLM 呼び出しは `runtime_manager.py` の Phase A で行われる。
  - `prompt = self.runtime.build_full_prompt(player_id)` で prompt dict を得る。
  - `tools_payload` を組み立てる。
  - reasoning 有効時は `append_force_tool_call_instruction(prompt["messages"])`
    で user message 末尾を変え、`tool_choice="auto"` にする。
  - 通常時は `prompt["messages"]` と `tool_choice="required"` を使う。
  - 参照: `src/ai_rpg_world/presentation/spot_graph_game/runtime_manager.py:1588`
    から `:1636`。
- LLM 呼び出しメトリクスは `LlmCallMetricsSink` 経由で trace に流れている。
  - ただし prompt 全文や tool call との結合用 ID はまだない。
- run 単位の provenance は `experiment.config.resolved.json` に保存される。
  - scenario hash、profile、runtime config、git commit / dirty、起動引数が入る。
  - 参照: `scripts/run_scenario_experiment.py:327` から `:377`。

Hugging Face `datasets` は JSON、CSV、Parquet などのファイルを
`load_dataset()` で読める。公式 docs でも、ローカルまたは Hub 上の JSON /
Parquet ファイルを `load_dataset()` に渡す使い方が示されている。

- https://huggingface.co/docs/datasets/en/loading
- https://huggingface.co/docs/datasets/en/package_reference/loading_methods

## 基本方針

1. **main trace を肥大させない。**
   `trace.jsonl` には従来どおり軽量なイベントだけを残し、プロンプト全文は
   `prompt_dataset/` 配下の別ファイルに保存する。
2. **1 行 = 1 LLM 呼び出し。**
   「1 observation = 1 LLM 起動 = 1 tool 呼び出し」という既存原則に合わせ、
   dataset の主テーブルも 1 LLM 呼び出しを 1 行にする。
3. **system prompt は重複保存しない。**
   system prompt は原則としてキャラクターごとに固定なので、`system_prompts`
   テーブルへ一度だけ保存し、turn 行は `system_prompt_id` を参照する。
4. **tool 定義も参照化する。**
   tool list は長く、かつ prefix cache 維持のため大きく変わらない。turn 行には
   `toolset_id` を持たせ、本文は `toolsets` テーブルへ保存する。
5. **有効化は profile/config 経由にする。**
   shell から環境変数を直渡しする運用は避け、`data/experiment_profiles/*.json`
   または `--experiment-config` の `runtime_config` で opt-in する。
6. **有効化された保存は静かに欠けさせない。**
   dataset capture は既定 off。明示的に on にした場合、出力先を開けない /
   書けない / schema を満たせないときは fail-fast を既定にする。
   長時間 run を守るため warning 継続が必要な場合だけ、明示的に
   `PROMPT_DATASET_CAPTURE_FAILURE_POLICY=warn` を使う。

## 保存場所と責務分離

データ本体はこの git repository で管理しない。repository に置くのは、
キャプチャコード、schema 定義、export スクリプト、dataset card テンプレート、
この設計文書だけにする。JSONL / Parquet の実データを commit すると履歴が肥大し、
Git LFS の誤用や差分レビュー不能な巨大ファイルを招くためである。

責務は以下に分ける。

| 場所 | 置くもの | git 管理 |
|---|---|---|
| `docs/` / `src/` / `scripts/` | 設計、schema、キャプチャ実装、export 実装、dataset card テンプレート | する |
| `var/runs/<run_id>/prompt_dataset/` | run 中に追記される生キャプチャ JSONL | しない |
| `var/datasets/<dataset_name>/` | ローカルで生成した Parquet / README / manifest | しない |
| Hugging Face Hub | 公開・共有する完成データセットの正史 | Hub 側で管理 |

ローカル開発では Hugging Face アカウントや token が無くても、
`var/runs/<run_id>/prompt_dataset/` から `var/datasets/<dataset_name>/` まで
変換・検証できるようにする。Hub への push は任意の最終ステップに分ける。

push 先の organization / repository 名や `HF_TOKEN` は秘密情報として扱い、
`.env` またはローカル設定から読む。設計上は「push 先は後設定」とし、
実験 profile に token や個人アカウント名を埋め込まない。

また、prompt dataset は trace とは完全に別系統の sink とする。
`trace.jsonl` は従来どおり実験分析用の軽量イベント列であり、
prompt dataset sink は LLM 呼び出しの本文・ツール定義・出力を保存する。
両者は `llm_call_id` で join できるが、片方がもう片方の保存責務を兼ねない。

## 提案する設定

`ResolvedLlmRuntimeConfig` に以下を追加する。値は profile/config の
`runtime_config` から解決し、`to_trace_dict()` と
`experiment.config.resolved.json` にも出す。

```json
{
  "PROMPT_DATASET_CAPTURE_ENABLED": true,
  "PROMPT_DATASET_CAPTURE_FORMAT": "jsonl",
  "PROMPT_DATASET_CAPTURE_FAILURE_POLICY": "fail",
  "PROMPT_DATASET_INCLUDE_TOOLS": true,
  "PROMPT_DATASET_INCLUDE_SYSTEM_PROMPTS": true
}
```

### 各設定

| キー | 既定 | 意味 |
|---|---:|---|
| `PROMPT_DATASET_CAPTURE_ENABLED` | `false` | プロンプト保存を有効化する |
| `PROMPT_DATASET_CAPTURE_FORMAT` | `jsonl` | 実験中の追記形式。初期実装は `jsonl` のみ |
| `PROMPT_DATASET_CAPTURE_FAILURE_POLICY` | `fail` | 保存失敗時に run を止めるか。`fail` / `warn` |
| `PROMPT_DATASET_INCLUDE_TOOLS` | `true` | tool 定義を `toolsets.jsonl` に保存する |
| `PROMPT_DATASET_INCLUDE_SYSTEM_PROMPTS` | `true` | system prompt を `system_prompts.jsonl` に保存する |

`PROMPT_DATASET_CAPTURE_FORMAT=parquet` は実験中の直接出力ではなく、後段の
export コマンドで扱う。実験中は append と壊れた行の調査がしやすい JSONL を使う。

## 出力ディレクトリ

run 出力ディレクトリ配下に `prompt_dataset/` を作る。

```text
var/runs/<run_id>/
  trace.jsonl
  report.md
  experiment.config.resolved.json
  prompt_dataset/
    schema_version.txt
    run.json
    calls.jsonl
    turn_results.jsonl
    system_prompts.jsonl
    toolsets.jsonl
    export_manifest.json
```

### ファイルの責務

| ファイル | 役割 |
|---|---|
| `run.json` | run 単位の provenance。`experiment.config.resolved.json` の dataset 用要約 |
| `calls.jsonl` | 1 LLM 呼び出し 1 行。litellm request kwargs、raw response、正規化出力、metrics |
| `turn_results.jsonl` | Phase B の action 実行結果。`llm_call_id` で `calls.jsonl` と結合 |
| `system_prompts.jsonl` | system prompt 本文の重複排除テーブル |
| `toolsets.jsonl` | LLM に渡した tools 配列の重複排除テーブル |
| `export_manifest.json` | 後段 export の入力確認用。行数、hash、schema version |

## capture 点

### 1. `PromptBuilder.build()` 末尾

`PromptBuilder.build()` は messages と section 本文を持っているため、ここで
「prompt build 成果物」を補助情報として作れる。ただし、この時点の情報は
正史ではない。reasoning 有効時に `runtime_manager.py` が messages を最終加工し、
さらに `LiteLLMClient.invoke()` が `extra_body` や timeout などを加えるためである。

ここでは以下を生成する。

- best-effort の section list
- `system_prompt_hash`
- `user_prompt_hash`
- `tool_runtime_context` に依存しない prompt 側の情報

v1 の最優先は **実際に LLM サーバへ送った最終 messages 全文をそのまま保存する**
ことである。section 分割は分析の補助であり、完全性を要求しない。現 builder は
最終的に user content を結合済みなので、section[] は best-effort と明記する。
全文 request から復元できることを優先し、section[] の欠落で replay を壊さない。

### 2. `runtime_manager.py` Phase A の `invoke` 直前

ここでは「ゲーム側の 1 回の LLM 呼び出し文脈」を確定する。

ここで `llm_call_id` を発行し、以下を accumulator に入れる。

- run id
- player id / being id / persona id
- world tick
- reasoning effort
- attempt index / parent attempt id

`llm_call_id` は UUID 文字列にする。将来 `LLM_CALL` trace にも同じ ID を入れると、
既存 trace と prompt dataset の join が容易になる。

`being_id` / `persona_id` はこの文脈で正規取得する。Phase 1 実装前に
`runtime_manager.py` の turn context から取得できるかを確認し、取得点を 1 箇所に
固定する。取れない場合は `PROMPT_DATASET_CAPTURE_ENABLED=true` の run を
fail-fast させる。`None` のまま静かに保存しない。

### 3. `LiteLLMClient.invoke()` の `litellm.completion(**kwargs)` 境界

ここが request/response 保存の正史である。

`PromptBuilder` から再構成した request ではなく、`LiteLLMClient.invoke()` 内で
実際に `litellm.completion(**completion_kw)` へ渡す kwargs を capture する。
現コードでは `src/ai_rpg_world/infrastructure/llm/litellm_client.py:606` から
`:626` で `completion_kw` を作り、`:630` で `litellm.completion(**completion_kw)`
を呼ぶ。この `completion_kw` を canonical request とする。

保存する request は、同じ kwargs を再送できる粒度にする。

- `model`
- 最終 `messages` 全文
- `tools`
- `tool_choice`
- `timeout`
- `max_retries`
- `api_base` の mask 済み識別子
- `extra_body`
- `temperature` / `top_p` / `max_tokens` / `seed` など、存在する sampling parameter
- 未指定の parameter は「未指定」として保存する

`api_key` は絶対に保存しない。`api_base` は host alias や private endpoint が
混ざる可能性があるため、保存する場合も mask した識別子にする。

`request_hash` を `calls.jsonl` に持たせる。対象は、mask 後かつ参照化後の
canonical request に加え、`system_prompt_id` / `toolset_id` / `tool_choice` /
model / sampling parameter / `extra_body` を含む正規化 JSON である。これにより、
同じ送信内容の重複検出と、復元後 request の整合性検査ができる。

wire level の HTTP request までは v1 の必須対象にしない。litellm が provider HTTP へ
変換する前の kwargs を canonical request とする。もし将来、provider routing や
HTTP header まで含む厳密再送が必要になったら、litellm callback 経由で wire metadata
を別テーブルに保存する案を検討する。ただしその場合も認証 header は保存しない。

### 4. `ILLMClient.invoke()` 後

raw response と正規化出力を accumulator に入れる。

成功時は、litellm response object を JSON 化して `response.raw` に保存する。
保存対象は以下を含む。

- `id`
- `model`
- `system_fingerprint`
- `choices`
- `message`
- `tool_calls`
- `finish_reason`
- `usage`
- provider が返した追加 field

正規化した `tool_name` / `arguments` / `inner_thought` / `expected_result` は、
`response.raw` から導出した便宜 field として `output` に残す。正史は raw response である。

例外時は raw response が存在しないため、`response.error` に例外 class、
error code、mask 済み message、provider error の取得可能な structured field を保存する。
trace に長文の provider error を流し込む必要はないが、dataset 側では replay 不能な
失敗 request として残す。

reasoning 有効時は失敗すると fallback で reasoning なしの 2 回目 invoke が走る。
そのため **1 Phase A が 1 LLM 呼び出しとは限らない**。dataset の主テーブルは
「1 行 = 1 LLM 呼び出し」なので、reasoning 失敗行と fallback 成功行を別行にする。
同じ player / tick の retry 関係は `attempt_index` と `parent_attempt_id` で表す。

この時点で `calls.jsonl` に append する。Phase B の action 実行前にプロセスが落ちても、
「どの prompt を LLM に送ったか」と「LLM が何を返したか」は失われないようにするためである。

### 5. `runtime_manager.py` Phase B 完了後

Phase B は tool call を実行し、`action` / `action_result` trace を出す。
ここで該当 `llm_call_id` に対して、以下を確定する。

- selected tool name
- parsed arguments
- action success
- error code
- remediation
- result summary
- was no-op

Phase B 完了時は `turn_results.jsonl` に append する。
`calls.jsonl` の既存行は更新しない。JSONL を追記専用に保つことで、途中終了時にも
壊れた更新途中ファイルを作らない。

後段 export は `calls.jsonl` と `turn_results.jsonl` を `llm_call_id` で結合し、
Hugging Face 向けの `turns` テーブルを作る。Phase A 失敗や no-tool で Phase B が
成立しない場合も、`turn_results.jsonl` に失敗結果を 1 行残す。もし crash により
結果行が存在しない call があれば、export validation で `result_missing=true` として
検出し、既定では export を失敗させる。

### 6. メトリクスとの結合

現状の `LlmCallMetricsSink` は LLM 呼び出し完了時に metrics を受ける。
prompt dataset 用には、既存 sink を wrap する `PromptDatasetMetricsSink` を作り、
同じ metrics を accumulator に渡す。

必要な変更:

- `_build_llm_metrics_sink()` が受け取る context に `llm_call_id` を追加する。
- `LLM_CALL` trace payload にも `llm_call_id` を追加する。
- prompt dataset row にも `llm_call_id` を入れる。

## schema

### `calls.jsonl`

1 行 1 LLM 呼び出し。request と response が正史であり、prompt / output は
分析しやすくするための補助 view である。system prompt と toolset は参照で持つが、
rehydrate すると capture 時の request に戻せることを必須にする。

```json
{
  "schema_version": 1,
  "llm_call_id": "018f2b0e-9f6e-7a42-a2a0-4dfb8b8d26d1",
  "run_id": "v3coop_postrefactor_001",
  "world_id": 1,
  "being_id": "being_w1_p3",
  "player_id": 3,
  "persona_id": "rio",
  "character_name": "リオ",
  "turn_index": 42,
  "attempt_index": 0,
  "parent_attempt_id": null,
  "timestamp_utc": "2026-07-20T11:00:00.000000+00:00",
  "world_tick": 51,
  "time_of_day": {
    "label": "Day 2 朝 1:30",
    "phase_name": "morning",
    "is_dark": false
  },
  "provenance": {
    "git_commit": "40470003e8ecfc44f00e7e5363d86a16565645da",
    "git_dirty": false,
    "profile": "belief_goal_full",
    "scenario_id": "survival_island_v3_coop",
    "scenario_sha256": "..."
  },
  "model": {
    "client": "litellm",
    "model": "openrouter/deepseek/deepseek-v4-flash",
    "provider": "DeepSeek",
    "api_base_kind": "openrouter",
    "reasoning_effort": null,
    "temperature": null,
    "top_p": null,
    "max_tokens": null,
    "seed": null,
    "tool_choice": "required"
  },
  "request": {
    "capture_boundary": "litellm.completion_kwargs",
    "request_hash": "request:sha256:...",
    "kwargs": {
      "model": "openrouter/deepseek/deepseek-v4-flash",
      "messages": [
        {"role": "system", "content_ref": "system_prompt:sha256:..."},
        {"role": "user", "content": "## 現在の状態\n..."}
      ],
      "tools_ref": "toolset:sha256:...",
      "tool_choice": "required",
      "timeout": 90,
      "max_retries": 0,
      "api_base": "masked:openrouter",
      "extra_body": {
        "provider": {
          "order": ["DeepSeek"],
          "allow_fallbacks": false
        }
      }
    },
    "omitted_secret_keys": ["api_key"],
    "unset_parameters": ["temperature", "top_p", "max_tokens", "seed"],
    "rehydration": {
      "system_prompt_id": "system_prompt:sha256:...",
      "toolset_id": "toolset:sha256:..."
    }
  },
  "prompt": {
    "messages": [
      {"role": "system", "content_ref": "system_prompt:sha256:..."},
      {"role": "user", "content": "## 現在の状態\n..."}
    ],
    "system_prompt_id": "system_prompt:sha256:...",
    "system_prompt_sha256": "...",
    "user_prompt_sha256": "...",
    "toolset_id": "toolset:sha256:...",
    "sections": [
      {
        "name": "objective",
        "title": "目的",
        "content": "...",
        "chars": 120,
        "tokens": null
      },
      {
        "name": "current_state",
        "title": "現在の状態",
        "content": "...",
        "chars": 1500,
        "tokens": null
      }
    ],
    "overflow": {
      "did_overflow": false,
      "dropped_sections": []
    },
    "sections_are_best_effort": true
  },
  "response": {
    "raw": {
      "id": "chatcmpl-...",
      "object": "chat.completion",
      "created": 1721450000,
      "model": "deepseek-v4-flash",
      "system_fingerprint": null,
      "choices": [
        {
          "index": 0,
          "message": {
            "role": "assistant",
            "content": null,
            "tool_calls": [
              {
                "id": "call_...",
                "type": "function",
                "function": {
                  "name": "spot_graph_interact",
                  "arguments": "{\"object_label\":\"流木の山\",\"action_name\":\"gather_driftwood\"}"
                }
              }
            ]
          },
          "finish_reason": "tool_calls"
        }
      ],
      "usage": {
        "prompt_tokens": 8200,
        "completion_tokens": 130,
        "total_tokens": 8330,
        "completion_tokens_details": {
          "reasoning_tokens": 0
        }
      }
    },
    "raw_sha256": "..."
  },
  "output": {
    "raw_tool_call": {
      "name": "spot_graph_interact",
      "arguments": "{\"object_label\":\"流木の山\",\"action_name\":\"gather_driftwood\"}"
    },
    "tool_name": "spot_graph_interact",
    "arguments": {
      "object_label": "流木の山",
      "action_name": "gather_driftwood"
    },
    "inner_thought": "流木が必要だ。まず確保する。",
    "expected_result": "流木を入手できるはずだ。"
  },
  "metrics": {
    "wall_latency_ms": 4123,
    "prompt_tokens": 8200,
    "completion_tokens": 130,
    "cached_tokens": 7800,
    "reasoning_tokens": 0,
    "cost_usd": 0.00042,
    "success": true,
    "error_code": null,
    "error_detail": ""
  },
  "trace_refs": {
    "llm_call_seq": 1233
  }
}
```

`request.kwargs.messages` は実際に送った最終 messages である。system message だけは
`content_ref` に置き換えてもよいが、`system_prompts.jsonl` から戻すと元の
`content` とバイト単位で一致しなければならない。`tools` も同様に `tools_ref` で
参照化してよいが、`toolsets.jsonl` から戻すと元の配列と一致しなければならない。

`response.raw` は provider 生レスポンス全体を JSON 化したものを保存する。
litellm response が pydantic model の場合は `model_dump(mode="json")` 相当、
dict の場合はそのまま、JSON 化できない値は明示的な変換規則で文字列化する。
正規化 `output` は便宜 field であり、再現・監査の正史は `response.raw` とする。

### `turn_results.jsonl`

1 行 1 Phase B 結果。`llm_call_id` は `calls.jsonl` の行を参照する。

```json
{
  "schema_version": 1,
  "llm_call_id": "018f2b0e-9f6e-7a42-a2a0-4dfb8b8d26d1",
  "run_id": "v3coop_postrefactor_001",
  "world_tick": 51,
  "player_id": 3,
  "result": {
    "action_success": true,
    "action_result_error_code": null,
    "result_summary": "[OK] 流木を 1 個拾った。",
    "remediation": null,
    "was_no_op": false
  },
  "trace_refs": {
    "action_seq": 1234,
    "action_result_seq": 1235
  }
}
```

export 後の Hugging Face 主テーブル `turns` では、`calls` の内容に `result` を
結合した 1 行 1 LLM 呼び出しの形にする。

#### 必須・任意の考え方

- 必須:
  - `schema_version`
  - `llm_call_id`
  - `run_id`
  - `being_id`
  - `player_id`
  - `persona_id`
  - `world_tick`
  - `request.request_hash`
  - `request.kwargs`
  - `request.kwargs.messages`
  - `response.raw` または `response.error`
  - `prompt.system_prompt_id`
  - `metrics.success`
- 任意:
  - `time_of_day`
  - `tokens`
  - `cost_usd`
  - `trace_refs`

`being_id` / `persona_id` は prompt dataset capture 有効時は必須にする。
取得できない場合は保存値を `null` にせず、run を開始時または最初の該当 turn で
fail-fast させる。任意項目は欠けても schema を壊さない。欠けた理由が異常な場合は
warning / trace ではなく dataset export validation で検出する。

### `system_prompts.jsonl`

system prompt は hash で重複排除する。将来、他キャラクターのペルソナが増えても
行を追加するだけで済む。

```json
{
  "schema_version": 1,
  "system_prompt_id": "system_prompt:sha256:...",
  "system_prompt_sha256": "...",
  "persona_id": "ada",
  "character_name": "エイダ",
  "player_id": 1,
  "being_id": "being_w1_p1",
  "prompt_builder_version": "default_prompt_builder:v1",
  "content": "あなたは医師のエイダです。...",
  "chars": 8400,
  "tokens": null,
  "first_seen_llm_call_id": "018f2b0e-..."
}
```

注意: system prompt が完全固定でなくなった場合でも、hash が変わるので別行として
保存される。turn 行は常に `system_prompt_id` を参照するため、schema 変更は不要。

### `toolsets.jsonl`

```json
{
  "schema_version": 1,
  "toolset_id": "toolset:sha256:...",
  "toolset_sha256": "...",
  "tool_names": [
    "spot_graph_explore",
    "spot_graph_interact",
    "speak"
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "spot_graph_explore",
        "description": "...",
        "parameters": {}
      }
    }
  ],
  "chars": 12000,
  "first_seen_llm_call_id": "018f2b0e-..."
}
```

tool 定義も system prompt と同じく hash で重複排除する。`LLM_TOOL_MODE` や
機能フラグで tool list が変わる場合も、別 toolset 行として保存される。

### `run.json`

```json
{
  "schema_version": 1,
  "run_id": "v3coop_postrefactor_001",
  "source_run_dir": "var/runs/v3coop_postrefactor_001",
  "experiment_manifest_path": "experiment.config.resolved.json",
  "experiment_manifest_sha256": "...",
  "profile": "belief_goal_full",
  "scenario_path": "data/scenarios/survival_island_v3_coop.json",
  "scenario_sha256": "...",
  "git": {
    "commit": "40470003e8ecfc44f00e7e5363d86a16565645da",
    "dirty": false
  },
  "runtime_config": {
    "LLM_CLIENT": "litellm",
    "LLM_MODEL": "openrouter/deepseek/deepseek-v4-flash",
    "PROMPT_DATASET_CAPTURE_ENABLED": true
  }
}
```

## section schema

prompt の section は固定カラムにしない。新しい記憶 section、目的 section、
失敗 feedback section が増えても、以下の list に要素を足す。

ただし v1 では section の完全分割を必須にしない。現 builder は最終 user content を
結合済みであり、後から完全な section 境界を復元できない場合があるためである。
replay と監査の正史は `request.kwargs.messages` の全文であり、section は分析用の
best-effort metadata とする。

```json
{
  "name": "prediction_feedback",
  "title": "予測誤差からの学習",
  "content": "...",
  "chars": 320,
  "tokens": null,
  "source": {
    "kind": "prompt_builder",
    "trace_kind": "prediction_outcome"
  }
}
```

初期実装で tokens は `null` でよい。後続で tokenizer を導入する場合は
export 時に埋める。呼び出し時の provider token usage は全体 token であり、
section 別 token ではないため、混同しない。

## request 復元と replay

v1 の replay 単位は「litellm に渡した kwargs」である。
`calls.jsonl` の `request.kwargs` にある `content_ref` と `tools_ref` を
`system_prompts.jsonl` / `toolsets.jsonl` で rehydrate すると、capture 時の
canonical request に戻る必要がある。

実装では以下の helper を用意する。

- `reconstruct_request(call, system_prompts, toolsets) -> dict`
  - `content_ref` を system prompt 本文に戻す。
  - `tools_ref` を tools 配列に戻す。
  - `api_key` は戻さない。replay 実行時の runtime secret から注入する。
  - `api_base` は mask 済み値なので、必要なら replay 側の mapping 設定で実 URL に戻す。
- `canonicalize_request(request) -> dict`
  - JSON key 順序、空白、参照表現を正規化する。
  - hash 計算の入力を固定する。
- `compute_request_hash(request) -> str`
  - `request_hash` を再計算する。

必須テスト:

1. system prompt を `content_ref` に置き換えて保存した call を
   `reconstruct_request()` で戻すと、元の `messages` と完全一致する。
2. `tools_ref` を戻すと、元の `tools` 配列と完全一致する。
3. `canonicalize_request(reconstruct_request(call))` の hash が
   `request.request_hash` と一致する。
4. `response.raw` から正規化した `output` が再導出できる。

確率的な揺らぎは replay の範囲外である。`temperature`、`top_p`、`seed`、
`max_tokens` などの実使用値または未指定状態は必ず保存し、replay は
「同一 parameter で再送できる」ことを保証する。モデル側の sampling による差分は
dataset card の Limitations に明記する。現時点で seed を固定していない場合は、
`unset_parameters` に `seed` を残し、replay の限界として扱う。

## Hugging Face 向け export

実験中は JSONL で保存し、公開・配布時に Parquet へ変換する。

提案コマンド:

```bash
uv run python scripts/export_prompt_dataset.py \
  --run-dir var/runs/v3coop_postrefactor_001 \
  --run-dir var/runs/v3coop_postrefactor_002 \
  --split-map data/dataset_splits/prompt_dataset_v1.json \
  --out var/datasets/llm-rpg-prompts-v1
```

`--run-dir` は複数指定できるようにする。単一 run export はその部分集合である。
多数 run を Hugging Face の正史へ積むため、export は run 跨ぎの merge を標準機能にする。
`system_prompts` と `toolsets` は run を跨いで hash 重複排除する。`runs` table には
入力 run をすべて積む。

split は merge 時に run 単位で指定する。例:

```json
{
  "train": ["v3coop_postrefactor_001", "v3coop_postrefactor_002"],
  "validation": ["v3coop_prompt_eval_001"],
  "test": ["v3coop_prompt_holdout_001"]
}
```

出力例:

```text
var/datasets/llm-rpg-prompts-v1/
  README.md
  dataset_infos.json
  data/
    train-00000-of-00001.parquet
  system_prompts/
    train-00000-of-00001.parquet
  toolsets/
    train-00000-of-00001.parquet
  runs/
    train-00000-of-00001.parquet
  raw/
    calls.jsonl.gz
    turn_results.jsonl.gz
    system_prompts.jsonl.gz
    toolsets.jsonl.gz
    run.json
```

### 読み込み例

Hugging Face Hub では named config を用意し、sidecar table も読みやすくする。

```python
from datasets import load_dataset

turns = load_dataset("Motifman/llm-rpg-prompts-v1", "turns")
system_prompts = load_dataset("Motifman/llm-rpg-prompts-v1", "system_prompts")
toolsets = load_dataset("Motifman/llm-rpg-prompts-v1", "toolsets")
runs = load_dataset("Motifman/llm-rpg-prompts-v1", "runs")
```

ローカル検証では `data_files` 指定でも読めるようにする。

```python
from datasets import load_dataset

turns = load_dataset(
    "parquet",
    data_files={"train": "data/train-00000-of-00001.parquet"},
)
```

Hugging Face Hub に置く場合は、`turns` を主 config として扱う。
`system_prompts`、`toolsets`、`runs` は sidecar config とし、`README.md` に
join key を明記する。`dataset_infos.json` には各 config の feature 定義を持たせる。

### split 方針

既定では run 単位で split する。複数 run export では `--split-map` で
run id を split に割り当てる。

- 複数 run がある場合:
  - `train`: 学習用 run
  - `validation`: 設計確認用 run
  - `test`: 最終評価用 run
- 1 run しかない場合:
  - `train` のみ

同一 run 内の turn を random split しない。理由は、同じキャラクター・同じ世界状態の
連続データが train / test に漏れるからである。キャラクター単位 split も、協調実験では
会話相手の発話が混ざるため既定にはしない。必要なら export オプションで追加する。

## Dataset card

`README.md` には以下を必ず書く。

- Dataset Summary
  - llm-rpg 実験 run から作った LLM tool-use prompt dataset であること
- Dataset Structure
  - `turns` / `system_prompts` / `toolsets` / `runs` の関係
  - join key: `system_prompt_id`、`toolset_id`、`run_id`
- Data Fields
  - `turns` の主要カラム
  - `request` が litellm kwargs、`response.raw` が provider response の正史であること
- Data Collection
  - 実験シナリオ、profile、LLM model、git commit
- Intended Use
  - tool-use decision の分析、prompt ablation、行動学習、request replay
- Limitations
  - 合成ゲーム内データであり、現実世界の一般対話ではない
  - tool schema と世界ルールに強く依存する
  - sampling parameter は保存するが、モデル側の確率的揺らぎは除去しない
  - seed が未指定の run は、同一 parameter で再送できても同一 response を保証しない
- Privacy
  - ゲーム内合成データであり、個人情報は含めない設計
  - ただし `.env` / API key / host alias は保存対象外で、manifest 側も mask する
- Versioning
  - schema version と生成 commit

## プライバシーと秘密情報

保存対象はゲーム内の合成データであり、原則として個人情報は含まない。
ただし prompt には scenario 文面や run 設定が入り得るため、以下を守る。

- API key、認証 token、`.env` の生値は保存しない。
- `experiment.config.resolved.json` と同じく秘密値は mask する。
- request の `api_key` は `omitted_secret_keys` に key 名だけ残し、値は保存しない。
- `api_base` は host alias や private endpoint を含み得るため、mask 済み識別子にする。
- response 内に秘密情報は通常入らない想定だが、provider が echo した request header、
  account id、organization id、token らしき field を返した場合は mask する。
- provider error detail は、replay 不能な失敗 request を理解するために prompt dataset 側にも
  mask 済み message と structured field を保存する。認証情報、host alias、token らしき値は
  保存前に除去する。
- user が手書きした scenario に現実個人名が入る可能性は dataset card に明記する。

## サイズ対策

- 実験中:
  - `calls.jsonl` と `turn_results.jsonl` に append。
  - system prompt と tools は hash 参照化して重複排除。
  - `messages` の system は `content_ref` とし、本文は `system_prompts.jsonl` に保存。
  - `request.kwargs.messages` の user message は turn ごとに全文保存する。
  - `response.raw` は全文保存する。tool call + usage が中心であり、prompt に比べれば小さい。
- export 時:
  - Parquet + zstd 圧縮を既定にする。
  - raw JSONL は `.jsonl.gz` で同梱するか、`--include-raw=false` で省く。

サイズ見積り:

- system prompt と toolset は run 内・run 跨ぎで重複排除される。
- per-turn で大きいのは user message 本文で、これは replay に必須なので削らない。
- raw response は通常 tool call、finish reason、usage 程度であり、user prompt より十分小さい。
- 200 tick × 4 player 規模では、JSONL 生データでも `trace.jsonl` より大きくなるが、
  Parquet + zstd では実用範囲に収まる見込みである。

## バージョニングと migration

すべてのテーブルに `schema_version` を持つ。初期値は `1`。

変更方針:

| 変更 | 対応 |
|---|---|
| section 追加 | `prompt.sections[]` に要素追加。schema version は維持可能 |
| persona 追加 | `system_prompts` に行追加。schema version は維持 |
| model/provider 追加 | `model` object に key 追加。schema version は維持 |
| request kwargs 追加 | `request.kwargs` に key 追加。schema version は維持 |
| response field 追加 | `response.raw` に provider field を保持。schema version は維持 |
| 必須 key の意味変更 | schema version を上げる |
| `messages` の構造変更 | schema version を上げる |

移行スクリプトは `scripts/migrate_prompt_dataset.py --from v1 --to v2` のような
別コマンドにする。実験中の writer は最新 schema のみを書く。

## 失敗時の扱い

`PROMPT_DATASET_CAPTURE_ENABLED=false` のときは何もしない。

`true` のとき:

1. run 開始時に `prompt_dataset/` を作れなければ fail-fast。
2. `system_prompts.jsonl` / `toolsets.jsonl` / `calls.jsonl` /
   `turn_results.jsonl` を開けなければ fail-fast。
3. 1 行 append に失敗したら既定では fail-fast。
4. `PROMPT_DATASET_CAPTURE_FAILURE_POLICY=warn` の場合のみ warning を出して続行する。
   ただし `export_manifest.json` に `capture_incomplete=true` を残す。

この方針は「有効化した収集が静かに欠ける」ことを避けるためである。

## 実装フェーズ案

### Phase 1: writer と schema の最小実装

- `PromptDatasetCaptureSink` を追加。
- `run_scenario_experiment.py` で profile/config から有効化し、run dir 配下へ sink を作る。
- `runtime_manager.py` Phase A / B から turn context と result を sink に渡す。
- `LiteLLMClient.invoke()` の `litellm.completion(**completion_kw)` 境界で
  request kwargs と raw response / error を capture する。
- `calls.jsonl` / `turn_results.jsonl` / `system_prompts.jsonl` / `toolsets.jsonl` を出す。
- `llm_call_id` を prompt dataset と `LLM_CALL` trace に入れる。
- `reconstruct_request()` と request hash round-trip test を追加する。

### Phase 2: export

- `scripts/export_prompt_dataset.py` を追加。
- `--run-dir` 複数指定と `--split-map` に対応する。
- `calls.jsonl` と `turn_results.jsonl` を結合し、Hugging Face 向け `turns` を
  Parquet に変換。
- run 跨ぎで `system_prompts` / `toolsets` を hash 重複排除する。
- `README.md` と named config 対応の `dataset_infos.json` を生成。
- `load_dataset(..., "turns")` と `load_dataset(..., "system_prompts")` で読める
  smoke test を追加する。

### Phase 3: 品質検査

- `calls.jsonl` の行数と `LLM_CALL` trace 件数の突合。
- `calls.jsonl` と `turn_results.jsonl` の `llm_call_id` 参照整合性検査。
- `system_prompt_id` / `toolset_id` の参照整合性検査。
- `request_hash` の再計算検査。
- `response.raw` から `output` を再導出できることの検査。
- `capture_incomplete=false` の検査。
- run 単位 split の検査。

## Phase 1 前に確定する事項

1. `being_id` / `persona_id` の正規取得元。
   - Phase A の turn context を正規取得点にできるか確認する。
   - 取得できるなら `PromptDatasetTurnContext` の必須 field にする。
   - 取得できないなら capture 有効 run は fail-fast。`None` を保存して進めない。
2. `temperature` の取得元。
   - 現行 `ILLMClient.invoke()` の port には temperature 引数が無い。
   - `LiteLLMClient.invoke()` の `completion_kw` に存在しない場合は
     `unset_parameters` に記録する。
   - provider 既定値を明示的に固定したい場合は、別 PR で `ResolvedLlmRuntimeConfig`
     に追加してから request に出す。
3. section 本文の正確な分割。
   - v1 では best-effort metadata とする。
   - 完全 replay は `request.kwargs.messages` 全文で保証する。
4. raw provider response。
   - 保存する。`response.raw` が正史。
   - 正規化 `output` は `response.raw` から導出する便宜 field とする。
