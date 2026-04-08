---
name: figma-bind-variables
description: Use when binding unbound fills, strokes, or corner radii in Figma component definitions to design system variables. Requires figma-use skill before any use_figma call.
---

# Figma: Bind Variables to Component Properties

## Overview

Scans component definitions for unbound fill colors, stroke colors, and corner radii, then binds them to the appropriate design system variables. Runs in five phases to keep scripts focused and recoverable.

Requires `figma-use` skill before any `use_figma` call.

## Workflow

```
Discover IDs → Resolve hex values → Scan unbound → Bind by property type → Verify
```

Five phases, always in order. Never skip phases on a fresh run. If re-running a partial bind with already-validated IDs, phases 1–2 may be skipped.

**Stop and confirm with the user before binding when:**
- A color has no obvious variable match by hex value
- The same hex is used in multiple semantic contexts (e.g. white as text-inverse AND surface-primary)
- A color appears in a very high count that seems wrong (sample it first)

---

## Hard Rules

| Rule | Why |
|---|---|
| Filter `!n.id.includes(';')` on every `findAll` | Compound-ID nodes are nested instance slots — accessing their properties throws |
| Never bind `COMPONENT_SET` fills or strokes | These are Figma's organizational markers, not design tokens |
| Validate every variable ID before the binding script | Stale or guessed IDs return null silently, causing the script to fail mid-loop |
| Discover IDs from `boundVariables` scan, not from memory | IDs from previous sessions may not exist in the current file/branch context |
| Resolve hex values before building the color map | Variable names don't tell you the actual color — always follow alias chains |
| Sample mystery high-count colors before binding | What looks like a brand color may be a third-party logo or icon asset |
| Split binding by property type: text fills / surface fills / strokes / corners | One monolithic script fails silently; four focused scripts are recoverable |

---

---

## Page Name Configuration

All phase scripts target a specific Figma page by name. Before running any phase, confirm the correct page name. Check `.claude/figma-config.json` for `componentsPage` — if set, use that value. Otherwise default to `"Components"`.

Set this constant at the top of each phase script:
```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage
```

---

## Phase 1 — Discover Variable IDs

**Do not use IDs from memory.** Always discover fresh from what's already bound in the file.

```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage

// Collect all variable IDs currently bound in COMPONENT nodes on the target page
const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
if (!compPage) return { error: "Components page not found" };
await figma.setCurrentPageAsync(compPage);

const boundVarIds = new Set();

function collectBound(node) {
  const bv = node.boundVariables;
  if (bv) {
    for (const [prop, binding] of Object.entries(bv)) {
      if (Array.isArray(binding)) {
        for (const b of binding) { if (b?.id) boundVarIds.add(b.id); }
      } else if (binding?.id) {
        boundVarIds.add(binding.id);
      }
    }
  }
  if ('children' in node) {
    for (const child of node.children) collectBound(child);
  }
}

const components = compPage.findAll(n => n.type === "COMPONENT");
for (const c of components) collectBound(c);

const resolved = {};
for (const id of boundVarIds) {
  const v = await figma.variables.getVariableByIdAsync(id);
  if (v) resolved[id] = { name: v.name, type: v.resolvedType };
}

return { boundCount: boundVarIds.size, resolved };
```

From the result, identify which IDs correspond to the semantic variables you need (text colors, surface colors, stroke colors, corner tokens). Copy their IDs — these are what you'll use in Phase 2.

Also use `getLocalVariableCollectionsAsync()` to list local collections if you need IDs that aren't yet bound to anything:

```js
const collections = await figma.variables.getLocalVariableCollectionsAsync();
const result = {};
for (const col of collections) {
  const vars = await Promise.all(col.variableIds.map(id => figma.variables.getVariableByIdAsync(id)));
  result[col.name] = {
    id: col.id,
    modes: col.modes.map(m => ({ name: m.name, modeId: m.modeId })),
    variables: vars.filter(Boolean).map(v => ({ name: v.name, id: v.id, type: v.resolvedType }))
  };
}
return result;
```

