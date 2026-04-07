# Tool Selection Decision Tree

```mermaid
flowchart TD
    START[Figma operation needed] --> TYPE{What type?}

    TYPE -->|Write| W_DEFAULT[use_figma — remote MCP]
    TYPE -->|Read| R_WHAT{What do you need?}
    TYPE -->|Screenshot| S_AFTER{After which write tool?}
    TYPE -->|Create instance| INST[figma_instantiate_component]
    TYPE -->|FigJam diagram| FIGJAM[generate_diagram]

    W_DEFAULT --> W_WORKS{Did it work?}
    W_WORKS -->|Yes| DONE[Done]
    W_WORKS -->|Silent failure| W_ESC{Known edge case?}
    W_ESC -->|Slot ghost nodes| BRIDGE[figma_execute — Desktop Bridge]
    W_ESC -->|Other| W_RETRY[Retry use_figma once]
    W_RETRY --> W_RETRY_OK{Success?}
    W_RETRY_OK -->|Yes| DONE
    W_RETRY_OK -->|No| BRIDGE

    BRIDGE --> B_PRE[figma_reconnect first]
    B_PRE --> B_EXEC[figma_execute]
    B_EXEC --> DONE

    R_WHAT -->|Find components/tokens| SEARCH[search_design_system]
    R_WHAT -->|Visual specs + code| CONTEXT[get_design_context]
    R_WHAT -->|Token definitions| VARS[get_variable_defs]
    R_WHAT -->|Page/section structure| META[get_metadata]
    R_WHAT -->|Visual snapshot| SCREENSHOT[get_screenshot]
    R_WHAT -->|DS overview| SUMMARY[figma_get_design_system_summary]

    S_AFTER -->|use_figma| S_REST[get_screenshot — REST API]
    S_AFTER -->|figma_execute| S_PLUGIN[figma_capture_screenshot — plugin runtime]

    INST --> INST_TYPE{Library or local?}
    INST_TYPE -->|Library| INST_LIB[componentKey only]
    INST_TYPE -->|Local| INST_LOCAL[componentKey + nodeId]
    INST_LIB --> INST_RULE[Use VARIANT key, never COMPONENT_SET key]
    INST_LOCAL --> INST_RULE
```

## Quick Reference

| I want to... | Use this tool |
|---|---|
| Create/edit nodes, components, variants | `use_figma` |
| Fix slot ghost nodes on existing instances | `figma_execute` |
| Find existing components before building | `search_design_system` |
| Get visual specs for a frame | `get_design_context` |
| Get token/variable values | `get_variable_defs` |
| Understand file structure | `get_metadata` |
| Verify visual result after remote write | `get_screenshot` |
| Verify visual result after desktop write | `figma_capture_screenshot` |
| Create a component instance | `figma_instantiate_component` |
| Create a FigJam diagram | `generate_diagram` |
| Check what user selected | `figma_get_selection` |
| Get lightweight DS overview | `figma_get_design_system_summary` |
