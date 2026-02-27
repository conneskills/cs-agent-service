# GEMINI.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Alma Coder** (package: `alma-coder`) is a markdown-based workflow orchestration system for Claude Code, Cursor IDE that transforms unreliable AI coding into production-ready development. The system uses executable Markdown files with XML-like structured tags to define workflows, commands, templates, and knowledge base references.

**Core value proposition:** Adds validation, persistent memory, and quality gates to AI coding to reduce bugs and rework from 30% to <5%.

**Branding:** The product displays as "Alma Coder" in all user-facing messages and banners.


## Architecture

### Shared Core (v2.1+)

All platform-agnostic files live in `.shared/`. Platform directories use symlinks:
- `.gemini/workflows -> ../.shared/workflows`
- `.gemini/agents -> ../.shared/agents`

```
.shared/                       # Single source of truth
├── workflows/
│   ├── workflows/             # 34 execution workflows
│   ├── commands-internal/     # 31 internal command implementations
│   ├── templates/             # 31+ document templates with [PLACEHOLDER] syntax
│   └── references/            # Knowledge base (patterns, guidelines, checklists)
└── agents/                    # 12 specialized agents

.gemini/commands/ac/           # 6 slash commands (/ac-*)
.planning/                     # Generated project state (NOT in repo)
├── PROJECT.md, ROADMAP.md, STATE.md
├── phases/                    # Phase plans and summaries
├── memory/chapters/           # Persistent architectural decisions (CAP-*.md)
└── config.json                # Model profiles, feature toggles
.indexes/                      # Local search index (in .gitignore)
```

### Core Abstractions

- **Commands** (`commands/*.md`): User-facing entry points with YAML frontmatter
- **Workflows** (`workflows/workflows/*.md`): Multi-step procedures with `<purpose>`, `<process>`, `<step>` tags
- **Templates** (`workflows/templates/*.md`): Reusable structures using `[PLACEHOLDER]` syntax
- **References** (`workflows/references/*.md`): Knowledge base (patterns, anti-patterns, checklists)
- **Agents** (`agents/*.md`): 12 specialized agents spawned via Task tool with isolated 200k token context

### alma-tools.js CLI

Zero-dependency Node.js CLI (`bin/alma-tools.js`) providing deterministic operations for state, phase, config, and workflow management. Replaces ~220 fragile AI-driven bash operations with JSON-first, CWD-relative commands.

**Command groups:**
| Command | Purpose | Example |
|---------|---------|---------|
| `state` | Read/write STATE.md fields | `state snapshot`, `state set "Status" "In progress"` |
| `phase` | Phase resolution, listing, CRUD | `phase list`, `phase complete 36` |
| `config` | Read/write config.json values | `config get modelProfile`, `config set features.commit_docs true` |
| `init` | Compound startup commands | `init go`, `init execute 36`, `init verify 36` |
| `roadmap` | Parse ROADMAP.md sections | `roadmap get-phase 36` |
| `frontmatter` | YAML frontmatter CRUD | `frontmatter get path/to/file.md` |
| `verify` | Structural + artifact verification | `verify plan-complete 36`, `verify wiring 45`, `verify alma-artifacts` |
| `template` | Template listing and fill | `template list`, `template fill summary --vars '{...}'` |
| `context` | Token estimation and budget | `context estimate file.js`, `context budget` |
| `slug` | Text to kebab-case | `slug "Hello World"` |
| `timestamp` | ISO/date/epoch formats | `timestamp`, `timestamp date` |
| `memory` | Chapter CRUD, citations, domain mapping | `memory list-chapters`, `memory update-from-diff HEAD` |
| `project` | PROJECT.md section access | `project list-sections`, `project get-section "Core Value"` |
| `extract` | SUMMARY.md decision/pattern parsing | `extract decisions path/SUMMARY.md` |
| `route` | Deterministic intent→handler dispatch | `route dispatch --intent fix --keywords auth`, `route list-intents` |
| `agent` | Agent registry and spawn config | `agent list`, `agent spawn-config debug-agent`, `agent validate executor-agent` |
| `mcp` | MCP server discovery and validation | `mcp list`, `mcp check serena`, `mcp available-tools` |

**Usage in workflows:** `**Primary:** node bin/alma-tools.js <command>` with `**Fallback:**` manual bash parsing when alma-tools.js unavailable.

### `/ac-go` Smart Router

Main entry point. LLM classifies natural language to one of **36 intents**, then `alma-tools.js route dispatch` handles deterministic routing (handler selection, memory pre-fetch, agent delegation). Modularized: `go.md` → `go-router.md` → `go-handlers*.md` (context: ~15% total, down from 30%).

### Dedicated Fast-Path Skills (8)

Skip LLM intent classification — ~73% less context overhead. Use when you KNOW what you want:

`/ac-fix`, `/ac-new`, `/ac-plan`, `/ac-verify`, `/ac-execute`, `/ac-research`, `/ac-investigate`, `/ac-status`

Each dispatches with a predetermined intent via `enforce-dedicated-commands.js` hook. `/ac-go` remains the universal fallback for all 36 intents + ambiguous input.

### Other Commands

