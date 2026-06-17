/**
 * server/index.ts — Express server for LLM Wiki web viewer.
 *
 * Renders wiki markdown pages with:
 * - Wikilink resolution ([[Page]] → clickable links)
 * - Mermaid diagrams (rendered client-side)
 * - KaTeX math formulas (rendered server-side)
 * - Audit feedback submission (POST /api/audit)
 *
 * Binds to 127.0.0.1 only. No auth; intended for personal use.
 */

import express from "express";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
// @ts-ignore
import MarkdownIt from "markdown-it";
import katex from "katex";
import {
  computeAnchor,
  makeId,
  filenameFor,
  toMarkdown,
  fromMarkdown,
} from "audit-shared";

// Parse command line arguments
let wikiRoot = "";
let port = 4175;

for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === "--wiki" && i + 1 < process.argv.length) {
    wikiRoot = process.argv[i + 1];
    i++;
  } else if (process.argv[i] === "--port" && i + 1 < process.argv.length) {
    port = parseInt(process.argv[i + 1], 10);
    i++;
  }
}

if (!wikiRoot) {
  console.error("Error: --wiki argument is required.");
  process.exit(1);
}

// Ensure wikiRoot is absolute
wikiRoot = path.resolve(wikiRoot);
const wikiDir = path.join(wikiRoot, "wiki");
const auditDir = path.join(wikiRoot, "audit");

console.log(`Starting LLM Wiki Web Viewer...`);
console.log(`Wiki Root: ${wikiRoot}`);
console.log(`Pages Directory: ${wikiDir}`);
console.log(`Audits Directory: ${auditDir}`);

// Ensure directories exist
if (!fs.existsSync(wikiDir)) {
  fs.mkdirSync(wikiDir, { recursive: true });
}
if (!fs.existsSync(auditDir)) {
  fs.mkdirSync(auditDir, { recursive: true });
}

const app = express();
app.use(express.json());

// Setup static directories
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const clientDir = path.resolve(__dirname, "../client");
app.use(express.static(clientDir));

// Markdown rendering engine setup (html: true to allow raw KaTeX HTML output)
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
});

/**
 * Traversal sanitation helper.
 * Resolves a path relative to a base directory, and ensures it stays strictly within the boundary.
 */
function sanitizePath(baseDir: string, relativePath: string): string | null {
  if (!relativePath) return null;
  const resolvedBase = path.resolve(baseDir);
  const resolvedTarget = path.resolve(resolvedBase, relativePath);
  // Ensure strict boundary checking using the trailing separator
  const prefix = resolvedBase.endsWith(path.sep) ? resolvedBase : resolvedBase + path.sep;
  if (!resolvedTarget.startsWith(prefix) && resolvedTarget !== resolvedBase) {
    return null;
  }
  return resolvedTarget;
}

/**
 * Utility to extract matching selections in the raw markdown file.
 */
function findSelectionInMarkdown(
  markdownText: string,
  selectedText: string,
  contextBefore: string,
  contextAfter: string
): { selStart: number; selEnd: number } {
  if (!selectedText) {
    return { selStart: 0, selEnd: 0 };
  }

  const occurrences: number[] = [];
  let pos = markdownText.indexOf(selectedText);
  while (pos !== -1) {
    occurrences.push(pos);
    pos = markdownText.indexOf(selectedText, pos + 1);
  }

  if (occurrences.length === 1) {
    return { selStart: occurrences[0], selEnd: occurrences[0] + selectedText.length };
  }

  if (occurrences.length > 1) {
    let bestStart = occurrences[0];
    let bestScore = -1;
    for (const start of occurrences) {
      const end = start + selectedText.length;
      
      const mdBefore = markdownText.slice(Math.max(0, start - 100), start);
      const mdAfter = markdownText.slice(end, Math.min(markdownText.length, end + 100));

      const scoreBefore = commonPrefixLength(
        mdBefore.split("").reverse().join(""),
        contextBefore.split("").reverse().join("")
      );
      const scoreAfter = commonPrefixLength(mdAfter, contextAfter);
      const score = scoreBefore + scoreAfter;

      if (score > bestScore) {
        bestScore = score;
        bestStart = start;
      }
    }
    return { selStart: bestStart, selEnd: bestStart + selectedText.length };
  }

  return { selStart: 0, selEnd: Math.min(markdownText.length, selectedText.length) };
}

function commonPrefixLength(a: string, b: string): number {
  let len = 0;
  const minLen = Math.min(a.length, b.length);
  for (let i = 0; i < minLen; i++) {
    if (a[i].toLowerCase() === b[i].toLowerCase()) {
      len++;
    } else {
      break;
    }
  }
  return len;
}

/**
 * Pre-processes wiki markdown and renders inline/block KaTeX to static HTML.
 */
function renderMath(text: string): string {
  // 1. Block math: $$ ... $$
  let processed = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false });
    } catch (e) {
      return `<span class="katex-error">${formula}</span>`;
    }
  });

  // 2. Inline math: $ ... $
  processed = processed.replace(/\$([^\$\n]+?)\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false });
    } catch (e) {
      return `<span class="katex-error">${formula}</span>`;
    }
  });

  return processed;
}

