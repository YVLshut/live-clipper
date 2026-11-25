import {
  AlertTriangle,
  Ban,
  Check,
  ChevronDown,
  Clapperboard,
  Copy,
  Download,
  Eye,
  EyeOff,
  FolderOpen,
  Link2,
  Loader2,
  Mic,
  RotateCcw,
  Scissors,
  Send,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api, openFolder } from "../api";
import { ScheduleModal } from "../components/ScheduleModal";
import {
  Badge,
  Button,
  Card,
  Confirm,
  Empty,
  ExtLink,
  Field,
  Input,
  PlatformIcon,
  ProgressBar,
  ScoreBadge,
  SectionTitle,
  Segmented,
  Textarea,
  Toggle,
  cx,
  fmtDay,
  fmtDuration,
} from "../components/ui";
import { useStore } from "../store";
import type { Clip, Job, Source, Stream } from "../types";

export function ClippingPage() {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          <span className="gradient-text">Lives</span>
        </h1>
        <p className="mt-1 text-sm text-ink-300">
          Colle des liens de lives, en direct ou terminés. En direct, le live est enregistré par tranches de 30 min et clippé au fur et à mesure ; terminé, il est clippé en entier.
        </p>
      </header>
      <NewJobForm />
      <StreamsSection />
      <JobsSection />
      <Gallery />
    </div>
  );
}

