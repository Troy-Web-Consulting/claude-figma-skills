---
name: figma-workspace
description: >
  Entry point for any Figma session. Routes operations to the correct tool
  (use_figma vs figma_execute), gathers design system context, and loads
  project-specific knowledge from the vault. Triggers on: any Figma mention,
  Figma URL, "do this in Figma," "what components exist," "audit the DS,"
  or as a prerequisite before figma-builder or figma-project-bridge work.
allowed-tools: Bash(cat *) Bash(jq *) Bash(python3 *) Bash(ls *) Bash(test *)
---

# Figma Workspace

Single entry point for every Figma session. Decides which tools to use, gathers context about the file, and loads project-specific knowledge before any work begins.

**Relationship to `figma-use`:** The official `figma-use` skill handles Plugin API rules, gotchas, and generic `use_figma` correctness. This skill handles session setup, tool routing, context gathering, and vault integration — the layer above the API.

For hard-won construction rules, see the `figma-builder` skill.
For spec cross-referencing or token sync, see the `figma-project-bridge` skill.
For replacing library component instances with local equivalents, see the `figma-swap-library-to-local` skill.
For binding unbound fills, strokes, and corner radii to design system variables, see the `figma-bind-variables` skill.

---

## Step 0: Contract Detection (first-use only)

Every Figma session operates over the **three-file contract**:

| Layer | File | Role |
|---|---|---|
| Rules | `design.md` (path in `designDocPath`) | Naming, token scales, architecture — read every invocation. |
| State | `figma-registry.json` (path in `registryPath`) | Cached component / variable / deprecation data. |
| Config | `.claude/figma-config.json` | Points to the two above, declares `fileKey`, page structure. |

Run this now to check contract state:

```bash
python3 - << 'PYEOF'
import json, os, sys
config_path = ".claude/figma-config.json"
if not os.path.exists(config_path):
    print("config_exists=no")
    sys.exit(0)
print("config_exists=yes")
try:
    d = json.load(open(config_path))
except Exception as e:
    print(f"config_error={e}")
    sys.exit(0)
design_doc = d.get("designDocPath") or d.get("conventionsPath")  # legacy fallback
registry = d.get("registryPath", "docs/figma-registry.json")
print(f"design_doc_path={design_doc or 'unset'}")
print(f"design_doc_exists={'yes' if (design_doc and os.path.exists(design_doc)) else 'no'}")
print(f"registry_path={registry}")
print(f"registry_exists={'yes' if os.path.exists(registry) else 'no'}")
if d.get("conventionsPath") and not d.get("designDocPath"):
    print("contract_warning=legacy_conventionsPath_field_rename_to_designDocPath")
PYEOF
```

Handle results as follows:

- `config_exists=no` → ask the user for `fileKey`, copy `templates/figma-config.json` from this repo into `.claude/figma-config.json`, and fill in the values.
- `design_doc_exists=no` → ask the user to copy `templates/design.md` to the path set in `designDocPath`. Skills cannot apply taste judgments without the rules layer. Do **not** fall back to a repo-local default.
- `registry_exists=no` → create a skeleton registry after the first session (see Step 6).
- `contract_warning=legacy_conventionsPath_field_rename_to_designDocPath` → tell the user the field has been renamed; keep working for this session but flag the fix.

Run this check once per session — subsequent invocations skip straight to the registry lookup.

---

## Step 0b: Registry-First Lookup

Run this now to load project context:

```bash
CONFIG=".claude/figma-config.json"
REGISTRY_PATH=$([ -f "$CONFIG" ] && python3 -c "import json; d=json.load(open('$CONFIG')); print(d.get('registryPath','docs/figma-registry.json'))" 2>/dev/null || echo "docs/figma-registry.json")
if [ -f "$REGISTRY_PATH" ]; then
  python3 -c "
import json, sys
try:
  d = json.load(open('$REGISTRY_PATH'))
  meta = d.get('meta', {})
  components = d.get('components', d)
  collections = d.get('variableCollections', {})
  comp_count = len([k for k in components if k not in ('meta','variableCollections')])
  col_count = len(collections)
  print(f'fileKey={meta.get(\"fileKey\", \"unknown\")}')
  print(f'componentCount={comp_count}')
  print(f'collectionCount={col_count}')
  if col_count: print(f'collections={list(collections.keys())}')
except Exception as e:
  print(f'registry_error={e}')
"
else
  echo "registry=not_found"
fi
if [ -f "$CONFIG" ]; then
  python3 -c "
import json
try:
  d = json.load(open('$CONFIG'))
  for k,v in d.items(): print(f'{k}={v}')
except: pass
"
fi
```

**Node IDs are permanent.** They are assigned at creation and never change, even across renames or moves. Registry entries do not expire — they only grow stale if the node was deleted.

### Project config

The full schema lives in `templates/figma-config.schema.json`. Minimum shape:

