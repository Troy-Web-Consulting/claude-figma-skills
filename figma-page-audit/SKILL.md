---
name: figma-page-audit
description: |
  Read-only audit of a Figma page or selection against the file's own
  design system — variable collections and local component library.
  Dumps all node properties, detects unbound variables, external library
  instances, and repeated raw values that are token candidates.
  Does NOT fix anything — report only.
  Auto-triggers on: figma audit, page audit, audit selection, audit page,
  check bindings, what's unbound, token candidates, external libraries
  NOT for: binding variables, swapping libraries, syncing code tokens
---

# Figma Page Audit

Read-only audit of a Figma page or selection against the file's own design system.
Walks every node, dumps all properties with binding status, cross-references against
variable collections and the local component registry, then produces a persistent
report of findings.

**This skill is read-only. It never modifies the Figma file.**

## Prerequisites

**Fast path (Desktop Bridge):** No skill prerequisites. Read local files first (see Pre-flight below), then call MCP tools directly.

**Fallback path (Cloud MCP only):** Load `figma-use` before any `use_figma` calls — it covers the Plugin API safety rules needed for chunked walks. `figma-workspace` is optional (provides session context but not required for the audit script itself).

## Input

**Primary:** Figma node URL (link to a frame, section, or page) or active selection.
**Fallback:** Page name, resolved via `.claude/figma-config.json` → `knownPages`.

Ask the user for a link or selection before starting. Extract the node ID from the URL.

## Workflow

```
Phase 1: Collect    ──→  {name}-raw.json        (MCP calls — node walk + variable collections)
  ↓ /clear — flush Figma API responses from context
Phase 2: Enrich     ──→  {name}-enriched.json    (local only — token matching, ignore rules)
Phase 3: Analyze    ──→  {name}-analysis.json    (local only — clustering, severity assignment)
Phase 4: Report     ──→  {name}-report.md/json   (local only — human + machine summaries)
```

All artifacts persist in `docs/audits/`. The `{name}` is derived from the page or selection name, kebab-cased (e.g., `org-management`, `user-drawer`).

## Token Budget Management

**Fast path (Desktop Bridge):** Minimal token cost. Two tool calls return compact
findings (~5k tokens total). No `/clear` needed. Analyze and write report immediately.

**Variable cache (`docs/audits/variable-cache.json`):** Pre-resolved color→variable
and float→variable maps plus local component inventory. Saves 3-5 seconds of variable
resolution per run. The `figma_execute` script can read this via the tool instead of
re-fetching collections. Regenerate when variables change: run Phase 1a or the cache
generation script. Check `generatedAt` — if older than a week, re-generate.

**Fallback path (Cloud MCP):** Expensive. Each `use_figma` call returns 10-20k tokens.
Rules for fallback:
1. **`/clear` after data collection completes.** Once findings are written to disk,
   the API responses are redundant.
2. **Use compact output format** — return findings not raw data. Cluster by pattern.
3. **Phases 2-4 are free.** Local file I/O only — no MCP calls.
4. **Split large audits across sessions if needed:** Session A = collect, Session B = report.

## Hard Rules

| Rule | Why |
|---|---|
| Compound-ID nodes are safe to READ, not to WRITE | For this read-only audit, use `findAll(() => true)` with try/catch per node. The `;` filter is only needed for write operations like `figma-bind-variables` |
| Never skip Phase 1 on a fresh audit | Stale raw dumps from prior sessions may not reflect current Figma state |
| Discover variable IDs fresh every run | IDs from previous sessions may not exist in the current file/branch |
| Read `bindIgnoreRules` before flagging | Prevents re-flagging values that have already been triaged |
| 3+ occurrences across distinct nodes for token candidates | Avoids noise from one-off overrides |
| Persist all phase artifacts | Enables historical comparison and manual cleanup |

---

## Phase 1 — Collect + Analyze (Fast Path)

**Two modes:** Desktop Bridge (fast, preferred) or Cloud MCP (fallback).

### Mode Selection

Check Desktop Bridge availability first:
1. Call `figma_get_status` with `probe: true`
2. If `setup.valid === true` → use **Fast Path** (Desktop Bridge)
3. If not available → use **Fallback Path** (Cloud MCP, see "Phase 1 — Fallback" below)

---

### Fast Path (Desktop Bridge) — ~10 seconds

When Desktop Bridge is connected, Phase 1 combines collect + analyze in two parallel calls.
No chunking needed — the local plugin runtime handles the full tree with no response caps.

#### Pre-flight: Load local files before any MCP calls

Read these two files **before** running the MCP tools. Their contents are injected as constants
into the `figma_execute` script, making the walk pre-filtered and deterministic.

**1. Read `docs/figma-registry.json` → extract `bindIgnoreRules`**

Extract the skip sets you'll inject into the script:
```
skipNodeTypes  = bindIgnoreRules.fills.byNodeType keys where action === "skip"
                 e.g. ["VECTOR", "BOOLEAN_OPERATION"]

skipHexAlways  = bindIgnoreRules.fills.byHex entries where action === "skip" AND no nodeTypes restriction
                 e.g. ["#000000"]

skipHexByType  = bindIgnoreRules.fills.byHex entries where action === "skip" AND nodeTypes array exists
                 e.g. { "#1b75bc": ["VECTOR"], "#ec2027": ["VECTOR"] }
```

These become the `SKIP_*` constants at the top of the execute script.

**2. Check `docs/audits/variable-cache.json`**

If the file exists and `generatedAt` is within the last 7 days, read the `colorMap` and
`floatMap` fields. These are pre-resolved `hex → variable` and `value → [variables]` maps.
Inject them into the script as `INJECTED_COLOR_MAP` and `INJECTED_FLOAT_MAP` to skip the
variable collection fetch entirely (saves ~3-5 seconds of runtime and removes the collection
loop from the response).

If the cache is missing or stale, the script fetches collections from Figma directly (the
original approach). Note that after a fresh collection fetch, you should write a new
`variable-cache.json` to avoid re-fetching next run — see Cache Regeneration below.