---

## Phase 2 — Resolve Hex Values + Validate IDs

**Separate call from Phase 1.** Resolves variable IDs to actual hex colors by following alias chains. Also validates that every ID loads successfully.

```js
// Paste the IDs identified in Phase 1
const varDefs = {
  textDefault:   "VariableID:xx:xxxx",
  textSecondary: "VariableID:xx:xxxx",
  textInverse:   "VariableID:xx:xxxx",
  // ... add all needed variables
};

function toHex(color) {
  return '#' + [color.r, color.g, color.b]
    .map(v => Math.round(v * 255).toString(16).padStart(2,'0')).join('');
}

async function resolveVar(id, depth = 0) {
  if (depth > 5) return { error: 'alias chain too deep' };
  const v = await figma.variables.getVariableByIdAsync(id);
  if (!v) return { error: 'not found' };
  const modeIds = Object.keys(v.valuesByMode);
  if (!modeIds.length) return { error: 'no modes' };
  const val = v.valuesByMode[modeIds[0]];
  if (val?.type === 'VARIABLE_ALIAS') return resolveVar(val.id, depth + 1);
  if (v.resolvedType === 'COLOR' && val && 'r' in val) return { hex: toHex(val) };
  if (v.resolvedType === 'FLOAT') return { value: val };
  return { raw: val };
}

const results = {};
const failed = [];
for (const [k, id] of Object.entries(varDefs)) {
  const v = await figma.variables.getVariableByIdAsync(id);
  if (!v) { failed.push(k); continue; }
  const resolved = await resolveVar(id);
  results[k] = { name: v.name, type: v.resolvedType, resolved };
}

return { results, failed };
```

**Stop if `failed` is non-empty.** Fix the IDs before proceeding.

Use the resolved hex values to build your color → variable map in the binding scripts.

---

## Phase 3 — Scan Unbound Properties

Run this before binding to understand scope. Groups unbound colors by hex and counts instances.

```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage

const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
if (!compPage) return { error: `Page "${COMPONENTS_PAGE}" not found` };
await figma.setCurrentPageAsync(compPage);

function toHex(c) {
  return '#' + [c.r, c.g, c.b].map(v => Math.round(v * 255).toString(16).padStart(2,'0')).join('');
}

const fillCounts = {}, strokeCounts = {}, cornerCounts = {};

const allNodes = compPage.findAll(n => !n.id.includes(';'));  // skip compound IDs

for (const node of allNodes) {
  // Fills
  if ('fills' in node && Array.isArray(node.fills) && node.fills !== figma.mixed) {
    for (let i = 0; i < node.fills.length; i++) {
      const f = node.fills[i];
      if (f.type === 'SOLID' && !node.boundVariables?.fills?.[i]?.id) {
        const key = toHex(f.color);
        fillCounts[key] = (fillCounts[key] || 0) + 1;
      }
    }
  }
  // Strokes
  if ('strokes' in node && Array.isArray(node.strokes) && node.strokes !== figma.mixed) {
    for (let i = 0; i < node.strokes.length; i++) {
      const s = node.strokes[i];
      if (s.type === 'SOLID' && !node.boundVariables?.strokes?.[i]?.id) {
        const key = toHex(s.color);
        strokeCounts[key] = (strokeCounts[key] || 0) + 1;
      }
    }
  }
  // Corners
  if ('cornerRadius' in node && node.cornerRadius !== figma.mixed &&
      typeof node.cornerRadius === 'number' && node.cornerRadius > 0 &&
      !node.boundVariables?.cornerRadius) {
    const v = Math.round(node.cornerRadius);
    cornerCounts[v] = (cornerCounts[v] || 0) + 1;
  }
}

return {
  fills: Object.entries(fillCounts).sort((a,b) => b[1]-a[1]),
  strokes: Object.entries(strokeCounts).sort((a,b) => b[1]-a[1]),
  corners: Object.entries(cornerCounts).sort((a,b) => b[1]-a[1]),
};
```

