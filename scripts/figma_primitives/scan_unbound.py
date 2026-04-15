"""
scan_unbound.py — Find unbound fills, strokes, and corner radii in a Figma export.

Takes a Figma node export (JSON from figma_execute or the Figma REST API)
and produces a structured report of all property values that are not bound
to a design variable. The report is the input for the figma-bind-variables
Phase 3 triage step.

Input shapes accepted:
  1. figma_execute result: { "result": [ <node>, ... ] }   (Desktop Bridge response)
  2. Figma REST /files nodes response: { "nodes": { "<nodeId>": { "document": <node> } } }
  3. Bare node tree: { "id": "...", "type": "...", "children": [...] }
  4. List of nodes: [ <node>, ... ]

Output (unbound-report.json):
  {
    "scanDate": "2026-04-15",
    "sourceFile": "<input path>",
    "summary": {
      "nodesScanned": 1200,
      "unboundFills": 45,
      "unboundStrokes": 12,
      "unboundCorners": 8
    },
    "unboundFills": [
      {
        "nodeId": "123:456",
        "nodeName": "Button/Primary",
        "nodeType": "FRAME",
        "fillIndex": 0,
        "hex": "1a2b3c",
        "opacity": 1.0
      }, ...
    ],
    "unboundStrokes": [ ... ],
    "unboundCorners": [
      {
        "nodeId": "123:456",
        "nodeName": "Button/Primary",
        "nodeType": "FRAME",
        "cornerRadius": 12
      }, ...
    ]
  }

CLI:
    python -m figma_primitives scan-unbound --input <figma-export.json> --output <unbound-report.json>
"""

import sys
import json
import argparse
from datetime import date
from pathlib import Path


def _to_hex(color: dict) -> str:
    """Convert Figma RGBA dict to 6-char hex string (no #)."""
    r = round(color.get("r", 0) * 255)
    g = round(color.get("g", 0) * 255)
    b = round(color.get("b", 0) * 255)
    return f"{r:02x}{g:02x}{b:02x}"


def _is_masked_white(fill: dict) -> bool:
    """True if fill is effectively transparent white (common no-op fill)."""
    c = fill.get("color", {})
    opacity = fill.get("opacity", 1.0)
    return (
        c.get("r", 0) > 0.99
        and c.get("g", 0) > 0.99
        and c.get("b", 0) > 0.99
        and opacity < 0.01
    )


SURFACE_TYPES = {"FRAME", "RECTANGLE", "ELLIPSE", "COMPONENT", "COMPONENT_SET", "INSTANCE"}
IGNORE_NODE_ID_SUFFIX = ";"  # library component separator in some exports


def _scan_node(node: dict, report: dict):
    """Recursively scan a node tree, mutating report in-place."""
    node_id = node.get("id", "")
    node_name = node.get("name", "")
    node_type = node.get("type", "")

    if IGNORE_NODE_ID_SUFFIX in node_id:
        return  # skip nested library instances

    report["summary"]["nodesScanned"] += 1
    bound_vars = node.get("boundVariables", {})

    # --- Fills ---
    if node_type == "TEXT" or node_type in SURFACE_TYPES:
        fills = node.get("fills", [])
        if fills and fills != "MIXED":
            for i, fill in enumerate(fills):
                if fill.get("type") != "SOLID":
                    continue
                if fill.get("visible") is False:
                    continue
                # Check if already bound
                bound_fills = bound_vars.get("fills", [])
                already_bound = False
                if isinstance(bound_fills, list) and i < len(bound_fills):
                    already_bound = bool(bound_fills[i])
                elif isinstance(bound_fills, dict) and str(i) in bound_fills:
                    already_bound = bool(bound_fills[str(i)])
                if already_bound:
                    continue

                if _is_masked_white(fill):
                    continue

                hex_val = _to_hex(fill.get("color", {}))
                report["unboundFills"].append({
                    "nodeId": node_id,
                    "nodeName": node_name,
                    "nodeType": node_type,
                    "fillIndex": i,
                    "hex": hex_val,
                    "opacity": fill.get("opacity", 1.0),
                })
                report["summary"]["unboundFills"] += 1

    # --- Strokes ---
    if "strokes" in node:
        strokes = node.get("strokes", [])
        if strokes and strokes != "MIXED":
            for i, stroke in enumerate(strokes):
                if stroke.get("type") != "SOLID":
                    continue
                bound_strokes = bound_vars.get("strokes", [])
                already_bound = False
                if isinstance(bound_strokes, list) and i < len(bound_strokes):
                    already_bound = bool(bound_strokes[i])
                elif isinstance(bound_strokes, dict) and str(i) in bound_strokes:
                    already_bound = bool(bound_strokes[str(i)])
                if already_bound:
                    continue

                hex_val = _to_hex(stroke.get("color", {}))
                report["unboundStrokes"].append({
                    "nodeId": node_id,
                    "nodeName": node_name,
                    "nodeType": node_type,
                    "strokeIndex": i,
                    "hex": hex_val,
                    "opacity": stroke.get("opacity", 1.0),
                })
                report["summary"]["unboundStrokes"] += 1

    # --- Corner radius ---
    if "cornerRadius" in node and node_type in SURFACE_TYPES:
        cr = node.get("cornerRadius")
        if cr and cr != "MIXED" and isinstance(cr, (int, float)) and cr > 0:
            if not bound_vars.get("cornerRadius"):
                report["unboundCorners"].append({
                    "nodeId": node_id,
                    "nodeName": node_name,
                    "nodeType": node_type,
                    "cornerRadius": cr,
                })
                report["summary"]["unboundCorners"] += 1

    # Recurse
    for child in node.get("children", []):
        _scan_node(child, report)


def _extract_root_nodes(data: dict | list) -> list:
    """Normalize various Figma export shapes into a list of root nodes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # figma_execute result: { "result": [...] }
        if "result" in data:
            r = data["result"]
            return r if isinstance(r, list) else [r]
        # REST API nodes response: { "nodes": { "<id>": { "document": <node> } } }
        if "nodes" in data:
            return [v["document"] for v in data["nodes"].values() if "document" in v]
        # Bare node with children
        if "id" in data and "type" in data:
            return [data]
    return []


def scan(data: dict | list, source_file: str = "") -> dict:
    """Scan a Figma node export and return an unbound-report dict."""
    report = {
        "scanDate": date.today().isoformat(),
        "sourceFile": source_file,
        "summary": {
            "nodesScanned": 0,
            "unboundFills": 0,
            "unboundStrokes": 0,
            "unboundCorners": 0,
        },
        "unboundFills": [],
        "unboundStrokes": [],
        "unboundCorners": [],
    }

    roots = _extract_root_nodes(data)
    for root in roots:
        _scan_node(root, report)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan Figma export for unbound fills, strokes, and corner radii",
        prog="figma_primitives scan-unbound",
    )
    parser.add_argument("--input", required=True, help="Figma export JSON")
    parser.add_argument("--output", required=True, help="Output unbound-report.json")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        data = json.load(f)

    report = scan(data, source_file=args.input)
    s = report["summary"]
    print(
        f"Scanned {s['nodesScanned']} nodes: "
        f"{s['unboundFills']} unbound fills, "
        f"{s['unboundStrokes']} unbound strokes, "
        f"{s['unboundCorners']} unbound corners",
        file=sys.stderr,
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
