"""
generate_css.py — Generate CSS custom properties from the Figma registry.

Reads figma-registry.json and emits a CSS file with :root declarations
for every variable in the registry's variables map.

Registry variables shape:
  {
    "variables": {
      "color":   { "color/brand/primary": "#1a2b3c", ... },
      "spacing": { "spacing/base": "16px", ... },
      "corners": { "corners/corner-base": "12px", ... }
    }
  }

Figma name → CSS custom property conversion:
  "color/brand/primary"   → --color-brand-primary
  "spacing/base"          → --spacing-base
  "corners/corner-base"   → --corner-base
  "font/size/xl"          → --font-size-xl

Output:
  CSS file with :root { ... } block grouping all variables by category.

CLI:
    python -m figma_primitives generate-css --input <registry.json> --output <file>
"""

import sys
import json
import argparse
from pathlib import Path


def figma_name_to_css(figma_name: str) -> str:
    """
    Convert a Figma variable name to a CSS custom property name.
    Slashes become separators, lower-cased.

    Examples:
      color/brand/primary   → --color-brand-primary
      spacing/base          → --spacing-base
      corners/corner-base   → --corner-base (strip leading category)
      font/size/xl          → --font-size-xl
    """
    parts = figma_name.lower().split("/")

    # "corners/corner-base" → strip the redundant "corner-" prefix on second part
    if len(parts) >= 2 and parts[0] == "corners":
        # corners/Corner-Base → --corner-base (drop "corners/" prefix entirely)
        rest = "-".join(parts[1:])
        rest = rest.replace(" ", "-")
        return f"--corner-{rest.replace('corner-', '', 1)}" if rest.startswith("corner-") else f"--corner-{rest}"

    joined = "-".join(parts).replace(" ", "-")
    return f"--{joined}"


def _flatten_registry_variables(registry: dict) -> dict:
    """Flatten registry.variables into a single figmaName → value map."""
    variables = registry.get("variables", {})
    flat = {}
    for section_or_name, value in variables.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[section_or_name] = value
    return flat


def generate(registry: dict) -> str:
    """Generate a CSS file from registry variables. Returns CSS string."""
    flat = _flatten_registry_variables(registry)

    # Group by top-level category (first path segment)
    categories: dict = {}
    for figma_name, value in flat.items():
        category = figma_name.split("/")[0].lower()
        categories.setdefault(category, []).append((figma_name, value))

    meta = registry.get("meta", {})
    file_key = meta.get("fileKey", "unknown")
    scan_date = meta.get("scanDate", "unknown")

    lines = [
        f"/* Generated from Figma registry — fileKey: {file_key} — scanDate: {scan_date} */",
        "/* Do not edit manually. Re-run: python -m figma_primitives generate-css */",
        "",
        ":root {",
    ]

    for category in sorted(categories):
        entries = sorted(categories[category], key=lambda x: x[0])
        lines.append(f"  /* {category} */")
        for figma_name, value in entries:
            css_name = figma_name_to_css(figma_name)
            lines.append(f"  {css_name}: {value};")
        lines.append("")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate CSS custom properties from figma-registry.json",
        prog="figma_primitives generate-css",
    )
    parser.add_argument("--input", required=True, help="figma-registry.json")
    parser.add_argument("--output", required=True, help="Output CSS file path")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        registry = json.load(f)

    flat = _flatten_registry_variables(registry)
    css = generate(registry)
    print(f"Generated CSS for {len(flat)} variables", file=sys.stderr)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(css)
    print(f"Wrote: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
