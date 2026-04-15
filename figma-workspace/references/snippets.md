# Figma Workspace Snippets

Reusable code blocks for common read and audit operations. For write/build snippets, see `figma-builder/references/snippets.md`.

---

## Connection & Audit

```js
// Quick health check (figma_execute)
return {
  file: figma.root.name,
  page: figma.currentPage.name,
  childCount: figma.currentPage.children.length
};
```

```js
// Find clear canvas space for new content
const page = figma.currentPage;
let maxY = 0, minX = Infinity;
for (const node of page.children) {
  const b = node.absoluteBoundingBox;
  if (b) {
    if (b.y + b.height > maxY) maxY = b.y + b.height;
    if (b.x < minX) minX = b.x;
  }
}
return { suggestedX: minX, suggestedY: maxY + 200 };
```

---

## Tree Walking

```js
// Collect all text from a subtree
function collectText(node) {
  const texts = [];
  if (node.type === 'TEXT') texts.push(node.characters.trim().slice(0, 80));
  if ('children' in node) for (const c of node.children) texts.push(...collectText(c));
  return texts.filter(Boolean);
}
```

```js
// Find all instances of a named component in a frame with nearby text
const root = await figma.getNodeByIdAsync('FRAME_ID');
const results = [];
async function walk(node) {
  if (node.type === 'INSTANCE' && node.name === 'TARGET_NAME') {
    const nearby = [];
    if (node.parent && 'children' in node.parent) {
      for (const sib of node.parent.children) {
        if (sib.id !== node.id) nearby.push(...collectText(sib));
      }
    }
    const mc = await node.getMainComponentAsync();
    results.push({
      id: node.id,
      props: Object.fromEntries(
        Object.entries(node.componentProperties || {}).map(([k,v]) => [k, v.value])
      ),
      parentName: node.parent?.name,
      nearbyText: nearby.slice(0, 4),
      mainCompName: mc?.name
    });
  }
  if ('children' in node) for (const c of node.children) await walk(c);
}
await walk(root);
return { count: results.length, results };
```

---

## Component Inspection

```js
// Deep inspect a node's property tree (3 levels)
const node = await figma.getNodeByIdAsync('NODE_ID');
function describeProps(n, depth = 0) {
  const info = {
    id: n.id, name: n.name, type: n.type,
    size: { w: Math.round(n.width), h: Math.round(n.height) }
  };
  if (n.componentProperties) {
    info.props = Object.fromEntries(
      Object.entries(n.componentProperties).map(([k,v]) => [k, v.value])
    );
  }
  if (n.fills?.length) {
    info.fills = n.fills.map(f =>
      f.type + (f.color ? `(${f.color.r.toFixed(2)},${f.color.g.toFixed(2)},${f.color.b.toFixed(2)})` : '')
    );
  }
  if (n.strokes?.length) info.strokes = n.strokes.map(s => s.type);
  if ('strokeWeight' in n) info.strokeWeight = n.strokeWeight;
  if ('clipsContent' in n) info.clipsContent = n.clipsContent;
  if ('children' in n && depth < 3) {
    info.children = n.children.map(c => describeProps(c, depth + 1));
  }
  return info;
}
return describeProps(node);
```

---

## Serving Large Data to figma_execute

For large datasets (many SVGs, big lookup tables), serve via local HTTP.

```bash
# bash_tool: set up local server
mkdir -p /tmp/serve
echo '{"IconName": "<svg...>"}' > /tmp/serve/data.json
python3 -m http.server 8765 --directory /tmp/serve &
sleep 1 && curl -s http://localhost:8765/data.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'items')"
```

```js
// figma_execute: fetch served data
const resp = await fetch('http://localhost:8765/data.json');
const data = await resp.json();
// ... use data in your operation
```

---

## Batch Token Binding — 2-Call Pattern

Use this pattern to bind design tokens to raw values across multiple pages in 2 calls instead of many.

**Known gotchas to handle upfront:**
- `cornerRadius` returns `figma.mixed` (a Symbol) when individual corners differ → use `typeof v === 'symbol'` check before returning
- `boundVariables` on a paint object is nested inside the paint, not on the node → access via `paint.boundVariables`
- `setBoundVariableForPaint` returns a NEW paint — must reassign `node.fills` / `node.strokes`
- Page context resets each call → always `await figma.setCurrentPageAsync(page)` at the top

**Variable IDs:** Cached in `docs/figma-registry.json` → `variables` section. Read from there — zero lookup calls needed.

### Call 1: Discovery — scan a frame for raw values

