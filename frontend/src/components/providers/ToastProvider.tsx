"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Info, X, AlertTriangle } from "lucide-react";

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

interface ToastCtx {
  toast: (message: string, kind?: ToastKind) => void;
}

const Ctx = createContext<ToastCtx>({ toast: () => {} });

const styles: Record<ToastKind, { ring: string; icon: React.ReactNode }> = {
  success: { ring: "border-emerald-400/30", icon: <Check className="h-4 w-4 text-emerald-300" /> },
  error: { ring: "border-red-500/30", icon: <AlertTriangle className="h-4 w-4 text-red-300" /> },
  info: { ring: "border-line-2", icon: <Info className="h-4 w-4 text-violet-2" /> },
};

let seq = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, kind: ToastKind = "success") => {
      const id = ++seq;
      setToasts((ts) => [...ts, { id, message, kind }]);
      setTimeout(() => dismiss(id), 3800);
    },
    [dismiss],
  );

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[320px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, scale: 0.96 }}
              transition={{ type: "spring", stiffness: 380, damping: 30 }}
              className={`pointer-events-auto flex items-start gap-2.5 rounded-xl border ${styles[t.kind].ring} bg-bg-2/95 px-3.5 py-3 shadow-2xl backdrop-blur`}
            >
              <span className="mt-0.5 shrink-0">{styles[t.kind].icon}</span>
              <p className="flex-1 text-[13px] text-ink">{t.message}</p>
              <button onClick={() => dismiss(t.id)} className="shrink-0 text-mut hover:text-ink">
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx).toast;
