---
name: figma-workspace
description: >
  Entry point for any Figma session. Routes operations to the correct tool
  (use_figma vs figma_execute), gathers design system context, and loads
  project-specific knowledge from the vault. Triggers on: any Figma mention,
  Figma URL, "do this in Figma," "what components exist," "audit the DS,"
  or as a prerequisite before figma-builder or figma-project-bridge work.
---

# Figma Workspace

Single entry point for every Figma session. Decides which tools to use, gathers context about the file, and loads project-specific knowledge before any work begins.

**Relationship to `figma-use`:** The official `figma-use` skill handles Plugin API rules, gotchas, and generic `use_figma` correctness. This skill handles session setup, tool routing, context gathering, and vault integration — the layer above the API.

For hard-won construction rules, see the `figma-builder` skill.
For spec cross-referencing or token sync, see the `figma-project-bridge` skill.
For replacing library component instances with local equivalents, see the `figma-swap-library-to-local` skill.
For binding unbound fills, strokes, and corner radii to design system variables, see the `figma-bind-variables` skill.

---

## Step 0: Bootstrap Check (first-use only)

Before anything else, verify this project is wired up:

1. Does `.claude/skills/figma-workspace` exist in the project? If not: `ln -s ~/.config/claude/skill-library/skills/figma-workspace .claude/skills/figma-workspace`
2. Does `.claude/figma-config.json` exist? If not: ask the user for the Figma fileKey, then create it (schema below)
3. Does `docs/figma-registry.json` exist? If not: create a skeleton after the first session

Only run this check once — subsequent invocations skip straight to the registry lookup.

---

## Step 0b: Registry-First Lookup

Before any tool call, check for a local registry in the project CWD:

1. Read `docs/figma-registry.json` if it exists
2. If found, extract: `meta.fileKey`, component node IDs, variable collection IDs
3. Announce what's already known: "Registry loaded — 30 components, 3 variable collections known"

**Node IDs are permanent.** They are assigned at creation and never change, even across renames or moves. Registry entries do not expire — they only grow stale if the node was deleted.

### Project config

Also check for `.claude/figma-config.json` in the project root. If present, it overrides defaults:

```json
{
  "registryPath": "docs/figma-registry.json",
  "fileKey": "gXWSfKn5TelgViNAz8hEDe",
  "knownPages": ["Design System", "Pages", "Composed"],
  "clearBetweenSegments": true
}
```

If neither file exists, proceed to Step 1 and create the registry after the first session (see Step 6).

---

## Step 1: Extract File Key

Every Figma MCP call requires a `fileKey`. The official `figma-use` skill documents URL parsing patterns — follow those. If no URL is provided, ask the user. Every `use_figma` call requires fileKey explicitly — it does not persist between calls.

---

## Step 2: Route to Tool

See `references/tool-inventory.md` for the complete tool table. Quick decision:

### Write operations

**DEFAULT: `Figma:use_figma` (remote MCP)**
- Runs Plugin API JavaScript against Figma cloud
- No desktop app needed
- 50k character code limit per call
- Requires fileKey every call

**ESCALATE to `figma-console:figma_execute` (Desktop Bridge) ONLY when:**
- Slot manipulation on pre-existing instances (ghost node problem)
- Immediate screenshot after a just-completed write (cloud cache lag)
- `use_figma` silently fails mid-operation

Both tools execute the same Plugin API. The escalation is based on observed reliability differences, not confirmed capability gaps. Desktop Bridge requires:
1. Figma Desktop app open
2. Desktop Bridge plugin running and showing "MCP Ready"
3. `figma_reconnect` before first use and after heavy operations

### Read operations (progressive detail)

Use the narrowest tool that answers the question. Each step costs significantly more than the one above it.

1. **Registry** — check `figma-registry.json` first. If the node ID is there, use it directly. No tool call needed.
2. `search_design_system` — find components/tokens by name (~1-2K tokens)
3. `get_design_context` on a specific `nodeId` — layout, component tree, token usage (~3-4K tokens)
4. `use_figma` with targeted JS — surgical reads; returns only what your code returns
5. `get_metadata` on a specific `nodeId` — XML structure for a known node (~5-8K tokens per call)
6. `get_variable_defs` — all variable definitions from the file (can exceed 50K tokens)

**Hard rules — never do these:**

| Forbidden | Why | Do this instead |
|-----------|-----|-----------------|
| `get_metadata` without a nodeId (full file) | Dumps entire node tree, 20-35K tokens | Target a specific nodeId, or use `search_design_system` |
| `get_variable_defs` on the whole file | Dumps all variables, triggers 387K+ cache_create | Use targeted JS with collection ID from registry |
| Re-running exploration queries for known nodes | Node IDs are permanent; you already have them | Read registry, call `getNodeByIdAsync` directly |

### Targeted variable access (instead of get_variable_defs)

When the collection ID is in the registry:
```js
// Query one collection by ID — never dumps the whole file
const col = await figma.variables.getVariableCollectionByIdAsync("VariableCollectionId:137:11364");
const vars = await Promise.all(col.variableIds.map(id => figma.variables.getVariableByIdAsync(id)));
return vars.map(v => ({ name: v.name, id: v.id }));
```

When the collection ID is unknown (first time only):
```js
// Returns collection names + IDs only — not all variable values
const collections = await figma.variables.getLocalVariableCollectionsAsync();
return collections.map(c => ({ name: c.name, id: c.id, variableCount: c.variableIds.length }));
```
→ Pick the collection you need, then use the targeted query above. Add the collection ID to the registry.

