# Google Stitch MCP Server

Use the Google Stitch MCP server to enable AI agent interaction with your Stitch design projects. This allows the agent to fetch design tokens, typography, colors, and layout rules directly from your designs to ensure code implementations are "pixel-perfect" and consistent with your design system.

### Why MCP for Google Stitch?

- **Pixel-Perfect Implementation**: Fetch exact CSS values, tokens, and components from the design.
- **Design System Consistency**: Ensure the agent uses the current "Design DNA" (colors, fonts, spacing).
- **Automated Scaffolding**: Generate React/Next.js components directly from Stitch design definitions.
- **Bidirectional Updates**: Some versions allow the agent to propose design changes back to Stitch.

### Installation

#### 1. Setup (One-time)
Run the initialization wizard to authenticate and select your Google Cloud project:
```bash
npx @_davideast/stitch-mcp init
```
*Requires `gcloud auth login` and `gcloud auth application-default login` first.*

#### 2. Configuration
Add the server to your AI tool's configuration.

| Tool              | Config File                           | Key                    |
|-------------------|---------------------------------------|------------------------|
| Gemini CLI        | `~/.gemini/settings.json`             | `mcpServers`           |
| Claude Code       | `~/.claude.json`                      | `mcpServers`           |
| Cursor            | `~/.cursor/mcp.json`                  | `mcpServers`           |
| VS Code (Copilot) | `.vscode/mcp.json`                    | `servers`              |

**JSON Entry:**
```json
{
  "mcpServers": {
    "stitch": {
      "command": "npx",
      "args": ["-y", "@_davideast/stitch-mcp", "proxy"],
      "env": {
        "GOOGLE_CLOUD_PROJECT": "your-project-id"
      }
    }
  }
}
```

### Usage in BMAD UX Workflow

When running the `bmad-create-ux-design` workflow, you can use the Stitch MCP to:

1. **Import existing designs**: "Fetch the 'Dashboard' project from Stitch and use it as context."
2. **Extract design tokens**: "Analyze the Stitch project and generate a `tailwind.config.js` or `variables.css`."
3. **Verify implementation**: "Compare this implementation with the Stitch design and report deviations."

### Common Commands

- **Fetch project metadata**: `stitch:get_project`
- **List files in project**: `stitch:list_files`
- **Get file content (JSON/DSL)**: `stitch:get_file`
- **Search components**: `stitch:search_components`

### Troubleshooting

Run the doctor command to check your auth and project setup:
```bash
npx @_davideast/stitch-mcp doctor
```

_Source: Google Stitch MCP Documentation_
