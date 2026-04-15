"""
diff_tokens.py — Diff normalized tokens against the Figma registry.

Compares code-side tokens (from parse_tokens) against the variable values
cached in figma-registry.json. Emits a drift-manifest.yaml with categorized
results: MATCH, DRIFT, NEW (in code, not Figma), ORPHAN (in Figma, not code).

Input:
  --input     normalized-tokens.json (list of token objects)
  --registry  figma-registry.json (project registry with variables map)
  --output    drift-manifest.yaml

Registry variables shape expected:
  {
    "variables": {
      "color":   { "color/brand/primary": "#1a2b3c", ... },
      "spacing": { "spacing/base": "16px", ... },
      "corners": { "corners/corner-base": "12px", ... }
    }
  }

Drift manifest output shape (YAML):
  scanDate: "2026-04-15"
  sourceFile: "src/styles/tokens/primitives.css"
  registryFile: "docs/figma-registry.json"
  summary:
    total: 120
    match: 110
    drift: 5
    new: 3
    orphan: 2
    issues: 2
  drift: [...]
  new: [...]
  orphan: [...]
  issues:
    duplicateValues: [...]
    circularAliases: [...]
    missingSemanticTokens: [...]

CLI:
    python -m figma_primitives diff-tokens --input <normalized.json> --registry <registry.json> --output <manifest.yaml>
"""

import sys
import json
import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path


def _flatten_registry_variables(registry: dict) -> dict:
    """
    Flatten registry.variables into a single figmaName → resolved-value map.
    Handles both the nested {color: {...}, spacing: {...}} shape and
    a flat {figmaName: value} shape.

    Note: entries whose value starts with "VariableID:" are IDs, not resolved
    values — they are skipped. The registry's color/spacing/corners maps should
    contain resolved values (hex strings, px values) for diff to produce results.
    If all values are IDs, the diff will report 0 matches — run figma-drift-scan
    (Phase 3) to populate resolved values from the Figma API.
    """
    variables = registry.get("variables", {})
    flat = {}
    id_count = 0
    for section_or_name, value in variables.items():
        if isinstance(value, dict):
            # Nested: { "color": { "color/brand/primary": "#hex" }, ... }
            for k, v in value.items():
                if isinstance(v, str) and v.startswith("VariableID:"):
                    id_count += 1
                elif isinstance(v, str):
                    flat[k] = v
        else:
            # Already flat: { "color/brand/primary": "#hex" }
            if isinstance(value, str) and value.startswith("VariableID:"):
                id_count += 1
            else:
                flat[section_or_name] = value
    if id_count > 0:
        import sys
        print(
            f"NOTE: Skipped {id_count} VariableID entries in registry — "
            "registry.variables must contain resolved values (hex, px) for diff to work. "
            "Run figma-drift-scan to populate resolved values.",
            file=sys.stderr,
        )
    return flat


def diff(tokens: list, registry: dict, source_file: str = "", registry_file: str = "") -> dict:
    """
    Compare tokens against registry variables.
    Returns a structured drift report dict.
    """
    figma_map = _flatten_registry_variables(registry)
    code_map = {t["figmaName"]: t for t in tokens}

    result = {
        "scanDate": date.today().isoformat(),
        "sourceFile": source_file,
        "registryFile": registry_file,
        "drift": [],
        "new": [],
        "orphan": [],
        "issues": {
            "duplicateValues": [],
            "circularAliases": [],
            "missingSemanticTokens": [],
        },
    }

    # Code → Figma comparison
    matched, drifted = [], []
    for name, token in code_map.items():
        if token.get("isAlias"):
            continue  # aliases are not directly compared; their resolved values are
        if name in figma_map:
            code_val = (token.get("resolvedValue") or token["value"]).lower().strip()
            figma_val = str(figma_map[name]).lower().strip()
            if code_val == figma_val:
                matched.append({"name": name, "value": token["value"]})
            else:
                drifted.append({
                    "name": name,
                    "codeValue": token["value"],
                    "figmaValue": figma_map[name],
                })
        else:
            result["new"].append({
                "name": name,
                "value": token["value"],
                "type": token["type"],
            })

    result["drift"] = drifted

    # Figma → Code orphans (in Figma registry but not in code tokens)
    for name, value in figma_map.items():
        if name not in code_map:
            result["orphan"].append({"name": name, "value": value})

    # --- Issues ---

    # Circular aliases
    circular = [t["figmaName"] for t in tokens if t.get("circularAlias")]
    result["issues"]["circularAliases"] = circular

    # Duplicate resolved values (non-alias COLOR tokens with same hex)
    value_to_names: dict = defaultdict(list)
    for t in tokens:
        if not t.get("isAlias") and t["type"] == "COLOR":
            v = (t.get("resolvedValue") or t["value"]).lower().strip()
            value_to_names[v].append(t["figmaName"])
    for val, names in value_to_names.items():
        if len(names) > 1:
            result["issues"]["duplicateValues"].append({"value": val, "names": names})

    # Missing semantic tokens: primitive tokens with no alias pointing at them
    referenced_by_aliases = {t["aliasTarget"] for t in tokens
                              if t.get("isAlias") and t.get("aliasTarget")}
    for t in tokens:
        if not t.get("isAlias") and t["figmaName"] not in referenced_by_aliases:
            # Top-level name with no slash = un-aliased primitive
            if "/" not in t["figmaName"]:
                result["issues"]["missingSemanticTokens"].append(t["figmaName"])

    # Summary
    issue_count = (
        len(result["issues"]["duplicateValues"])
        + len(result["issues"]["circularAliases"])
        + len(result["issues"]["missingSemanticTokens"])
    )
    result["summary"] = {
        "total": len(tokens),
        "match": len(matched),
        "drift": len(drifted),
        "new": len(result["new"]),
        "orphan": len(result["orphan"]),
        "issues": issue_count,
    }

    return result


def _to_yaml(obj, indent=0) -> str:
    """Minimal YAML serializer — no external deps, covers our output shape."""
    pad = "  " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_to_yaml(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")
        return "\n".join(lines)
    elif isinstance(obj, list):
        if not obj:
            return f"{pad}[]"
        lines = []
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(v, (dict, list)):
                        lines.append(f"{prefix}{k}:")
                        lines.append(_to_yaml(v, indent + 2))
                    else:
                        lines.append(f"{prefix}{k}: {_scalar(v)}")
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return "\n".join(lines)
    else:
        return f"{pad}{_scalar(obj)}"


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    # Quote strings that need it
    s = str(v)
    if any(c in s for c in (':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`')):
        return f'"{s}"'
    return s


def render_yaml(report: dict) -> str:
    """Render the drift report as YAML."""
    return _to_yaml(report) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Diff normalized tokens against Figma registry → drift-manifest.yaml",
        prog="figma_primitives diff-tokens",
    )
    parser.add_argument("--input", required=True, help="normalized-tokens.json")
    parser.add_argument("--registry", required=True, help="figma-registry.json")
    parser.add_argument("--output", required=True, help="Output drift-manifest.yaml path")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        tokens = json.load(f)
    with open(args.registry) as f:
        registry = json.load(f)

    report = diff(tokens, registry, source_file=args.input, registry_file=args.registry)
    s = report["summary"]
    print(
        f"Diff: {s['match']} match, {s['drift']} drift, "
        f"{s['new']} new, {s['orphan']} orphan, {s['issues']} issues",
        file=sys.stderr,
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(render_yaml(report))
    print(f"Wrote: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
