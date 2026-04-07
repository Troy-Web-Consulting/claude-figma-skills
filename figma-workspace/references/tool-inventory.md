# Figma Tool Inventory

Complete reference of available Figma tools across both MCP servers.

## Write Tools

| Tool | Server | Purpose | Requires Desktop? |
|---|---|---|---|
| `Figma:use_figma` | Remote MCP | General-purpose Plugin API execution. DEFAULT for all writes. | No |
| `figma-console:figma_execute` | Desktop Bridge | Plugin API execution via desktop plugin. Fallback for edge cases. | Yes |

## Read Tools

| Tool | Server | Purpose | Best For |
|---|---|---|---|
| `Figma:search_design_system` | Remote MCP | Search components, variables, styles by query | Finding existing components before creating |
| `Figma:get_design_context` | Remote MCP | Structured layout, component tree, token usage, screenshot | Visual specs for a specific node |
| `Figma:get_variable_defs` | Remote MCP | Variable/token definitions from a node context | Token values for implementation |
| `Figma:get_metadata` | Remote MCP | File/node structure in XML (IDs, positions, sizes) | Understanding page/section structure |
| `Figma:get_screenshot` | Remote MCP | Visual snapshot of a node | Fidelity checks, ground truth |
| `Figma:get_code_connect_map` | Remote MCP | Component → code mappings | Finding existing code implementations |
| `Figma:get_code_connect_suggestions` | Remote MCP | AI-suggested code connect mappings | Setting up new code connections |
| `figma-console:figma_get_selection` | Desktop Bridge | Currently selected node in Figma Desktop | Starting from user's selection |
| `figma-console:figma_get_component` | Desktop Bridge | Deep component inspection | Detailed property/variant analysis |
| `figma-console:figma_get_component_details` | Desktop Bridge | Component details with image | Visual component reference |
| `figma-console:figma_get_styles` | Desktop Bridge | File styles | Style audit |
| `figma-console:figma_get_variables` | Desktop Bridge | File variables | Variable audit |
| `figma-console:figma_browse_tokens` | Desktop Bridge | Browse token values | Token exploration |
| `figma-console:figma_get_token_values` | Desktop Bridge | Specific token values | Targeted token lookup |
| `figma-console:figma_search_components` | Desktop Bridge | Search components by name | Component discovery |
| `figma-console:figma_get_design_system_summary` | Desktop Bridge | Lightweight DS overview | Quick orientation |
| `figma-console:figma_get_file_data` | Desktop Bridge | Full file data | Comprehensive file analysis |

## Screenshot Tools

| Tool | Server | Purpose | When to Use |
|---|---|---|---|
| `Figma:get_screenshot` | Remote MCP | REST API screenshot | After `use_figma` writes (may have brief cache lag) |
| `figma-console:figma_take_screenshot` | Desktop Bridge | REST API screenshot | General verification |
| `figma-console:figma_capture_screenshot` | Desktop Bridge | Plugin runtime screenshot | After `figma_execute` writes (immediate, no lag) |
| `figma-console:figma_get_component_image` | Desktop Bridge | Component image export | Component visual reference |

## Create Tools

| Tool | Server | Purpose |
|---|---|---|
| `Figma:create_new_file` | Remote MCP | Create blank Figma/FigJam file in drafts |
| `figma-console:figma_instantiate_component` | Desktop Bridge | Create component instance |
| `figma-console:figma_create_child` | Desktop Bridge | Create child node |
| `figma-console:figma_clone_node` | Desktop Bridge | Clone existing node |
| `figma-console:figma_create_variable` | Desktop Bridge | Create single variable |
| `figma-console:figma_batch_create_variables` | Desktop Bridge | Create multiple variables |
| `figma-console:figma_create_variable_collection` | Desktop Bridge | Create variable collection |
| `figma-console:figma_setup_design_tokens` | Desktop Bridge | Set up design token system |

## Modify Tools (Desktop Bridge)

| Tool | Purpose |
|---|---|
| `figma_set_text` | Set text content |
| `figma_set_fills` | Set fill colors |
| `figma_set_strokes` | Set stroke styles |
| `figma_move_node` | Move node position |
| `figma_resize_node` | Resize node |
| `figma_rename_node` | Rename node |
| `figma_delete_node` | Delete node |
| `figma_set_instance_properties` | Set instance properties |
| `figma_set_description` | Set node description |
| `figma_update_variable` | Update variable value |
| `figma_batch_update_variables` | Update multiple variables |
| `figma_delete_variable` | Delete variable |
| `figma_arrange_component_set` | Arrange component set layout |

## Navigation & Utility (Desktop Bridge)

| Tool | Purpose |
|---|---|
| `figma_navigate` | Navigate to a node |
| `figma_reconnect` | Reconnect bridge after drops |
| `figma_reload_plugin` | Reload the bridge plugin |
| `figma_get_status` | Check connection status |
| `figma_get_console_logs` | Read plugin console output |
| `figma_clear_console` | Clear plugin console |
| `figma_list_open_files` | List open Figma files |

## Diagram Tool

| Tool | Server | Purpose |
|---|---|---|
| `Figma:generate_diagram` | Remote MCP | Generate diagrams in FigJam (FigJam files only) |

## Code Connect Tools

| Tool | Server | Purpose |
|---|---|---|
| `Figma:get_code_connect_map` | Remote MCP | Get existing component → code mappings |
| `Figma:get_code_connect_suggestions` | Remote MCP | AI-suggested mappings for unmapped components |
| `Figma:send_code_connect_mappings` | Remote MCP | Save approved mappings |
| `Figma:add_code_connect_map` | Remote MCP | Add mapping entries |

## Design System Rules

| Tool | Server | Purpose |
|---|---|---|
| `Figma:create_design_system_rules` | Remote MCP | Generate project-specific design system rules |
