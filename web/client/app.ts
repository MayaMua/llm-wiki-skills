/**
 * client/app.ts — Client-side SPA for LLM Wiki web viewer.
 *
 * Renders wiki pages, fetches audits, manages the selection feedback popover,
 * and compiles Mermaid diagrams dynamically.
 */

// Define global interface for Mermaid loaded via CDN
declare const mermaid: any;

import { ParticleField } from "./particles.js";

interface PageInfo {
  path: string;
  title: string;
  category: string;
}

interface AuditEntry {
  id: string;
  target: string;
  target_lines: [number, number];
  anchor_before: string;
  anchor_text: string;
  anchor_after: string;
  severity: "info" | "suggest" | "warn" | "error";
  author: string;
  source: string;
  created: string;
  status: string;
  body: string;
}

// Client Application State
let currentPage = "";
let selectedText = "";
let contextBefore = "";
let contextAfter = "";

// Track D3 simulation instance for clean teardown
let graphSimulation: any = null;
let activeParticles: ParticleField | null = null;

// DOM Elements
const navigationSidebar = document.getElementById("navigation-sidebar")!;
const markdownContainer = document.getElementById("markdown-container")!;
const currentPageHeader = document.getElementById("current-page-header")!;
const auditsContainer = document.getElementById("audits-container")!;
const auditsCountBadge = document.getElementById("audits-count")!;
const selectionPopover = document.getElementById("selection-popover")!;
const feedbackModal = document.getElementById("feedback-modal")!;
const modalQuote = document.getElementById("modal-quote")!;
const feedbackAuthorInput = document.getElementById("feedback-author") as HTMLInputElement;
const feedbackCommentInput = document.getElementById("feedback-comment") as HTMLTextAreaElement;
const modalCloseX = document.getElementById("modal-close-x")!;
const modalCancelBtn = document.getElementById("modal-cancel-btn")!;
const modalSubmitBtn = document.getElementById("modal-submit-btn")!;
const graphViewBtn = document.getElementById("graph-view-btn")!;

// Init App
document.addEventListener("DOMContentLoaded", () => {
  // Pre-fill author from localStorage if available
  const savedAuthor = localStorage.getItem("wiki-author");
  if (savedAuthor) {
    feedbackAuthorInput.value = savedAuthor;
  }

  // Load sidebar navigation
  loadNavigation();

  // Selection change listener to track user selection
  document.addEventListener("selectionchange", handleSelectionChange);
  
  // Selection popover trigger
  selectionPopover.addEventListener("click", openFeedbackModal);

  // Modal dismiss buttons
  modalCloseX.addEventListener("click", closeFeedbackModal);
  modalCancelBtn.addEventListener("click", closeFeedbackModal);
  
  // Submit feedback
  modalSubmitBtn.addEventListener("click", submitFeedback);

  // Knowledge Graph View Trigger
  graphViewBtn.addEventListener("click", loadGraph);

  // Sidebar Collapse Toggles
  const toggleLeftBtn = document.getElementById("toggle-left-btn")!;
  const toggleRightBtn = document.getElementById("toggle-right-btn")!;
  const auditsSidebar = document.getElementById("audits-sidebar")!;

  toggleLeftBtn.addEventListener("click", () => {
    navigationSidebar.classList.toggle("collapsed");
    const arrow = toggleLeftBtn.querySelector(".arrow")!;
    if (arrow) {
      arrow.textContent = navigationSidebar.classList.contains("collapsed") ? "▶" : "◀";
    }
  });

  toggleRightBtn.addEventListener("click", () => {
    auditsSidebar.classList.toggle("collapsed");
    const arrow = toggleRightBtn.querySelector(".arrow")!;
    if (arrow) {
      arrow.textContent = auditsSidebar.classList.contains("collapsed") ? "◀" : "▶";
    }
  });
});

/**
 * Loads the categories and pages navigation tree from the server.
 */
