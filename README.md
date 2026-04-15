# Claude Figma Skills

Reusable Claude Code skills for Figma work — built from real sessions on design system projects at Troy Web. These cover the full Figma-in-Claude workflow: session setup, component construction, spec cross-reference, token sync, variable binding, and library migration.

These are **not** the official Figma MCP skills. They're the layer above: operational workflows, hard-won API patterns, and codified technique that the official skills don't provide.

---

## The Three-File Contract

Every skill in this repo reads the same three project files. Drop them into a project once and every skill works without per-skill configuration.

| Layer | File | Lives in | Role |
|---|---|---|---|
| **Rules** | `design.md` | consuming project (e.g. `my-project/docs/design.md`) | Prose: naming, token scales, architecture, taste. Short (200–800 words). Skills read it every invocation. |
| **State** | `figma-registry.json` | consuming project (e.g. `my-project/docs/figma-registry.json`) | Machine-maintained cache: component node IDs, variable collection IDs, resolved alias chains, deprecation maps, audit triage rules. |
| **Config** | `.claude/figma-config.json` | consuming project | Declares `fileKey`, points at `design.md` and `figma-registry.json`, sets artifact paths. |

The contract is **input-format as interface** — skills detect the three files, they don't assume layouts. Starter versions of all three live in `templates/`.

**Design philosophy:** skills encode *how to do things*, not *what things should be called*. Taste and naming live in `design.md`; state lives in `figma-registry.json`; skills stay thin.

---

## Skills

### `figma-workspace`
**Entry point for every Figma session.** Detects the three-file contract, loads `design.md`, surfaces the registry, and routes operations to the correct tool (`use_figma` vs Desktop Bridge).

Always invoke this first — other skills assume the context it establishes.

### `figma-builder`
**Build and modify Figma components via the Plugin API.** Covers variant schemas, property binding, `combineAsVariants`, slot operations, SVG import, instance rules, and batch operations with error recovery. Naming and structural conventions are read from the project's `design.md`.

### `figma-spec-crossref`
**Cross-reference a spec against existing Figma components.** Produces REUSE / EXTEND / CREATE / UNCLEAR verdicts per screen or feature. Run after `spec-design-interpreter` produces a companion doc — this skill adds the live Figma lookup layer.

### `figma-drift-scan`
**Detect drift between code tokens and Figma variables.** Runs `parse_tokens` + `diff_tokens` primitives against the project's token files and registry, emits a `drift-manifest.yaml`, then asks the LLM to judge whether each drift item is intentional. Read-only. Input for `figma-design-sync` (Phase 6).

### `figma-design-audit`
**Audit the registry and components against the project's design rules.** Runs structural checks via the `audit` primitive (naming patterns, token tier violations, orphaned components, alias chain issues) then applies `design.md` prose rules for taste-level findings. Emits `audit-report.yaml`. Read-only.

### `figma-bind-variables`
**Bind unbound fills, strokes, and corner radii to design system variables.** Five-phase workflow: discover variable IDs → resolve hex values → scan unbound properties → bind by property type → verify. Each phase is a separate script, recoverable independently.

### `figma-swap-library-to-local`
**Replace published library instances with local equivalents.** Uses parent-down traversal to avoid mid-loop node invalidation. Handles non-obvious name mappings and iterates until all swappable instances are resolved.

---

## Templates

Copy-into-project starters. Each skill reads from the paths you declare in `.claude/figma-config.json`, so you own where these files live.

| File | Purpose |
|---|---|
| [`templates/design.md`](templates/design.md) | Rules layer starter — fill in your project's naming, token scales, architecture. |
| [`templates/figma-config.json`](templates/figma-config.json) | Config starter — fill in `fileKey` and artifact paths. |
| [`templates/figma-config.schema.json`](templates/figma-config.schema.json) | JSON Schema for config. Editors can validate against it. |
| [`templates/figma-registry.schema.json`](templates/figma-registry.schema.json) | JSON Schema for the registry. Registries are created by skills on first run. |

---

## Scripts