/**
 * Replaces Obsidian [[Wikilinks]] with custom anchor tags targeting our SPA loader.
 */
function resolveWikiLinks(markdown: string): string {
  return markdown.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (match, target, label) => {
    const cleanTarget = target.trim();
    const cleanLabel = label ? label.trim() : cleanTarget.split("/").pop();
    
    let pagePath = cleanTarget;
    if (!pagePath.endsWith(".md")) {
      pagePath += ".md";
    }
    if (!pagePath.startsWith("wiki/")) {
      pagePath = "wiki/" + pagePath;
    }
    return `<a class="wiki-link" href="#" data-page="${pagePath}">${cleanLabel}</a>`;
  });
}

/**
 * Recursive directory scanner for build index navigation.
 */
async function scanWikiDir(dir: string, baseDir: string): Promise<any[]> {
  const entries = await fs.promises.readdir(dir, { withFileTypes: true });
  const results: any[] = [];
  
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name.startsWith(".")) continue;
      const subPages = await scanWikiDir(fullPath, baseDir);
      results.push(...subPages);
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      const relPath = path.relative(baseDir, fullPath);
      const content = await fs.promises.readFile(fullPath, "utf-8");
      
      let title = entry.name.replace(/\.md$/, "");
      
      // Try to parse title from frontmatter
      const fmMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
      if (fmMatch) {
        const titleMatch = /^title:\s*(.+)$/m.exec(fmMatch[1]);
        if (titleMatch) {
          title = titleMatch[1].trim().replace(/^['"]|['"]$/g, "");
        }
      }
      
      // Fallback to first H1 heading
      if (title === entry.name.replace(/\.md$/, "")) {
        const h1Match = /^\s*#\s+(.+)$/m.exec(content);
        if (h1Match) {
          title = h1Match[1].trim();
        }
      }
      
      const parts = relPath.split(path.sep);
      const category = parts.length > 1 ? parts[0] : "general";
      
      results.push({
        path: "wiki/" + relPath,
        title,
        category,
      });
    }
  }
  return results;
}

// Serve Client Shell
app.get("/", (req, res) => {
  res.sendFile(path.join(clientDir, "index.html"));
});