async function loadNavigation() {
  try {
    const res = await fetch("/api/nav");
    if (!res.ok) throw new Error("Failed to load navigation data");
    const data = await res.json();
    const pages: PageInfo[] = data.pages;

    // Group pages by category
    const categories: Record<string, PageInfo[]> = {};
    pages.forEach((page) => {
      if (!categories[page.category]) {
        categories[page.category] = [];
      }
      categories[page.category].push(page);
    });

    // Build sidebar DOM nodes
    navigationSidebar.replaceChildren();

    Object.keys(categories).sort().forEach((catName) => {
      const section = document.createElement("div");
      section.className = "nav-section";

      const title = document.createElement("div");
      title.className = "nav-section-title";
      title.textContent = catName.toUpperCase();
      
      const list = document.createElement("ul");
      list.className = "nav-list";

      // Sort pages within category alphabetically
      categories[catName].sort((a, b) => a.title.localeCompare(b.title)).forEach((page) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.className = "nav-item";
        a.textContent = page.title;
        a.setAttribute("data-path", page.path);
        
        a.addEventListener("click", (e) => {
          e.preventDefault();
          loadPage(page.path);
        });

        li.appendChild(a);
        list.appendChild(li);
      });

      // Expand/Collapse trigger
      title.addEventListener("click", () => {
        section.classList.toggle("collapsed");
      });

      section.appendChild(title);
      section.appendChild(list);
      navigationSidebar.appendChild(section);
    });

    // If there is an index.md page, load it by default
    const indexPath = "wiki/index.md";
    const hasIndex = pages.some(p => p.path === indexPath);
    if (hasIndex) {
      loadPage(indexPath);
    } else if (pages.length > 0) {
      loadPage(pages[0].path);
    }
  } catch (err) {
    console.error("Error loading navigation:", err);
    showErrorMessage(navigationSidebar, "Error loading navigation menu.");
  }
}

/**
 * Loads and renders a single wiki page.
 */
async function loadPage(pagePath: string) {
  currentPage = pagePath;
  hidePopover();
  
  // Stop active D3 graph simulation to prevent CPU leak
  if (graphSimulation) {
    graphSimulation.stop();
    graphSimulation = null;
  }
  if (activeParticles) {
    activeParticles.stop();
    activeParticles = null;
  }
  
  // Highlight active menu item
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach((item) => {
    if (item.getAttribute("data-path") === pagePath) {
      item.classList.add("active");
      
      // Auto expand parent category container if collapsed
      const parentSection = item.closest(".nav-section");
      if (parentSection) {
        parentSection.classList.remove("collapsed");
      }
    } else {
      item.classList.remove("active");
    }
  });

  // Show page loading state
  showLoadingSpinner(markdownContainer);
  currentPageHeader.textContent = pagePath;

  try {
    const res = await fetch(`/api/page/${encodeURIComponent(pagePath)}`);
    if (!res.ok) throw new Error(`Failed to load page: ${pagePath}`);
    const data = await res.json();
    
    // Parse using DOMParser to avoid innerHTML completely (Prevents XSS)
    const parser = new DOMParser();
    const doc = parser.parseFromString(data.html, "text/html");
    
    const markdownBody = document.createElement("div");
    markdownBody.className = "markdown-body";
    
    while (doc.body.firstChild) {
      markdownBody.appendChild(doc.body.firstChild);
    }
    
    markdownContainer.replaceChildren(markdownBody);

    // Intercept rendered page wikilinks for SPA navigation
    const wikiLinks = markdownBody.querySelectorAll("a.wiki-link");
    wikiLinks.forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const targetPage = link.getAttribute("data-page");
        if (targetPage) {
          loadPage(targetPage);
        }
      });
    });

    // Compile Mermaid Diagrams client-side
    renderMermaidDiagrams(markdownBody);
    
    // Fetch audits for this page
    loadAudits(pagePath);
  } catch (err) {
    console.error("Error loading page content:", err);
    showErrorMessage(markdownContainer, "Error loading page contents. Verify the file exists.");
  }
}

/**
 * Render mermaid diagrams in the markdown document securely.
 */