### Reviewing scan results

For each high-count color:
1. Does it match a known variable hex from Phase 2? → Map it.
2. No match? Sample it before deciding (see Sampling below).
3. High count and no variable? → Flag to user; may need a new token.

**Never bind a color you haven't confirmed matches a variable by hex value.**

### Sampling a mystery color

```js
// Replace TARGET_HEX with the 6-char hex to investigate
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage
const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
await figma.setCurrentPageAsync(compPage);

const target = "172b85"; // example
function matches(c) {
  const hex = [c.r,c.g,c.b].map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('');
  return hex === target;
}

const samples = [];
const allNodes = compPage.findAll(n => !n.id.includes(';'));
for (const node of allNodes) {
  if (samples.length >= 10) break;
  if ('fills' in node && Array.isArray(node.fills) && node.fills !== figma.mixed) {
    for (const f of node.fills) {
      if (f.type === 'SOLID' && matches(f.color)) {
        let comp = node;
        while (comp && comp.type !== 'COMPONENT') comp = comp.parent;
        samples.push({ nodeType: node.type, nodeName: node.name, compName: comp?.name });
        break;
      }
    }
  }
}
return { samples };
```

---

## Phase 4 — Bind by Property Type

Run as four separate scripts. Each is independent and recoverable if it fails.

### 4a. Text fills

```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage

const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
if (!compPage) return { error: `Page "${COMPONENTS_PAGE}" not found` };
await figma.setCurrentPageAsync(compPage);

// Paste IDs from Phase 2 validation
const varDefs = {
  textInverse:    "VariableID:xx:xxxx",  // #ffffff
  textDefault:    "VariableID:xx:xxxx",  // #292e3e (example)
  textSecondary:  "VariableID:xx:xxxx",
  textTertiary:   "VariableID:xx:xxxx",
  textAccentDark: "VariableID:xx:xxxx",
  textLink:       "VariableID:xx:xxxx",
};
const V = {};
for (const [k, id] of Object.entries(varDefs)) {
  V[k] = await figma.variables.getVariableByIdAsync(id);
  if (!V[k]) return { error: `Failed to load: ${k}` };
}

// hex (no #) → variable key — built from Phase 2 resolved values
const colorMap = {
  "ffffff": "textInverse",
  "292e3e": "textDefault",
  // ... fill in from Phase 2 hex results
};

function toHex8(c) {
  return [c.r,c.g,c.b].map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('');
}

const bound = [], errors = [];
const allText = compPage.findAll(n => n.type === "TEXT" && !n.id.includes(';'));

for (const node of allText) {
  if (node.fills === figma.mixed || !Array.isArray(node.fills)) continue;
  let fills = [...node.fills];
  let changed = false;
  for (let i = 0; i < fills.length; i++) {
    const fill = fills[i];
    if (fill.type !== 'SOLID' || fill.opacity === 0) continue;
    if (node.boundVariables?.fills?.[i]?.id) continue;
    const varKey = colorMap[toHex8(fill.color)];
    if (!varKey) continue;
    try {
      fills[i] = figma.variables.setBoundVariableForPaint(fills[i], 'color', V[varKey]);
      changed = true;
      bound.push({ varKey, hex: toHex8(fill.color) });
    } catch (e) { errors.push({ nodeId: node.id, err: e.message.slice(0,80) }); }
  }
  if (changed) {
    try { node.fills = fills; } catch (e) { errors.push({ phase: 'assign', err: e.message.slice(0,80) }); }
  }
}

const tally = {};
for (const b of bound) tally[b.varKey] = (tally[b.varKey]||0)+1;
return { boundTotal: bound.length, tally, errorCount: errors.length, errors: errors.slice(0,5) };
```

### 4b. Surface fills

