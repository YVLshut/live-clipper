import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useStore } from "../store";
import { cx } from "./ui";

const styles = {
  info: { icon: Info, cls: "border-sky-500/30 text-sky-200" },
  success: { icon: CheckCircle2, cls: "border-emerald-500/30 text-emerald-200" },
  warning: { icon: AlertTriangle, cls: "border-amber-500/40 text-amber-200" },
  error: { icon: XCircle, cls: "border-red-500/40 text-red-200" },
};

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismiss);
  return (
    <div className="pointer-events-none fixed right-5 bottom-5 z-[60] flex w-96 flex-col gap-2">
      {toasts.map((t) => {
        const { icon: Icon, cls } = styles[t.level] ?? styles.info;
        return (
          <div key={t.id} className={cx("animate-fade-up pointer-events-auto flex items-start gap-3 rounded-xl border bg-ink-800/95 p-3.5 shadow-2xl backdrop-blur", cls)}>
            <Icon className="mt-0.5 size-4 shrink-0" />
            <p className="flex-1 text-sm leading-snug text-ink-100">{t.message}</p>
            <button onClick={() => dismiss(t.id)} className="text-ink-400 hover:text-white cursor-pointer" aria-label="Fermer">
              <X className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
