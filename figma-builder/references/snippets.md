# Figma Builder Snippets

Code blocks for common build operations. For read/audit snippets, see `figma-workspace/references/snippets.md`.

---

## Font Loading

```js
// Load all common font variants before any text work
// Add or remove variants based on your project's typography
await Promise.all([
  figma.loadFontAsync({ family: "Inter", style: "Regular" }),
  figma.loadFontAsync({ family: "Inter", style: "Medium" }),
  figma.loadFontAsync({ family: "Inter", style: "Semi Bold" }),
  figma.loadFontAsync({ family: "Inter", style: "Bold" }),
  figma.loadFontAsync({ family: "Inter", style: "Italic" }),
]);
```

---

## Create Component with Auto-Layout

```js
// Standard pattern: component with vertical auto-layout
const comp = figma.createComponent();
comp.name = "MyComponent";
comp.layoutMode = "VERTICAL";
comp.primaryAxisSizingMode = "AUTO";
comp.counterAxisSizingMode = "AUTO";
comp.itemSpacing = 8;
comp.paddingTop = 16;
comp.paddingRight = 16;
comp.paddingBottom = 16;
comp.paddingLeft = 16;
comp.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 }, opacity: 1 }];

// Add children FIRST
const text = figma.createText();
text.characters = "Label";
comp.appendChild(text);

// THEN set sizing (FILL requires auto-layout parent)
text.layoutSizingHorizontal = "FILL";
```

---

## Add Variant to Existing Component Set

```js
// 1. Create the new variant component
const newVariant = figma.createComponent();
newVariant.name = "Property=NewValue"; // Must match schema
newVariant.resize(existingWidth, existingHeight);
newVariant.layoutMode = "VERTICAL";
// ... build out the variant content ...

// 2. Merge into existing set
const existingSet = await figma.getNodeByIdAsync('SET_ID');
const setX = existingSet.x, setY = existingSet.y, setName = existingSet.name;
const parent = existingSet.parent;

// Existing FIRST to preserve naming schema
const merged = figma.combineAsVariants(
  [...existingSet.children, newVariant],
  parent
);
merged.name = setName;
merged.x = setX;
merged.y = setY;

// 3. Post-merge audit
const variantNames = merged.children.map(c => c.name);
const duplicates = variantNames.filter((n, i) => variantNames.indexOf(n) !== i);
const clipsContentValues = [...new Set(merged.children.map(c => c.clipsContent))];

return {
  newId: merged.id,
  variantCount: merged.children.length,
  duplicateNames: duplicates,
  clipsContentConsistent: clipsContentValues.length === 1
};
```

---

## Property Binding Verification

```js
// Check if a component's properties are actually wired to visual elements
const comp = await figma.getNodeByIdAsync('COMPONENT_ID');

function auditBindings(node, depth = 0) {
  const result = { id: node.id, name: node.name, type: node.type };

  if (node.componentPropertyReferences) {
    const refs = node.componentPropertyReferences;
    if (Object.keys(refs).length > 0) {
      result.bindings = refs;
    }
  }

  if (node.componentProperties) {
    result.exposedProps = Object.fromEntries(
      Object.entries(node.componentProperties).map(([k, v]) => [k, v.type + ':' + v.value])
    );
  }

  if ('children' in node && depth < 4) {
    const childBindings = node.children.map(c => auditBindings(c, depth + 1)).filter(c => c.bindings || c.exposedProps || c.children);
    if (childBindings.length) result.children = childBindings;
  }

  return result;
}

return auditBindings(comp);
```

---

## SVG to Component

```js
// Convert SVG string to a scaled component
async function svgToComponent(name, svgString, targetSize = 32, viewBoxSize = 256) {
  const scale = targetSize / viewBoxSize;
  const BLACK = [{ type: 'SOLID', color: { r: 0, g: 0, b: 0 }, opacity: 1 }];

  const svgNode = figma.createNodeFromSvg(svgString);

  const comp = figma.createComponent();
  comp.name = 'Type=' + name;
  comp.resize(targetSize, targetSize);
  comp.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 }, opacity: 1 }];
  comp.clipsContent = true;

  // Invisible bounding box — first child, always transparent
  const bbox = figma.createVector();
  bbox.resize(targetSize, targetSize);
  bbox.x = 0;
  bbox.y = 0;
  bbox.fills = [];
  bbox.strokes = [];
  bbox.strokeWeight = 0.125;
  comp.appendChild(bbox);

  // Scale and move SVG children
  for (const child of [...svgNode.children]) {
    comp.appendChild(child);
    child.x = child.x * scale;
    child.y = child.y * scale;
    child.resize(
      Math.max(child.width * scale, 0.5),
      Math.max(child.height * scale, 0.5)
    );
    if (child.strokes?.length > 0) {
      child.strokes = BLACK;
      child.strokeWeight = 2;
      child.fills = [];
    } else if (child.fills?.length > 0) {
      child.fills = BLACK;
    }
  }

  svgNode.remove();
  comp.x = -99999;
  comp.y = -99999; // park off-canvas until merged
  return comp;
}
```

---

## Bulk Property Setting with Error Handling

```js
// Set a property on multiple instances, handling nested properties
const SWAPS = [
  { id: 'INSTANCE_ID', propKey: 'Type', value: 'NewVariant' },
];
const results = [];
for (const swap of SWAPS) {
  try {
    const node = await figma.getNodeByIdAsync(swap.id);
    if (!node) { results.push({ id: swap.id, ok: false, reason: 'not found' }); continue; }

    let target = node;
    if (!(swap.propKey in (node.componentProperties || {}))) {
      // Property is on a child instance — find it
      target = node.findOne(n =>
        n.type === 'INSTANCE' && swap.propKey in (n.componentProperties || {})
      );
    }
    if (!target) { results.push({ id: swap.id, ok: false, reason: `no ${swap.propKey} prop` }); continue; }

    target.setProperties({ [swap.propKey]: swap.value });
    results.push({ id: swap.id, ok: true });
  } catch (e) {
    results.push({ id: swap.id, ok: false, reason: e.message?.slice(0, 80) });
  }
}
return { succeeded: results.filter(r => r.ok).length, failed: results.filter(r => !r.ok) };
```

---

## Post-combineAsVariants Cleanup

```js
// Run after any combineAsVariants to catch common issues
const set = await figma.getNodeByIdAsync('NEW_SET_ID');

// Check duplicate variant names
const names = set.children.map(c => c.name);
const duplicates = names.filter((n, i) => names.indexOf(n) !== i);

// Check clipsContent consistency
const clipsValues = [...new Set(set.children.map(c => c.clipsContent))];

// Check first-child bounding box vectors
const bboxIssues = [];
for (const variant of set.children) {
  if (variant.children?.[0]?.type === 'VECTOR') {
    const bbox = variant.children[0];
    if (bbox.fills?.length > 0 && bbox.fills.some(f => f.type === 'SOLID' && f.opacity > 0)) {
      bboxIssues.push({ variant: variant.name, issue: 'bounding box has visible fill' });
    }
  }
}

// Resize set to wrap contents
set.layoutSizingHorizontal = "HUG";
set.layoutSizingVertical = "HUG";

return {
  variantCount: set.children.length,
  duplicateNames: duplicates,
  clipsContentConsistent: clipsValues.length === 1,
  clipsContentValues: clipsValues,
  bboxIssues
};
```