```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage

const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
if (!compPage) return { error: `Page "${COMPONENTS_PAGE}" not found` };
await figma.setCurrentPageAsync(compPage);

// Paste IDs from Phase 2 validation
const varDefs = {
  surfacePrimary:   "VariableID:xx:xxxx",  // #ffffff (example)
  surfaceSecondary: "VariableID:xx:xxxx",
  surfaceAccent:    "VariableID:xx:xxxx",
  // ... add all needed surface variables
};
const V = {};
for (const [k, id] of Object.entries(varDefs)) {
  V[k] = await figma.variables.getVariableByIdAsync(id);
  if (!V[k]) return { error: `Failed to load: ${k}` };
}

// hex (no #) → variable key — built from Phase 2 resolved values
const colorMap = {
  "ffffff": "surfacePrimary",
  // ... fill in from Phase 2 hex results
};

function toHex8(c) {
  return [c.r,c.g,c.b].map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('');
}

const SURFACE_TYPES = new Set(["FRAME", "RECTANGLE", "ELLIPSE", "COMPONENT"]);
const bound = [], errors = [];

const candidates = compPage.findAll(n =>
  SURFACE_TYPES.has(n.type) && !n.id.includes(';') && !n.isMask
);

for (const node of candidates) {
  if (node.fills === figma.mixed || !Array.isArray(node.fills)) continue;
  let fills = [...node.fills];
  let changed = false;
  for (let i = 0; i < fills.length; i++) {
    const fill = fills[i];
    if (fill.type !== 'SOLID') continue;
    // Skip near-transparent white — likely a ghost or overlay, not a surface token
    if (fill.color.r > 0.99 && fill.color.g > 0.99 && fill.color.b > 0.99 && (fill.opacity ?? 1) < 0.99) continue;
    if (node.boundVariables?.fills?.[i]?.id) continue;
    const varKey = colorMap[toHex8(fill.color)];
    if (!varKey) continue;
    try {
      fills[i] = figma.variables.setBoundVariableForPaint(fills[i], 'color', V[varKey]);
      changed = true;
      bound.push({ varKey, hex: toHex8(fill.color) });
    } catch (e) { errors.push({ nodeId: node.id, err: e.message.slice(0,80) }); }
  }
  if (changed) {
    try { node.fills = fills; } catch (e) { errors.push({ phase: 'assign', err: e.message.slice(0,80) }); }
  }
}

const tally = {};
for (const b of bound) tally[b.varKey] = (tally[b.varKey]||0)+1;
return { boundTotal: bound.length, tally, errorCount: errors.length, errors: errors.slice(0,5) };
```

### 4c. Strokes

```js
// Same structure — filter nodes that have 'strokes', skip compound IDs
const candidates = compPage.findAll(n => 'strokes' in n && !n.id.includes(';'));

for (const node of candidates) {
  if (!Array.isArray(node.strokes) || node.strokes === figma.mixed) continue;
  let strokes = [...node.strokes];
  let changed = false;
  for (let i = 0; i < strokes.length; i++) {
    const stroke = strokes[i];
    if (stroke.type !== 'SOLID') continue;
    if (node.boundVariables?.strokes?.[i]?.id) continue;
    const varKey = colorMap[toHex8(stroke.color)];
    if (!varKey) continue;
    try {
      strokes[i] = figma.variables.setBoundVariableForPaint(strokes[i], 'color', V[varKey]);
      changed = true;
    } catch (e) { errors.push({ nodeId: node.id, err: e.message.slice(0,80) }); }
  }
  if (changed) {
    try { node.strokes = strokes; } catch (e) { /* ... */ }
  }
}
```

### 4d. Corner radii

The threshold values below use the default scale from `figma-workspace/references/conventions.md`. If your project uses a different corner radius scale, check your active conventions source (`conventionsPath` in `figma-config.json`) and adjust the `getCornerVar` thresholds accordingly before running this script.