Deterministic primitives live in `scripts/figma_primitives/` — a runnable Python package with structured JSON/YAML I/O. Skills call these as subprocesses; the LLM handles only taste and judgment that actually needs it.

**Entry point:** `python -m figma_primitives <subcommand> [options]`

| Subcommand | Module | Purpose |
|---|---|---|
| `parse-tokens` | `parse_tokens.py` | CSS / Tailwind / Style Dictionary / Tokens Studio → `normalized-tokens.json` |
| `resolve-aliases` | `resolve_aliases.py` | Flatten alias chains in `normalized-tokens.json`; detect circular refs |
| `diff-tokens` | `diff_tokens.py` | `normalized-tokens.json` + `figma-registry.json` → `drift-manifest.yaml` |
| `generate-css` | `generate_css.py` | `figma-registry.json` → CSS custom properties file |
| `generate-utilities` | `generate_utilities.py` | `figma-registry.json` → CSS utility classes (text-*, bg-*, rounded-*, etc.) |
| `scan-unbound` | `scan_unbound.py` | Figma node export → `unbound-report.json` (fills, strokes, corners) |
| `prep-bind` | `prep_bind.py` | Phase 1+2 JSON → Phase 4a-4d Plugin API scripts |
| `prep-idmap` | `prep_idmap.py` | Phase 2 idMap JSON + node ID → Phase 3 swap script |
| `audit` | `audit.py` | `figma-registry.json` → `audit-report.yaml` (naming, tiers, orphans, aliases) |

Each subcommand follows the same contract: `--input` / `--output` (or `--phase1` / `--phase2` / `--output-dir` for multi-file subcommands), JSON/YAML in, JSON/YAML out, exit 0 on success.

Output schemas live in `scripts/figma_primitives/contracts/`.

---

## Skill references (per-skill accumulated knowledge)

These files encode Figma API knowledge, not project taste. They stay inside each skill.

| File | Purpose |
|---|---|
| `figma-workspace/references/figma-mcp-patterns.md` | Write operations, token architecture, rate limits, drift detection. |
| `figma-workspace/references/tool-inventory.md` | Complete table of all Figma MCP tools across both servers. |
| `figma-workspace/references/decision-tree.md` | Mermaid diagram for tool selection. |
| `figma-workspace/references/snippets.md` | Reusable code blocks for read and audit operations. |
| `figma-builder/references/snippets.md` | Write-side code blocks: component creation, variant combining. |
| `figma-builder/references/batch-patterns.md` | Batch operation patterns with error recovery. |
| `figma-drift-scan/references/mapping-rules.md` | REUSE / EXTEND / CREATE verdict rules for spec cross-reference. |
| `figma-drift-scan/references/token-formats.md` | CSS / Tailwind / JSON / YAML token format detection. |

---

## Prerequisites

