import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clapperboard,
  Copy,
  Eye,
  EyeOff,
  FolderOpen,
  Link2,
  Loader2,
  Plus,
  Send,
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
  cx,
  fmtDay,
  fmtDuration,
} from "../components/ui";
import { useStore } from "../store";
import type { Clip, Job, Source, Stream } from "../types";

export function ClippingPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          <span className="gradient-text">Lives</span>
        </h1>
        <p className="mt-1 text-sm text-ink-300">Dépose tes liens de lives, en direct ou terminés. Ils sont clippés automatiquement ; les clips arrivent dans l'onglet Clips.</p>
      </header>
      <LiveDepot />
      <StreamsSection />
    </div>
  );
}

export function ClipsPage() {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          <span className="gradient-text">Clips</span>
        </h1>
        <p className="mt-1 text-sm text-ink-300">Tous les clips créés à partir de tes lives. Rejette ceux que tu ne veux pas voir publiés.</p>
      </header>
      <Gallery />
    </div>
  );
}

// ------------------------------------------------------------------ dépôt de lives (liens uniquement)
function LiveDepot() {
  const settings = useStore((s) => s.settings);
  const toast = useStore((s) => s.toast);
  const [urls, setUrls] = useState("");
  const [busy, setBusy] = useState(false);
  const count = useMemo(() => (urls.match(/https?:\/\/\S+/g) || []).length, [urls]);

  async function submit() {
    setBusy(true);
    try {
      const res = await api.post<{ jobs: Job[]; streams?: number; warning?: string }>("/api/jobs", { urls, options: {} });
      toast(`${res.streams ?? res.jobs.length} live(s) ajouté(s) à la liste`, "success");
      if (res.warning) toast(res.warning, "warning");
      setUrls("");
      useStore.getState().loadStreams();
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
      <div className="relative">
        <h2 className="mb-1 text-lg font-semibold">Dépôt de lives</h2>
        <p className="mb-4 text-sm text-ink-300">Un lien par ligne : chaîne en direct (ex. twitch.tv/pseudo) ou rediffusion. Twitch, YouTube, Kick.</p>
        <Textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={4}
          placeholder={"https://www.twitch.tv/pseudo\nhttps://www.twitch.tv/videos/123456789\nhttps://www.youtube.com/watch?v=…\nhttps://kick.com/pseudo"}
          className="font-mono text-[13px]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && count) submit();
          }}
        />
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" icon={<Plus className="size-4" />} loading={busy} disabled={!urls.trim()} onClick={submit}>
            Ajouter {count > 1 ? `ces ${count} lives` : "à la liste"}
          </Button>
          {settings && !settings.secrets.anthropic_api_key && (
            <span className="flex items-center gap-1.5 text-xs text-amber-300">
              <AlertTriangle className="size-3.5" /> Sans clé API Anthropic, le repérage se limite aux pics de volume.
            </span>
          )}
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
        title="Liste des lives"
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
        <div className={cx("truncate", STATE_STYLE[st.state])} title={st.label}>
          {st.label}
        </div>
        {st.progress != null && <ProgressBar value={st.progress} active className="my-1 h-1.5" />}
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
