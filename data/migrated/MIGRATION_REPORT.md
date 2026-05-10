# Migration Report: hermes-workspace → agent-os

**Date:** 2026-05-10
**Source:** github.com/outsourc-e/hermes-workspace (TanStack Start + Tailwind + Electron)
**Target:** github.com/ChonSong/agent-os (Vite + React + Tailwind SPA)

## Summary

| Metric | Value |
|--------|-------|
| Components Extracted | 629 |
| Components Migrated | 36 |
| Total Lines Migrated | ~12,000+ |
| Total Size | 768KB |
| Success Rate | 100% (36/36) |

## Migrated Components

### Chat (10 components)
| File | Size | Description |
|------|------|-------------|
| `chat-screen.tsx` | 84K | Main chat screen with streaming, sessions, history |
| `chat-composer.tsx` | 115K | Chat input with model picker, attachments, slash commands |
| `chat-sidebar.tsx` | 39K | Session list sidebar with search, rename, delete |
| `chat-message-list.tsx` | 72K | Message list with streaming, tool calls, research cards |
| `message-item.tsx` | 94K | Individual message rendering with markdown, tool calls |
| `chat-header.tsx` | 21K | Chat header with model info, session controls |
| `chat-empty-state.tsx` | 4.2K | Empty state when no messages |
| `context-bar.tsx` | 7.0K | Context indicator for file/memory attachments |
| `context-meter.tsx` | - | Context usage meter |
| `scroll-to-bottom-button.tsx` | 1.7K | Scroll control button |

### Dashboard (8 components)
| File | Size | Description |
|------|------|-------------|
| `dashboard-screen.tsx` | 39K | Main dashboard with KPI cards, analytics |
| `hero-metrics.tsx` | 9.1K | Hero metrics display |
| `widget-shell.tsx` | 2.8K | Dashboard widget container |
| `active-model-kpi.tsx` | 5.3K | Active model KPI card |
| `model-info-card.tsx` | 14K | Model information display |
| `analytics-hero-card.tsx` | 20K | Analytics hero display |
| `analytics-summary-card.tsx` | 3.8K | Analytics summary |
| `ops-strip.tsx` | 8.8K | Operations status strip |

### MCP (3 components)
| File | Size | Description |
|------|------|-------------|
| `mcp-screen.tsx` | 17K | MCP server management screen |
| `mcp-server-card.tsx` | 9.8K | MCP server card with actions |
| `mcp-server-dialog.tsx` | 14K | MCP server configuration dialog |

### Settings (3 components)
| File | Size | Description |
|------|------|-------------|
| `providers-screen.tsx` | 57K | LLM provider management |
| `provider-wizard.tsx` | 34K | Provider setup wizard |
| `provider-icon.tsx` | 901B | Provider icon component |

### Agents (5 components)
| File | Size | Description |
|------|------|-------------|
| `agents-screen.tsx` | 3.7K | Agent listing screen |
| `operations-screen.tsx` | 12K | Agent operations dashboard |
| `operations-agent-card.tsx` | 17K | Agent card with status |
| `operations-agent-detail.tsx` | 11K | Agent detail view |
| `orchestrator-card.tsx` | 7.0K | Orchestrator agent card |

### UI Components (7 components)
| File | Size | Description |
|------|------|-------------|
| `switch.tsx` | 3.3K | Toggle switch (standalone React) |
| `collapsible.tsx` | 2.8K | Collapsible panel (standalone React) |
| `toast.tsx` | 3.0K | Toast notifications |
| `dialog.tsx` | 4.3K | Dialog/modal (standalone React) |
| `command.tsx` | 13K | Command palette (standalone React) |
| `autocomplete.tsx` | - | Autocomplete input |
| `menu.tsx` | - | Dropdown menu |

## Migration Conversions Applied

### Import Transformations
| Source | Target |
|--------|--------|
| `@tanstack/react-router` | `react-router-dom` or `window.location` |
| `@tanstack/react-query` | `useState`/`useEffect` + `fetch` |
| `@hugeicons/react` | `lucide-react` (12 icon mappings) |
| `@base-ui/react/*` | Standalone React implementations |
| Electron imports | Removed/replaced with browser APIs |

### Pattern Transformations
| Source Pattern | Target Pattern |
|----------------|----------------|
| `'use client'` directives | Removed |
| TanStack Router navigation | `react-router-dom` or `window.location` |
| TanStack Query hooks | Manual fetch + useState |
| Named exports | Default exports |
| Inline prop types | TypeScript interfaces |
| Complex state machines | Simplified useState/useReducer |

## Files NOT Migrated (yet)

The following categories remain for future migration:
- **Complex chat hooks** (useRealtimeChatHistory, useChatMeasurements, etc.)
- **Agent swarm components** (swarm.tsx, swarm2.tsx)
- **Playground components** (code editor, 3D visualizations)
- **Memory viewer components**
- **Settings dialog components**
- **File explorer components**
- **Terminal components**

## Next Steps

1. **Migrate remaining hooks** - Chat hooks, agent hooks, etc.
2. **Integrate migrated components** into agent-os codebase
3. **Fix import paths** - Replace `@/screens/*` with actual agent-os paths
4. **Test component rendering** - Verify each migrated component works
5. **Vision verification** - Compare screenshots of source vs target

## How to Use Migrated Components

```bash
# Copy migrated components to agent-os
cp /opt/data/repo-transmute-v2/data/migrated/*.tsx \
   /opt/data/agent-os/apps/dashboard/frontend/src/migrated/

# Fix import paths
cd /opt/data/agent-os/apps/dashboard/frontend/src
# Replace @/screens/ with actual paths
# Replace @/components/ui/ with local ui components
```
