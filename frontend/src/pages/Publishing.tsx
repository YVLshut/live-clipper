import { AlertTriangle, Ban, CalendarDays, Check, ChevronLeft, ChevronRight, ExternalLink, Image, List, Play, Rocket, RotateCcw, Send, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { Badge, Button, Card, Empty, ExtLink, Input, Modal, PlatformIcon, ProgressBar, ScoreBadge, Segmented, cx, fmtDate } from "../components/ui";
import { useStore } from "../store";
import type { Campaign, Publication, PubStatus } from "../types";

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
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Publier</h1>
        <p className="mt-1 text-sm text-ink-300">Choisis combien de clips publier sur chaque compte : Live Clipper prend automatiquement les meilleurs clips et les publie au rythme réglé sur chaque compte.</p>
      </header>
      <NewCampaign />
      <Campaigns />
      <div className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h2 className="text-lg font-semibold">File de publication et historique</h2>
          <p className="mt-0.5 text-sm text-ink-300">Posts programmés, publiés et en échec, compte par compte.</p>
        </div>
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: "list", label: <><List className="size-3.5" /> Liste</> },
            { value: "calendar", label: <><CalendarDays className="size-3.5" /> Calendrier</> },
          ]}
        />
      </div>
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

// ------------------------------------------------------------------ campagnes « N clips par compte »
const PRESETS = [10, 50, 100];

function NewCampaign() {
  const accounts = useStore((s) => s.accounts);
  const clips = useStore((s) => s.clips);
  const toast = useStore((s) => s.toast);
  const setTab = useStore((s) => s.setTab);
  const [count, setCount] = useState<number>(10);
  const [custom, setCustom] = useState("");
  const [selected, setSelected] = useState<number[] | null>(null);
  const [busy, setBusy] = useState(false);
  const chosen = selected ?? accounts.filter((a) => a.status === "connected").map((a) => a.id);
  const n = custom ? Math.max(0, parseInt(custom) || 0) : count;
  const stock = clips.filter((c) => c.status !== "rejected").length;
  const needed = n * chosen.length;
  const maxDays = Math.max(0, ...accounts.filter((a) => chosen.includes(a.id)).map((a) => Math.ceil(n / Math.max(1, a.max_per_day))));

  async function start() {
    setBusy(true);
    try {
      const r = await api.post<Campaign & { warning?: string }>("/api/campaigns", { count: n, account_ids: chosen });
      toast(`Publication lancée : ${n} clips sur ${chosen.length} compte(s)`, "success");
      if (r.warning) toast(r.warning, "warning");
      useStore.getState().loadCampaigns();
      useStore.getState().loadPublications();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (!accounts.length)
    return (
      <Empty icon={<Send className="size-6" />} title="Aucun compte connecté">
        <button className="text-brand-400 hover:underline cursor-pointer" onClick={() => setTab("accounts")}>
          Connecte d'abord tes comptes
        </button>{" "}
        dans l'onglet Comptes.
      </Empty>
    );

  return (
    <Card className="relative overflow-hidden p-6">
      <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-pink-500/10 blur-3xl" />
      <div className="relative grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div>
          <p className="mb-2 text-xs font-medium tracking-wide text-ink-300 uppercase">Nombre de clips par compte</p>
          <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => {
                  setCount(p);
                  setCustom("");
                }}
                className={cx(
                  "h-14 w-24 rounded-xl border text-lg font-semibold transition cursor-pointer",
                  !custom && count === p ? "border-brand-500 bg-brand-500/15 text-white" : "border-ink-600 text-ink-200 hover:border-ink-500",
                )}
              >
                {p}
                <span className="block text-[10px] font-normal text-ink-400">clips</span>
              </button>
            ))}
            <div className="w-28">
              <Input type="number" min={1} max={1000} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Autre" className="h-14 text-center text-lg" />
            </div>
          </div>
          <div className="mt-5 space-y-1.5 text-sm text-ink-300">
            <p>
              <b className="text-ink-100">{n * chosen.length}</b> publications au total ({n} × {chosen.length} compte{chosen.length > 1 ? "s" : ""}).
            </p>
            {maxDays > 0 && <p>Durée estimée : environ <b className="text-ink-100">{maxDays} jour{maxDays > 1 ? "s" : ""}</b> selon le nombre de posts par jour de chaque compte.</p>}
            <p>
              Clips disponibles : <b className="text-ink-100">{stock}</b>
              {needed > stock && (
                <span className="text-amber-300">
                  {" "}
                  — chaque compte reçoit des clips différents tant que possible, puis les clips sont réutilisés. Ajoute des lives pour en avoir plus.
                </span>
              )}
            </p>
          </div>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium tracking-wide text-ink-300 uppercase">Comptes</p>
          <div className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {accounts.map((a) => {
              const on = chosen.includes(a.id);
              return (
                <label key={a.id} className={cx("flex items-center gap-3 rounded-lg border px-3 py-2 cursor-pointer transition", on ? "border-brand-500/60 bg-brand-500/10" : "border-ink-700 hover:border-ink-500")}>
                  <input type="checkbox" className="size-4 accent-brand-500" checked={on} onChange={(e) => setSelected(e.target.checked ? [...chosen, a.id] : chosen.filter((x) => x !== a.id))} />
                  <PlatformIcon platform={a.platform} />
                  <span className="flex-1 truncate text-sm">{a.name}</span>
                  <span className="text-[11px] text-ink-400">{a.max_per_day}/jour</span>
                  {a.status !== "connected" && (
                    <Badge color="amber">
                      <AlertTriangle className="size-3" /> à connecter
                    </Badge>
                  )}
                </label>
              );
            })}
          </div>
          <Button variant="primary" size="lg" className="mt-4 w-full" icon={<Rocket className="size-4" />} loading={busy} disabled={!n || !chosen.length} onClick={start}>
            Publier {n} clips sur {chosen.length} compte{chosen.length > 1 ? "s" : ""}
          </Button>
          <p className="mt-2 text-xs text-ink-400">Automatique : les meilleurs clips (score IA) sont publiés sans validation. Rejette un clip dans l'onglet Lives pour l'exclure.</p>
        </div>
      </div>
    </Card>
  );
}