### Token efficiency

Figma tool results accumulate in context for the entire session. Each result stays in the window for every subsequent turn.

- **`/clear` between major work segments** — resets accumulated results; start each segment fresh
- A "segment" is a logical phase: discovery → design → review → another feature. Clear between them.
- After any large read (screenshot, design context), assess whether the result is still needed before continuing

### Screenshots

- After `use_figma` writes: `get_screenshot` (REST API, may have brief cache lag)
- After `figma_execute` writes: `figma_capture_screenshot` (plugin runtime, immediate)
- Always target a specific nodeId — never screenshot the full page root

### Instantiation

- Library components: `figma_instantiate_component` with `componentKey`
- Local components: `figma_instantiate_component` with BOTH `componentKey` + `nodeId`
- Use VARIANT keys, never COMPONENT_SET keys
- Re-search before instantiating (nodeIds are session-specific)

---

## Step 3: Gather Context

Run this audit sequence before any write operation. Skip steps that aren't relevant to the task at hand.

### 3a. Component inventory

Tool: `search_design_system` with queries based on the task (e.g., "drawer," "form," "button")

Output: matching components with keys, variant properties, nodeIds.

**Rule: check for existing components before creating new ones.** Import matches via `importComponentByKeyAsync` / `importComponentSetByKeyAsync` instead of recreating.

### 3b. Token values

Tool: `get_variable_defs` on a relevant node

Focus on: colors, spacing, typography tokens used by target components.

### 3c. Visual spec of reference components

Tool: `get_design_context` on specific component nodes

Output: visual specs (padding, colors, typography), screenshot.

**Rule: always look at comparable existing patterns before designing new ones.**

### 3d. Target area audit

Tool: `use_figma` with a read-only script to scan the target section/page

Output: what already exists where you're about to build, canvas positions of existing content.

**Rule: understand canvas positions to avoid overlapping existing work.**

---

## Step 4: Load Project Context

### Universal patterns

Read `references/figma-mcp-patterns.md` (ships with this skill) — MCP tool selection rules, rate limits, write operation patterns, token architecture, agentic workflow conventions.

### Project-specific context

Check `.claude/figma-config.json` for a `contextDir` field:

```json
{
  "contextDir": "docs/design-context"
}
```

If `contextDir` is set, read files from that directory. Look for: component naming conventions, design decisions, prior specs, token formats.

If `contextDir` is absent, skip this step — proceed from registry and live Figma reads alone.

**`contextDir` can point anywhere**: a project docs folder, a vault directory, a shared drive path — whatever the team uses for project context. Set it once in `.claude/figma-config.json`, never hardcode paths in the skill.

---

## Step 5: Output

Present a structured summary in the conversation (not a file):

- **File:** name, fileKey, page structure
- **Components found:** names, keys, relevant variants
- **Tokens relevant:** names, resolved values
- **Existing patterns to reference:** comparable components/frames
- **Canvas position for new work:** coordinates below existing content
- **Tool selection:** which write tool and why

This summary becomes the foundation for `figma-builder` or `figma-project-bridge` work.

---

## Connection Protocol (Desktop Bridge)

When using the Desktop Bridge path:

```
figma_reconnect           -> confirm connection, get active file name
figma_get_selection       -> see what user is pointing at (if anything)
figma_execute (audit)     -> scan target before touching anything
```

If `figma_get_status` shows `websocket.available: false`:
-> Ask user to open Desktop Bridge plugin (Plugins -> Development -> Figma Desktop Bridge)
-> Confirm "MCP Ready", then `figma_reconnect`

**Bridge drops silently** after heavy operations (`combineAsVariants`, bulk node creation). Always `figma_reconnect` before any operation following a large write.

---

## Error Recovery (Desktop Bridge-specific)

Generic `use_figma` error recovery is handled by the official `figma-use` skill. The entries below cover Desktop Bridge and tool-routing issues only.

| Error | Recovery |
|---|---|
| "No approval received" from `use_figma` | Retry once; if persistent, ask user to refresh Figma file in browser |
| "dynamic-page" errors | Use async methods: `figma.getNodeByIdAsync()`, `node.getMainComponentAsync()` |
| Bridge drops after heavy ops | `figma_reconnect` before next operation |
| 50k character limit | Break into smaller operations (see `figma-builder` batch patterns) |

---

## Step 6: Registry Maintenance

The registry is the project's Figma knowledge base. Keep it current.

**After creating a new component or variable collection**, add an entry before ending the session:
```json
{
  "ComponentName": {
    "figmaNodeId": "123:456",
    "syncStatus": "synced",
    "lastSynced": "YYYY-MM-DD"
  }
}
```

**After a cache miss** (component not in registry but found via `search_design_system`): write its node ID to the registry so the next session pays nothing.

**Registry location**: `docs/figma-registry.json` in the project root (or the path in `.claude/figma-config.json`). If the project has no registry yet, create it after the first session with the fileKey and any discovered component/collection IDs.

**Registry does not need full re-syncs.** It is append-only. Only delete entries if you've confirmed the node was removed from the Figma file.

---

## References

- `references/tool-inventory.md` — complete table of all Figma MCP tools
- `references/snippets.md` — reusable code blocks for common operations
- `references/decision-tree.md` — mermaid diagram of tool selection logic
- `references/figma-mcp-patterns.md` — accumulated MCP patterns, token architecture, agentic workflow conventions
