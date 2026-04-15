"""
parse_tokens.py — Parse code-side design tokens into normalized-tokens.json.

Supported input formats:
  css             CSS custom properties (:root { --name: value; })
  tailwind        Tailwind config JS (module.exports = { theme: { ... } })
  style-dictionary  Style Dictionary JSON ({ "token": { "value": "#hex", "type": "color" } })
  tokens-studio   Tokens Studio JSON ({ "token": { "$value": "{ref}", "$type": "color" } })

Output shape (one object per token):
  {
    "figmaName": "color/brand/primary",    -- slash-separated, matches Figma variable name
    "cssName":   "--color-brand-primary",  -- original CSS property name (css format only)
    "twKey":     "colors.brand.primary",   -- original Tailwind key (tailwind format only)
    "sdPath":    "brand.primary",          -- original SD path (style-dictionary format only)
    "type":      "COLOR" | "FLOAT" | "STRING",
    "value":     "#1a2b3c",               -- normalized value
    "isAlias":   false,
    "aliasTarget": null,                  -- figmaName of aliased token, or null
    "description": ""                     -- from SD/TS only
  }

CLI:
    python -m figma_primitives parse-tokens --input <file> [--format css|tailwind|style-dictionary|tokens-studio] --output <file>
"""

import sys
import re
import json
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# CSS → Figma name mapping
# ---------------------------------------------------------------------------

PREFIX_MAP = {
    "--color-":           "color/",
    "--colours-":         "color/",
    "--spacing-":         "spacing/",
    "--space-":           "spacing/",
    "--size-":            "size/",
    "--font-family-":     "font/family/",
    "--font-size-":       "font/size/",
    "--font-weight-":     "font/weight/",
    "--line-height-":     "font/line-height/",
    "--letter-spacing-":  "font/letter-spacing/",
    "--radius-":          "radius/",
    "--border-radius-":   "radius/",
    "--corner-":          "corners/",
    "--shadow-":          "shadow/",
    "--opacity-":         "opacity/",
    "--z-":               "z-index/",
    "--duration-":        "motion/duration/",
    "--ease-":            "motion/easing/",
}

TAILWIND_CATEGORY_MAP = {
    "colors":                    "color",
    "spacing":                   "spacing",
    "fontSize":                  "font/size",
    "fontFamily":                "font/family",
    "fontWeight":                "font/weight",
    "lineHeight":                "font/line-height",
    "letterSpacing":             "font/letter-spacing",
    "borderRadius":              "radius",
    "boxShadow":                 "shadow",
    "opacity":                   "opacity",
    "zIndex":                    "z-index",
    "transitionDuration":        "motion/duration",
    "transitionTimingFunction":  "motion/easing",
}


def css_to_figma_name(css_name: str) -> str:
    """Convert --color-brand-primary → color/brand/primary."""
    for prefix, replacement in PREFIX_MAP.items():
        if css_name.startswith(prefix):
            rest = css_name[len(prefix):]
            return replacement + rest.replace("-", "/")
    return css_name.lstrip("-").replace("-", "/")


def tailwind_key_to_figma_name(category: str, key_path: list) -> str:
    """Convert tailwind {colors: {brand: {primary: #hex}}} → color/brand/primary."""
    base = TAILWIND_CATEGORY_MAP.get(category, category.lower())
    parts = [p for p in key_path if p != "DEFAULT"]
    return (base + "/" + "/".join(parts)) if parts else base


def infer_type(figma_name: str, value: str) -> str:
    """Infer token type from Figma name and raw value."""
    n = figma_name.lower()
    if n.startswith(("color/", "colour/")):
        return "COLOR"
    if n.startswith(("spacing/", "size/", "font/size/", "radius/", "corners/",
                      "opacity/", "z-index/", "font/weight/",
                      "font/line-height/", "font/letter-spacing/")):
        return "FLOAT"
    if n.startswith(("font/family/", "shadow/", "motion/")):
        return "STRING"
    if re.match(r"^#[0-9a-fA-F]{3,8}$", value) or re.match(r"^rgba?", value):
        return "COLOR"
    if re.match(r"^\d+(\.\d+)?(px|rem|em|%)?$", value):
        return "FLOAT"
    return "STRING"


