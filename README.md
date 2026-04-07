# Claude Figma Skills

Reusable Claude Code skills for Figma work — built from real sessions on design system projects. These cover the full Figma-in-Claude workflow: session setup, component construction, spec cross-reference, token sync, variable binding, and library migration.

These are **not** the official Figma MCP skills. They're the layer above: opinionated workflows, hard-won patterns, and codified rules that the official skills don't provide.

## Skills

### `figma-workspace`
**Entry point for every Figma session.** Routes operations to the correct tool (`use_figma` vs Desktop Bridge), loads the project registry, gathers design system context, and loads project-specific knowledge before any work begins.

Includes a reference file (`references/figma-mcp-patterns.md`) with accumulated patterns on MCP rate limits, write operations, token architecture, drift detection, and agentic design workflows.

### `figma-builder`
**Build and modify Figma components via the Plugin API.** Covers variant schemas, property binding, `combineAsVariants`, naming conventions, slot operations, SVG import, instance rules, and batch operations with error recovery.

### `figma-project-bridge`
**Bridge non-Figma inputs into Figma.** Two modes:
- **Spec Cross-Reference** — analyze a technical spec against existing Figma components, producing REUSE / EXTEND / CREATE / UNCLEAR verdicts
- **Token Sync** — bidirectional sync between code tokens (CSS, Tailwind, JSON) and Figma variables, including audit mode

### `figma-bind-variables`
**Bind unbound fills, strokes, and corner radii to design system variables.** Four-phase workflow: discover variable IDs → resolve hex values → scan unbound properties → bind by property type. Recoverable if any phase fails.

### `figma-swap-library-to-local`
**Replace published library instances with local equivalents.** Uses parent-down traversal to avoid mid-loop node invalidation. Handles non-obvious component name mappings and iterates until all swappable instances are resolved.

---

## Prerequisites

- **Claude Code** with the [Figma MCP server](https://developers.figma.com/docs/figma-mcp-server/) connected
- The official **`figma-use`** skill (ships with the Figma MCP superpowers plugin) — these skills build on top of it, not around it
- For Desktop Bridge operations: Figma Desktop app + Desktop Bridge plugin running

---

## Installation

### 1. Clone this repo

```bash
git clone https://github.com/jakecooper-troyweb/claude-figma-skills.git
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

Start with `figma-workspace` — it's the prerequisite for everything else.

### 3. Create `.claude/figma-config.json` in your project

```json
{
  "fileKey": "YOUR_FIGMA_FILE_KEY",
  "registryPath": "docs/figma-registry.json",
  "knownPages": ["Design System", "Components"],
  "clearBetweenSegments": true,
  "contextDir": "docs/design-context"
}
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `fileKey` | Yes | Figma file key (from the URL: `figma.com/design/[fileKey]/...`) |
| `registryPath` | Yes | Path to the local component registry (created after first session) |
| `knownPages` | Yes | Page names in the Figma file |
| `clearBetweenSegments` | No | Whether to `/clear` context between major work phases (recommended: `true`) |
| `contextDir` | No | Directory containing project-specific context: design decisions, prior specs, token formats. Can be any path — a local docs folder, a notes system, a shared drive |

`contextDir` is optional. If absent, skills operate from the registry and live Figma reads alone.

---

## How Skills Are Invoked

Claude Code loads skills automatically when they're in `.claude/skills/`. Invoke them by name in conversation:

- "Use figma-workspace to set up context for this file"
- "Run figma-builder to add a new variant to the Button component set"
- "Use figma-project-bridge to cross-reference this spec against our components"

`figma-workspace` should always run first — it establishes the session context that other skills depend on.

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

These skills improve through real usage. If you run into a Plugin API edge case, a pattern that reliably works, or a fix for something that didn't — open a PR and add it to the relevant skill or its `references/` folder.

The `references/` folders are where accumulated knowledge lives. Prefer adding to those over modifying the main `SKILL.md` workflow unless the workflow itself is wrong.