```json
{
  "fileKey": "YOUR_FIGMA_FILE_KEY",
  "knownPages": ["Design System", "Components"],
  "componentsPage": "Components",
  "designDocPath": "docs/design.md",
  "registryPath": "docs/figma-registry.json",
  "clearBetweenSegments": true
}
```

All artifact paths (`driftManifestPath`, `auditReportPath`, `auditsDir`, etc.) are declared in the config and consumed by the new-generation skills (`figma-drift-scan`, `figma-design-audit`, `figma-design-sync`). See `templates/figma-config.json` for the canonical starter.

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

**ESCALATE to `figma-console:figma_execute` (Desktop Bridge) when:**
- Slot manipulation on pre-existing instances (ghost node problem)
- Immediate screenshot after a just-completed write (cloud cache lag)
- `use_figma` silently fails mid-operation
- **5+ discrete write operations in a session** — `use_figma` loads file context on every call; figma-console's granular tools (`figma_set_fills`, `figma_resize_node`, `figma_move_node`, etc.) are significantly cheaper per-operation for bulk iterative work and amortize the reconnect cost

Both tools execute the same Plugin API. The escalation is based on cost and reliability differences, not capability gaps. Desktop Bridge requires:
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

**Break-even rule for subagents:** Each subagent spawn costs ~10-11k tokens of overhead (~$0.008 on Haiku, ~$0.030 on Sonnet). If a result would survive 3+ turns in main context, a Haiku subagent is cheaper. Single one-and-done lookups can stay inline.

### Screenshots

**Never take screenshots in main context.** Image tokens cannot be cached and re-bill on every subsequent turn. Always route through a Haiku subagent — the image is discarded when the subagent exits, only text findings return:

```
Agent({
  model: "haiku",
  prompt: "Take a screenshot of the current Figma canvas via figma_take_screenshot. Return only: (1) bullet list of visual issues (alignment, spacing, overflow, clipping, imbalance), (2) pass/fail verdict. Do not describe what looks correct."
})
```

- After `use_figma` writes: use `get_screenshot` (REST API) inside the subagent
- After `figma_execute` writes: use `figma_capture_screenshot` (plugin runtime) inside the subagent
- Always target a specific nodeId — never screenshot the full page root

**Mechanical lookups that return large payloads** also belong in Haiku subagents when the result would linger multi-turn:

| Task | Return only |
|---|---|
| `figma_get_variables` | Variables matching the pattern — name→value pairs |
| `figma_search_components` / `figma_get_library_components` | Matching names + nodeIds |
| `figma_lint_design` / `figma_scan_code_accessibility` | Failing issues only, grouped by severity |
| `figma_browse_tokens` | Tokens in target collection as flat name→value list |

**Stay in main context (Sonnet):** design decisions, component architecture, code generation, orchestration.

### Instantiation

- Library components: `figma_instantiate_component` with `componentKey`
- Local components: `figma_instantiate_component` with BOTH `componentKey` + `nodeId`
- Use VARIANT keys, never COMPONENT_SET keys
- Component keys and node IDs are permanent — if the registry has them, use directly without re-searching

---

## Step 3: Gather Context

Before any write operation, run only the steps below that are relevant to your task. These have real token cost — don't run steps you don't need.

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

Load the rules layer (`design.md`) plus any supplementary context files. This is the only prose loaded per session — downstream skills defer to this rather than encoding rules of their own.

```bash
python3 - << 'PYEOF'
import json, os, sys
try:
  d = json.load(open(".claude/figma-config.json"))
  design_doc = d.get("designDocPath") or d.get("conventionsPath")  # legacy fallback
  context_dir = d.get("contextDir", "")

  if design_doc and os.path.exists(design_doc):
    print(f"=== DESIGN RULES ({design_doc}) ===")
    print(open(design_doc).read())
  else:
    print(f"=== DESIGN RULES: MISSING ===")
    print(f"designDocPath is '{design_doc or 'unset'}'. Skills cannot defer to the rules layer.")
    print("Copy templates/design.md from the claude-figma-skills repo into your project and set designDocPath in .claude/figma-config.json.")

  if context_dir and os.path.isdir(context_dir):
    print(f"\n=== PROJECT CONTEXT ({context_dir}/) ===")
    for fname in os.listdir(context_dir):
      fpath = os.path.join(context_dir, fname)
      if os.path.isfile(fpath) and fname.endswith(".md"):
        print(f"\n--- {fname} ---")
        print(open(fpath).read())
except Exception as e:
  print(f"Context load error: {e}", file=sys.stderr)
PYEOF
```

All operational skills (`figma-builder`, `figma-bind-variables`, `figma-drift-scan`, etc.) defer to whichever `design.md` is active. They do not encode taste, naming, or scale defaults themselves.

For MCP tool selection rules, rate limit info, and token architecture guidance, consult `references/figma-mcp-patterns.md` — only if those topics are relevant to the current task.

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

**Rules layer (`design.md`)** lives in the consuming project, not in this skill. See `templates/design.md` in the `claude-figma-skills` repo root for the starter template; the path is declared per-project via `designDocPath` in `.claude/figma-config.json`.