#### Step 1: Run both tools in parallel

**Tool A: `figma_lint_design`** — built-in DS compliance check
```
figma_lint_design({
  nodeId: "<target node ID>",
  rules: ["hardcoded-color", "no-text-style"],
  maxFindings: 200
})
```
Returns: hardcoded color node IDs and text nodes without styles.

**Do NOT use `rules: ["design-system"]`** — that ruleset includes `default-name`, which
flags every Vector sublayer inside icon instances (typically 100-150 nodes of pure noise that
cost ~12k tokens and are not actionable). Use the narrow rules above.

**Tool B: `figma_execute`** — custom variable binding analysis
Run a single script that walks all nodes, compares against variable collections,
and returns clustered findings (not raw data). The script should:

1. Fetch all variable collections and build lookup maps (color hex → variable, float → variable)
2. Walk all descendants with `findAll(() => true)` (safe for reads)
3. For each node: check fills, strokes, corners, spacing, instances
4. Track: raw value clusters with counts, bound vs raw totals, instance sources
5. Return a summary object with: coverage %, top raw colors, raw corners, raw spacing, instances
6. Skip COMPONENT_SET nodes (Figma chrome)
7. Use property-aware matching (see Phase 2 enrichment rules)

**Key: the script returns findings, not raw data.** Analysis happens inside Figma's runtime.

#### Script: Walk + Analyze in One Pass

Before pasting this script into the tool call, substitute the three `/* INJECT … */` blocks
with values extracted during the Pre-flight step above.