// API: List All Wiki Pages for Navigation
app.get("/api/nav", async (req, res) => {
  try {
    const pages = await scanWikiDir(wikiDir, wikiDir);
    res.json({ pages });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// API: Render Page HTML
app.get("/api/page/*", async (req, res) => {
  try {
    let targetRel = (req.params as any)[0];
    if (targetRel.startsWith("wiki/")) {
      targetRel = targetRel.slice(5);
    }
    
    const safePath = sanitizePath(wikiDir, targetRel);
    if (!safePath) {
      return res.status(403).json({ error: "Access denied" });
    }
    
    if (!fs.existsSync(safePath)) {
      return res.status(404).json({ error: `File not found: ${targetRel}` });
    }
    
    const rawMarkdown = await fs.promises.readFile(safePath, "utf-8");
    
    // Strip frontmatter YAML block
    const frontmatterRegex = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;
    const markdownWithoutFm = rawMarkdown.replace(frontmatterRegex, "");
    
    // Render math formulas
    const processedMath = renderMath(markdownWithoutFm);
    
    // Resolve [[Wikilinks]]
    const processedLinks = resolveWikiLinks(processedMath);
    
    // Compile using markdown-it
    const html = md.render(processedLinks);
    
    res.json({ html });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// API: List Open Audits for a Page
app.get("/api/audits/*", async (req, res) => {
  try {
    let targetPage = (req.params as any)[0];
    if (!targetPage.startsWith("wiki/")) {
      targetPage = "wiki/" + targetPage;
    }
    
    const files = await fs.promises.readdir(auditDir);
    const openAudits = [];
    
    for (const file of files) {
      if (!file.endsWith(".md")) continue;
      const safeAuditPath = path.join(auditDir, file);
      const content = await fs.promises.readFile(safeAuditPath, "utf-8");
      try {
        const entry = fromMarkdown(content);
        if (entry.target === targetPage && entry.status === "open") {
          openAudits.push(entry);
        }
      } catch (e) {
        // Skip malformed/invalid audit files
      }
    }
    
    res.json(openAudits);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// API: File a New Audit
app.post("/api/audit", async (req, res) => {
  try {
    const {
      target,
      selectedText,
      contextBefore,
      contextAfter,
      severity,
      author,
      comment,
    } = req.body;
    
    if (!target || !author || !comment) {
      return res.status(400).json({ error: "Missing required parameters" });
    }
    
    let pageRel = target;
    if (pageRel.startsWith("wiki/")) {
      pageRel = pageRel.slice(5);
    }
    
    const safePagePath = sanitizePath(wikiDir, pageRel);
    if (!safePagePath) {
      return res.status(403).json({ error: "Invalid target path" });
    }
    
    if (!fs.existsSync(safePagePath)) {
      return res.status(404).json({ error: "Target page file not found" });
    }
    
    const pageText = await fs.promises.readFile(safePagePath, "utf-8");
    const { selStart, selEnd } = findSelectionInMarkdown(
      pageText,
      selectedText,
      contextBefore,
      contextAfter
    );
    
    const anchor = computeAnchor(pageText, selStart, selEnd);
    const id = makeId();
    
    // Slug based on the first few words of the comment
    const commentFirstLine = comment.split("\n")[0] || "";
    const firstFiveWords = commentFirstLine.trim().split(/\s+/).slice(0, 5).join(" ");
    const slug = firstFiveWords;
    
    const filename = filenameFor(id, slug);
    const safeAuditPath = sanitizePath(auditDir, filename);
    if (!safeAuditPath) {
      return res.status(403).json({ error: "Invalid audit filename" });
    }
    
    const entry = {
      id,
      target: target.startsWith("wiki/") ? target : "wiki/" + target,
      target_lines: anchor.target_lines,
      anchor_before: anchor.anchor_before,
      anchor_text: anchor.anchor_text,
      anchor_after: anchor.anchor_after,
      severity,
      author,
      source: "web-viewer" as const,
      created: new Date().toISOString(),
      status: "open" as const,
      body: `# Comment\n\n${comment.trim()}\n\n# Resolution\n\n<!-- filled in when the audit is processed -->\n`,
    };
    
    const mdContent = toMarkdown(entry);
    await fs.promises.writeFile(safeAuditPath, mdContent, "utf-8");
    
    console.log(`Created new audit file: ${filename}`);
    res.json({ success: true, entry });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Helper to collect all markdown files recursively
async function collectFiles(dir: string, baseDir: string): Promise<string[]> {
  const entries = await fs.promises.readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name.startsWith(".")) continue;
      const sub = await collectFiles(fullPath, baseDir);
      files.push(...sub);
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(fullPath);
    }
  }
  return files;
}

// API: Get full knowledge graph node-link dataset
app.get("/api/graph", async (req, res) => {
  try {
    const files = await collectFiles(wikiDir, wikiDir);
    const lookup: Map<string, string> = new Map();
    
    const nodeMap: Map<string, any> = new Map();
    const parsedFilesData: { id: string; links: string[] }[] = [];

    // First pass: register lookup keys and populate nodes
    for (const f of files) {
      const relPath = path.relative(wikiDir, f).split(path.sep).join("/");
      const id = "wiki/" + relPath;
      const stem = path.basename(f, ".md").toLowerCase();
      const relWithoutExt = relPath.replace(/\.md$/, "").toLowerCase();
      
      lookup.set(stem, id);
      lookup.set(relWithoutExt, id);
      lookup.set(id.toLowerCase(), id);

      const content = await fs.promises.readFile(f, "utf-8");
      
      let title = path.basename(f, ".md");
      const fmMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
      if (fmMatch) {
        const titleMatch = /^title:\s*(.+)$/m.exec(fmMatch[1]);
        if (titleMatch) {
          title = titleMatch[1].trim().replace(/^['"]|['"]$/g, "");
        }
      }
      if (title === path.basename(f, ".md")) {
        const h1Match = /^\s*#\s+(.+)$/m.exec(content);
        if (h1Match) {
          title = h1Match[1].trim();
        }
      }

      const parts = relPath.split("/");
      const group = parts.length > 1 ? parts[0] : "general";

      nodeMap.set(id, {
        id,
        label: title,
        path: id,
        group,
        degree: 0,
        title: title
      });

      // Parse wikilinks
      const links: string[] = [];
      let m;
      const wikilinkRegex = /\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g;
      while ((m = wikilinkRegex.exec(content)) !== null) {
        if (m[1]) {
          links.push(m[1].trim().toLowerCase());
        }
      }
      parsedFilesData.push({ id, links });
    }

    const edges: any[] = [];
    const edgeSet: Set<string> = new Set();

    // Second pass: resolve edges and degrees
    for (const fileData of parsedFilesData) {
      const source = fileData.id;
      for (const linkTarget of fileData.links) {
        const target = lookup.get(linkTarget);
        if (target && target !== source) {
          const edgeKey = `${source}->${target}`;
          const reverseEdgeKey = `${target}->${source}`;
          if (!edgeSet.has(edgeKey) && !edgeSet.has(reverseEdgeKey)) {
            edgeSet.add(edgeKey);
            edges.push({ source, target });
            
            const sourceNode = nodeMap.get(source);
            const targetNode = nodeMap.get(target);
            if (sourceNode) sourceNode.degree++;
            if (targetNode) targetNode.degree++;
          }
        }
      }
    }

    res.json({
      nodes: Array.from(nodeMap.values()),
      edges
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Bind specifically to 127.0.0.1 (local only) for security
app.listen(port, "127.0.0.1", () => {
  console.log(`LLM Wiki Web Viewer is running locally: http://127.0.0.1:${port}`);
});
