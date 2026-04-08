# Claude Figma Skills

Reusable Claude Code skills for Figma work — built from real sessions on design system projects at Troy Web. These cover the full Figma-in-Claude workflow: session setup, component construction, spec cross-reference, token sync, variable binding, and library migration.

These are **not** the official Figma MCP skills. They're the layer above: operational workflows, hard-won API patterns, and codified technique that the official skills don't provide.

**Design philosophy:** Skills encode *how to do things*, not *what things should be called*. Naming conventions, token scales, and structural standards live in a separate conventions source (either the shared defaults or a project-specific override) that skills defer to at runtime. This keeps the skills portable across projects.

---

## Skills

### `figma-workspace`
**Entry point for every Figma session.** Routes operations to the correct tool (`use_figma` vs Desktop Bridge), loads the project registry, resolves the active conventions source, and gathers design system context before any work begins.

Always invoke this first — other skills assume the context it establishes.

### `figma-builder`
**Build and modify Figma components via the Plugin API.** Covers variant schemas, property binding, `combineAsVariants`, slot operations, SVG import, instance rules, and batch operations with error recovery. Naming and structural conventions are deferred to the active conventions source.

### `figma-project-bridge`
**Bridge non-Figma inputs into Figma.** Two modes:
- **Spec Cross-Reference** — analyze a technical spec against existing Figma components, producing REUSE / EXTEND / CREATE / UNCLEAR verdicts
- **Token Sync** — bidirectional sync between code tokens (CSS, Tailwind, JSON) and Figma variables, including drift detection and audit mode

### `figma-bind-variables`
**Bind unbound fills, strokes, and corner radii to design system variables.** Five-phase workflow: discover variable IDs → resolve hex values → scan unbound properties → bind by property type → verify. Each phase is a separate script, recoverable independently.

### `figma-swap-library-to-local`
**Replace published library instances with local equivalents.** Uses parent-down traversal to avoid mid-loop node invalidation. Handles non-obvious name mappings and iterates until all swappable instances are resolved.

---

## References (inside `figma-workspace/references/`)

| File | Purpose |
|---|---|
| `conventions.md` | Default conventions: component naming, variable naming, layer structure, corner radius scale, page structure. Override per project via `conventionsPath` in `figma-config.json` |
| `figma-mcp-patterns.md` | Accumulated MCP patterns: write operations, token architecture, rate limits, drift detection, Plugin API architecture |
| `tool-inventory.md` | Complete table of all Figma MCP tools across both servers |
| `decision-tree.md` | Mermaid diagram for tool selection |
| `snippets.md` | Reusable code blocks for read and audit operations |

---

## Prerequisites

- **Claude Code** with the [Figma MCP server](https://developers.figma.com/docs/figma-mcp-server/) connected
- The official **`figma-use`** skill (ships with the Figma MCP superpowers plugin) — these skills build on top of it, not around it
- For Desktop Bridge operations: Figma Desktop app + Desktop Bridge plugin running

---

## Installation

### 1. Clone this repo

```bash
git clone https://github.com/troyweb/claude-figma-skills.git
```

### 2. Symlink skills into your project

Each skill you want to use gets symlinked into your project's `.claude/skills/` directory:

```bash
mkdir -p your-project/.claude/skills

ln -s /path/to/claude-figma-skills/figma-workspace your-project/.claude/skills/figma-workspace
ln -s /path/to/claude-figma-skills/figma-builder your-project/.claude/skills/figma-builder
ln -s /path/to/claude-figma-skills/figma-project-bridge your-project/.claude/skills/figma-project-bridge
ln -s /path/to/claude-figma-skills/figma-bind-variables your-project/.claude/skills/figma-bind-variables
ln -s /path/to/claude-figma-skills/figma-swap-library-to-local your-project/.claude/skills/figma-swap-library-to-local
```

`figma-workspace` is required — it's the prerequisite for every other skill.

### 3. Create `.claude/figma-config.json` in your project

```json
{
  "fileKey": "YOUR_FIGMA_FILE_KEY",
  "registryPath": "docs/figma-registry.json",
  "knownPages": ["Design System", "Components"],
  "componentsPage": "Components",
  "conventionsPath": "docs/design-context/conventions.md",
  "clearBetweenSegments": true,
  "contextDir": "docs/design-context"
}
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `fileKey` | Yes | Figma file key (from the URL: `figma.com/design/[fileKey]/...`) |
| `registryPath` | Yes | Path to the local component registry (created automatically after the first session) |
| `knownPages` | Yes | Page names in the Figma file |
| `componentsPage` | No | Name of the page containing component definitions. Default: `"Components"` |
| `conventionsPath` | No | Path to a project-specific conventions doc. When set, overrides the shared defaults in `figma-workspace/references/conventions.md` |
| `clearBetweenSegments` | No | Whether to `/clear` context between major work phases. Recommended: `true` |
| `contextDir` | No | Directory containing project-specific context: design decisions, prior specs, token formats. Can point to any directory — a local docs folder, a notes system, a shared drive |

`conventionsPath` and `contextDir` are both optional. Without them, skills operate from the shared conventions defaults and the registry + live Figma reads.

---

## Conventions

Naming conventions, variable naming patterns, token scales, and layer structure are defined in `figma-workspace/references/conventions.md` — the shared defaults used when no project overrides are set.

To override for a specific project, create a conventions doc at any path and point `conventionsPath` in `figma-config.json` to it. Skills read whichever source is active and defer to it — they do not hardcode conventions.

This separation means you can update conventions for one project without touching the skills, and update a skill's process without disturbing any project's naming standards.

---

## The Registry (`figma-registry.json`)

Skills maintain a local registry of discovered component and variable collection IDs. Node IDs in Figma are permanent — the registry means subsequent sessions skip re-discovery entirely.

Created automatically after the first session. Append-only: only delete entries if you've confirmed the node was removed from Figma.

```json
{
  "meta": {
    "fileKey": "abc123",
    "lastUpdated": "2026-04-07"
  },
  "Button": {
    "figmaNodeId": "123:456",
    "syncStatus": "synced",
    "lastSynced": "2026-04-07"
  }
}
```

---

## Contributing

These skills improve through real usage. If you find a Plugin API edge case, a pattern that reliably works, or a fix for something that didn't — open a PR.

**Where to put things:**
- New or corrected API behavior → relevant skill's `SKILL.md`
- Reusable code blocks → `references/snippets.md` in the relevant skill
- MCP patterns, rate limit behavior, Plugin API architecture → `figma-workspace/references/figma-mcp-patterns.md`
- Default naming or structural conventions → `figma-workspace/references/conventions.md`

Keep skills focused on process. Keep conventions in `conventions.md`. Keep accumulated API knowledge in the reference files.
