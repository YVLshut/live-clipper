import { CalendarClock, Scissors, Settings as Cog, Users } from "lucide-react";
import { useStore } from "../store";
import { cx } from "./ui";

const items = [
  { id: "clipping", label: "Clipping", icon: Scissors },
  { id: "accounts", label: "Comptes", icon: Users },
  { id: "publishing", label: "Publication", icon: CalendarClock },
  { id: "settings", label: "Paramètres", icon: Cog },
] as const;

export function Sidebar() {
  const tab = useStore((s) => s.tab);
  const setTab = useStore((s) => s.setTab);
  const connected = useStore((s) => s.connected);
  const running = useStore((s) => s.jobs.filter((j) => j.status === "running" || j.status === "queued").length);
  const pending = useStore((s) => s.clips.filter((c) => c.status === "pending").length);
  const scheduled = useStore((s) => s.publications.filter((p) => p.status === "scheduled" || p.status === "paused").length);
  const reconnect = useStore((s) => s.accounts.filter((a) => a.status !== "connected").length);
  const badges: Record<string, number> = { clipping: running || pending, publishing: scheduled, accounts: reconnect };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-ink-700 bg-ink-950/60">
      <div className="flex items-center gap-3 px-5 pt-6 pb-8">
        <img src="/icon.svg" className="size-9" alt="" />
        <div>
          <div className="text-[15px] leading-tight font-semibold">Live Clipper</div>
          <div className="text-xs text-ink-400">Clips automatiques</div>
        </div>
      </div>
      <nav className="flex flex-col gap-1 px-3">
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cx(
              "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition cursor-pointer",
              tab === id ? "bg-ink-700/80 text-white" : "text-ink-300 hover:bg-ink-800 hover:text-ink-100",
            )}
          >
            {tab === id && <span className="absolute top-2 bottom-2 left-0 w-1 rounded-full gradient-bg" />}
            <Icon className={cx("size-[18px]", tab === id ? "text-brand-400" : "text-ink-400 group-hover:text-ink-200")} />
            {label}
            {!!badges[id] && (
              <span className={cx("ml-auto rounded-full px-2 py-0.5 text-[11px] tabular-nums", id === "accounts" ? "bg-amber-500/20 text-amber-300" : "bg-ink-600 text-ink-100")}>
                {badges[id]}
              </span>
            )}
          </button>
        ))}
      </nav>
      <div className="mt-auto px-5 py-5 text-xs text-ink-400">
        <div className="flex items-center gap-2">
          <span className={cx("size-2 rounded-full", connected ? "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/60" : "bg-red-400 animate-pulse")} />
          {connected ? "Moteur connecté" : "Connexion au moteur…"}
        </div>
      </div>
    </aside>
  );
}
