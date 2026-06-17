# web — Local Wiki Preview + Feedback Server

A local Node.js server that renders the LLM Wiki with full support for mermaid
diagrams, KaTeX math, and wikilinks, and lets you file feedback from your browser.

## Purpose

While Obsidian is the primary way to browse the wiki, this web viewer provides:

- **Rendered mermaid diagrams** — client-side rendering without Obsidian plugins
- **Server-side KaTeX** — math formulas rendered consistently
- **Wikilink resolution** — clickable `[[links]]` that navigate between pages
- **Text selection feedback** — select any text → "💬 Add feedback" popover →
  creates an audit file in `audit/` using the same format as the Obsidian plugin
- **Audit sidebar** — shows open feedback items for the current page

## Status

**Scaffold** — The server and client structure are defined. Implementation is
pending. The `audit-shared` library provides schema and serialization.

## Planned Architecture

```
web/
├── server/
│   └── index.ts       ← Express server: markdown rendering, API routes
├── client/
│   ├── index.html     ← SPA shell
│   └── app.ts         ← Client: mermaid rendering, selection popover
└── package.json
```

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve client SPA |
| GET | `/api/pages` | List all wiki pages |
| GET | `/api/page/:path` | Render a page as HTML |
| GET | `/api/audits/:path` | Open audits for a page |
| POST | `/api/audit` | Create new audit file |
| GET | `/api/nav` | Navigation tree |

## Running (once implemented)

```bash
cd audit-shared && npm install && npm run build && cd ..
cd web && npm install && npm run build
npm start -- --wiki "/path/to/wiki-root" --port 4175
# open http://127.0.0.1:4175
```

Binds to `127.0.0.1` only. No auth; intended for personal use on your machine.
