import { Ban, CalendarDays, ChevronLeft, ChevronRight, ExternalLink, Image, List, Play, RotateCcw, Send, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { Badge, Button, Card, Empty, ExtLink, Modal, PlatformIcon, ScoreBadge, Segmented, cx, fmtDate } from "../components/ui";
import { useStore } from "../store";
import type { Publication, PubStatus } from "../types";

const STATUS: Record<PubStatus, { label: string; color: "gray" | "violet" | "green" | "red" | "amber" | "blue" }> = {
  scheduled: { label: "En attente", color: "blue" },
  running: { label: "En cours", color: "violet" },
  published: { label: "Publié", color: "green" },
  failed: { label: "Échec", color: "red" },
  paused: { label: "En pause — vérification", color: "amber" },
  cancelled: { label: "Annulé", color: "gray" },
};

type Filter = "all" | "pending" | "published" | "failed";

export function PublishingPage() {
  const pubs = useStore((s) => s.publications);
  const accounts = useStore((s) => s.accounts);
  const [view, setView] = useState<"list" | "calendar">("list");
  const [filter, setFilter] = useState<Filter>("all");
  const [accountId, setAccountId] = useState<number | 0>(0);

  const filtered = pubs
    .filter((p) => !accountId || p.account_id === accountId)
    .filter((p) =>
      filter === "all" ? true : filter === "pending" ? ["scheduled", "running", "paused"].includes(p.status) : filter === "published" ? p.status === "published" : ["failed", "paused"].includes(p.status),
    );
  const counts = {
    pending: pubs.filter((p) => ["scheduled", "running", "paused"].includes(p.status)).length,
    published: pubs.filter((p) => p.status === "published").length,
    failed: pubs.filter((p) => ["failed", "paused"].includes(p.status)).length,
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Publication</h1>
          <p className="mt-1 text-sm text-ink-300">Posts programmés, publiés et en échec, compte par compte.</p>
        </div>
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: "list", label: <><List className="size-3.5" /> Liste</> },
            { value: "calendar", label: <><CalendarDays className="size-3.5" /> Calendrier</> },
          ]}
        />
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `Tout (${pubs.length})` },
            { value: "pending", label: `À venir (${counts.pending})` },
            { value: "published", label: `Publiés (${counts.published})` },
            { value: "failed", label: `Échecs / pauses (${counts.failed})` },
          ]}
        />
        <select value={accountId} onChange={(e) => setAccountId(+e.target.value)} className="h-8 rounded-lg border border-ink-600 bg-ink-900 px-2 text-xs text-ink-200">
          <option value={0}>Tous les comptes</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
      {view === "list" ? <PubList pubs={filtered} /> : <Calendar pubs={filtered} />}
    </div>
  );
}

function PubList({ pubs }: { pubs: Publication[] }) {
  const sorted = [...pubs].sort((a, b) => {
    const order = (p: Publication) => (["paused", "running", "scheduled"].includes(p.status) ? 0 : 1);
    if (order(a) !== order(b)) return order(a) - order(b);
    const ta = new Date(a.published_at ?? a.scheduled_at).getTime();
    const tb = new Date(b.published_at ?? b.scheduled_at).getTime();
    return order(a) === 0 ? ta - tb : tb - ta;
  });
  if (!sorted.length)
    return (
      <Empty icon={<Send className="size-6" />} title="Aucune publication">
        Approuve un clip dans l'onglet Clipping puis clique sur « Programmer », ou active la publication automatique d'un compte.
      </Empty>
    );
  return (
    <div className="space-y-2.5">
      {sorted.map((p) => (
        <PubRow key={p.id} pub={p} />
      ))}
    </div>
  );
}