```js
// ── Injected from bindIgnoreRules (pre-flight) ─────────────────────────────
// Replace these with actual values from docs/figma-registry.json
const SKIP_NODE_TYPES = new Set(/* INJECT: skipNodeTypes array e.g. */ ["VECTOR", "BOOLEAN_OPERATION"]);
const SKIP_HEX_ALWAYS = new Set(/* INJECT: skipHexAlways array e.g. */ ["#000000"]);
const SKIP_HEX_BY_TYPE = /* INJECT: skipHexByType object e.g. */ { "#1b75bc": ["VECTOR"], "#ec2027": ["VECTOR"], "#ffffff": ["VECTOR"] };

// ── Injected from variable-cache.json (pre-flight, if cache is fresh) ──────
// If cache is available: replace with the colorMap and floatMap objects from the cache file.
// If cache is missing/stale: set both to null — the script will fetch from Figma instead.
const INJECTED_COLOR_MAP = /* INJECT: colorMap or */ null;
const INJECTED_FLOAT_MAP = /* INJECT: floatMap or */ null;
// ────────────────────────────────────────────────────────────────────────────

const target = await figma.getNodeByIdAsync("TARGET_NODE_ID");
if (!target) return { error: "Node not found" };

// Build variable maps — use injected cache if available, otherwise fetch from Figma
const colorVarMap = new Map();
const floatVarMap = new Map();

if (INJECTED_COLOR_MAP && INJECTED_FLOAT_MAP) {
  // Fast path: use pre-resolved cache (no Figma API calls needed)
  for (const [hex, v] of Object.entries(INJECTED_COLOR_MAP)) colorVarMap.set(hex, v);
  for (const [val, vars] of Object.entries(INJECTED_FLOAT_MAP)) floatVarMap.set(+val, vars);
} else {
  // Slow path: resolve from Figma variable collections
  const collections = await figma.variables.getLocalVariableCollectionsAsync();
  for (const col of collections) {
    const vars = await Promise.all(col.variableIds.map(id => figma.variables.getVariableByIdAsync(id)));
    for (const v of vars.filter(Boolean)) {
      const modeId = col.modes[0]?.modeId;
      if (!modeId) continue;
      let val = v.valuesByMode[modeId];
      let depth = 0;
      while (val?.type === 'VARIABLE_ALIAS' && depth < 5) {
        const aliased = await figma.variables.getVariableByIdAsync(val.id);
        if (!aliased) break;
        val = aliased.valuesByMode[Object.keys(aliased.valuesByMode)[0]];
        depth++;
      }
      if (v.resolvedType === 'COLOR' && val && 'r' in val) {
        const hex = '#' + [val.r, val.g, val.b].map(c => Math.round(c * 255).toString(16).padStart(2, '0')).join('');
        colorVarMap.set(hex, { name: v.name, collection: col.name });
      } else if (v.resolvedType === 'FLOAT' && typeof val === 'number') {
        if (!floatVarMap.has(val)) floatVarMap.set(val, []);
        floatVarMap.get(val).push({ name: v.name, collection: col.name });
      }
    }
  }
}

// Helper: should this fill/stroke be skipped per ignore rules?
function shouldSkipFill(hex, nodeType) {
  if (SKIP_NODE_TYPES.has(nodeType)) return true;
  if (SKIP_HEX_ALWAYS.has(hex)) return true;
  const byTypeList = SKIP_HEX_BY_TYPE[hex];
  if (byTypeList && byTypeList.includes(nodeType)) return true;
  return false;
}

const rawFills = {}, rawCorners = {}, rawSpacing = {};
let totalProps = 0, boundProps = 0, rawProps = 0;
const instanceSources = {};

const allNodes = [target];
if ('findAll' in target) {
  try { allNodes.push(...target.findAll(() => true)); } catch(e) {}
}

for (const node of allNodes) {
  if (node.type === 'COMPONENT_SET') continue;

  // Fills + Strokes
  for (const prop of ['fills', 'strokes']) {
    try {
      if (!(prop in node) || node[prop] === figma.mixed || !Array.isArray(node[prop])) continue;
      node[prop].forEach((p, i) => {
        if (p.type !== 'SOLID' || !p.color) return;
        const hex = '#' + [p.color.r, p.color.g, p.color.b].map(c => Math.round(c * 255).toString(16).padStart(2, '0')).join('');
        if (shouldSkipFill(hex, node.type)) return; // pre-filtered by ignore rules
        totalProps++;
        const bv = node.boundVariables?.[prop];
        if (Array.isArray(bv) && bv[i]?.id) { boundProps++; return; }
        rawProps++;
        if (!rawFills[hex]) rawFills[hex] = { count: 0, matchedVar: colorVarMap.get(hex)?.name || null, samples: [] };
        rawFills[hex].count++;
        if (rawFills[hex].samples.length < 3) rawFills[hex].samples.push({ name: node.name, type: node.type });
      });
    } catch(e) {}
  }

  // Corners — include node IDs when there is an exact token match (actionable for bind-variables)
  try {
    if ('cornerRadius' in node && node.cornerRadius !== figma.mixed && node.cornerRadius > 0) {
      totalProps++;
      if (node.boundVariables?.cornerRadius?.id) { boundProps++; }
      else {
        rawProps++;
        const v = Math.round(node.cornerRadius);
        if (!rawCorners[v]) {
          const match = floatVarMap.get(v)?.find(f => /corner/i.test(f.name));
          rawCorners[v] = { count: 0, matchedVar: match?.name || null, nodeIds: [] };
        }
        rawCorners[v].count++;
        // Collect node IDs only when there's an exact match (these are the binding targets)
        if (rawCorners[v].matchedVar && rawCorners[v].nodeIds.length < 50) rawCorners[v].nodeIds.push(node.id);
      }
    }
  } catch(e) {}

  // Spacing (padding + gap) — include node IDs when there is an exact token match
  try {
    if ('layoutMode' in node && node.layoutMode !== 'NONE') {
      for (const p of ['paddingTop','paddingRight','paddingBottom','paddingLeft','itemSpacing']) {
        const val = (p === 'itemSpacing') ? node.itemSpacing : node[p];
        if (val > 0 && val < 200) {
          totalProps++;
          const bvKey = (p === 'itemSpacing') ? 'itemSpacing' : p;
          if (node.boundVariables?.[bvKey]?.id) { boundProps++; }
          else {
            rawProps++;
            if (!rawSpacing[val]) {
              const match = floatVarMap.get(val)?.find(f => /spac/i.test(f.name));
              rawSpacing[val] = { count: 0, matchedVar: match?.name || null, nodeIds: [] };
            }
            rawSpacing[val].count++;
            if (rawSpacing[val].matchedVar && rawSpacing[val].nodeIds.length < 50) rawSpacing[val].nodeIds.push(node.id);
          }
        }
      }
    }
  } catch(e) {}

  // Instances — MUST use getMainComponentAsync (sync throws in Desktop Bridge)
  if (node.type === 'INSTANCE') {
    try {
      const mc = await node.getMainComponentAsync();
      if (mc) {
        const lib = mc.remote ? (mc.parent?.name || 'external') : 'local';
        if (!instanceSources[lib]) instanceSources[lib] = {};
        if (!instanceSources[lib][mc.name]) instanceSources[lib][mc.name] = { count: 0, nodeIds: [] };
        instanceSources[lib][mc.name].count++;
        if (mc.remote && instanceSources[lib][mc.name].nodeIds.length < 10) instanceSources[lib][mc.name].nodeIds.push(node.id);
      }
    } catch(e) {}
  }
}

// Check remote instances against local components in the file
const remoteEntries = Object.entries(instanceSources).filter(([lib]) => lib !== 'local');
let localEquivalents = {};
if (remoteEntries.length > 0) {
  const localComps = {};
  for (const page of figma.root.children) {
    try {
      await figma.setCurrentPageAsync(page);
      page.findAll(n => {
        if (n.type === 'COMPONENT' || n.type === 'COMPONENT_SET')
          localComps[n.name] = { id: n.id, page: page.name };
        return false;
      });
    } catch(e) {}
  }
  for (const [lib, comps] of remoteEntries) {
    for (const name of Object.keys(comps)) {
      const match = localComps[name] || localComps['M' + name];
      if (match) localEquivalents[name] = { ...match, matchType: localComps[name] ? 'exact' : 'M-prefixed' };
    }
  }
}

const coverage = totalProps > 0 ? Math.round((boundProps / totalProps) * 100) : 0;
return {
  summary: { totalNodes: allNodes.length, totalProps, boundProps, rawProps, coverage: coverage + '%' },
  rawColors: Object.entries(rawFills).sort((a,b) => b[1].count - a[1].count).slice(0, 15).map(([hex, d]) => ({ hex, ...d })),
  // rawCorners and rawSpacing include nodeIds[] for entries with exact token matches — feed directly to figma-bind-variables
  rawCorners: Object.entries(rawCorners).sort((a,b) => b[1].count - a[1].count).map(([v, d]) => ({ value: +v, ...d })),
  rawSpacing: Object.entries(rawSpacing).sort((a,b) => b[1].count - a[1].count).slice(0, 15).map(([v, d]) => ({ value: +v, ...d })),
  instances: Object.entries(instanceSources).map(([lib, comps]) => ({
    library: lib,
    components: Object.entries(comps).map(([n, d]) => ({
      name: n, count: d.count,
      nodeIds: d.nodeIds || [],
      localEquivalent: localEquivalents[n] || null
    }))
  })),
  usedCache: !!(INJECTED_COLOR_MAP && INJECTED_FLOAT_MAP),
};
```

Set `timeout: 30000` on the `figma_execute` call — the variable resolution loop needs time.

#### Step 2: Combine results and write report

Merge the `figma_lint_design` findings with the `figma_execute` analysis:
- Lint gives you: hardcoded color node IDs, text nodes without styles
- Execute gives you: binding coverage %, clustered raw values with token matches, node IDs for exact-match corners/spacing, instance provenance

Write the combined results directly to `docs/audits/{name}-report.md` and
`docs/audits/{name}-report.json`. In fast-path mode, the intermediate files
(raw.json, enriched.json, analysis.json) are **optional** — write them only if the
user wants historical tracking. The findings are already analyzed.

**Total time: ~10 seconds for data collection (or ~5s with cache), then local file writing.**

#### Cache Regeneration (after slow-path variable fetch)

If the execute script ran in slow-path mode (`usedCache: false`), the variable maps were
freshly resolved from Figma. Write them to `docs/audits/variable-cache.json` so the next
audit run can skip the collection fetch:

```json
{
  "generatedAt": "<ISO timestamp>",
  "colorMap": { "<hex>": { "name": "<varName>", "collection": "<colName>" }, ... },
  "floatMap": { "<value>": [{ "name": "<varName>", "collection": "<colName>" }], ... }
}
```

Extract these maps from the `figma_execute` result: `colorVarMap` and `floatVarMap` were
built during the run. Return them in the script result or reconstruct from the rawColors/rawCorners/rawSpacing `matchedVar` fields. Do not write the full variable collection — only the resolved hex→var and float→var lookups.

---

### Fallback Path (Cloud MCP) — when Desktop Bridge is unavailable

If `figma_get_status` shows no connection, fall back to the cloud `use_figma` approach.
This is slower (minutes, not seconds) due to 20kb response caps and network round trips.

## Phase 1 — Fallback (Cloud MCP)

Use this path only when Desktop Bridge is unavailable. It's slower (~8 minutes for 500 nodes)
due to 20kb response caps and network round trips, but works without Figma Desktop.

The fallback uses `use_figma` (remote MCP) with chunked walks. Load `figma-workspace`
and `figma-use` skills before any calls.

### Step 1a: Fetch Variable Collections

Run this first to get the file's design system vocabulary. These collections define
what variables exist and their resolved values — the source of truth for binding checks.

#### Script: Fetch Variable Collections

```js
const collections = await figma.variables.getLocalVariableCollectionsAsync();

function toHex(c) {
  return '#' + [c.r, c.g, c.b]
    .map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}

async function resolveValue(val, depth = 0) {
  if (depth > 5) return { error: 'alias chain too deep' };
  if (val?.type === 'VARIABLE_ALIAS') {
    const aliased = await figma.variables.getVariableByIdAsync(val.id);
    if (!aliased) return { error: 'alias target not found', id: val.id };
    const modeIds = Object.keys(aliased.valuesByMode);
    return resolveValue(aliased.valuesByMode[modeIds[0]], depth + 1);
  }
  if (val && typeof val === 'object' && 'r' in val) return { hex: toHex(val) };
  if (typeof val === 'number') return { value: val };
  if (typeof val === 'boolean') return { value: val };
  if (typeof val === 'string') return { value: val };
  return { raw: JSON.stringify(val) };
}

const result = [];
for (const col of collections) {
  const vars = await Promise.all(
    col.variableIds.map(id => figma.variables.getVariableByIdAsync(id))
  );
  const variables = [];
  for (const v of vars.filter(Boolean)) {
    const valuesByMode = {};
    for (const mode of col.modes) {
      const raw = v.valuesByMode[mode.modeId];
      valuesByMode[mode.name] = await resolveValue(raw);
    }
    variables.push({
      name: v.name,
      id: v.id,
      type: v.resolvedType,
      valuesByMode
    });
  }
  result.push({
    name: col.name,
    id: col.id,
    modes: col.modes.map(m => ({ name: m.name, modeId: m.modeId })),
    variables
  });
}

return { collectionCount: result.length, variableCount: result.reduce((s, c) => s + c.variables.length, 0), collections: result };
```

Save the returned `collections` array — it becomes the `variableCollections` field in the raw JSON output.

### Step 1b: Walk All Nodes (Chunked)

Extracts every property from every descendant of the target node. The walk is **chunked**
to avoid API response truncation on large frames (500+ nodes).

**Strategy:** First discover the target's direct children and their node counts. Then walk
each child subtree in a separate `use_figma` call. Combine all chunks into the final raw dump.

**Input:** Set `TARGET_NODE_ID` to the node ID from the user's link or selection.
If auditing a full page, set `TARGET_PAGE_NAME` instead.

#### Step 1b-i: Discover Chunks

Run this first to get the target's direct children and decide how to chunk:

```js
const TARGET_NODE_ID = "REPLACE_ME";  // or null
const TARGET_PAGE_NAME = null;        // or "Organization Management"

let target;
if (TARGET_NODE_ID) {
  target = await figma.getNodeByIdAsync(TARGET_NODE_ID);
  if (!target) return { error: `Node ${TARGET_NODE_ID} not found` };
} else if (TARGET_PAGE_NAME) {
  target = figma.root.children.find(p => p.name === TARGET_PAGE_NAME);
  if (!target) return { error: `Page "${TARGET_PAGE_NAME}" not found` };
  await figma.setCurrentPageAsync(target);
}

function countDescendants(node) {
  let count = 1;
  if ('children' in node) {
    for (const child of node.children) count += countDescendants(child);
  }
  return count;
}

const children = ('children' in target) ? target.children : [];
const chunks = children.map(child => ({
  id: child.id,
  name: child.name,
  type: child.type,
  descendantCount: countDescendants(child)
}));

return {
  targetId: target.id,
  targetName: target.name,
  targetType: target.type,
  totalDescendants: countDescendants(target),
  directChildren: chunks.length,
  chunks
};
```

Review the chunks. If any single child has 300+ descendants, it may need further
sub-chunking. For most page designs, direct children are a good chunking boundary.

#### Step 1b-ii: Walk One Chunk

Run this for **each chunk** identified above. Replace `CHUNK_NODE_ID` with the child's ID.
Accumulate results across calls — each returns a `nodes` array to merge.

