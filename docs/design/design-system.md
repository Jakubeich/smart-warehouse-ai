# UI specification — revision 2

The user's review rejected the dense dark dashboard. The active reference is `simulation-concept-v2.png`, generated with the built-in image tool before this redesign. The previous concept is historical context only. The light palette is the implementation choice for the requested cleaner interface.

## Hierarchy

Simulation is one toolbar, one shared map/fleet workspace, three inline run counters and a collapsed details row. The map comes first. Robot/task details use an accessible shadcn Sheet opened by selection. Planner and scheduling configuration belong in a Dialog; layers and obstacle editing use DropdownMenu. Event logs and technical metrics are collapsed initially. Dashboard scenarios are rows rather than decorative cards. Experiment results use Summary / Charts / Individual runs tabs, and advanced run limits are collapsed. Mobile uses a navigation Sheet and shows the map before the fleet.

## Tokens and components

- Color lock: white background `#ffffff`, neutral sidebar/canvas `#fafafa`, zinc text `#18181b`, muted text `#71717a`, border `#e4e4e7`. Indigo `#4f46e5` marks the primary action and focus. Green/red communicate actual state.
- Typography: system sans, 14px body and controls, 12px captions, 26px page headings, 15px panel headings. No uppercase tracking, decorative labels or slogans.
- Geometry: 8px radius for primary panels, 6px controls, one-pixel borders, 24–30px page gutters, 16–20px inner spacing. No gradients or ornamental shadows.
- Components: shadcn/ui Radix Button, Select, Input, Dialog, Sheet, Tabs, DropdownMenu, Collapsible, Badge, Field and Separator. Lucide outline icons. Shared tokens apply to every route.
- Data remains real. The concept's positions/counts are illustrative; rendered coordinates are zero-based and derived exclusively from backend state. Map geometry follows the selected scenario. Map tool and add-task controls remain accessible because the requested workflows require them.

## Concept brief

Full desktop Smart Warehouse simulation screen, light shadcn zinc system, sidebar navigation, concise heading and scenario context, one run toolbar, dominant 2D grid, one robot/task list, summary strip and collapsed run details. No metric-card grid, gradients, slogans or always-visible inspector. Native controls and real simulation data in implementation. Asset generated with the built-in image tool and saved as `simulation-concept-v2.png`.