```js
// Returns a work list: nodes with unbound fills, strokes, or corner radii
// Replace FRAME_ID and PAGE_NAME with your targets
const page = figma.root.children.find(p => p.name === 'PAGE_NAME');
await figma.setCurrentPageAsync(page);

const root = await figma.getNodeByIdAsync('FRAME_ID');
const isMixed = v => typeof v === 'symbol';
const findings = [];

function audit(node, path) {
  const issues = [];

  // Fills
  if (node.fills && Array.isArray(node.fills)) {
    node.fills.forEach((f, i) => {
      if (f.type === 'SOLID' && (!f.boundVariables || !f.boundVariables.color)) {
        const c = f.color;
        issues.push({ prop: `fills[${i}].color`, r: c.r.toFixed(3), g: c.g.toFixed(3), b: c.b.toFixed(3) });
      }
    });
  }

  // Strokes
  if (node.strokes && Array.isArray(node.strokes)) {
    node.strokes.forEach((s, i) => {
      if (s.type === 'SOLID' && (!s.boundVariables || !s.boundVariables.color)) {
        const c = s.color;
        issues.push({ prop: `strokes[${i}].color`, r: c.r.toFixed(3), g: c.g.toFixed(3), b: c.b.toFixed(3) });
      }
    });
  }

  // Corner radius
  const corners = ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'];
  const bound = node.boundVariables || {};
  corners.forEach(k => {
    const val = node[k];
    if (val !== undefined && !isMixed(val) && val > 0 && !bound[k]) {
      issues.push({ prop: k, value: val });
    }
  });

  if (issues.length) findings.push({ id: node.id, name: node.name, path, issues });
  if ('children' in node) node.children.forEach(c => audit(c, path + '/' + c.name));
}

audit(root, root.name);
return { count: findings.length, findings };
```

### Call 2: Write — bind all targets in one script

```js
// Pre-load variable IDs from registry cache — no lookup calls needed
const VAR = {
  cornerLarge:   'VariableID:42:13409',
  textDefault:   'VariableID:37:3881',
  textTertiary:  'VariableID:1362:1828',
  surfaceSecondary: 'VariableID:37:3916',
  regionBg:      'VariableID:1362:1758',
  regionText:    'VariableID:1362:1759',
  // add others from registry as needed
};

// Helper: get variable object (cached within this call)
const varCache = {};
async function getVar(id) {
  if (!varCache[id]) varCache[id] = await figma.variables.getVariableByIdAsync(id);
  return varCache[id];
}

// Work list: each entry is { pageName, nodeId, prop, varId }
// prop is one of: 'topLeftRadius' | 'fills.0.color' | 'strokes.0.color'
const workList = [
  // Example — replace with actual findings from Call 1:
  { pageName: 'Organization Management', nodeId: '3938:12200', prop: 'topLeftRadius', varId: VAR.cornerLarge },
  { pageName: 'Components',              nodeId: '3040:27652', prop: 'strokes.0.color', varId: VAR.textDefault },
];

const results = [];
let currentPage = null;

for (const item of workList) {
  // Switch page only when needed
  if (!currentPage || currentPage.name !== item.pageName) {
    currentPage = figma.root.children.find(p => p.name === item.pageName);
    await figma.setCurrentPageAsync(currentPage);
  }

  const node = await figma.getNodeByIdAsync(item.nodeId);
  if (!node) { results.push({ ...item, status: 'NODE_NOT_FOUND' }); continue; }

  const variable = await getVar(item.varId);
  if (!variable) { results.push({ ...item, status: 'VAR_NOT_FOUND' }); continue; }

  try {
    if (item.prop === 'topLeftRadius' || item.prop.endsWith('Radius')) {
      node.setBoundVariable(item.prop, variable);
    } else if (item.prop.startsWith('fills')) {
      const idx = parseInt(item.prop.split('.')[1]) || 0;
      const newFills = [...node.fills];
      newFills[idx] = figma.variables.setBoundVariableForPaint(newFills[idx], 'color', variable);
      node.fills = newFills;
    } else if (item.prop.startsWith('strokes')) {
      const idx = parseInt(item.prop.split('.')[1]) || 0;
      const newStrokes = [...node.strokes];
      newStrokes[idx] = figma.variables.setBoundVariableForPaint(newStrokes[idx], 'color', variable);
      node.strokes = newStrokes;
    }
    results.push({ ...item, status: 'OK' });
  } catch (e) {
    results.push({ ...item, status: 'ERROR', error: e.message });
  }
}

return { applied: results.filter(r => r.status === 'OK').length, results };
```

---

## Finding Components Across All Pages

```js
// Scan all pages for component sets matching a list of names
const targets = ['BlockIcon', 'Icons', 'Card-Wide'];
const found = [];
for (const page of figma.root.children) {
  const sets = page.findAll(n =>
    (n.type === 'COMPONENT_SET' || n.type === 'COMPONENT') &&
    targets.some(t => n.name.includes(t))
  );
  for (const s of sets) {
    found.push({ page: page.name, name: s.name, id: s.id, type: s.type });
  }
}
return found;
```