```js
const CHUNK_NODE_ID = "REPLACE_ME";

function toHex(c) {
  return '#' + [c.r, c.g, c.b]
    .map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}

const target = await figma.getNodeByIdAsync(CHUNK_NODE_ID);
if (!target) return { error: `Node ${CHUNK_NODE_ID} not found` };

function getBindingStatus(node, prop, index) {
  const bv = node.boundVariables;
  if (!bv || !bv[prop]) return { status: 'raw' };
  const binding = bv[prop];
  if (Array.isArray(binding)) {
    const b = binding[index];
    if (b?.id) return { status: 'bound', variableId: b.id };
    return { status: 'raw' };
  }
  if (binding?.id) return { status: 'bound', variableId: binding.id };
  return { status: 'raw' };
}

function extractFills(node) {
  if (!('fills' in node) || node.fills === figma.mixed || !Array.isArray(node.fills)) return [];
  return node.fills.map((f, i) => {
    const entry = { type: f.type, visible: f.visible !== false, opacity: f.opacity ?? 1 };
    if (f.type === 'SOLID' && f.color) {
      entry.value = toHex(f.color);
    } else if (f.type === 'GRADIENT_LINEAR' || f.type === 'GRADIENT_RADIAL' || f.type === 'GRADIENT_ANGULAR' || f.type === 'GRADIENT_DIAMOND') {
      entry.value = 'gradient';
      entry.stops = f.gradientStops?.map(s => ({ color: toHex(s.color), position: s.position }));
    } else if (f.type === 'IMAGE') {
      entry.value = 'image';
    }
    entry.binding = getBindingStatus(node, 'fills', i);
    return entry;
  });
}

function extractStrokes(node) {
  if (!('strokes' in node) || node.strokes === figma.mixed || !Array.isArray(node.strokes)) return [];
  return node.strokes.map((s, i) => {
    const entry = { type: s.type, visible: s.visible !== false, opacity: s.opacity ?? 1 };
    if (s.type === 'SOLID' && s.color) entry.value = toHex(s.color);
    entry.binding = getBindingStatus(node, 'strokes', i);
    return entry;
  });
}

function extractCorners(node) {
  if (!('cornerRadius' in node)) return null;
  if (node.cornerRadius === figma.mixed) {
    return {
      mixed: true,
      topLeft: { value: node.topLeftRadius, binding: getBindingStatus(node, 'topLeftRadius') },
      topRight: { value: node.topRightRadius, binding: getBindingStatus(node, 'topRightRadius') },
      bottomLeft: { value: node.bottomLeftRadius, binding: getBindingStatus(node, 'bottomLeftRadius') },
      bottomRight: { value: node.bottomRightRadius, binding: getBindingStatus(node, 'bottomRightRadius') },
    };
  }
  return {
    mixed: false,
    all: { value: node.cornerRadius, binding: getBindingStatus(node, 'cornerRadius') }
  };
}

function extractText(node) {
  if (node.type !== 'TEXT') return null;
  const props = {};
  const textProps = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'textDecoration', 'textCase'];
  for (const p of textProps) {
    if (p in node) {
      const val = node[p];
      props[p] = {
        value: val === figma.mixed ? 'MIXED' : (typeof val === 'object' && val !== null ? JSON.parse(JSON.stringify(val)) : val),
        binding: getBindingStatus(node, p)
      };
    }
  }
  props.characters = node.characters?.substring(0, 100);
  return props;
}

function extractLayout(node) {
  if (!('layoutMode' in node)) return null;
  const layout = {
    layoutMode: node.layoutMode,
    primaryAxisAlignItems: node.primaryAxisAlignItems,
    counterAxisAlignItems: node.counterAxisAlignItems,
  };
  if (node.layoutMode !== 'NONE') {
    layout.padding = {
      top: { value: node.paddingTop, binding: getBindingStatus(node, 'paddingTop') },
      right: { value: node.paddingRight, binding: getBindingStatus(node, 'paddingRight') },
      bottom: { value: node.paddingBottom, binding: getBindingStatus(node, 'paddingBottom') },
      left: { value: node.paddingLeft, binding: getBindingStatus(node, 'paddingLeft') },
    };
    layout.gap = { value: node.itemSpacing, binding: getBindingStatus(node, 'itemSpacing') };
    layout.counterGap = ('counterAxisSpacing' in node) ? { value: node.counterAxisSpacing, binding: getBindingStatus(node, 'counterAxisSpacing') } : null;
  }
  layout.sizing = {
    horizontal: node.layoutSizingHorizontal,
    vertical: node.layoutSizingVertical,
  };
  if ('minWidth' in node) layout.minWidth = node.minWidth;
  if ('maxWidth' in node) layout.maxWidth = node.maxWidth;
  if ('minHeight' in node) layout.minHeight = node.minHeight;
  if ('maxHeight' in node) layout.maxHeight = node.maxHeight;
  return layout;
}

function extractEffects(node) {
  if (!('effects' in node) || !Array.isArray(node.effects)) return [];
  return node.effects.map(e => ({
    type: e.type,
    visible: e.visible !== false,
    radius: e.radius,
    offset: e.offset ? { x: e.offset.x, y: e.offset.y } : null,
    color: (e.color && 'r' in e.color) ? toHex(e.color) : null,
    spread: e.spread,
  }));
}

async function extractInstance(node) {
  if (node.type !== 'INSTANCE') return null;
  const info = {
    componentName: null,
    componentKey: null,
    isLocal: false,
    sourceLibrary: null,
    overrides: [],
  };
  try {
    const mainComp = await node.getMainComponentAsync();
    if (mainComp) {
      info.componentName = mainComp.name;
      info.componentKey = mainComp.key;
      const remote = mainComp.remote;
      info.isLocal = !remote;
      if (remote) {
        info.sourceLibrary = mainComp.parent?.name || 'unknown library';
      }
    }
  } catch (e) { /* instance may be detached */ }
  try {
    const overrides = node.overrides;
    if (overrides && Array.isArray(overrides)) {
      info.overrides = overrides.slice(0, 20).map(o => ({
        id: o.id,
        overriddenFields: o.overriddenFields,
      }));
    }
  } catch (e) { /* overrides may not be accessible */ }
  return info;
}

function buildParentChain(node) {
  const chain = [];
  let current = node.parent;
  while (current && current.type !== 'PAGE' && current.type !== 'DOCUMENT') {
    chain.unshift(current.name);
    current = current.parent;
  }
  return chain.join(' > ');
}

const nodes = [];
// Read-only audit: compound-ID nodes are safe to read (only writes throw).
// Include the target itself + all descendants, wrapped in try/catch per node.
const allNodes = [target];
if ('findAll' in target) {
  try { allNodes.push(...target.findAll(() => true)); } catch (e) {}
}

for (const node of allNodes) {
  const entry = {
    id: node.id,
    name: node.name,
    type: node.type,
    parentChain: buildParentChain(node),
    visible: node.visible !== false,
    opacity: ('opacity' in node) ? node.opacity : 1,
    blendMode: ('blendMode' in node) ? node.blendMode : null,
    fills: extractFills(node),
    strokes: extractStrokes(node),
    strokeWeight: ('strokeWeight' in node && node.strokeWeight !== figma.mixed)
      ? { value: node.strokeWeight, binding: getBindingStatus(node, 'strokeWeight') }
      : null,
    strokeAlign: ('strokeAlign' in node) ? node.strokeAlign : null,
    corners: extractCorners(node),
    text: extractText(node),
    layout: extractLayout(node),
    effects: extractEffects(node),
    instance: await extractInstance(node),
    width: node.width,
    height: node.height,
  };
  nodes.push(entry);
}

return { chunkId: CHUNK_NODE_ID, chunkName: target.name, nodeCount: nodes.length, nodes };
```