// ------------------------------------------------------------------ formulaire
function NewJobForm() {
  const settings = useStore((s) => s.settings);
  const toast = useStore((s) => s.toast);
  const [urls, setUrls] = useState("");
  const [maxClips, setMaxClips] = useState<number | "">("");
  const [minLen, setMinLen] = useState<number | "">("");
  const [maxLen, setMaxLen] = useState<number | "">("");
  const [layout, setLayout] = useState<"blur" | "crop" | "">("");
  const [useSection, setUseSection] = useState(false);
  const [secStart, setSecStart] = useState("00:00:00");
  const [secEnd, setSecEnd] = useState("01:00:00");
  const [busy, setBusy] = useState(false);

  const count = useMemo(() => (urls.match(/https?:\/\/\S+/g) || []).length, [urls]);
  const lay = layout || (settings?.layout as "blur" | "crop") || "blur";

  async function submit() {
    setBusy(true);
    try {
      const res = await api.post<{ jobs: Job[]; warning?: string }>("/api/jobs", {
        urls,
        options: {
          max_clips: maxClips || undefined,
          min_len: minLen || undefined,
          max_len: maxLen || undefined,
          layout: layout || undefined,
          section: useSection ? `${secStart}-${secEnd}` : undefined,
        },
      });
      toast(`${(res as { streams?: number }).streams ?? res.jobs.length} live(s) ajouté(s) à « Mes lives »`, "success");
      useStore.getState().loadStreams();
      if (res.warning) toast(res.warning, "warning");
      setUrls("");
      useStore.getState().loadJobs();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative overflow-hidden p-6">
      <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-brand-500/10 blur-3xl" />
      <div className="relative grid gap-6 lg:grid-cols-[1fr_340px]">
        <div>
          <Field label="Liens des lives (Twitch, YouTube, Kick)" hint="Un lien par ligne. Lien d'une chaîne en direct (ex. twitch.tv/pseudo) ou d'une rediffusion.">
            <Textarea
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              rows={5}
              placeholder={"https://www.twitch.tv/pseudo   (live en direct)\nhttps://www.twitch.tv/videos/123456789\nhttps://www.youtube.com/watch?v=…\nhttps://kick.com/pseudo"}
              className="font-mono text-[13px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && count) submit();
              }}
            />
          </Field>
          <div className="mt-4 flex items-center gap-3">
            <Button variant="primary" size="lg" icon={<Scissors className="size-4" />} loading={busy} disabled={!urls.trim()} onClick={submit}>
              Ajouter {count > 1 ? `ces ${count} lives` : "ce live"}
            </Button>
            {!settings?.secrets.anthropic_api_key && (
              <span className="flex items-center gap-1.5 text-xs text-amber-300">
                <AlertTriangle className="size-3.5" /> Sans clé API Anthropic, le repérage se limite aux pics de volume.
              </span>
            )}
          </div>
        </div>
        <div className="space-y-4 rounded-xl border border-ink-700 bg-ink-900/60 p-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Clips max" hint="par live (ou par tranche de 30 min en direct)">
              <Input type="number" min={1} max={30} value={maxClips} placeholder={String(settings?.max_clips ?? 5)} onChange={(e) => setMaxClips(e.target.value ? +e.target.value : "")} />
            </Field>
            <Field label="Durée min (s)">
              <Input type="number" min={3} max={180} value={minLen} placeholder={String(settings?.min_len ?? 15)} onChange={(e) => setMinLen(e.target.value ? +e.target.value : "")} />
            </Field>
            <Field label="Durée max (s)">
              <Input type="number" min={3} max={180} value={maxLen} placeholder={String(settings?.max_len ?? 60)} onChange={(e) => setMaxLen(e.target.value ? +e.target.value : "")} />
            </Field>
          </div>
          <Field label="Mise en page">
            <Segmented
              value={lay}
              onChange={(v) => setLayout(v)}
              options={[
                { value: "blur", label: "Fond flou" },
                { value: "crop", label: "Recadrage" },
              ]}
            />
          </Field>
          <div>
            <Toggle checked={useSection} onChange={setUseSection} label="Passage précis uniquement (rediffusion)" />
            {useSection && (
              <div className="mt-3 flex items-center gap-2">
                <Input value={secStart} onChange={(e) => setSecStart(e.target.value)} className="font-mono" placeholder="HH:MM:SS" />
                <span className="text-ink-400">→</span>
                <Input value={secEnd} onChange={(e) => setSecEnd(e.target.value)} className="font-mono" placeholder="HH:MM:SS" />
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ « Mes lives » (œil)
function StreamsSection() {
  const streams = useStore((s) => s.streams);
  const on = streams.filter((x) => x.enabled).length;
  return (
    <section>
      <SectionTitle
        title="Mes lives"
        subtitle={
          streams.length
            ? `${on} live${on > 1 ? "s" : ""} clippé${on > 1 ? "s" : ""} sur ${streams.length}. L'œil coupe ou réactive le clipping d'un live.`
            : "Les lives que tu ajoutes apparaissent ici. L'œil permet de couper ou de réactiver le clipping de chacun."
        }
      />
      {streams.length ? (
        <Card className="divide-y divide-ink-700 overflow-hidden">
          {streams.map((st) => (
            <StreamRow key={st.id} stream={st} />
          ))}
        </Card>
      ) : (
        <Empty icon={<Eye className="size-6" />} title="Aucun live ajouté">
          Colle un lien de live ou de chaîne dans le champ ci-dessus puis clique sur « Ajouter ».
        </Empty>
      )}
    </section>
  );
}

const STATE_STYLE: Record<Stream["state"], string> = {
  live: "text-red-300",
  processing: "text-brand-300",
  watching: "text-ink-300",
  done: "text-emerald-300",
  failed: "text-red-300",
  paused: "text-ink-400",
};

function StreamRow({ stream: st }: { stream: Stream }) {
  const toast = useStore((s) => s.toast);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function toggle() {
    setBusy(true);
    try {
      await api.patch(`/api/streams/${st.id}`, { enabled: !st.enabled });
      await useStore.getState().loadStreams();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={cx("flex items-center gap-4 px-4 py-3 transition", !st.enabled && "opacity-55")}>
      <button
        onClick={toggle}
        disabled={busy}
        title={st.enabled ? "Couper le clipping de ce live" : "Réactiver le clipping de ce live"}
        aria-label={st.enabled ? "Couper le clipping" : "Réactiver le clipping"}
        className={cx(
          "flex size-10 shrink-0 items-center justify-center rounded-xl border transition cursor-pointer disabled:opacity-50",
          st.enabled ? "border-brand-500/40 bg-brand-500/15 text-brand-300 hover:bg-brand-500/25" : "border-ink-600 bg-ink-900 text-ink-400 hover:text-ink-200",
        )}
      >
        {busy ? <Loader2 className="size-5 animate-spin" /> : st.enabled ? <Eye className="size-5" /> : <EyeOff className="size-5" />}
      </button>
      <PlatformIcon platform={st.platform || (st.url.includes("twitch") ? "twitch" : st.url.includes("kick") ? "kick" : st.url.includes("youtu") ? "youtube" : "")} className="size-4 shrink-0 text-ink-200" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-ink-100">{st.author || st.url.replace(/^https?:\/\/(www\.)?/, "")}</span>
          {st.state === "live" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-300">
              <span className="size-1.5 animate-pulse rounded-full bg-red-500" /> EN DIRECT
            </span>
          )}
          {st.channel && <Badge>Chaîne</Badge>}
        </div>
        <div className="truncate text-xs text-ink-400">
          {st.title ? `${st.title} · ` : ""}
          <ExtLink href={st.url}>{st.url.replace(/^https?:\/\//, "")}</ExtLink>
        </div>
      </div>
      <div className="hidden w-80 shrink-0 text-right text-xs md:block">
        <div className={STATE_STYLE[st.state]}>{st.label}</div>
        <div className="text-ink-400">
          {st.clips} clip{st.clips > 1 ? "s" : ""}
          {st.recorded > 0 && ` · ${fmtDuration(st.recorded)} enregistrées`}
        </div>
      </div>
      <Button size="sm" variant="ghost" aria-label="Retirer de la liste" icon={<Trash2 className="size-3.5" />} onClick={() => setConfirm(true)} />
      <Confirm
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Retirer ce live de la liste ?"
        message="Le clipping de ce live s'arrête. Les clips déjà créés restent dans la galerie."
        confirmLabel="Retirer"
        danger
        onConfirm={async () => {
          await api.del(`/api/streams/${st.id}`);
          await useStore.getState().loadStreams();
        }}
      />
    </div>
  );
}

// ------------------------------------------------------------------ jobs
const STEPS = [
  { id: "download", label: "Téléchargement", icon: Download },
  { id: "transcribe", label: "Transcription", icon: Mic },
  { id: "detect", label: "Repérage IA", icon: Sparkles },
  { id: "render", label: "Montage", icon: Clapperboard },
] as const;

function JobsSection() {
  const jobs = useStore((s) => s.jobs);
  const toast = useStore((s) => s.toast);
  const visible = jobs.filter((j) => j.kind === "clip" || j.kind === "live" || j.status === "running" || j.status === "failed");
  if (!visible.length) return null;
  const finished = visible.some((j) => ["done", "failed", "cancelled"].includes(j.status));
  return (
    <section>
      <SectionTitle
        title="Lives en cours de traitement"
        subtitle="Enregistrement, transcription, repérage IA et montage, en direct."
        right={
          finished && (
            <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={() => api.del("/api/jobs").catch((e) => toast(e.message, "error"))}>
              Effacer les jobs terminés
            </Button>
          )
        }
      />
      <div className="space-y-3">
        {visible.slice(0, 20).map((j) => (
          <JobCard key={j.id} job={j} />
        ))}
      </div>
    </section>
  );
}

function SourceLine({ source, compact }: { source: Source; compact?: boolean }) {
  return (
    <div className={cx("flex flex-wrap items-center gap-x-2 gap-y-1 text-ink-300", compact ? "text-xs" : "text-sm")}>
      <PlatformIcon platform={source.platform} className="size-3.5 text-ink-200" />
      <ExtLink href={source.author_url} className="font-medium">
        {source.author}
      </ExtLink>
      <span className="text-ink-500">•</span>
      <span>{source.platform}</span>
      {source.date && (
        <>
          <span className="text-ink-500">•</span>
          <span>{fmtDay(source.date)}</span>
        </>
      )}
      {source.url?.startsWith("http") && (
        <ExtLink href={source.url} className="inline-flex items-center gap-1">
          <Link2 className="size-3" /> live
        </ExtLink>
      )}
    </div>
  );
}

function LiveCard({ job }: { job: Job }) {
  const toast = useStore((s) => s.toast);
  const src = (job.extra?.source ?? job.source ?? null) as Source | null;
  const onAir = job.status === "running";
  // sélectionner un nombre (valeur stable) : une liste recréée à chaque lecture ferait boucler le rendu
  const clips = useStore((s) =>
    s.jobs.reduce((n, j) => n + ((j.options as { live_job_id?: number })?.live_job_id === job.id ? j.clips_count || 0 : 0), 0),
  );
  const act = (p: Promise<unknown>) => p.catch((e) => toast(e.message, "error"));
  return (
    <Card className={cx("animate-fade-up p-4", onAir && "ring-1 ring-red-500/40")}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {onAir ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-semibold text-red-300">
                <span className="size-1.5 animate-pulse rounded-full bg-red-500" /> EN DIRECT
              </span>
            ) : (
              <StatusBadge status={job.status} />
            )}
            <p className="truncate font-medium text-ink-100">{src?.title || job.url}</p>
          </div>
          {src && (
            <div className="mt-1">
              <SourceLine source={src as Source} compact />
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onAir && (
            <Button size="sm" variant="ghost" icon={<Ban className="size-3.5" />} onClick={() => act(api.post(`/api/jobs/${job.id}/cancel`))}>
              Arrêter l'enregistrement
            </Button>
          )}
          {(job.status === "failed" || job.status === "cancelled") && (
            <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => act(api.post(`/api/jobs/${job.id}/retry`))}>
              Reprendre
            </Button>
          )}
          {!onAir && (
            <Button size="sm" variant="ghost" aria-label="Supprimer" icon={<Trash2 className="size-3.5" />} onClick={() => act(api.del(`/api/jobs/${job.id}`))} />
          )}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="Enregistré" value={fmtDuration(job.extra?.recorded ?? 0)} />
        <Stat label="Tranches clippées" value={String(job.extra?.segments ?? 0)} />
        <Stat label="Clips créés" value={String(clips)} />
      </div>
      <p className="mt-2 text-xs text-ink-400">{job.message}</p>
      {job.status === "failed" && job.error && <p className="mt-2 rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2 text-sm text-red-300">{job.error}</p>}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/50 py-2">
      <div className="text-base font-semibold tabular-nums text-ink-100">{value}</div>
      <div className="text-[11px] text-ink-400">{label}</div>
    </div>
  );
}

function JobCard({ job }: { job: Job }) {
  const toast = useStore((s) => s.toast);
  if (job.kind === "live") return <LiveCard job={job} />;
  const stepIdx = STEPS.findIndex((s) => s.id === job.step);
  const active = job.status === "running";
  const liveSrc = (job.options as { live_source?: Source; segment?: number })?.live_source;
  const segment = (job.options as { segment?: number })?.segment ?? 0;
  const title =
    job.kind === "rerender"
      ? `Remontage du clip ${job.clip_id}`
      : liveSrc
        ? `${liveSrc.title || "Live"} — tranche ${segment + 1}`
        : job.source?.title || job.url;
  const act = (p: Promise<unknown>) => p.catch((e) => toast(e.message, "error"));

  return (
    <Card className="animate-fade-up p-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={job.status} />
            <p className="truncate font-medium text-ink-100" title={job.url ?? ""}>
              {title}
            </p>
          </div>
          {job.source && (
            <div className="mt-1">
              <SourceLine source={job.source} compact />
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {(job.status === "running" || job.status === "queued") && (
            <Button size="sm" variant="ghost" icon={<Ban className="size-3.5" />} onClick={() => act(api.post(`/api/jobs/${job.id}/cancel`))}>
              Annuler
            </Button>
          )}
          {(job.status === "failed" || job.status === "cancelled") && (
            <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => act(api.post(`/api/jobs/${job.id}/retry`))}>
              Réessayer
            </Button>
          )}
          {!["running", "queued"].includes(job.status) && (
            <Button size="sm" variant="ghost" aria-label="Supprimer" icon={<Trash2 className="size-3.5" />} onClick={() => act(api.del(`/api/jobs/${job.id}`))} />
          )}
        </div>
      </div>

      {job.kind === "clip" && job.status !== "failed" && job.status !== "cancelled" && (
        <div className="mt-4 grid grid-cols-4 gap-2">
          {STEPS.map((s, i) => {
            const done = job.status === "done" || i < stepIdx;
            const cur = active && i === stepIdx;
            const Icon = s.icon;
            return (
              <div
                key={s.id}
                className={cx(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition",
                  done && "border-emerald-500/25 bg-emerald-500/5 text-emerald-300",
                  cur && "border-brand-500/40 bg-brand-500/10 text-brand-300",
                  !done && !cur && "border-ink-700 text-ink-400",
                )}
              >
                {cur ? <Loader2 className="size-3.5 animate-spin" /> : done ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
                {s.label}
              </div>
            );
          })}
        </div>
      )}

      {(active || job.status === "queued") && (
        <div className="mt-3">
          <ProgressBar value={job.progress} active={active} />
          <div className="mt-1.5 flex justify-between text-xs text-ink-400">
            <span>{job.message}</span>
            <span className="tabular-nums">{Math.round(job.progress * 100)} %</span>
          </div>
        </div>
      )}
      {job.status === "done" && job.kind === "clip" && <p className="mt-3 text-sm text-emerald-300">✔ {job.message}</p>}
      {job.status === "failed" && <p className="mt-3 rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2 text-sm text-red-300">{job.error}</p>}
      {!!job.warnings?.length && (
        <ul className="mt-2 space-y-1">
          {job.warnings.map((w) => (
            <li key={w} className="flex items-start gap-1.5 text-xs text-amber-300">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {w}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StatusBadge({ status }: { status: Job["status"] }) {
  const map = {
    queued: <Badge>En attente</Badge>,
    running: <Badge color="violet">En cours</Badge>,
    done: <Badge color="green">Terminé</Badge>,
    failed: <Badge color="red">Échec</Badge>,
    cancelled: <Badge>Annulé</Badge>,
  };
  return map[status];
}

// ------------------------------------------------------------------ galerie
type Filter = "pending" | "approved" | "rejected" | "all";

function Gallery() {
  const clips = useStore((s) => s.clips);
  const sources = useStore((s) => s.sources);
  const settings = useStore((s) => s.settings);
  const [filter, setFilter] = useState<Filter>("pending");
  const [sourceId, setSourceId] = useState("");
  const counts = {
    pending: clips.filter((c) => c.status === "pending").length,
    approved: clips.filter((c) => c.status === "approved").length,
    rejected: clips.filter((c) => c.status === "rejected").length,
    all: clips.length,
  };
  const shown = clips
    .filter((c) => filter === "all" || c.status === filter)
    .filter((c) => !sourceId || c.source_id === sourceId)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  return (
    <section>
      <SectionTitle
        title="Galerie des clips"
        subtitle="Vérifie, ajuste l'accroche et la légende, puis approuve les clips à publier."
        right={
          <div className="flex items-center gap-2">
            {sources.length > 1 && (
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="h-8 max-w-64 rounded-lg border border-ink-600 bg-ink-900 px-2 text-xs text-ink-200"
              >
                <option value="">Tous les lives</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.author} — {s.title}
                  </option>
                ))}
              </select>
            )}
            {settings && (
              <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(settings.output_dir_effective)}>
                Ouvrir le dossier
              </Button>
            )}
          </div>
        }
      />
      <div className="mb-4">
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { value: "pending", label: `À valider (${counts.pending})` },
            { value: "approved", label: `Approuvés (${counts.approved})` },
            { value: "rejected", label: `Rejetés (${counts.rejected})` },
            { value: "all", label: `Tous (${counts.all})` },
          ]}
        />
      </div>
      {shown.length ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(330px,1fr))] gap-5">
          {shown.map((c) => (
            <ClipCard key={c.id} clip={c} />
          ))}
        </div>
      ) : (
        <Empty icon={<Clapperboard className="size-6" />} title={clips.length ? "Aucun clip dans cette catégorie" : "Aucun clip pour l'instant"}>
          {clips.length ? "Change de filtre pour voir les autres clips." : "Lance un premier clipping avec le formulaire ci-dessus."}
        </Empty>
      )}
    </section>
  );
}

function ClipCard({ clip }: { clip: Clip }) {
  const toast = useStore((s) => s.toast);
  const upsertClip = useStore((s) => s.upsertClip);
  const [hook, setHook] = useState(clip.hook);
  const [caption, setCaption] = useState(clip.caption);
  const [tags, setTags] = useState(clip.hashtags.join(" "));
  const [saving, setSaving] = useState(false);
  const [showFinal, setShowFinal] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [schedule, setSchedule] = useState(false);
  const [lastClip, setLastClip] = useState(clip);

  // resynchronise les champs quand le clip change côté serveur (sans écraser une saisie en cours)
  if (lastClip !== clip) {
    if (hook === lastClip.hook) setHook(clip.hook);
    if (caption === lastClip.caption) setCaption(clip.caption);
    if (tags === lastClip.hashtags.join(" ")) setTags(clip.hashtags.join(" "));
    setLastClip(clip);
  }

  const dirty = hook !== clip.hook || caption !== clip.caption || tags !== clip.hashtags.join(" ");
  const hookChanged = hook.trim() !== clip.hook;

  async function save() {
    setSaving(true);
    try {
      const c = await api.patch<Clip>(`/api/clips/${clip.id}`, { hook, caption, hashtags: tags });
      upsertClip(c);
      toast(hookChanged ? "Accroche modifiée : remontage du clip en cours…" : "Modifications enregistrées", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(action: "approve" | "reject") {
    try {
      upsertClip(await api.post<Clip>(`/api/clips/${clip.id}/${action}`));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  const published = clip.publications.filter((p) => p.status === "published");
  const planned = clip.publications.filter((p) => p.status === "scheduled" || p.status === "running");

  return (
    <Card className={cx("animate-fade-up flex flex-col overflow-hidden", clip.status === "approved" && "ring-1 ring-emerald-500/40", clip.status === "rejected" && "opacity-60")}>
      <div className="relative flex justify-center bg-black">
        <video key={clip.video_url} src={clip.video_url} poster={clip.thumb_url} controls preload="none" className="aspect-[9/16] max-h-[440px] w-auto bg-black" />
        <div className="absolute top-2 left-2 flex gap-1.5">
          <ScoreBadge score={clip.score} />
          <Badge className="bg-black/60 tabular-nums">{fmtDuration(clip.duration)}</Badge>
        </div>
        {clip.status !== "pending" && (
          <div className="absolute top-2 right-2">
            {clip.status === "approved" ? <Badge color="green">Approuvé</Badge> : <Badge color="red">Rejeté</Badge>}
          </div>
        )}
        {clip.rendering && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 text-sm text-ink-100 backdrop-blur-sm">
            <Loader2 className="size-6 animate-spin text-brand-400" />
            Remontage avec la nouvelle accroche…
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <h3 className="font-semibold leading-snug text-ink-100">{clip.title || "Sans titre"}</h3>
          <p className="mt-0.5 text-xs text-ink-400 tabular-nums">
            {fmtDuration(clip.start)} → {fmtDuration(clip.end)} dans le live
          </p>
          <div className="mt-1.5">
            <SourceLine source={clip.source} compact />
          </div>
        </div>
        <Field label="Accroche (affichée 3 s en haut)" hint={hookChanged ? "Enregistrer relancera le montage de ce clip." : undefined}>
          <Input value={hook} onChange={(e) => setHook(e.target.value)} maxLength={80} placeholder="Aucune accroche" disabled={clip.rendering} />
        </Field>
        <Field label="Légende">
          <Textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={2} />
        </Field>
        <Field label="Hashtags">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="#gaming #twitch" />
        </Field>
        {dirty && (
          <div className="flex gap-2">
            <Button size="sm" variant="primary" loading={saving} icon={hookChanged ? <Wand2 className="size-3.5" /> : <Check className="size-3.5" />} onClick={save}>
              {hookChanged ? "Enregistrer et remonter" : "Enregistrer"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setHook(clip.hook);
                setCaption(clip.caption);
                setTags(clip.hashtags.join(" "));
              }}
            >
              Annuler
            </Button>
          </div>
        )}
        <div>
          <button onClick={() => setShowFinal(!showFinal)} className="flex items-center gap-1 text-xs text-ink-300 hover:text-ink-100 cursor-pointer">
            <ChevronDown className={cx("size-3.5 transition", showFinal && "rotate-180")} /> Légende publiée (avec crédit de la source)
          </button>
          {showFinal && (
            <div className="relative mt-2 rounded-lg border border-ink-700 bg-ink-900 p-3 pr-9 text-xs whitespace-pre-wrap text-ink-200">
              {clip.final_caption}
              <button
                className="absolute top-2 right-2 rounded p-1 text-ink-400 hover:bg-ink-700 hover:text-white cursor-pointer"
                title="Copier"
                onClick={() => {
                  navigator.clipboard?.writeText(clip.final_caption);
                  toast("Légende copiée", "success");
                }}
              >
                <Copy className="size-3.5" />
              </button>
            </div>
          )}
        </div>
        {(published.length > 0 || planned.length > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {published.map((p) => (
              <Badge key={p.id} color="green">
                Publié
              </Badge>
            ))}
            {planned.map((p) => (
              <Badge key={p.id} color="blue">
                Programmé
              </Badge>
            ))}
          </div>
        )}
        <div className="mt-auto flex flex-wrap gap-2 border-t border-ink-700 pt-3">
          {clip.status !== "approved" && (
            <Button size="sm" variant="success" icon={<Check className="size-3.5" />} onClick={() => setStatus("approve")}>
              Approuver
            </Button>
          )}
          {clip.status === "approved" && (
            <Button size="sm" variant="primary" icon={<Send className="size-3.5" />} onClick={() => setSchedule(true)}>
              Programmer
            </Button>
          )}
          {clip.status !== "rejected" && (
            <Button size="sm" variant="secondary" icon={<X className="size-3.5" />} onClick={() => setStatus("reject")}>
              Rejeter
            </Button>
          )}
          <Button size="sm" variant="danger" className="ml-auto" icon={<Trash2 className="size-3.5" />} onClick={() => setConfirmDelete(true)}>
            Supprimer
          </Button>
        </div>
      </div>
      <Confirm
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Supprimer ce clip ?"
        message="La vidéo sera supprimée du disque et les publications programmées seront annulées."
        confirmLabel="Supprimer"
        danger
        onConfirm={async () => {
          try {
            await api.del(`/api/clips/${clip.id}`);
            toast("Clip supprimé", "success");
          } catch (e) {
            toast((e as Error).message, "error");
          }
        }}
      />
      {schedule && <ScheduleModal clip={clip} onClose={() => setSchedule(false)} />}
    </Card>
  );
}
