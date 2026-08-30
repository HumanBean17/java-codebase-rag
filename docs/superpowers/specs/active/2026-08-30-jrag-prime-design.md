# jrag prime — replace skill/agent artifacts with a SessionStart priming hook

**Status:** draft

## Context

Issue #464: bench condition D (jrag full) over-explores — the agent graph-walks
(`microservices → http-routes → flow → inspect → callees → …`, 14 calls on
`bc-sem-01_D`) where condition A reads-and-answers with grep. Answer quality is
equal when D finishes; the failure mode is procedure, not tool quality.

Hypothesis (this spec): the shipped teaching artifacts — two skills and two
subagents (~45 KB of decision frameworks, workflow patterns, recovery
playbooks, all "MUST BE USED PROACTIVELY") — teach agents an elaborate
exploration procedure and thereby bias them toward over-exploration. Modern
LLMs need only know that the tool exists, what it can do, and what state it is
in; the CLI already self-documents (`--help` prints commands, flags, enum
values) and the MCP surface carries just-in-time hints
(`agent_next_actions`, `hints_structured`).

Nuance the bench makes explicit: condition D does not use the skill — its own
prompt enumerates verbs and still over-walks. So the testable claim is "less
teaching surface → less over-exploration," which the bench can measure
directly. The distinction this design draws is **capability description vs
procedure teaching**: prime describes what jrag is and what it can do; it does
not teach how to explore.

## Goal

