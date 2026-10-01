import Link from "next/link";
import { cn } from "@/lib/utils/cn";

/** The wordmark. One place, so a rename is one edit. */
export function Brand({ className, href = "/dashboard", size = "md" }: { className?: string; href?: string; size?: "sm" | "md" }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2.5 font-extrabold tracking-tight", size === "md" ? "text-[18px]" : "text-[16px]", className)}>
      <span className={cn("rounded-full shadow-[0_0_16px_rgba(183,156,255,0.4)] [background:conic-gradient(from_210deg,#f4f5fa,#8890a2,#2b2f3a,#b79cff,#f4f5fa)]", size === "md" ? "h-7 w-7" : "h-6 w-6")} />
      <span>Lemniscate Growth <span className="font-medium text-soft">· Maya</span></span>
    </Link>
  );
}
