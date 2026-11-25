import { Ban, CalendarDays, Check, ChevronLeft, ChevronRight, ExternalLink, History, Image, List, Play, RotateCcw, Send, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Badge, Button, Card, Confirm, Empty, ExtLink, Modal, PlatformIcon, ProgressBar, ScoreBadge, Segmented, cx, fmtDate } from "../components/ui";
import { useStore } from "../store";
import type { Account, Campaign, Publication, PubStatus } from "../types";

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
  const [showHistory, setShowHistory] = useState(false);

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
          <h1 className="text-2xl font-semibold tracking-tight">Publier</h1>
          <p className="mt-1 text-sm text-ink-300">Clique sur 10, 50 ou 100 sous un compte : ses meilleurs clips sont publiés automatiquement, 1 par heure.</p>
        </div>
        <Button variant={showHistory ? "secondary" : "ghost"} icon={<History className="size-4" />} onClick={() => setShowHistory(!showHistory)}>
          Historique{counts.failed ? ` (${counts.failed} à vérifier)` : ""}
        </Button>
      </header>
      <AccountTiles />
      {showHistory && (
        <>
      <div className="flex flex-wrap items-end justify-between gap-4 pt-4">
        <div>
          <h2 className="text-lg font-semibold">Historique des publications</h2>
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
        </>
      )}
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