function PubRow({ pub }: { pub: Publication }) {
  const toast = useStore((s) => s.toast);
  const [shot, setShot] = useState(false);
  const st = STATUS[pub.status];
  const act = (url: string, method: "post" | "del" = "post", ok?: string) =>
    (method === "post" ? api.post(url) : api.del(url))
      .then(() => ok && toast(ok, "success"))
      .catch((e) => toast(e.message, "error"));

  return (
    <Card className={cx("animate-fade-up flex items-center gap-4 p-3 pr-4", pub.status === "paused" && "ring-1 ring-amber-500/40")}>
      {pub.clip ? (
        <img src={pub.clip.thumb_url} alt="" loading="lazy" className="aspect-[9/16] h-24 shrink-0 rounded-lg bg-black object-cover" />
      ) : (
        <div className="aspect-[9/16] h-24 shrink-0 rounded-lg bg-ink-800" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge color={st.color}>{st.label}</Badge>
          {pub.auto && <Badge>Auto</Badge>}
          <span className="truncate font-medium">{pub.clip?.title || pub.clip_id}</span>
          {pub.clip && <ScoreBadge score={pub.clip.score} />}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-300">
          {pub.account && (
            <span className="flex items-center gap-1.5">
              <PlatformIcon platform={pub.account.platform} className="size-3.5" />
              {pub.account.name}
            </span>
          )}
          <span className="tabular-nums">
            {pub.status === "published" ? `Publié le ${fmtDate(pub.published_at)}` : `Prévu le ${fmtDate(pub.scheduled_at)}`}
          </span>
          {pub.attempts > 1 && <span className="text-xs text-ink-400">{pub.attempts} tentatives</span>}
        </div>
        {pub.error && pub.status !== "cancelled" && <p className={cx("mt-1.5 text-xs", pub.status === "paused" ? "text-amber-300" : "text-red-300")}>{pub.error}</p>}
        {pub.post_url && (
          <ExtLink href={pub.post_url} className="mt-1 inline-flex items-center gap-1 text-xs">
            <ExternalLink className="size-3" /> Voir le post
          </ExtLink>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
        {pub.screenshot_url && (
          <Button size="sm" variant="ghost" icon={<Image className="size-3.5" />} onClick={() => setShot(true)}>
            Capture
          </Button>
        )}
        {pub.status === "scheduled" && (
          <Button size="sm" variant="secondary" icon={<Play className="size-3.5" />} onClick={() => act(`/api/publications/${pub.id}/publish-now`, "post", "Publication lancée")}>
            Publier maintenant
          </Button>
        )}
        {pub.status === "paused" && (
          <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => act(`/api/publications/${pub.id}/retry`, "post", "Reprise de la publication")}>
            Reprendre
          </Button>
        )}
        {pub.status === "failed" && (
          <Button size="sm" variant="primary" icon={<RotateCcw className="size-3.5" />} onClick={() => act(`/api/publications/${pub.id}/retry`, "post", "Nouvel essai lancé")}>
            Réessayer
          </Button>
        )}
        {["scheduled", "paused", "failed"].includes(pub.status) && (
          <Button size="sm" variant="ghost" icon={<Ban className="size-3.5" />} onClick={() => act(`/api/publications/${pub.id}/cancel`)}>
            Annuler
          </Button>
        )}
        {["published", "cancelled", "failed"].includes(pub.status) && (
          <Button size="sm" variant="ghost" aria-label="Supprimer de l'historique" icon={<Trash2 className="size-3.5" />} onClick={() => act(`/api/publications/${pub.id}`, "del")} />
        )}
      </div>
      {shot && pub.screenshot_url && (
        <Modal open onClose={() => setShot(false)} title="Capture d'écran au moment de l'erreur" width="max-w-5xl">
          <img src={pub.screenshot_url} className="w-full rounded-lg border border-ink-700" alt="Capture d'écran" />
          {pub.error && <p className="mt-3 text-sm text-ink-300">{pub.error}</p>}
        </Modal>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ calendrier (semaine)
const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const DOT: Record<PubStatus, string> = {
  scheduled: "bg-sky-400",
  running: "bg-brand-400",
  published: "bg-emerald-400",
  failed: "bg-red-400",
  paused: "bg-amber-400",
  cancelled: "bg-ink-400",
};

function startOfWeek(d: Date) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}

function Calendar({ pubs }: { pubs: Publication[] }) {
  const [week, setWeek] = useState(() => startOfWeek(new Date()));
  const [detail, setDetail] = useState<Publication | null>(null);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(week.getTime() + i * 86400_000)), [week]);
  const byDay = (d: Date) =>
    pubs
      .filter((p) => {
        const t = new Date(p.published_at ?? p.scheduled_at);
        return t >= d && t < new Date(d.getTime() + 86400_000);
      })
      .sort((a, b) => new Date(a.published_at ?? a.scheduled_at).getTime() - new Date(b.published_at ?? b.scheduled_at).getTime());
  const today = new Date().toDateString();
  const end = new Date(week.getTime() + 6 * 86400_000);

  return (
    <Card className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" aria-label="Semaine précédente" icon={<ChevronLeft className="size-4" />} onClick={() => setWeek(new Date(week.getTime() - 7 * 86400_000))} />
          <Button size="sm" variant="ghost" aria-label="Semaine suivante" icon={<ChevronRight className="size-4" />} onClick={() => setWeek(new Date(week.getTime() + 7 * 86400_000))} />
          <Button size="sm" variant="ghost" onClick={() => setWeek(startOfWeek(new Date()))}>
            Aujourd'hui
          </Button>
        </div>
        <span className="text-sm font-medium text-ink-200">
          {week.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} — {end.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}
        </span>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {days.map((d, i) => (
          <div key={i} className={cx("min-h-[360px] rounded-xl border p-2", d.toDateString() === today ? "border-brand-500/50 bg-brand-500/5" : "border-ink-700 bg-ink-900/40")}>
            <div className="mb-2 flex items-baseline justify-between px-1">
              <span className="text-xs font-medium text-ink-300 uppercase">{DAYS[i]}</span>
              <span className={cx("text-sm tabular-nums", d.toDateString() === today ? "font-semibold text-brand-300" : "text-ink-400")}>{d.getDate()}</span>
            </div>
            <div className="space-y-1.5">
              {byDay(d).map((p) => (
                <button key={p.id} onClick={() => setDetail(p)} className="w-full rounded-lg border border-ink-700 bg-ink-800 p-1.5 text-left transition hover:border-ink-500 cursor-pointer">
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-300 tabular-nums">
                    <span className={cx("size-1.5 rounded-full", DOT[p.status])} />
                    {new Date(p.published_at ?? p.scheduled_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                    {p.account && <PlatformIcon platform={p.account.platform} className="ml-auto size-3" />}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-ink-100">{p.clip?.title || p.clip_id}</div>
                  <div className="truncate text-[10px] text-ink-400">{p.account?.name}</div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {detail && (
        <Modal open onClose={() => setDetail(null)} title="Publication" width="max-w-3xl">
          <PubRow pub={pubs.find((p) => p.id === detail.id) ?? detail} />
        </Modal>
      )}
    </Card>
  );
}
