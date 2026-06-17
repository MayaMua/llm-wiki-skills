/**
 * client/particles.ts — Twinkling ambient particle background.
 *
 * Soft, twinkling dots drift across a canvas positioned behind the
 * D3 knowledge graph, adding depth and dynamic texture without visual noise.
 */

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  baseAlpha: number;
  phase: number;
  phaseSpeed: number;
  color: [number, number, number];
}

const PALETTE: [number, number, number][] = [
  [180, 190, 254], // Lavender
  [137, 180, 250], // Blue
  [203, 166, 247], // Mauve
  [148, 226, 213], // Teal
  [245, 194, 231], // Pink
  [116, 199, 236], // Sapphire
];

export class ParticleField {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private particles: Particle[] = [];
  private raf: number | null = null;
  private lastTime = 0;
  private w = 0;
  private h = 0;
  private running = false;
  private count: number;
  private resizeHandler = () => this.resize();

  constructor(canvas: HTMLCanvasElement, count = 90) {
    this.canvas = canvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D rendering context not available");
    this.ctx = ctx;
    this.count = count;
    this.resize();
    this.spawn(count);
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    window.addEventListener("resize", this.resizeHandler);
    this.lastTime = performance.now();
    this.raf = requestAnimationFrame((t) => this.tick(t));
  }

  stop(): void {
    this.running = false;
    window.removeEventListener("resize", this.resizeHandler);
    if (this.raf !== null) {
      cancelAnimationFrame(this.raf);
      this.raf = null;
    }
  }

  private resize(): void {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.w = rect.width || this.canvas.parentElement?.clientWidth || window.innerWidth;
    this.h = rect.height || this.canvas.parentElement?.clientHeight || window.innerHeight;

    this.canvas.width = this.w * dpr;
    this.canvas.height = this.h * dpr;
    this.ctx.scale(dpr, dpr);
  }

  private spawn(count: number): void {
    this.particles = [];
    for (let i = 0; i < count; i++) {
      const colorIndex = Math.floor(Math.random() * PALETTE.length);
      this.particles.push({
        x: Math.random() * this.w,
        y: Math.random() * this.h,
        vx: (Math.random() - 0.5) * 6, // Very slow drifting velocity
        vy: (Math.random() - 0.5) * 6,
        r: Math.random() * 2.2 + 1.0, // Dynamic radiuses between 1px and 3.2px
        baseAlpha: Math.random() * 0.18 + 0.08, // Muted ambient opacities
        phase: Math.random() * Math.PI * 2,
        phaseSpeed: Math.random() * 0.0015 + 0.0005, // Twinkle speed frequencies
        color: PALETTE[colorIndex]
      });
    }
  }

  private tick(time: number): void {
    if (!this.running) return;

    let dt = time - this.lastTime;
    // Bound dt to prevent large frame jumps on tab sleeping
    if (dt > 100) dt = 16.67;
    this.lastTime = time;

    this.ctx.clearRect(0, 0, this.w, this.h);
    
    // Use additive compositing to allow overlapping glowing highlights
    this.ctx.globalCompositeOperation = "lighter";

    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];

      // Update positions cleanly and wrap around edges
      p.x += (p.vx * dt) / 1000;
      p.y += (p.vy * dt) / 1000;

      if (p.x < 0) p.x = this.w;
      if (p.x > this.w) p.x = 0;
      if (p.y < 0) p.y = this.h;
      if (p.y > this.h) p.y = 0;

      // Update twinkle alpha phase
      p.phase += p.phaseSpeed * dt;
      const alpha = Math.max(0.02, p.baseAlpha + Math.sin(p.phase) * 0.07);

      // Create a smooth radial gradient halo
      const grad = this.ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 2.5);
      const [r, g, b] = p.color;
      grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${alpha})`);
      grad.addColorStop(0.3, `rgba(${r}, ${g}, ${b}, ${alpha * 0.6})`);
      grad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

      this.ctx.fillStyle = grad;
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, p.r * 2.5, 0, Math.PI * 2);
      this.ctx.fill();
    }

    this.raf = requestAnimationFrame((t) => this.tick(t));
  }
}