function renderMermaidDiagrams(container: HTMLElement) {
  if (typeof mermaid === "undefined") return;

  try {
    mermaid.initialize({ startOnLoad: false, theme: "dark" });
    const mermaidBlocks = container.querySelectorAll("code.language-mermaid");
    const parser = new DOMParser();

    mermaidBlocks.forEach((block, index) => {
      const code = block.textContent || "";
      const parent = block.parentElement; // pre element
      if (parent && code) {
        const id = `mermaid-diagram-${index}`;
        mermaid.render(id, code).then(({ svg }: { svg: string }) => {
          const wrapper = document.createElement("div");
          wrapper.className = "mermaid-container";
          
          // Secure SVG rendering using DOMParser
          const svgDoc = parser.parseFromString(svg, "image/svg+xml");
          wrapper.appendChild(svgDoc.documentElement);
          
          parent.replaceWith(wrapper);
        }).catch((err: any) => {
          console.error("Failed to render diagram:", err);
        });
      }
    });
  } catch (err) {
    console.error("Mermaid setup failed:", err);
  }
}

/**
 * Loads page audits and updates the right sidebar.
 */
async function loadAudits(pagePath: string) {
  auditsContainer.replaceChildren();
  showLoadingSpinner(auditsContainer);
  auditsCountBadge.textContent = "0";

  try {
    const res = await fetch(`/api/audits/${encodeURIComponent(pagePath)}`);
    if (!res.ok) throw new Error("Failed to load audits");
    const audits: AuditEntry[] = await res.json();

    auditsContainer.replaceChildren();
    auditsCountBadge.textContent = String(audits.length);

    if (audits.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-audits";
      empty.textContent = "No open feedback audits on this page.";
      auditsContainer.appendChild(empty);
      return;
    }

    // Sort audits by creation date descending
    audits.sort((a, b) => new Date(b.created).getTime() - new Date(a.created).getTime());

    audits.forEach((audit) => {
      const card = document.createElement("div");
      card.className = "audit-card";

      const meta = document.createElement("div");
      meta.className = "audit-card-meta";
      
      const author = document.createElement("span");
      author.className = "audit-author";
      author.textContent = audit.author;
      
      const createdDate = new Date(audit.created);
      const dateStr = createdDate.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
      const date = document.createElement("span");
      date.className = "audit-date";
      date.textContent = dateStr;

      meta.appendChild(author);
      meta.appendChild(date);

      const sevRow = document.createElement("div");
      const sevTag = document.createElement("span");
      sevTag.className = `severity-tag ${audit.severity}`;
      sevTag.textContent = audit.severity;
      sevRow.appendChild(sevTag);

      const quote = document.createElement("div");
      quote.className = "audit-quote";
      quote.textContent = `"${audit.anchor_text}"`;
      quote.title = audit.anchor_text;

      // Extract the comment body text from markdown block
      const commentText = extractCommentBody(audit.body);
      const comment = document.createElement("div");
      comment.className = "audit-comment";
      comment.textContent = commentText;

      card.appendChild(meta);
      card.appendChild(sevRow);
      card.appendChild(quote);
      card.appendChild(comment);

      auditsContainer.appendChild(card);
    });
  } catch (err) {
    console.error("Error loading audits:", err);
    showErrorMessage(auditsContainer, "Error loading open audits.");
  }
}

/**
 * Handle mouse selection event to position selection popover trigger.
 */
function handleSelectionChange() {
  const selection = window.getSelection();
  
  if (!selection || selection.isCollapsed || !currentPage) {
    hidePopover();
    return;
  }

  const range = selection.getRangeAt(0);
  
  // Make sure selection is inside the markdown container content area
  if (!markdownContainer.contains(range.commonAncestorContainer)) {
    hidePopover();
    return;
  }

  const text = selection.toString().trim();
  if (text.length === 0) {
    hidePopover();
    return;
  }

  selectedText = text;

  // Retrieve context before selection
  const preRange = range.cloneRange();
  preRange.selectNodeContents(markdownContainer);
  preRange.setEnd(range.startContainer, range.startOffset);
  contextBefore = preRange.toString().slice(-100);

  // Retrieve context after selection
  const postRange = range.cloneRange();
  postRange.selectNodeContents(markdownContainer);
  postRange.setStart(range.endContainer, range.endOffset);
  contextAfter = postRange.toString().slice(0, 100);

  // Calculate coordinates to render floating button popover
  const rects = range.getClientRects();
  if (rects.length > 0) {
    const firstRect = rects[0]!;
    
    // Position button floating top-center above selection
    selectionPopover.style.left = `${firstRect.left + firstRect.width / 2 + window.scrollX}px`;
    selectionPopover.style.top = `${firstRect.top + window.scrollY - 10}px`;
    selectionPopover.classList.remove("hidden");
  }
}