#### Step 1b-iii: Assemble Chunks

After all chunks complete, merge the results:

1. Concatenate all `nodes` arrays from each chunk response
2. Also include the target node itself (run the walk script on the target ID with
   `findAll` replaced by `[target]` — just the one node, no descendants)
3. Total `nodeCount` = sum of all chunk node counts + 1 (for target)

If any chunk returned fewer nodes than expected (compare `nodeCount` in response vs
`descendantCount` from Step 1b-i), that chunk was truncated — sub-chunk it by running
Step 1b-i on that chunk's ID and recursing.

### Step 1c: Resolve Binding Names

After running 1a and 1b, resolve the `variableId` references in the walk output to
human-readable names. Build a lookup from the collections fetched in Step 1a:

```
variableId → { variable: "Color/Text/Default", collection: "Semantic" }
```

Then walk every binding in the nodes output. For each `{ status: "bound", variableId: "..." }`,
replace with `{ status: "bound", variableId: "...", variable: "<name>", collection: "<collection>" }`.
If a variableId has no match in the collections lookup, keep the ID and add
`variable: "unknown"`, `collection: "unknown"` — this will be caught in Phase 3 Pass 4.

This makes the raw dump self-describing — readable without enrichment.

**After running 1a, 1b, and 1c**, combine the results into `docs/audits/{name}-raw.json`:

```json
{
  "meta": {
    "source": "<URL or selection description>",
    "page": "<page name>",
    "targetName": "<target node name>",
    "auditDate": "<YYYY-MM-DD>",
    "nodeCount": <count from walk>
  },
  "variableCollections": <collections from Step 1a>,
  "nodes": <nodes from Step 1b>
}
```

Write this file using the Write tool. The `{name}` is the target name kebab-cased
(e.g., "Organization Management" → `org-management`).

---

## Phase 2 — Enrich

Pure local analysis. No MCP calls. Reads the raw JSON and cross-references against:
- The `variableCollections` already in the raw dump (from Phase 1a)
- `docs/figma-registry.json` → `bindIgnoreRules` (known skip/snap decisions)
- `docs/figma-registry.json` → `components` (local component inventory)

### Instructions

Read `docs/audits/{name}-raw.json` and `docs/figma-registry.json`. Build these
lookup structures in memory:

**Variable lookup (from raw JSON → variableCollections):**
- Color variables: map of hex value → { variableName, collectionName }
  - Use the first mode's resolved value for matching
  - Include both primitives and semantic collections
- Float variables: map of numeric value → { variableName, collectionName }
  - Covers corners, spacing, stroke weights

**Property-aware variable categories (match by property context, not just value):**

Float variables must be matched against the correct semantic category based on where
the raw value appears. A 12px padding should match `Spacing/*`, not `Corners/Corner-Base`:

| Property context | Match against these variable name patterns | Never match |
|---|---|---|
| cornerRadius, topLeftRadius, etc. | `Corners/*`, `Corner-*` | Spacing, Stroke weights |
| paddingTop/Right/Bottom/Left, itemSpacing, counterAxisSpacing | `Spacing/*`, `Space-*` | Corners, Stroke weights |
| strokeWeight | `Stroke/Weight/*`, `Strokes/Weights/*` | Corners, Spacing |
| fontSize | `Typography/Font-Size/*` | Corners, Spacing, Strokes |
| gap (itemSpacing) | `Spacing/*`, component-specific gaps (e.g., `Drawer/Gap`) | Corners, Strokes |

This prevents false matches where different token categories share numeric values.

**Ignore rules lookup (from figma-registry.json → bindIgnoreRules):**
- By hex value: `bindIgnoreRules.fills.byHex` — keyed by hex, has action (skip/snap/pending)
- By node type: `bindIgnoreRules.fills.byNodeType` — e.g., VECTOR → always skip
- Same structure for strokes and corners sections

**Component lookup (from figma-registry.json → components):**
- Map of component name → { nodeId, key, type, section, properties }
- Also build a normalized name map: strip "M" prefix, lowercase, for fuzzy matching

### Enrichment Logic

For each node in the raw dump, add an `enrichment` key:

**For each fill/stroke with `binding.status === "raw"`:**

1. Check ignore rules by node type → if hit, attach `{ ignored: true, reason: "..." }`
2. Check ignore rules by hex value → if hit, attach `{ ignored: true, action: "skip|snap", reason: "..." }`
3. Find nearest variable match:
   - Compute normalized RGB distance: `distance = sqrt((r1-r2)^2 + (g1-g2)^2 + (b1-b2)^2) / sqrt(3)` where r/g/b are 0-1
   - This produces a 0-1 score where 0 = identical, 1 = maximally different
   - `matchScore = 1 - distance` (1.0 = exact, 0.0 = no match)
   - `exact`: matchScore === 1.0 (distance === 0)
   - `near`: matchScore >= 0.96 (~10 RGB per channel tolerance)
   - `none`: matchScore < 0.96
   - Attach: `{ match: "exact|near|none", variable: "Color/Text/Default", collection: "Semantic", matchScore: 0.98 }`
   - Sort suggestions by matchScore descending — best match first

