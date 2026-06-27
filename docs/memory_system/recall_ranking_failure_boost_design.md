# 想起階層が「行動を変えない」問題と recall ranking 改善案

無人島 Y 実走 (#596) の subagent review (#596 後段) で指摘された
「想起階層 ON でも agent の行動は変わらない、recall_chars 1230 字を消費して
silent inefficiency」問題への改善案。

## 問題の構造

### 現在の挙動

`src/ai_rpg_world/application/llm/services/episodic_passive_recall_retrieval.py` の
`multi_cue_score` は:

- 各 episode が cue arms (= place_spot / entity / action / outcome 等)
  で何 distinct (axis:value) hit したかを数える
- ランキング: `multi_cue_score - habituation_penalty`
- 上位 N (= slot capacity 4) が想起 slot に乗る

### Fix D の意図と副作用

`src/ai_rpg_world/application/llm/services/episodic_cue_rules.py:301-327`
の `_outcome_cue_from_success_and_error`:

```python
if success:
    return None  # Fix D: 成功 outcome cue は index 選択性が極端に低い
# 失敗時のみ axis="outcome", value="failure_<error_code>" を貼る
```

**意図**: 成功 outcome cue が全 episode に貼られると recall が肥大して
selection 力を失う問題への対策。

**副作用**: failure episode は **「現在 失敗中の tick の outcome cue マッチ」
でしか recall に上がらない** 構造に。直前 action が成功 / 未実行の tick では
failure 軸が立たず、failure episode は cue match 0 で recall から脱落する。

### Y 実走で観察された反証

- 412 recall events 中、outcome 軸で match したのは **19 件 (4.6%)** のみ
- player 1 が `gather_dry_leaves` を 4 連続失敗したが、recall は同 place の
  「枯れ葉を成功で集めた」過去エピソードを強化
- failure からの「学習」経路が事実上不在 = subagent 3 が指摘した
  「想起階層が agent 行動を変えていない」現象の構造的原因

## 改善案 5 つ

### 案 A: failure boost in `multi_cue_score`

```python
def multi_cue_score(eid: str) -> int:
    base = len(multi_cue_canonicals.get(eid, frozenset()))
    ep = episode_by_id.get(eid)
    if ep and _has_failure_cue(ep):
        base += 1  # failure boost
    return base
```

- 効果: failure episode の総合 rank が +1 されて上位に来やすくなる
- 問題: 全 failure を一律 boost すると、過去の全失敗が常に上位に張り付く
  リスク。habituation が効かないと永続的になる

### 案 B: intended_action / current_attempt cue (本命)

現在 situation cue は「直前 tick の実行結果」由来。これに加えて
**「これから何をしようとしているか」** の cue を立てる:

- LLM が直前 turn で `inner_thought` に「枯れ葉を集めたい」と書いた → 次 tick で
  「intended_action:gather」みたいな cue を立てる
- もしくは agent が直前 tick で同じ tool を 1 回失敗したら、その tool 名を
  「retrying_action:gather_dry_leaves」cue として次 tick に持ち越す
- = 同 action の過去 episode (= 成功・失敗両方) が cue でヒット

効果:
- 関連経験の自然な想起 (= 「同じことをやろうとした時の過去」)
- failure episode は outcome cue で **追加** hit → multi_cue_score が高くなる
- Fix D の意図 (= 成功 outcome cue 廃止) を壊さない

### 案 C: failure episode の score boost (案 A の精緻版)

failure cue 単体 boost ではなく、**「同 action cue + outcome:failure」両方
を持つ episode に score +1**:

```python
def _intent_aligned_failure_boost(eid: str, situation_cues: set[str]) -> int:
    ep = episode_by_id.get(eid)
    if not ep:
        return 0
    has_failure = any(c.axis == "outcome" and c.value.startswith("failure_") for c in ep.cues)
    if not has_failure:
        return 0
    # episode の action cue が現在の situation cue にも居るか?
    ep_actions = {c.value for c in ep.cues if c.axis == "action"}
    sit_actions = {c.split(":")[1] for c in situation_cues if c.startswith("action:")}
    if ep_actions & sit_actions:
        return 1
    return 0
```

- 効果: 「現在やろうとしている action」の過去失敗だけが boost される
- 案 A より selective、案 B より実装が小さい

### 案 D: chain detection で recall_by_handle auto-trigger

同 action の連続失敗を tick scheduler で検知し、過去の同種失敗 episode を
自動で slot に強制注入する:

- 効果: agent が prompt で「過去にも失敗した」を必ず読まされる
- 問題: agent の自律判断を奪う overreach。recall_by_handle tool の
  meaning が崩れる

### 案 E: 「最近の失敗」専用 buffer

過去 K tick で起きた failure episode を最大 M 件 slot に強制注入:

- 効果: 直近失敗が常に意識に上がる
- 問題: 「働き者の失敗」(= 沢山 try してる agent) ですぐ buffer が埋まり、
  古い重要 episode の余地を奪う

## 推奨: 案 B + 案 C の組み合わせ

### 設計

**案 B (intended_action cue)**:

`PromptBuilder.build_full_prompt` の situation cue 生成箇所で、
直前 turn の `inner_thought` または `tool_call` から「next intended action」
を抽出し、`intended_action:<tool_name>` のような新 axis として situation cues
に加える。

```python
# 仮の擬似コード:
last_action = action_result_store.get_last(player_id)
if last_action and not last_action.success:
    intended_cues.add(f"retry_action:{last_action.tool_name}")
```

cue rules 側にも対称に `action:<tool_name>` を episode 側に立てる
(= 既に立っているはず) → cue match が成立する。

**案 C (intent-aligned failure boost)**:

`_arm_score_key` の計算で multi_cue_score に `_intent_aligned_failure_boost`
を加算する。boost は **現在の retry_action cue とマッチする** failure
episode に対してのみ +1。

```python
def _arm_score_key(ep):
    penalty = habituation_penalty(ep.episode_id)
    boost = _intent_aligned_failure_boost(ep.episode_id, situation_cues)
    return multi_cue_score(ep.episode_id) + boost - penalty
```

### 想定される変化

| 状況 | 旧挙動 | 新挙動 |
|---|---|---|
| 同 action を初めて試す | 関連 episode は cue で hit | 同じ (= 影響なし) |
| 同 action を 1 回失敗、次 tick で再 try | 過去成功 episode が rank 上位 | retry_action cue + failure boost で **過去同種失敗** episode が rank 上位 |
| ループから抜けた (= 成功した) 後 | habituation で recall が落ち着く | habituation が同様に効く |
| 異種 action での通常想起 | 通常通り | 通常通り (= boost は intent aligned のみ) |

= **「同じことをやろうとした時に過去の同種失敗が真っ先に思い出される」**
構造になる。これは人間の記憶に近い (= 「あれ、これ前も失敗したな」)。

### 実装スコープ (= 想定 PR-P)

1. `cue_rules.py` に `_build_intent_cues(action_result_store, player_id)` を追加
2. `prompt_builder.py` の situation cue 生成で `intent_cues` を merge
3. `episodic_passive_recall_retrieval.py` に
   `_intent_aligned_failure_boost(eid, situation_cues)` を追加
4. `_arm_score_key` で boost を加算
5. テスト:
   - 同 action retry 時に過去同種失敗 episode が recall 上位に上がる
   - 異種 action では boost が効かない
   - habituation が同じく適用される
   - intent cue が空 (= 初期 tick / no last action) の時の挙動

## 評価指標 (= Y 実走 再走 で観察したい)

- 同 action 連続失敗の回数 (= 旧 4 連続 から 1-2 連続に減る期待)
- recall に乗る failure episode の割合 (= 旧 19/412 = 4.6% から増える)
- agent の inner_thought に「前にも失敗した」「別の方法を試す」が現れる頻度
- 全体の完走率 (= survival_island_v2 で rescue 到達率)

## 設計判断の振り返り

- Fix D 自体は今でも正しい (= 全 success に outcome cue を貼ると selection
  力が崩壊)
- ただし Fix D の **副作用**として failure 系経験が想起されにくくなった
- 案 B + C は Fix D を温存しつつ failure の selection 力を取り戻す方向
- 「想起階層が行動を変える」を観測できる最小改修

## 関連

- subagent 3 review (#596): 「想起階層は behavior change を起こしていない」
- Fix D: `episodic_cue_rules.py:301-327`
- recall ranking: `episodic_passive_recall_retrieval.py:398`