function hidePopover() {
  selectionPopover.classList.add("hidden");
}

function openFeedbackModal() {
  if (!selectedText) return;
  
  // Display quote in modal Box
  modalQuote.textContent = `"${selectedText}"`;
  
  // Clear comment field
  feedbackCommentInput.value = "";
  
  // Display Modal Window
  feedbackModal.classList.remove("hidden");
  
  // Focus Comment Area
  feedbackCommentInput.focus();
}

function closeFeedbackModal() {
  feedbackModal.classList.add("hidden");
  
  // Clear window selection range
  window.getSelection()?.removeAllRanges();
}

/**
 * Submit feedback form values to backend API.
 */
async function submitFeedback() {
  const author = feedbackAuthorInput.value.trim();
  const comment = feedbackCommentInput.value.trim();
  
  // Get checked severity
  const severityRadio = document.querySelector('input[name="severity"]:checked') as HTMLInputElement;
  const severity = severityRadio ? severityRadio.value : "info";

  if (!author) {
    alert("Please specify your name.");
    feedbackAuthorInput.focus();
    return;
  }

  if (!comment) {
    alert("Please provide feedback comments.");
    feedbackCommentInput.focus();
    return;
  }

  // Persist author name
  localStorage.setItem("wiki-author", author);

  try {
    const res = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: currentPage,
        selectedText,
        contextBefore,
        contextAfter,
        severity,
        author,
        comment
      })
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || "Failed to submit feedback");
    }

    closeFeedbackModal();
    
    // Reload audits side panel immediately
    loadAudits(currentPage);
  } catch (err: any) {
    alert(`Failed to save feedback: ${err.message}`);
  }
}

/**
 * Extracts the user comment block from full markdown serialization file
 */
function extractCommentBody(body: string): string {
  const commentHeader = "# Comment";
  const resolutionHeader = "# Resolution";
  const startIdx = body.indexOf(commentHeader);
  if (startIdx === -1) return body.trim();
  
  const endIdx = body.indexOf(resolutionHeader, startIdx + commentHeader.length);
  const text = endIdx !== -1 
    ? body.slice(startIdx + commentHeader.length, endIdx) 
    : body.slice(startIdx + commentHeader.length);
    
  return text.trim();
}

/* UI Loading/Error Element Helpers (Strictly Vanilla DOM) */
function showLoadingSpinner(element: HTMLElement) {
  element.replaceChildren();
  const loading = document.createElement("div");
  loading.className = "loading-container";
  
  const spinner = document.createElement("div");
  spinner.className = "spinner";
  
  const text = document.createElement("span");
  text.textContent = "Loading...";

  loading.appendChild(spinner);
  loading.appendChild(text);
  element.appendChild(loading);
}

function showErrorMessage(element: HTMLElement, msg: string) {
  element.replaceChildren();
  const error = document.createElement("div");
  error.className = "loading-container";
  
  const text = document.createElement("span");
  text.style.color = "var(--sev-error)";
  text.textContent = msg;

  error.appendChild(text);
  element.appendChild(error);
}

/**
 * Loads graph data from /api/graph and renders a fully interactive knowledge graph
 * using vis-network. Clicking a node navigates directly to the wiki page.
 */
/**
 * Loads graph data from /api/graph and renders a fully custom, interactive
 * force-directed knowledge graph using D3.js v7.
 */