- `/ac-jira [ISSUE-KEY]` — Jira issue analysis with full hierarchy → `.planning/jira/JIRA-CONTEXT-[KEY].md`
- `/ac-code-review [target]` — Delegates to native /review + cross-language anti-pattern detection

### UAT Pipeline (verify → diagnose → fix)

Full closed-loop testing: `verify-work.md` creates persistent UAT.md per phase, guides manual testing with auto-severity inference (P0-P3), spawns parallel debug agents via `diagnose-issues.md` for failures, and feeds diagnosed gaps into `plan-fix` or `plan-milestone-gaps` for automated remediation.

Flow: `/ac-verify-work` → UAT.md + ISSUES.md → `/ac-diagnose-issues` → DIAGNOSIS.md → `/ac-plan-fix` → FIX.md → execute

### Phase System (Critical)

ALL work flows through `.planning/phases/`. Rules:
1. `PROJECT.md` and `ROADMAP.md` must exist before any work
2. Phases numbered sequentially, each has PLAN.md + SUMMARY.md
3. **NEVER create loose plans outside `.planning/phases/`**
4. **UAT loop:** On test failure, auto-diagnose and retry up to 3x before escalating (`@references/uat-loop.md`)
5. **Checkpoints:** `.continue-here.md` saved after each task commit for interrupted execution resume (`@references/checkpoint-protocol.md`)
6. **UI Brand:** All user-facing output follows standardized patterns — banners, checkpoint boxes, spawning indicators, "Next Up" blocks (`@references/ui-brand.md`)

### Memory System

Location: `.planning/memory/chapters/` with `INDEX.md`. Format: domain-specific chapters (CAP-AUTH, CAP-API, etc.) with v2 structured citations:
```yaml
key_files:
  - path: src/auth/login.ts
    symbol: handleLogin
    verified: 2026-02-09
```
Never flat lists. Tiers: Hot (INDEX, STATE) → Warm (chapters) → Cold (plans) → Archive.

Memory operations are deterministic via `alma-tools.js memory` commands (10 subcommands). Workflows auto-invoke these — developers never call them directly.

## Testing & TDD (Quality Gates)

Alma Coder uses a **Pragmatic TDD** approach.

- **Mandatory TDD:** For plans with `type: tdd` (Business logic, APIs, Algorithms).
- **Cycle:** RED (failing test) → GREEN (passing code) → REFACTOR (cleanup).
- **Standard Flow:** For UI/Config, add tests during or after implementation.
- **Always Verify:** No task is complete until `verify` command passes.

## Naming Conventions

- **Files**: `kebab-case.md` | **Directories**: plural (`commands/`, `workflows/`)
- **Placeholders**: `[UPPER_SNAKE_CASE]` | **Variables**: `camelCase`

## Git Commit Format

```
<type>(<scope>): <description>
Types: feat, fix, refactor, test, docs, chore
```

## Adding New Components

| Component | Location | Key Steps |
|-----------|----------|-----------|
| Command | `.gemini/commands/ac/{name}.md` | YAML frontmatter + update help.md |
| Workflow | `.shared/workflows/workflows/{name}.md` | `<purpose>`/`<process>` tags + `npm run generate-index` |
| Template | `.shared/workflows/templates/{name}.md` | `[PLACEHOLDER]` syntax |
| Reference | `.shared/workflows/references/{name}.md` | Guidelines/patterns/checklists |
| Agent | `.shared/agents/{role}-agent.md` | Copy template + update README.md |
| Skill | `.gemini/skills/{name}/SKILL.md` | YAML frontmatter + `<process>` steps |

**Agents (13):** research (haiku), debug (sonnet), planner (sonnet), plan-checker (haiku), executor (sonnet), verifier (haiku), integration-checker (haiku), stack/features/architecture/pitfalls researchers (haiku), synthesizer (haiku), jira (haiku).

**File size limits:** Workflows <8KB, Templates <10KB, References <12KB, detect-mcp-tools.md <4KB.

## MCP Integration

- **serena**: Semantic code navigation and editing with 40+ tools — symbol search, cross-references, file ops, memory, project management. Modes: planning (read-only), editing (read/write), one-shot (quick fixes). Requires `uvx`. Launch: `uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd`

**Serena memory coexistence:** Serena has its own `.serena/memories/` directory. Use workflow memory (`.planning/memory/chapters/`) for architectural decisions. Use Serena memory for Serena-specific state (onboarding, LSP config). Do not duplicate.

Config: `.mcp.json` (Claude Code), `.cursor/mcp.json` (Cursor). Guide: `@.gemini/workflows/references/mcp-integration-guide.md`

## Hooks

- **Statusline**: `.shared/workflows/hooks/statusline.sh` — phase/task visibility
- **Auto-update**: `.shared/workflows/hooks/check-updates.js` — SessionStart, checks GitHub Releases API
Build before publishing: `npm run build:hooks`


## For More Context

- `@.gemini/workflows/REFERENCE-MAP.md` — File organization
- `@.gemini/workflows/WORKFLOWS-INDEX.md` — Workflow documentation
- `@.gemini/agents/README.md` — Agent definitions
- `@.gemini/workflows/references/mcp-integration-guide.md` — MCP guide