Replace the four shipped skill/agent artifacts with `jrag prime` — a compact,
state-derived orientation payload injected via a SessionStart hook on the CLI
surface (beads `bd prime --hook-json` model). Validate the hypothesis in the
bench (#464 slice) *before* the breaking removal ships.

## Non-goals

- Changing the MCP surface's tools, descriptions, or hints.
- Any coaching in the prime payload — no decision tables, workflow patterns,
  escalation rules, recovery playbooks, or "stop early" instruction.
- Managed sections in AGENTS.md/CLAUDE.md (no beads-style pointer section).
- Renaming or touching on-disk `.java-codebase-rag*` state or env vars.

## Design

### `jrag prime` command

New read-only subcommand (registered in `jrag.py` alongside `status`). Default
output: bare markdown. `--hook-json`: the same markdown wrapped in the Claude
Code SessionStart envelope (`hookSpecificOutput.hookEventName: "SessionStart"`,
payload in `additionalContext`; qwen-code consumes the same shape).

Payload contract — navigation framing, four parts:

1. **Identity.** `jrag` is a prebuilt structural map of this Java/Kotlin repo,
   queried from the shell: resolve a name to its file, walk who-calls-whom and
   dependency edges, see entry points and service boundaries — instead of
   grepping for structure.
2. **Ability catalog.** The command verbs, one line each, grouped by intent
   (Locate / Traverse / Compose / Entries / Orient), plus a standalone line:
   `jrag --help` lists every command; `jrag <command> --help` lists flags and
   enum values.
3. **One trust rule.** If jrag and the files disagree, trust the files — the
   map may lag the working tree.
4. **Live state.** Freshness (fresh / stale with changed-file count, last
   increment age), service count and names (truncated), symbol/route/client/
   producer counts, watch daemon running or not.

Parts 1–3 are a static template (module constant in the source tree, not
`install_data`); part 4 is computed.

States and degradation:

| State | stdout | exit |
|---|---|---|
| Indexed (fresh or stale) | full payload | 0 |
| No project YAML / no index discovered | nothing | 0 |
| Internal error (unreadable meta, corrupt YAML) | nothing; one stderr line | 0 |

Silence when unindexed is what makes a user-scope hook tolerable — prime fires
in every session of every repo and must never nag repos it does not index.
Prime is hook-safe by construction: every soft state degrades to empty output.

Latency constraint: SessionStart fires on start, resume, and after compaction.
Prime reads filesystem metadata only — project-root discovery, index-dir
mtimes, graph meta, the watch daemon state file (`watch/paths.py`). It must
not import the vector stack or open Lance/graph stores; freshness detection is
extracted from `_cmd_status` (`jrag.py`) into a shared helper if currently
embedded there. Coverage counts that would require opening a store are dropped
from the payload rather than paid for.

### Surfaces

- **CLI surface** (`--surface cli`): prime + SessionStart hook is the only
  discovery mechanism. No skill, no subagent.
- **MCP surface** (`--surface mcp`): MCP server entry as today, tools only.
  The tool list self-announces; no prime, no artifacts.

### Installer / wizard

- `jrag install --surface cli` writes a SessionStart hook
  (`jrag prime --hook-json`) into each selected host's settings: claude-code →
  `.claude/settings.json` (project) / `~/.claude/settings.json` (user);
  qwen-code / gigacode → their `HostConfig` settings paths if they support
  SessionStart hooks — otherwise warn and skip (manual wiring documented in
  JRAG-CLI.md). Merge follows the `merge_mcp_config` pattern: idempotent,
  keyed on the command, write only on change, never touch unrelated hooks.
- `jrag update`: refreshes the hook's command path; removes all four
  previously deployed artifact files wherever they exist in the scope
  (existing per-file removal + directory-cleanup machinery in `installer.py`),
  covering upgrades from any 0.12.x; handles surface switching both directions
  (hook ⇄ MCP entry). The install marker grows a hook record.
- `INSTALL_TARGETS`, `install_data` packaging, and `--surface` help text
  updated to the hook model.

### Artifact removal (Phase B)

Deleted from the repo: `skills/explore-codebase/`, `skills/explore-codebase-cli/`,
`skills/README.md`, `agents/explorer-rag-enhanced.md`, `agents/explorer-rag-cli.md`.

### Bench revision (Phase A — runs first)

- `bench/prompts/D_jrag_full.md` keeps the `_shared_skeleton.md` structure;
  its hand-written tool enumeration is replaced by the real prime output,
  generated at run time by the bench harness — the bench tests the shipped
  artifact, not a drifting copy.
- Slice per #464: glm-4.7, seed 0, bank-chat; conditions A + revised-D, plus
  old-D for the before/after delta. Recorded in `bench/PREREGISTRATION.md`
  before the run.
- Gate: revised-D cap rate on call-trace + semantic ≤ A's (~≤2); C1/C2 improve
  without regressing blast-radius.

### Docs

- `docs/JRAG-CLI.md`: prime (payload states, `--hook-json`, silence rule);
  install flows rewritten (cli = hook, mcp = entry, neither deploys files);
  exit-code table gains prime.
- `docs/AGENT-GUIDE.md`: repositioned as a human reference for the MCP surface
  and hook-less hosts; the "copy-paste into AGENTS.md/CLAUDE.md" mandate is
  removed.
- `docs/DESIGN.md` / `docs/ARCHITECTURE.md`: surfaces sections move from
  skill/agent artifacts to prime + hook.
- Repo `CLAUDE.md` "Shipped artifacts" section and `README.md` claims updated.
- `docs/MIGRATION.md`, `docs/CONFIGURATION.md`: unchanged.

## Testing

- prime: golden payloads (fresh / stale / unindexed-silent / daemon on-off);
  `--hook-json` envelope schema validity; an import-set guard proving the
  prime path pulls no vector/Lance/graph-store modules (protects the latency
  budget); empty stdout + exit 0 on soft states.
- installer: hook merge idempotency (run twice → one entry), unrelated hooks
  preserved, unparseable settings → warn and skip without writing; `update`
  removes all four artifact files from a fixture mimicking a 0.12.x
  deployment; surface switch both directions.
- bench: the Phase A slice per the preregistration.
- Full suite once at the end (project rules; editable install enforced by
  `tests/conftest.py`).

## Rollout

Single release 0.13.0 carrying prime + hook wiring + artifact removal, tagged
only after the Phase A gate passes. If the gate fails: 0.13.0 ships prime
alone as opt-in, removal deferred, hypothesis recorded as falsified. Release
notes carry the breaking-change line (skills/agents removed; `jrag update`
cleans up deployed copies). Dual PyPI publish (`jrag-cli` + `java-codebase-rag`,
same version) per the publish-pip skill.

## Open Questions

1. Do qwen-code / gigacode support SessionStart hooks, and in what settings
   shape? Verify in Phase B; unsupported hosts warn and skip.
2. Which coverage counts are obtainable from metadata alone vs requiring a
   store open? Resolved during implementation by the drop-don't-pay rule.
3. Is the freshness computation in `_cmd_status` reusable as-is, or does it
   need extraction into a shared helper? Implementation detail, resolved in
   Phase A.

## TLDR

Remove all four shipped skill/agent artifacts (teaching causes over-exploration,
#464); replace with `jrag prime --hook-json` — a ~15-line navigation-framed
orientation (what jrag is, the verb catalog, trust-the-files, live index state)
injected by a SessionStart hook wired through the install wizard. CLI surface
only; MCP tools self-announce. Bench Phase A rewrites the D prompt to
runtime-generated prime output and runs the #464 slice; Phase B (removal +
hook wiring, one 0.13.0 release) proceeds only if revised-D caps drop to ≤ A's.
