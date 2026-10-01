"use client";

import { useEffect, useRef } from "react";

/** Liquid metal orb: a chrome sphere with a flowing iridescent oil-slick. */
export function LiquidOrb({ className }: { className?: string }) {
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

    const iri = [
      [120, 180, 255], [90, 255, 224], [176, 120, 255], [255, 214, 150], [255, 120, 190],
    ];
    let raf = 0;

    const frame = (t: number) => {
      const W = cv.width, H = cv.height, cx = W / 2, cy = H / 2, tt = (t || 0) * 0.001;
      ctx.clearRect(0, 0, W, H);
      const R = Math.min(W, H) * 0.42 * (1 + Math.sin(tt * 1.1) * 0.02);

      const halo = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 1.9);
      halo.addColorStop(0, "rgba(150,190,255,0.20)");
      halo.addColorStop(1, "rgba(150,190,255,0)");
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.9, 0, Math.PI * 2); ctx.fill();

      ctx.save();
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();

      const chrome = ctx.createLinearGradient(0, cy - R, 0, cy + R);
      chrome.addColorStop(0, "#EEF2F8"); chrome.addColorStop(0.34, "#B4BCCC");
      chrome.addColorStop(0.6, "#6D7688"); chrome.addColorStop(0.82, "#3A404C"); chrome.addColorStop(1, "#20242D");
      ctx.fillStyle = chrome; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);

      ctx.globalCompositeOperation = "overlay";
      iri.forEach((c, i) => {
        const ang = tt * (0.16 + i * 0.05) * (i % 2 ? -1 : 1) + i * 1.7;
        const bx = cx + Math.cos(ang) * R * (0.3 + 0.14 * Math.sin(tt * 0.7 + i));
        const by = cy + Math.sin(ang * 1.15) * R * (0.3 + 0.14 * Math.cos(tt * 0.6 + i));
        const bR = R * (0.85 + 0.25 * Math.sin(tt * 1.3 + i));
        const g = ctx.createRadialGradient(bx, by, 0, bx, by, bR);
        g.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},0.55)`);
        g.addColorStop(1, `rgba(${c[0]},${c[1]},${c[2]},0)`);
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(bx, by, bR, 0, Math.PI * 2); ctx.fill();
      });

      ctx.globalCompositeOperation = "screen";
      const sx = cx + Math.cos(tt * 0.5) * R * 0.35, sy = cy - R * 0.42 + Math.sin(tt * 0.4) * R * 0.1;
      const spec = ctx.createRadialGradient(sx, sy, 0, sx, sy, R * 0.7);
      spec.addColorStop(0, "rgba(255,255,255,0.85)"); spec.addColorStop(0.5, "rgba(255,255,255,0.12)"); spec.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = spec;
      ctx.beginPath(); ctx.arc(sx, sy, R * 0.7, 0, Math.PI * 2); ctx.fill();

      ctx.globalCompositeOperation = "multiply";
      const sh = ctx.createRadialGradient(cx, cy + R * 0.55, 0, cx, cy + R * 0.55, R * 0.9);
      sh.addColorStop(0, "rgba(10,12,18,0.55)"); sh.addColorStop(1, "rgba(10,12,18,0)");
      ctx.fillStyle = sh;
      ctx.beginPath(); ctx.arc(cx, cy + R * 0.55, R * 0.9, 0, Math.PI * 2); ctx.fill();
      ctx.restore();

      ctx.globalCompositeOperation = "source-over";
      const rim = ctx.createLinearGradient(0, cy - R, 0, cy + R);
      rim.addColorStop(0, "rgba(255,255,255,0.55)"); rim.addColorStop(0.5, "rgba(255,255,255,0.04)"); rim.addColorStop(1, "rgba(0,0,0,0.35)");
      ctx.strokeStyle = rim; ctx.lineWidth = 1.4 * dp;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();

      if (!reduce) raf = requestAnimationFrame(frame);
    };

    if (reduce) frame(1500);
    else raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
