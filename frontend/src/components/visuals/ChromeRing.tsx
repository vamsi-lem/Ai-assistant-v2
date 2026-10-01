"use client";

import { useEffect, useRef } from "react";

/**
 * Liquid chrome ring: a rotating conic-gradient metal band with violet/warm
 * iridescence, a gliding specular highlight and a soft violet glow.
 * The visual signature of the sign in page.
 */
export function ChromeRing({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    let dp = 1;
    const resize = () => {
      dp = Math.min(window.devicePixelRatio || 1, 2);
      const r = cv.getBoundingClientRect();
      cv.width = Math.max(1, Math.floor(r.width * dp));
      cv.height = Math.max(1, Math.floor(r.height * dp));
    };
    resize();
    window.addEventListener("resize", resize);

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hasConic = typeof (ctx as CanvasRenderingContext2D).createConicGradient === "function";
    let raf = 0;

    const frame = (t: number) => {
      const W = cv.width;
      const H = cv.height;
      const cx = W / 2;
      const cy = H / 2;
      const tt = (t || 0) * 0.001;
      ctx.clearRect(0, 0, W, H);

      const R = Math.min(W, H) * 0.33 * (1 + Math.sin(tt * 0.9) * 0.015);
      const tube = R * 0.36;

      // violet drop glow
      const halo = ctx.createRadialGradient(cx, cy, R * 0.4, cx, cy, R * 1.7);
      halo.addColorStop(0, "rgba(139,107,240,0.28)");
      halo.addColorStop(1, "rgba(139,107,240,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.7, 0, Math.PI * 2);
      ctx.fill();

      // chrome band
      ctx.lineWidth = tube;
      ctx.lineCap = "round";
      if (hasConic) {
        const cg = ctx.createConicGradient(tt * 0.5, cx, cy);
        const stops: [number, string][] = [
          [0, "#F6F7FB"], [0.07, "#8B93A6"], [0.14, "#24272F"], [0.22, "#CDD2DE"],
          [0.32, "#5A6070"], [0.4, "#B79CFF"], [0.5, "#EFF1F7"], [0.6, "#2B2E38"],
          [0.7, "#FF9E7A"], [0.8, "#9DA3B2"], [0.9, "#23262E"], [1, "#F6F7FB"],
        ];
        stops.forEach(([p, c]) => cg.addColorStop(p, c));
        ctx.strokeStyle = cg;
      } else {
        const lg = ctx.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
        lg.addColorStop(0, "#EFF1F7");
        lg.addColorStop(0.5, "#5A6070");
        lg.addColorStop(1, "#23262E");
        ctx.strokeStyle = lg;
      }
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.stroke();

      // gliding specular arc
      const a0 = tt * 0.5 - 0.35;
      const a1 = tt * 0.5 + 0.35;
      ctx.lineWidth = tube * 0.9;
      const mid = (a0 + a1) / 2;
      const sgx = cx + Math.cos(mid) * R;
      const sgy = cy + Math.sin(mid) * R;
      const sp = ctx.createRadialGradient(sgx, sgy, 0, sgx, sgy, tube * 1.2);
      sp.addColorStop(0, "rgba(255,255,255,0.85)");
      sp.addColorStop(1, "rgba(255,255,255,0)");
      ctx.strokeStyle = sp;
      ctx.beginPath();
      ctx.arc(cx, cy, R, a0, a1);
      ctx.stroke();

      // crisp glass rims
      ctx.lineCap = "butt";
      ctx.lineWidth = 1.4 * dp;
      ctx.strokeStyle = "rgba(255,255,255,0.28)";
      ctx.beginPath();
      ctx.arc(cx, cy, R + tube / 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = "rgba(0,0,0,0.45)";
      ctx.beginPath();
      ctx.arc(cx, cy, R - tube / 2, 0, Math.PI * 2);
      ctx.stroke();

      if (!reduce) raf = requestAnimationFrame(frame);
    };

    if (reduce) frame(1400);
    else raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
