import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/Card";

/** The three states every list has. Pages use these so the wording stays the same everywhere. */

export function Spinner({ className = "min-h-[240px]" }: { className?: string }) {
  return (
    <div className={`grid place-items-center ${className}`}>
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
    </div>
  );
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card className="border-red-500/30 bg-red-500/[0.05]">
      <p className="flex items-center gap-2 text-[13.5px] font-semibold text-red-300"><AlertTriangle className="h-4 w-4" /> Could not load</p>
      <pre className="mt-2 whitespace-pre-wrap font-mono text-[12px] text-soft">{message}</pre>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 rounded-full border border-line-2 bg-panel px-4 py-1.5 text-[12.5px] text-soft hover:text-ink">Try again</button>
      )}
    </Card>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <Card className="py-12 text-center text-[13px] text-mut">{children}</Card>;
}