function Campaigns() {
  const campaigns = useStore((s) => s.campaigns);
  const toast = useStore((s) => s.toast);
  if (!campaigns.length) return null;
  return (
    <div className="space-y-3">
      {campaigns.slice(0, 10).map((c) => (
        <Card key={c.id} className="p-4">
          <div className="flex items-center gap-3">
            {c.status === "active" ? <Badge color="violet">En cours</Badge> : c.status === "done" ? <Badge color="green"><Check className="size-3" /> Terminée</Badge> : <Badge>Arrêtée</Badge>}
            <span className="font-medium">
              {c.count} clips par compte · {c.accounts.length} compte{c.accounts.length > 1 ? "s" : ""}
            </span>
            <span className="text-xs text-ink-400">lancée le {fmtDate(c.created_at)}</span>
            <span className="ml-auto text-sm tabular-nums text-ink-300">
              {c.published_total} / {c.count * c.accounts.length} publiés
            </span>
            {c.status === "active" ? (
              <Button size="sm" variant="ghost" icon={<Ban className="size-3.5" />} onClick={() => api.post(`/api/campaigns/${c.id}/cancel`).catch((e) => toast(e.message, "error"))}>
                Arrêter
              </Button>
            ) : (
              <Button size="sm" variant="ghost" aria-label="Supprimer" icon={<Trash2 className="size-3.5" />} onClick={() => api.del(`/api/campaigns/${c.id}`).then(() => useStore.getState().loadCampaigns()).catch((e) => toast(e.message, "error"))} />
            )}
          </div>
          <ProgressBar value={c.progress} active={c.status === "active"} className="mt-3" />
          <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {c.accounts.map((a) => (
              <div key={a.account_id} className="flex items-center gap-2 rounded-lg bg-ink-900/60 px-3 py-2 text-xs">
                <PlatformIcon platform={a.platform} className="size-3.5" />
                <span className="flex-1 truncate text-ink-200">{a.name}</span>
                {!a.connected && c.status === "active" && <AlertTriangle className="size-3.5 text-amber-300" />}
                <span className="tabular-nums text-ink-300">
                  <b className="text-ink-100">{a.published}</b>/{a.target}
                  {a.scheduled > 0 && <span className="text-sky-300"> · {a.scheduled} prévus</span>}
                  {a.failed > 0 && <span className="text-red-300"> · {a.failed} échec</span>}
                </span>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