async function loadGraph() {
  currentPage = "";
  hidePopover();

  // Stop any active simulation
  if (graphSimulation) {
    graphSimulation.stop();
    graphSimulation = null;
  }
  if (activeParticles) {
    activeParticles.stop();
    activeParticles = null;
  }

  // Clear menu highlights
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach((item) => item.classList.remove("active"));

  showLoadingSpinner(markdownContainer);
  currentPageHeader.textContent = "Global Knowledge Graph";

  // Clear audits sidebar
  auditsContainer.replaceChildren();
  auditsCountBadge.textContent = "0";
  const empty = document.createElement("div");
  empty.className = "empty-audits";
  empty.textContent = "Select a concept or source node in the graph to view audits.";
  auditsContainer.appendChild(empty);

  try {
    const res = await fetch("/api/graph");
    if (!res.ok) throw new Error("Failed to load knowledge graph data");
    const data = await res.json();

    const container = document.createElement("div");
    container.id = "network-graph";
    container.style.width = "100%";
    container.style.height = "calc(100vh - 10rem)";
    container.style.position = "relative";
    container.style.background = "var(--bg-base)";
    container.style.borderRadius = "0.5rem";
    container.style.border = "1px solid var(--border-color)";
    container.style.overflow = "hidden";

    // Create canvas for background particles
    const canvasEl = document.createElement("canvas");
    canvasEl.id = "graph-particles";
    canvasEl.style.position = "absolute";
    canvasEl.style.top = "0";
    canvasEl.style.left = "0";
    canvasEl.style.width = "100%";
    canvasEl.style.height = "100%";
    canvasEl.style.pointerEvents = "none";
    canvasEl.style.zIndex = "0";
    container.appendChild(canvasEl);

    // Create SVG namespace element
    const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgEl.setAttribute("width", "100%");
    svgEl.setAttribute("height", "100%");
    svgEl.style.display = "block";
    svgEl.style.position = "relative";
    svgEl.style.zIndex = "1";
    container.appendChild(svgEl);

    markdownContainer.replaceChildren(container);

    // Instantiate and start background particles
    try {
      activeParticles = new ParticleField(canvasEl, 90);
      activeParticles.start();
    } catch (particleErr) {
      console.warn("Failed to initialize background particle field:", particleErr);
    }

    const d3 = (window as any).d3;
    const svg = d3.select(svgEl);
    
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    // ── Defs: Gaussian blur halo filter + radial vignette background ────────
    const defs = svg.append("defs");
    
    // Blur Filter for Nodes Halos
    const filter = defs.append("filter")
      .attr("id", "graph-node-glow")
      .attr("x", "-50%")
      .attr("y", "-50%")
      .attr("width", "200%")
      .attr("height", "200%");
    filter.append("feGaussianBlur")
      .attr("stdDeviation", "5");

    // Radial vignette overlay gradient
    const vignette = defs.append("radialGradient")
      .attr("id", "graph-bg-vignette")
      .attr("cx", "50%")
      .attr("cy", "50%")
      .attr("r", "70%");
    vignette.append("stop").attr("offset", "0%").attr("stop-color", "rgba(0,0,0,0)");
    vignette.append("stop").attr("offset", "100%").attr("stop-color", "rgba(10,12,18,0.75)");

    // Background Vignette Rect
    svg.append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "url(#graph-bg-vignette)")
      .style("pointer-events", "none");

    // Main transform group supporting Zoom
    const mainGroup = svg.append("g").attr("class", "graph-root");
    
    const zoom = d3.zoom()
      .scaleExtent([0.15, 4.0])
      .on("zoom", (event: any) => {
        mainGroup.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Render layers
    const linkLayer = mainGroup.append("g").attr("class", "links");
    const nodeLayer = mainGroup.append("g").attr("class", "nodes");

    // Color theme mapping (matching Catppuccin Mocha colors)
    const groupColors: Record<string, string> = {
      concepts: "#b4befe",   // Lavender/Violet
      sources: "#a6e3a1",    // Green
      entities: "#89b4fa",   // Blue/Cyan
      general: "#9399b2"     // Muted Slate
    };

    // Prepare Node/Link data structures
    const nodes = data.nodes.map((n: any) => ({
      id: n.id,
      label: n.label,
      group: n.group,
      degree: n.degree,
      title: n.title,
      x: width / 2 + (Math.random() - 0.5) * 120,
      y: height / 2 + (Math.random() - 0.5) * 120
    }));

    const links = data.edges.map((e: any) => ({
      source: e.source,
      target: e.target
    }));

    // Initialize D3 Force Simulation
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(105))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .alphaTarget(0.04)  // Alpha target above zero keeps layout breathing slightly
      .alphaDecay(0.012); // Low decay allows spread animations to settle smoothly

    // Save simulation reference for page teardowns
    graphSimulation = simulation;

    // Render Curved Arc links
    const link = linkLayer.selectAll("path")
      .data(links)
      .enter()
      .append("path")
      .attr("stroke", "var(--border-color)")
      .attr("stroke-opacity", 0.4)
      .attr("stroke-width", 1.5)
      .attr("fill", "none")
      .attr("class", "graph-link");

    // Render Nodes Groups
    const node = nodeLayer.selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .attr("class", "graph-node")
      .style("cursor", "pointer")
      .on("click", (event: any, d: any) => {
        loadPage(d.id);
      });

    // 1. Soft blurred halos behind nodes colored by group
    node.append("circle")
      .attr("r", (d: any) => Math.max(14, Math.min(32, 11 + d.degree * 2.2)))
      .attr("fill", (d: any) => groupColors[d.group] || "#cdd6f4")
      .attr("filter", "url(#graph-node-glow)")
      .attr("opacity", 0.22);

    // 2. High-contrast core node dots
    node.append("circle")
      .attr("r", (d: any) => Math.max(6, Math.min(15, 5 + d.degree * 1.1)))
      .attr("fill", "var(--bg-surface)")
      .attr("stroke", (d: any) => groupColors[d.group] || "#cdd6f4")
      .attr("stroke-width", 2.2);

    // 3. Clear text labels
    node.append("text")
      .attr("dy", (d: any) => Math.max(21, 15 + d.degree * 1.4))
      .attr("text-anchor", "middle")
      .attr("fill", "var(--text-primary)")
      .style("font-size", "0.72rem")
      .style("font-family", "Inter, sans-serif")
      .style("font-weight", "500")
      .style("pointer-events", "none")
      .text((d: any) => d.label);

    // Drag behavior implementation
    node.call(d3.drag()
      .on("start", (event: any, d: any) => {
        if (!event.active) simulation.alphaTarget(0.12).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event: any, d: any) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event: any, d: any) => {
        if (!event.active) simulation.alphaTarget(0.04);
        d.fx = null;
        d.fy = null;
      })
    );

    // Hover Highlight Interactions
    node.on("mouseover", (event: any, d: any) => {
      // Flow dash offset highlight on paths
      link.style("stroke", (l: any) => {
        if (l.source.id === d.id || l.target.id === d.id) {
          return groupColors[d.group] || "var(--accent-primary)";
        }
        return "var(--border-color)";
      })
      .style("stroke-opacity", (l: any) => (l.source.id === d.id || l.target.id === d.id ? 1.0 : 0.15))
      .style("stroke-width", (l: any) => (l.source.id === d.id || l.target.id === d.id ? 2.5 : 1.5))
      .classed("link-flowing", (l: any) => l.source.id === d.id || l.target.id === d.id);

      // Fade disconnected nodes
      node.style("opacity", (n: any) => {
        if (n.id === d.id) return 1.0;
        const connected = links.some((l: any) =>
          (l.source.id === d.id && l.target.id === n.id) ||
          (l.target.id === d.id && l.source.id === n.id)
        );
        return connected ? 1.0 : 0.3;
      });
    })
    .on("mouseout", () => {
      link.style("stroke", "var(--border-color)")
        .style("stroke-opacity", 0.4)
        .style("stroke-width", 1.5)
        .classed("link-flowing", false);

      node.style("opacity", 1.0);
    });

    // Simulation tick callback
    simulation.on("tick", () => {
      // Perpetual breathe: tiny random noise velocity perturbations
      nodes.forEach((n: any) => {
        n.vx += (Math.random() - 0.5) * 0.045;
        n.vy += (Math.random() - 0.5) * 0.045;
      });

      // Position links as elegant curved arcs
      link.attr("d", (d: any) => {
        const dx = d.target.x - d.source.x;
        const dy = d.target.y - d.source.y;
        const dr = Math.sqrt(dx * dx + dy * dy) * 1.45;
        return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
      });

      // Position nodes groups
      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

  } catch (err) {
    console.error("Error rendering D3 knowledge graph:", err);
    showErrorMessage(markdownContainer, "Error loading knowledge graph dataset.");
  }
}