def normalize_value(value: str, token_type: str) -> str:
    """Normalize value: rem→px for FLOAT, lowercase hex for COLOR."""
    value = value.strip()
    if token_type == "COLOR":
        return value.lower()
    if token_type == "FLOAT":
        rem_match = re.match(r"^([\d.]+)rem$", value)
        if rem_match:
            px = float(rem_match.group(1)) * 16
            return f"{px:.2f}px"
    return value


# ---------------------------------------------------------------------------
# Format parsers
# ---------------------------------------------------------------------------

def parse_css(content: str) -> list:
    """Parse CSS custom properties from :root {} blocks (and bare declarations)."""
    root_blocks = re.findall(r":root\s*\{([^}]+)\}", content, re.DOTALL)
    body = "\n".join(root_blocks) if root_blocks else content

    tokens = []
    for match in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", body):
        css_name = match.group(1).strip()
        raw_value = match.group(2).strip()
        figma_name = css_to_figma_name(css_name)
        token_type = infer_type(figma_name, raw_value)

        is_alias = raw_value.startswith("var(")
        alias_target = None
        if is_alias:
            alias_match = re.match(r"var\((--[\w-]+)", raw_value)
            if alias_match:
                alias_target = css_to_figma_name(alias_match.group(1))

        tokens.append({
            "cssName": css_name,
            "figmaName": figma_name,
            "type": token_type,
            "value": normalize_value(raw_value, token_type),
            "isAlias": is_alias,
            "aliasTarget": alias_target,
            "description": "",
        })

    return tokens


def parse_tailwind(content: str) -> list:
    """Parse Tailwind config JS (best-effort; recommend pre-extracting JSON)."""
    tokens = []

    # Try to find JSON-ified theme object
    json_match = re.search(r"theme\s*:\s*(\{.+\})\s*[,}]", content, re.DOTALL)
    if not json_match:
        print(
            "WARNING: Could not extract theme object from Tailwind config.\n"
            "Consider pre-extracting with:\n"
            "  node -e \"console.log(JSON.stringify(require('./tailwind.config.js').theme))\" > /tmp/tw-theme.json",
            file=sys.stderr,
        )
        return tokens

    raw = json_match.group(1)
    raw = re.sub(r"//[^\n]*", "", raw)
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"(\w+):", r'"\1":', raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)

    try:
        theme = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse Tailwind config as JSON: {e}\n"
              "Pass a pre-extracted JSON theme file instead.", file=sys.stderr)
        return tokens

    def flatten(obj, category, key_path):
        for k, v in obj.items():
            if k in ("extend", "DEFAULT") and isinstance(v, dict):
                flatten(v, category, key_path)
            elif isinstance(v, dict):
                flatten(v, category, key_path + [k])
            elif isinstance(v, str):
                figma_name = tailwind_key_to_figma_name(category, key_path + [k])
                token_type = infer_type(figma_name, v)
                tokens.append({
                    "twKey": ".".join([category] + key_path + [k]),
                    "figmaName": figma_name,
                    "type": token_type,
                    "value": normalize_value(v, token_type),
                    "isAlias": False,
                    "aliasTarget": None,
                    "description": "",
                })

    for category, values in theme.items():
        if isinstance(values, dict):
            flatten(values, category, [])

    return tokens


def parse_style_dictionary(content: str) -> list:
    """Parse Style Dictionary JSON: { "token": { "value": "#hex", "type": "color" } }"""
    tokens = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        return tokens

    SD_TYPE_MAP = {
        "color": "COLOR", "dimension": "FLOAT", "number": "FLOAT",
        "string": "STRING", "fontFamily": "STRING", "fontWeight": "FLOAT",
    }

    def flatten(obj, path):
        if isinstance(obj, dict):
            if "value" in obj:
                raw_value = str(obj["value"])
                sd_type = obj.get("type", "")
                token_type = SD_TYPE_MAP.get(sd_type) or infer_type("/".join(path), raw_value)

                is_alias = raw_value.startswith("{") and raw_value.endswith("}")
                alias_target = raw_value[1:-1].replace(".", "/") if is_alias else None

                tokens.append({
                    "sdPath": ".".join(path),
                    "figmaName": "/".join(path),
                    "type": token_type,
                    "value": normalize_value(raw_value, token_type),
                    "isAlias": is_alias,
                    "aliasTarget": alias_target,
                    "description": obj.get("description", ""),
                })
            else:
                for k, v in obj.items():
                    if not k.startswith("$"):  # skip metadata keys
                        flatten(v, path + [k])

    flatten(data, [])
    return tokens