function fmtHour(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  return today
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

function TileAvatar({ account }: { account: Account }) {
  const [broken, setBroken] = useState(false);
  if (account.avatar_url && !broken)
    return <img src={account.avatar_url} onError={() => setBroken(true)} className="size-16 rounded-2xl object-cover ring-2 ring-ink-700" alt="" />;
  return (
    <div className={cx("flex size-16 items-center justify-center rounded-2xl text-2xl font-semibold text-white", account.platform === "instagram" ? "bg-gradient-to-br from-amber-400 via-pink-500 to-purple-600" : "bg-gradient-to-br from-cyan-400 via-ink-900 to-pink-500")}>
      {account.name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function AccountTiles() {
  const accounts = useStore((s) => s.accounts);
  const campaigns = useStore((s) => s.campaigns);
  const clips = useStore((s) => s.clips);
  const setTab = useStore((s) => s.setTab);
  const [openId, setOpenId] = useState<number | null>(null);
  const stock = clips.filter((c) => c.status !== "rejected").length;
  if (!accounts.length)
    return (
      <Empty icon={<Send className="size-6" />} title="Aucun compte">
        <button className="text-brand-400 hover:underline cursor-pointer" onClick={() => setTab("accounts")}>
          Ajoute et connecte tes comptes
        </button>{" "}
        dans l'onglet Comptes.
      </Empty>
    );
  return (
    <>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-4">
        {accounts.map((a) => (
          <AccountTile key={a.id} account={a} campaign={campaigns.find((c) => c.status === "active" && c.account_ids.includes(a.id))} onOpen={setOpenId} />
        ))}
      </div>
      <p className="text-xs text-ink-400">
        {stock} clip{stock > 1 ? "s" : ""} disponible{stock > 1 ? "s" : ""} · les meilleurs partent d'abord, différents d'un compte à l'autre tant que possible · rejette un clip dans l'onglet Clips pour l'exclure.
      </p>
      {openId !== null && <CampaignModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

function AccountTile({ account: a, campaign, onOpen }: { account: Account; campaign?: Campaign; onOpen: (id: number) => void }) {
  const toast = useStore((s) => s.toast);
  const [busy, setBusy] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const row = campaign?.accounts.find((x) => x.account_id === a.id);
  const connected = a.status === "connected";

  async function start(n: number) {
    setBusy(n);
    try {
      const r = await api.post<Campaign & { warning?: string }>("/api/campaigns", { count: n, account_ids: [a.id], interval_minutes: 60 });
      if (r.warning) toast(r.warning, "warning");
      await useStore.getState().loadCampaigns();
      useStore.getState().loadPublications();
      onOpen(r.id);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className={cx("relative flex flex-col items-center p-5 text-center transition", campaign && "ring-1 ring-brand-500/40")}>
      <button
        onClick={() => setConfirm(true)}
        className="absolute top-3 right-3 rounded-lg p-1.5 text-ink-400 transition hover:bg-red-500/15 hover:text-red-300 cursor-pointer"
        title="Supprimer ce compte"
        aria-label="Supprimer ce compte"
      >
        <Trash2 className="size-4" />
      </button>
      <div className="relative">
        <TileAvatar account={a} />
        <span className="absolute -right-1.5 -bottom-1.5 rounded-lg bg-ink-800 p-1 text-white ring-2 ring-ink-850">
          <PlatformIcon platform={a.platform} className="size-3.5" />
        </span>
      </div>
      <div className="mt-3 w-full truncate font-semibold">{a.name}</div>
      <div className="text-xs text-ink-400">{a.username ? `@${a.username}` : a.platform === "instagram" ? "Instagram" : "TikTok"}</div>
      <div className="mt-1.5">
        {connected ? <Badge color="green">● Connecté</Badge> : <Badge color="amber">● À reconnecter</Badge>}
      </div>

      {campaign && row ? (
        <button onClick={() => onOpen(campaign.id)} className="mt-4 w-full rounded-xl border border-brand-500/30 bg-brand-500/10 p-3 text-left transition hover:bg-brand-500/20 cursor-pointer">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-brand-300">Publication en cours</span>
            <span className="text-sm font-semibold tabular-nums text-white">
              {row.published}
              <span className="text-xs text-ink-400"> / {row.target}</span>
            </span>
          </div>
          <ProgressBar value={row.target ? row.published / row.target : 0} active className="mt-2 h-1.5" />
          <div className="mt-1.5 text-[11px] text-ink-400">Voir l'avancée →</div>
        </button>
      ) : (
        <div className="mt-4 w-full">
          <div className="mb-1.5 text-[11px] text-ink-400">Publier (1 clip / heure)</div>
          <div className="grid grid-cols-3 gap-2">
            {PRESETS.map((n) => (
              <button
                key={n}
                disabled={!connected || busy !== null}
                onClick={() => start(n)}
                title={connected ? `Publier ${n} clips sur ${a.name}` : "Connecte d'abord ce compte"}
                className="rounded-lg border border-ink-600 bg-ink-900 py-2 text-sm font-semibold text-ink-100 transition hover:border-brand-500 hover:bg-brand-500/15 disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
              >
                {busy === n ? "…" : n}
              </button>
            ))}
          </div>
        </div>
      )}
      <Confirm
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Supprimer « ${a.name} » ?`}
        message="Le compte est retiré de Live Clipper (jetons de connexion, profil de navigateur, publications programmées). Les posts déjà publiés restent sur Instagram / TikTok."
        confirmLabel="Supprimer"
        danger
        onConfirm={async () => {
          try {
            await api.del(`/api/accounts/${a.id}`);
            toast("Compte supprimé", "success");
            useStore.getState().loadAccounts();
          } catch (e) {
            toast((e as Error).message, "error");
          }
        }}
      />
    </Card>
  );
}

function CampaignModal({ id, onClose }: { id: number; onClose: () => void }) {
  const c = useStore((s) => s.campaigns.find((x) => x.id === id));
  const toast = useStore((s) => s.toast);
  useEffect(() => {
    // l'avancée arrive par WebSocket ; on rafraîchit aussi toutes les 15 s par sécurité
    const t = window.setInterval(() => useStore.getState().loadCampaigns(), 15000);
    return () => window.clearInterval(t);
  }, []);
  if (!c) return null;
  const total = c.count * c.accounts.length;
  return (
    <Modal open onClose={onClose} title={`Publication : ${c.count} clips par compte`} width="max-w-3xl">
      <div className="space-y-5">
        <div>
          <div className="flex items-end justify-between">
            <div>
              <div className="text-3xl font-semibold tabular-nums text-white">
                {c.published_total}
                <span className="text-lg text-ink-400"> / {total}</span>
              </div>
              <div className="text-sm text-ink-300">clips postés au total · 1 clip toutes les {c.interval_minutes ?? 60} min par compte</div>
            </div>
            {c.status === "active" ? <Badge color="violet">En cours</Badge> : c.status === "done" ? <Badge color="green"><Check className="size-3" /> Terminé</Badge> : <Badge>Arrêté</Badge>}
          </div>
          <ProgressBar value={c.progress} active={c.status === "active"} className="mt-3 h-3" />
        </div>
        <div className="space-y-2">
          {c.accounts.map((a) => (
            <div key={a.account_id} className="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
              <div className="flex items-center gap-3">
                <PlatformIcon platform={a.platform} />
                <span className="flex-1 truncate font-medium">{a.name}</span>
                <span className="text-lg font-semibold tabular-nums text-white">
                  {a.published}
                  <span className="text-sm text-ink-400"> / {a.target} postés</span>
                </span>
              </div>
              <ProgressBar value={a.target ? a.published / a.target : 0} active={c.status === "active" && a.published < a.target} className="mt-2" />
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-400">
                {a.running > 0 && <span className="text-brand-300">● publication en cours…</span>}
                {c.status === "active" && a.published < a.target && a.next_at && !a.running && <span>Prochain clip : <b className="text-ink-200">{fmtHour(a.next_at)}</b></span>}
                {a.last_published_at && <span>Dernier : {fmtHour(a.last_published_at)}</span>}
                {a.last_post_url && (
                  <ExtLink href={a.last_post_url} className="inline-flex items-center gap-1">
                    <ExternalLink className="size-3" /> voir le dernier post
                  </ExtLink>
                )}
                {!a.connected && c.status === "active" && <span className="text-amber-300">⚠ compte à reconnecter</span>}
                {a.blocked && <span className="text-red-300">⏸ en pause après 3 échecs — {a.last_error}</span>}
                {!a.blocked && a.failed > 0 && <span className="text-red-300">{a.failed} échec(s)</span>}
                {a.paused > 0 && <span className="text-amber-300">⏸ vérification de sécurité à faire</span>}
                {c.status === "active" && !a.next_at && !a.running && a.published < a.target && a.connected && !a.blocked && (
                  <span className="text-amber-300">En attente de nouveaux clips (ajoute des lives)</span>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-between gap-2">
          {c.status === "active" ? (
            <Button variant="danger" icon={<Ban className="size-4" />} onClick={() => api.post(`/api/campaigns/${c.id}/cancel`).catch((e) => toast(e.message, "error"))}>
              Arrêter la publication
            </Button>
          ) : (
            <span />
          )}
          <Button variant="secondary" onClick={onClose}>
            Fermer (continue en arrière-plan)
          </Button>
        </div>
      </div>
    </Modal>
  );
}