```js
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage

const compPage = figma.root.children.find(p => p.name === COMPONENTS_PAGE);
if (!compPage) return { error: `Page "${COMPONENTS_PAGE}" not found` };
await figma.setCurrentPageAsync(compPage);

const varDefs = {
  cornerXS:    "VariableID:xx:xxxx",  // 4px
  cornerSmall: "VariableID:xx:xxxx",  // 8px
  cornerBase:  "VariableID:xx:xxxx",  // 12px
  cornerLarge: "VariableID:xx:xxxx",  // 20px
  cornerFull:  "VariableID:xx:xxxx",  // 100px
};
const V = {};
for (const [k, id] of Object.entries(varDefs)) {
  V[k] = await figma.variables.getVariableByIdAsync(id);
  if (!V[k]) return { error: `Failed to load: ${k}` };
}

// value (px) → variable key
// Default scale from figma-workspace/references/conventions.md.
// If your project uses different values, update these thresholds to match
// the corner radius scale in your active conventions source (conventionsPath).
function getCornerVar(val) {
  if (Math.abs(val - 4)   < 0.5) return 'cornerXS';
  if (Math.abs(val - 8)   < 0.5) return 'cornerSmall';
  if (Math.abs(val - 12)  < 0.5) return 'cornerBase';
  if (Math.abs(val - 20)  < 0.5) return 'cornerLarge';
  if (Math.abs(val - 100) < 0.5 || val > 10000) return 'cornerFull';  // Figma stores "full" corner radius as 16777200 internally
  return null;
}

const bound = [], errors = [];
const candidates = compPage.findAll(n => 'cornerRadius' in n && !n.id.includes(';'));

for (const node of candidates) {
  if (node.cornerRadius === figma.mixed) continue;
  if (typeof node.cornerRadius !== 'number' || node.cornerRadius <= 0) continue;
  if (node.boundVariables?.cornerRadius) continue;
  const varKey = getCornerVar(node.cornerRadius);
  if (!varKey) continue;
  try {
    node.setBoundVariable('cornerRadius', V[varKey]);
    bound.push({ varKey, value: node.cornerRadius });
  } catch (e) { errors.push({ nodeId: node.id, err: e.message.slice(0,80) }); }
}

const tally = {};
for (const b of bound) tally[b.varKey] = (tally[b.varKey]||0)+1;
return { boundTotal: bound.length, tally, errorCount: errors.length, errors: errors.slice(0,5) };
```

---

## Phase 5 — Verify

Re-run the Phase 3 scan unchanged. Compare counts before and after.

- **Counts dropped for all mapped colors:** Done.
- **A color still has a high count:** Check if those nodes are VECTOR/BOOLEAN_OPERATION (graphic assets, skip) or if they were filtered by compound-ID and need fixing at the component definition level.
- **Unexpected high counts in any category:** Sample them before deciding.

---

## Known Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Compound-ID nodes in `findAll` | Script throws on `node.fills` access | Add `!n.id.includes(';')` filter to every `findAll` |
| Stale variable IDs across sessions | `getVariableByIdAsync` returns null; script fails mid-loop | Discover IDs from current `boundVariables` scan; validate all before binding |
| Same hex used for multiple semantics | e.g. `#ffffff` = text-inverse AND surface-primary | Split by node type: TEXT → text variable, FRAME/RECT → surface variable |
| COMPONENT_SET fills/strokes | Purple/violet strokes on COMPONENT_SET nodes | These are Figma organizational markers — skip entirely |
| Vector icon fills | High-count hex that's actually an icon or brand logo color | Sample before binding; skip VECTOR and BOOLEAN_OPERATION node types for fills |
| `setBoundVariableForPaint` returns new paint | Original fill not updated | Must reassign: `fills[i] = setBoundVariableForPaint(fills[i], ...)` then `node.fills = fills` |
| Corners at non-standard values | 5px, 10px, 40px — no matching variable | Flag to user; may need new semantic corner tokens or component updates |
| Script returns no output | Usually an error before the `return` — wrap entire body in try/catch | Add `try { ... } catch (e) { return { error: e.message } }` |