def parse_tokens_studio(content: str) -> list:
    """Parse Tokens Studio JSON: same shape as Style Dictionary but uses $value/$type."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        return []

    tokens = []
    SD_TYPE_MAP = {
        "color": "COLOR", "dimension": "FLOAT", "number": "FLOAT",
        "string": "STRING", "fontFamily": "STRING", "fontWeight": "FLOAT",
        "sizing": "FLOAT", "spacing": "FLOAT", "borderRadius": "FLOAT",
        "opacity": "FLOAT", "fontSizes": "FLOAT",
    }

    def flatten(obj, path):
        if isinstance(obj, dict):
            value_key = "$value" if "$value" in obj else ("value" if "value" in obj else None)
            type_key = "$type" if "$type" in obj else ("type" if "type" in obj else None)
            if value_key:
                raw_value = str(obj[value_key])
                ts_type = obj.get(type_key, "") if type_key else ""
                token_type = SD_TYPE_MAP.get(ts_type) or infer_type("/".join(path), raw_value)

                is_alias = raw_value.startswith("{") and raw_value.endswith("}")
                alias_target = raw_value[1:-1].replace(".", "/") if is_alias else None

                tokens.append({
                    "sdPath": ".".join(path),
                    "figmaName": "/".join(path),
                    "type": token_type,
                    "value": normalize_value(raw_value, token_type),
                    "isAlias": is_alias,
                    "aliasTarget": alias_target,
                    "description": obj.get("$description", obj.get("description", "")),
                })
            else:
                for k, v in obj.items():
                    if not k.startswith("$"):
                        flatten(v, path + [k])

    flatten(data, [])
    return tokens


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def _find_first_dict_leaf(obj):
    """Walk nested dicts to find the first dict leaf (for SD format detection)."""
    if isinstance(obj, dict):
        for v in obj.values():
            result = _find_first_dict_leaf(v)
            if result is not None:
                return result
    return obj if isinstance(obj, dict) else None


def detect_format(content: str, path: str) -> str:
    """Auto-detect token format from file extension and content."""
    if path.endswith(".css"):
        return "css"
    if path.endswith((".js", ".ts", ".mjs")):
        return "tailwind"
    if path.endswith(".json"):
        try:
            data = json.loads(content)
            leaf = _find_first_dict_leaf(data)
            if leaf:
                if "$value" in leaf or "$type" in leaf:
                    return "tokens-studio"
                if "value" in leaf:
                    return "style-dictionary"
        except Exception:
            pass
        return "style-dictionary"
    if "--" in content and ":root" in content:
        return "css"
    return "css"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PARSERS = {
    "css": parse_css,
    "tailwind": parse_tailwind,
    "style-dictionary": parse_style_dictionary,
    "tokens-studio": parse_tokens_studio,
}


def parse(input_path: str, fmt: str | None = None) -> list:
    """Parse a token file and return normalized token list."""
    with open(input_path) as f:
        content = f.read()
    resolved_fmt = fmt or detect_format(content, input_path)
    if resolved_fmt not in PARSERS:
        raise ValueError(f"Unknown format '{resolved_fmt}'. Valid: {list(PARSERS)}")
    return PARSERS[resolved_fmt](content)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Parse design tokens into normalized-tokens.json",
        prog="figma_primitives parse-tokens",
    )
    parser.add_argument("--input", required=True, help="Token file (CSS, JS, JSON)")
    parser.add_argument(
        "--format",
        choices=list(PARSERS),
        default=None,
        help="Force format (default: auto-detect)",
    )
    parser.add_argument("--output", required=True, help="Output path for normalized-tokens.json")
    args = parser.parse_args(argv)

    tokens = parse(args.input, args.format)
    print(f"Parsed {len(tokens)} tokens from {args.input}", file=sys.stderr)

    by_type: dict = {}
    for t in tokens:
        by_type[t["type"]] = by_type.get(t["type"], 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}", file=sys.stderr)
    alias_count = sum(1 for t in tokens if t.get("isAlias"))
    if alias_count:
        print(f"  ({alias_count} aliases)", file=sys.stderr)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(tokens, f, indent=2)
    print(f"Wrote: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