**For each corner/spacing/gap/strokeWeight with `binding.status === "raw"`:**

1. Check ignore rules (corners section)
2. Find nearest float variable match:
   - `exact`: value difference === 0
   - `near`: value difference <= 1
   - `none`: value difference > 1
   - Attach same structure as above

**For each fill/stroke with `binding.status === "bound"`:**

1. Look up the `variableId` in the variable collections
2. If found: attach `{ valid: true, variableName: "...", collection: "..." }`
3. If not found: attach `{ valid: false, reason: "variable not found in collections" }`

**For each instance node:**

1. Look up `componentName` in the component registry (exact match first, then M-prefixed)
2. Classify:
   - `local-match`: exact name match in registry
   - `local-candidate`: partial match (e.g., "Button" matches "MButton")
   - `external-only`: no match found
3. Attach: `{ localEquivalent: "local-match|local-candidate|external-only", matchedComponent: "MButton" }`

### Output

Write `docs/audits/{name}-enriched.json` — same structure as raw, with `enrichment`
added to each property and instance. Preserve the raw file unchanged.

---

## Phase 3 — Analyze

Pure local analysis. Reads the enriched JSON and produces structured findings
with severity levels. Four analysis passes.

### Instructions

Read `docs/audits/{name}-enriched.json`. Run these passes:

### Pass 1 — Unbound Properties

Filter all properties where `binding.status === "raw"` AND `enrichment.ignored !== true`.

Group by property type (fill, stroke, corner, text fontSize, padding, gap, strokeWeight, etc.).
Within each group, sort by the raw value — cluster identical values together with a count
of how many nodes use that value.

**Severity assignment per finding:**
- **critical**: raw value has an `exact` match to a variable (should clearly be bound)
- **warning**: raw value has a `near` match (likely drift — snap to nearest)
- **info**: raw value has no match (may be intentional, needs human decision)

**Finding structure:**
```json
{
  "severity": "critical",
  "property": "fill",
  "value": "#1A1A2E",
  "matchedVariable": "Color/Text/Default",
  "matchConfidence": "exact",
  "distance": 0,
  "nodeCount": 14,
  "nodes": [
    { "id": "123:456", "name": "Title", "parentChain": "Frame > Header" }
  ]
}
```

### Pass 2 — Token Candidates

