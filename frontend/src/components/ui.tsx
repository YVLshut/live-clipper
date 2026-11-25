import { Loader2, X } from "lucide-react";
import { useEffect, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { openExternal } from "../api";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";

const variants: Record<Variant, string> = {
  primary: "gradient-bg text-white shadow-lg shadow-brand-500/20 hover:brightness-110",
  secondary: "bg-ink-700 text-ink-100 hover:bg-ink-600 border border-ink-600",
  ghost: "text-ink-300 hover:text-ink-100 hover:bg-ink-700/60",
  danger: "bg-red-500/10 text-red-300 border border-red-500/30 hover:bg-red-500/20",
  success: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const sizes = { sm: "h-8 px-3 text-xs gap-1.5", md: "h-9 px-4 text-sm gap-2", lg: "h-11 px-6 text-sm gap-2" };
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center rounded-lg font-medium transition-all cursor-pointer",
        "disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-brand-400",
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("rounded-2xl border border-ink-700 bg-ink-850", className)}>{children}</div>;
}

export function SectionTitle({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-ink-100">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-300">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

const inputBase =
  "w-full rounded-lg border border-ink-600 bg-ink-900 px-3 text-sm text-ink-100 placeholder:text-ink-400 " +
  "focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/25 transition";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(inputBase, "h-9", className)} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(inputBase, "py-2 resize-y", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(inputBase, "h-9 pr-8 cursor-pointer", className)}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-400">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="group inline-flex items-center gap-3 text-sm text-ink-200 disabled:opacity-50 cursor-pointer"
    >
      <span className={cx("relative h-5 w-9 rounded-full transition", checked ? "gradient-bg" : "bg-ink-600")}>
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
      </span>
      {label}
    </button>
  );
}

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[] }) {
  return (
    <div className="inline-flex rounded-lg border border-ink-600 bg-ink-900 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cx(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition cursor-pointer",
            value === o.value ? "bg-ink-600 text-white shadow" : "text-ink-300 hover:text-ink-100",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const badgeColors = {
  gray: "bg-ink-700 text-ink-200 border-ink-600",
  violet: "bg-brand-500/15 text-brand-400 border-brand-500/30",
  green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  red: "bg-red-500/15 text-red-300 border-red-500/30",
  amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  blue: "bg-sky-500/15 text-sky-300 border-sky-500/30",
};

export function Badge({ color = "gray", children, className }: { color?: keyof typeof badgeColors; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium", badgeColors[color], className)}>
      {children}
    </span>
  );
}

export function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return <Badge>—</Badge>;
  const color = score >= 8 ? "green" : score >= 6 ? "amber" : "red";
  return (
    <Badge color={color} className="tabular-nums">
      ★ {score.toFixed(1)}/10
    </Badge>
  );
}

export function ProgressBar({ value, active, className }: { value: number; active?: boolean; className?: string }) {
  return (
    <div className={cx("h-2 overflow-hidden rounded-full bg-ink-700", className)}>
      <div
        className={cx("h-full rounded-full gradient-bg transition-all duration-500", active && "progress-stripes")}
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}

export function Modal({ open, onClose, title, children, width = "max-w-2xl" }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  // portail : un parent animé (transform) casserait le position: fixed
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onMouseDown={onClose}>
      <div
        className={cx("animate-fade-up flex max-h-full w-full flex-col overflow-hidden rounded-2xl border border-ink-600 bg-ink-850 shadow-2xl", width)}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
          <h3 className="text-base font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-ink-300 hover:bg-ink-700 hover:text-white cursor-pointer" aria-label="Fermer">
            <X className="size-5" />
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function Confirm({ open, title, message, confirmLabel = "Confirmer", danger, onConfirm, onClose }: { open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void | Promise<void>; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal open={open} onClose={onClose} title={title} width="max-w-md">
      <div className="text-sm text-ink-200">{message}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Annuler
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          loading={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } finally {
              setBusy(false);
            }
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export function ExtLink({ href, children, className }: { href: string | null | undefined; children: ReactNode; className?: string }) {
  if (!href) return <span className={className}>{children}</span>;
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        openExternal(href);
      }}
      className={cx("cursor-pointer text-brand-400 hover:text-brand-300 hover:underline", className)}
      title={href}
    >
      {children}
    </a>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-ink-600 px-6 py-14 text-center">
      <div className="mb-3 rounded-2xl bg-ink-800 p-3 text-ink-300">{icon}</div>
      <p className="font-medium text-ink-200">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-ink-400">{children}</div>}
    </div>
  );
}

export function PlatformIcon({ platform, className = "size-4" }: { platform: string | null | undefined; className?: string }) {
  const p = (platform || "").toLowerCase();
  if (p === "instagram")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <circle cx="12" cy="12" r="4" />
        <circle cx="17.5" cy="6.5" r="1" fill="currentColor" />
      </svg>
    );
  if (p === "tiktok")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor">
        <path d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5 2.6 2.6 0 0 1-2.6-2.6 2.6 2.6 0 0 1 3.37-2.48V9.66A5.73 5.73 0 0 0 4.18 15.3a5.72 5.72 0 0 0 5.68 5.7 5.7 5.7 0 0 0 5.68-5.7V9.01a7.35 7.35 0 0 0 4.3 1.38V7.3s-1.88.09-3.24-1.48Z" />
      </svg>
    );
  if (p === "twitch")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor">
        <path d="M4.3 3 3 6.4v13.1h4.5V22h2.5l2.5-2.5h3.7L21 14.7V3H4.3Zm15 10.9-2.9 2.9h-4.6l-2.5 2.5v-2.5H5.5V4.7h13.8v9.2ZM16 7.8v4.8h-1.7V7.8H16Zm-4.6 0v4.8H9.7V7.8h1.7Z" />
      </svg>
    );
  if (p === "youtube")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor">
        <path d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.3 5 12 5 12 5s-6.3 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8c1.5.4 7.8.4 7.8.4s6.3 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8ZM10 15V9l5.2 3L10 15Z" />
      </svg>
    );
  if (p === "kick")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor">
        <path d="M3 3h6v4h2V5h2V3h8v6h-2v2h-2v2h2v2h2v6h-8v-2h-2v-2H9v4H3V3Z" />
      </svg>
    );
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m10 9 5 3-5 3z" fill="currentColor" />
    </svg>
  );
}

export function fmtDuration(s: number) {
  s = Math.round(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined, withTime = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
}

export function fmtDay(iso: string | null | undefined) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}