- **Claude Code** with the [Figma MCP server](https://developers.figma.com/docs/figma-mcp-server/) connected.
- The official **`figma-use`** skill (ships with the Figma MCP superpowers plugin) — these skills build on top of it, not around it.
- For Desktop Bridge operations: Figma Desktop app + Desktop Bridge plugin running.

---

## Installation

### 1. Clone this repo

```bash
git clone https://github.com/Troy-Web-Consulting/claude-figma-skills.git
```

### 2. Symlink skills into your project

Each skill you want to use gets symlinked into your project's `.claude/skills/` directory:

```bash
mkdir -p your-project/.claude/skills

ln -s /path/to/claude-figma-skills/figma-workspace your-project/.claude/skills/figma-workspace
ln -s /path/to/claude-figma-skills/figma-builder your-project/.claude/skills/figma-builder
ln -s /path/to/claude-figma-skills/figma-spec-crossref your-project/.claude/skills/figma-spec-crossref
ln -s /path/to/claude-figma-skills/figma-drift-scan your-project/.claude/skills/figma-drift-scan
ln -s /path/to/claude-figma-skills/figma-design-audit your-project/.claude/skills/figma-design-audit
ln -s /path/to/claude-figma-skills/figma-bind-variables your-project/.claude/skills/figma-bind-variables
ln -s /path/to/claude-figma-skills/figma-swap-library-to-local your-project/.claude/skills/figma-swap-library-to-local
```

`figma-workspace` is required — it's the prerequisite for every other skill.

### 3. Copy the contract templates

```bash
cp /path/to/claude-figma-skills/templates/design.md your-project/docs/design.md
cp /path/to/claude-figma-skills/templates/figma-config.json your-project/.claude/figma-config.json
```

Edit `your-project/.claude/figma-config.json`:
- Set `fileKey` to your Figma file's key (from the URL: `figma.com/design/[fileKey]/...`).
- Confirm `designDocPath` and `registryPath` point where you want them.
- Update `knownPages` and `componentsPage` to match your Figma file's page structure.

Edit `your-project/docs/design.md` to reflect your project's actual naming, token scales, and architecture. The template's defaults are examples — override every section.

The registry (`docs/figma-registry.json`) is created automatically by `figma-workspace` after the first session.

---

## Config fields

Complete list in [`templates/figma-config.schema.json`](templates/figma-config.schema.json). Highlights:

| Field | Required | Description |
|---|---|---|
| `fileKey` | Yes | Figma file key. |
| `branchKey` | No | Used as the effective fileKey when working on a Figma branch. |
| `knownPages` | Yes | Page names in the Figma file. |
| `componentsPage` | No | Page containing component definitions (default: `"Components"`). |
| `designDocPath` | Yes | Path to the project's `design.md`. |
| `registryPath` | Yes | Path to `figma-registry.json`. |
| `auditsDir` | No | Directory for per-page audit artifacts (default: `docs/audits`). |
| `driftManifestPath` | No | Output path for `figma-drift-scan`. |
| `auditReportPath` | No | Output path for `figma-design-audit`. |
| `parityReportPath` | No | Output path for `figma-design-sync`. |
| `tokensDir` | No | Directory holding project token files (CSS/JSON/YAML). |
| `tailwindThemePath` | No | Optional Tailwind theme CSS path. |
| `contextDir` | No | Optional directory of supplementary context docs loaded per session. |
| `scriptsPath` | No | Override for `scripts/figma_primitives` location. |
| `clearBetweenSegments` | No | Whether to `/clear` context between major work phases. |

### Legacy field — `conventionsPath`

The old `conventionsPath` field is accepted as a fallback by `figma-workspace` (with a deprecation warning) but will be removed after all consuming projects migrate. Rename to `designDocPath`.

---

## The Registry (`figma-registry.json`)

Skills maintain a local registry of discovered component IDs, variable collections, deprecation maps, and audit triage rules. Node IDs in Figma are permanent — the registry means subsequent sessions skip re-discovery entirely.

Full shape: [`templates/figma-registry.schema.json`](templates/figma-registry.schema.json). Top-level keys:

- `meta` — fileKey, branchKey, scanDate.
- `sections` — named layout sections on the components page.
- `components` — all components and component sets, with `id`, `key`, `name`, `section`, `type`.
- `variables` — cached collection IDs and resolved color/spacing/corner maps.
- `versionMap` — component deprecation history (powers non-obvious mappings in `figma-swap-library-to-local`).
- `bindIgnoreRules` — persistent triage: values reviewed and intentionally left unbound.

Created automatically after the first session. Append-only — only delete entries if the underlying Figma node was confirmed removed.

---

## Contributing

These skills improve through real usage. If you find a Plugin API edge case, a pattern that reliably works, or a fix for something that didn't — open a PR.

**Where to put things:**
- New or corrected API behavior → relevant skill's `SKILL.md`.
- Reusable code blocks → `references/snippets.md` in the relevant skill.
- MCP patterns, rate limit behavior, Plugin API architecture → `figma-workspace/references/figma-mcp-patterns.md`.
- Project-specific naming or scales → **the consuming project's `design.md`**, never a skill file. Update `templates/design.md` only to improve the generic starter.

Keep skills focused on process. Keep rules in `design.md`. Keep accumulated API knowledge in the reference files.