From the Pass 1 results, extract clusters where:
- `matchConfidence === "none"` (no existing variable matches)
- The same raw value appears on **3+ distinct nodes** (not counting nodes within the same component's variants)

For each candidate:
- Suggest a variable name following the file's existing naming convention
  (inspect `variableCollections` names — e.g., `Color/{Category}/{Variant}` for colors,
  `Corner/{Name}` for radii)
- Suggest which collection it belongs in
- List all node locations

**Finding structure:**
```json
{
  "severity": "info",
  "value": "#4A90D9",
  "type": "COLOR",
  "occurrences": 7,
  "suggestedName": "Color/Brand/Accent-Light",
  "suggestedCollection": "Semantic",
  "nodes": [ ... ]
}
```

### Pass 3 — Library Provenance

Group all instance nodes by source. Three buckets:
- **Local instances** (`isLocal: true`) — just count them
- **External with local equivalent** (`enrichment.localEquivalent === "local-match"` or `"local-candidate"`)
- **External only** (`enrichment.localEquivalent === "external-only"`)

For external instances, produce a per-library summary:

```json
{
  "library": "MYE Design System (published)",
  "totalInstances": 24,
  "uniqueComponents": ["Button", "Badge", "Input"],
  "withLocalMatch": [
    { "external": "Button", "local": "MButton", "confidence": "local-match", "instanceCount": 12 }
  ],
  "withoutLocalMatch": [
    { "external": "Tooltip", "instanceCount": 3 }
  ]
}
```

Severity: all **info** (human decides equivalence).

### Pass 4 — Binding Validation

Filter bound properties where `enrichment.valid === false`.

- Variable not found in collections → **critical** (stale binding)
- Variable found but value mismatch → **warning** (drift)

### Output

Write `docs/audits/{name}-analysis.json`:

```json
{
  "meta": {
    "auditDate": "<YYYY-MM-DD>",
    "source": "<from raw meta>",
    "page": "<from raw meta>",
    "nodeCount": "<from raw meta>"
  },
  "summary": {
    "totalProperties": "<count of all fill + stroke + corner + text + layout properties>",
    "bound": "<count with status bound>",
    "raw": "<count with status raw>",
    "ignored": "<count with enrichment.ignored>",
    "bindingCoverage": "<percentage as string, e.g. 87%>",
    "findings": { "critical": "<n>", "warning": "<n>", "info": "<n>" }
  },
  "passes": {
    "unboundProperties": [ "<Pass 1 findings>" ],
    "tokenCandidates": [ "<Pass 2 findings>" ],
    "libraryProvenance": [ "<Pass 3 findings>" ],
    "bindingValidation": [ "<Pass 4 findings>" ]
  }
}
```

---

## Phase 4 — Report

Reads the analysis JSON and produces two output files: a human-readable markdown
summary and a machine-readable JSON report.

### Instructions

Read `docs/audits/{name}-analysis.json`. Generate both outputs:

### Markdown Report

Write `docs/audits/{name}-report.md` with this structure:

````
# Figma Page Audit: {Page Name}

**Date:** {auditDate} | **Source:** {source} | **Nodes:** {nodeCount} | **Binding coverage:** {bindingCoverage}

## Summary

| Category | Critical | Warning | Info | Total |
|----------|----------|---------|------|-------|
| Unbound Properties | {n} | {n} | {n} | {n} |
| Token Candidates | — | — | {n} | {n} |
| Library Provenance | — | — | {n} | {n} |
| Binding Validation | {n} | {n} | — | {n} |
| **Total** | **{n}** | **{n}** | **{n}** | **{n}** |

## Critical Findings

{For each critical finding from Passes 1 and 4:}

### {N}. {property type}: {value} — {matchedVariable}

- **Property:** {fill/stroke/corner/...}
- **Value:** `{raw value}`
- **Matched variable:** `{variable name}` ({collection}) — {exact/near} match
- **Affected nodes:** {count}
  - `{node name}` in {parentChain}
  - `{node name}` in {parentChain}
  - ...
- **Action:** Bind to `{variable name}` using `figma-bind-variables`

## Warning Findings

{Same structure as Critical, for warning-severity findings}

## Token Candidates

{For each token candidate from Pass 2:}

### {value} ({type}) — {occurrences} occurrences

- **Suggested name:** `{suggestedName}`
- **Suggested collection:** {suggestedCollection}
- **Locations:**
  - `{node name}` in {parentChain}
  - ...
- **Action:** Create new variable or identify correct existing variable

## External Library Instances

{For each external library from Pass 3:}

### {library name} — {totalInstances} instances

| External Component | Instances | Local Equivalent | Confidence |
|---|---|---|---|
| {name} | {n} | {localName or "—"} | {match/candidate/none} |

**Action:** Run `figma-swap-library-to-local` for components with local matches.

## Binding Drift

{For each finding from Pass 4, if any:}

- **Node:** `{name}` ({parentChain})
- **Variable:** `{variable name}` ({collection})
- **Issue:** {variable not found / value mismatch}
- **Action:** Re-bind or update variable

## Recommended Next Steps

1. Run `figma-bind-variables` to fix {n} unbound properties with exact matches
2. Run `figma-swap-library-to-local` for {n} external instances with local equivalents
3. Review {n} token candidates — create new variables or identify correct bindings
4. Investigate {n} binding validation issues
````

### JSON Report

Write `docs/audits/{name}-report.json` — same data as the analysis JSON but with
the `meta` section expanded to include the markdown report path:

```json
{
  "meta": {
    "auditDate": "...",
    "source": "...",
    "page": "...",
    "nodeCount": 347,
    "reportPath": "docs/audits/{name}-report.md",
    "rawPath": "docs/audits/{name}-raw.json",
    "enrichedPath": "docs/audits/{name}-enriched.json",
    "analysisPath": "docs/audits/{name}-analysis.json"
  },
  "summary": { "..." : "..." },
  "passes": { "..." : "..." }
}
```

### After Phase 4

Print the Summary table from the markdown report to the terminal so the user
sees results immediately without opening the file.

---

## Known Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Compound-ID nodes (writes) | Script throws on property **write** access | `!n.id.includes(';')` filter on `findAll` **for write operations only**. For read-only audits, compound-ID nodes are safe to read — wrap property access in try/catch |
| Instance descendants all have compound IDs | `findAll` with `;` filter returns 0 nodes on instances | For audit targets that are INSTANCE nodes, use `findAll(() => true)` with try/catch per node instead of filtering |
| Large pages timeout | `use_figma` returns no result or truncates at ~200 nodes | Split the walk: audit sub-frames in chunks of ~50-100 nodes. Walk top-level children first, then recurse into each |
| API response truncation | Walk returns nodeCount but `nodes` array is incomplete | Compare `nodes.length` to `nodeCount` — if they differ, the response was truncated. Re-walk by targeting sub-frames individually |
| Stale variable IDs | Enrichment marks bound variables as "not found" | Always fetch fresh collections in Phase 1a — never reuse from prior audits |
| Gradient/image fills | Not color-matchable | Walk script records them as `gradient`/`image` type — enrichment skips these |
| Mixed properties | `figma.mixed` on text or corners | Walk script handles mixed — records `MIXED` for text, per-corner values for corners |
| Component variant nodes | Same raw value repeated across variants inflates counts | Pass 2 de-duplicates by requiring 3+ **distinct parent components**, not just 3+ nodes |
| Instance overrides | Override values aren't the component's fault | Walk captures overrides list — enrichment can flag but shouldn't count toward token candidates |
| `node.overrides` not available | API version doesn't support it | Walk script wraps in try/catch, returns empty overrides array |
| Raw typography inside instances | TEXT nodes in instances show raw fontSize/fontWeight even if the component definition has them bound | Before flagging, check if the node is inside an instance (parent chain contains INSTANCE type). If so, the raw values may come from the component definition — verify against the master component before reporting as unbound |
| Semantic mismatches | A property is bound but to the wrong semantic category | Phase 3 should check: text tokens on text, stroke tokens on strokes, surface tokens on fills. Flag cross-category bindings as warnings (e.g., Text-Default used as a stroke color) |
| COMPONENT_SET default frame styles | Figma adds a #9747FF stroke and 16px padding to COMPONENT_SET frames as organizational markers | Always skip COMPONENT_SET nodes for fill, stroke, padding, and corner checks. These are Figma's UI chrome, not design tokens. Filter: `if (node.type === 'COMPONENT_SET') skip` |
| `node.mainComponent` throws in Desktop Bridge | "Cannot call with documentAccess: dynamic-page" | Always use `await node.getMainComponentAsync()` instead. The sync accessor only works in cloud `use_figma`, not in `figma_execute` |

---

## File Layout

All audit artifacts persist in `docs/audits/`:

```
docs/audits/
  {name}-raw.json           ← Phase 1 (historical snapshot)
  {name}-enriched.json      ← Phase 2 (working copy)
  {name}-analysis.json      ← Phase 3 (findings)
  {name}-report.md          ← Phase 4 (human summary)
  {name}-report.json        ← Phase 4 (machine summary)
```

Files are named by the target, kebab-cased. Successive runs overwrite existing files
for the same target. To preserve history, rename or copy the raw file before re-running.

---

## Relationship to Other Skills

| Skill | Relationship |
|---|---|
| `figma-bind-variables` | Audit recommends it for unbound properties. Reads same `bindIgnoreRules`. No shared execution. |
| `figma-swap-library-to-local` | Audit recommends it for external instances. No shared execution. |
| `design-system-sync` | Separate concern (Figma↔code parity). This audit stays within Figma's own DS. |
| `design-audit` | Code-side counterpart. Same report format conventions. |
| `component-build` | Can consume audit findings to identify components needing attention. |
