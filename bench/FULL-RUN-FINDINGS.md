# Full-run findings — 2026-07-29 (Plan 4 CLI surface)

The first complete CLI-surface run of the effectiveness benchmark: 1,200 cells
(50 questions × 4 conditions × 2 models × 3 seeds), graded by the final grader
set (see PREREG Amendment 2026-07-28). Raw artifacts live in the gitignored
`bench/results/20260728T173105/` (local only); this file is the durable record.

> **Provisional.** The LLM-judge-driven verdicts below are pending the human κ
> gate (κ = N/A — no human labels yet). The judge was spot-checked on one cell
> (`bc-cs-01_D`) but never validated against humans at scale. Trust the
> programmatic (`set_match`) numbers; treat `llm_judge` numbers as directional
> until κ is closed.

## Headline — mean correctness by condition (capped = 0)

| Condition | Mean | n | cap rate |
|---|---|---|---|
| **A** lexical (grep/glob/read/bash) | **0.66** | 300 | 42 |
| **B** vector-only (`jrag search`) | 0.55 | 300 | 83 |
| **C** raw agent + shell | 0.61 | 300 | 52 |
| **D** jrag full (system under test) | 0.65 | 300 | 41 |

**A ≈ D.** jrag does not beat an intelligent grep baseline at end-to-end task
success. B (vector-only) is clearly worst — it caps most *and* scores lowest.

## The C1–C6 verdicts

| # | Claim | Verdict | Why |
|---|---|---|---|
| C1 | jrag > vector **and** grep on structural | **PARTIAL** | Beats vector-only everywhere. vs grep: **tied overall** (0.65 vs 0.66). Wins blast-radius (0.53 vs 0.37), upstream (0.56 vs 0.49), absence; loses call-trace (0.73 vs 0.95) and semantic (0.52 vs 0.74) to over-exploration. |
| C2 | jrag fewer steps + tokens | **PARTIAL** | Fewest **steps** (10.6 vs 10.9) and **context bytes** (13K vs 16K); but **more tokens** (6082 vs 5352). |
| C3 | cross-service: baselines fail, jrag resolves | **NOT SUPPORTED** | grep ≈ jrag (0.65 vs 0.61 capped; 0.82 vs 0.81 cap-excluded). Feign clients are greppable — baselines don't structurally fail. |
| C4 | re-index deterministic | **SUPPORTED** | PHASE0: n=2 byte-identical node/edge counts. |
| C5 | cost within ~2× vector-only | **SUPPORTED** | PHASE0 per-corpus build cost. |
| C6 | advantage holds across model tiers | **NOT SUPPORTED** | D−A gap ≈ 0 at both tiers (glm-4.7 −0.01, glm-5.1 −0.02). No advantage to hold. |

## The reframe — cap rate is the differentiator, not answer quality

Quality **conditional on finishing** (caps excluded):

| category | A | B | C | D | D cap vs A cap |
|---|---|---|---|---|---|
| call-trace | 0.98 | 0.99 | 0.99 | **1.00** | D 8 ≫ A 1 |
| cross-service | 0.82 | 0.80 | 0.77 | 0.81 | ~equal |
| semantic | 0.81 | 0.80 | 0.76 | 0.78 | D 8 ≫ A 2 |
| blast-radius | 0.62 | 0.35 | 0.57 | 0.62 | **D 4 ≪ A 12, B 22** |

When conditions finish, they are ~equal. What separates them:

- **jrag's genuine strength — finishing hard transitive questions.** On
  blast-radius, D is the only condition that reliably finishes (caps 4× vs A's
  12×, B's 22×). The graph pays off exactly where grep exhausts the budget.
- **jrag's genuine weakness — over-exploration.** D caps *more* than grep on
  trace (8 vs 1) and semantic (8 vs 2): it keeps graph-walking where grep
  reads-and-answers. The "richer verbs → fewer steps" thesis (Plan 4) inverts on
  open-ended questions.

## Per-corpus (capped = 0)

| corpus | A | B | C | D |
|---|---|---|---|---|
| bank-chat-system | 0.64 | 0.51 | 0.56 | **0.66** |
| shopizer (biggest) | **0.66** | 0.42 | 0.59 | 0.60 |
| spring-petclinic | 0.70 | 0.74 | 0.70 | 0.70 |

bank-chat (the calibration corpus) flattered jrag — it was the *only* corpus
where D won. shopizer (largest, 1167 files) favors grep. The bank-chat-only
pilot (D=0.66 > A=0.53) was favorable variance; the full grid reverses it to a
tie. **Lesson: never draw conclusions from an under-powered slice.**

## Efficiency & isolation

- Steps: A 10.9 / B 14.2 / C 12.7 / **D 10.6** (fewest).
- Tokens: A 5352 / B 9322 / C 8384 / D 6082.
- Context bytes: A 16331 / B 33213 / C 25020 / **D 12964** (most targeted).
- Lexical leakage (B isolation fidelity): A 0.13 / **B 0.16** / C 0.74 / D 0.59.
  B's residual leakage is the documented, accepted Plan-4 caveat.

## Methodology — 5 grader fixes that made this credible

The smoke + pilot exposed five grader defects, each validated on real cells and
amended in `PREREGISTRATION.md`. Without them, C3 would have been a manufactured
false negative (D's correct cross-service answers scored 0.00):

1. `client_route_match` positional extractor → cross-service (10 q) to `llm_judge`.
2. `path_match` numbered-list shredding → call-trace (5 q) to `llm_judge`.
3. `absence_check` phrase roulette → absence (3 q) to `llm_judge`.
4. Judge `--output-format json` double-escaped quotes → `--output-format text` + retry-once (errors 7.5% → 1%).
5. `set_match` F1 → **F2** recall-weighted (fixes verbose-correct under-credit; rejects spray false-positives).

137 bench tests green.

## Reproduce

```
.venv/bin/python -m bench.run_bench --models glm-4.7,glm-5.1 --seeds 0,1,2 --max-turns 30 --wall-timeout 900
.venv/bin/python -m bench.grade --cells bench/results/<run>/cells.jsonl --expected bench/oracle/expected --questions-glob "bench/questions/*.jsonl"
.venv/bin/python -m bench.report --run-dir bench/results/<run>
```

## TL;DR

jrag (D=0.65) **ties** an intelligent grep baseline (A=0.66) and beats
vector-only (B=0.55) on end-to-end task success. The headline cross-service
claim (C3) does **not** hold — Feign clients are greppable. jrag's real edge is
narrow: it finishes hard transitive blast-radius questions that grep/vector/raw
can't (caps 4× vs 12–22×). Its real weakness is over-exploration (capping on
trace/semantic where grep reads-and-answers). C2 partial, C6 not supported, C4/C5
supported. **All judge-driven verdicts are provisional pending the human κ gate.**
