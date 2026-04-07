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
