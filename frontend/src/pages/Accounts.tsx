import { AlertTriangle, BookOpen, Camera, ChevronDown, ClipboardPaste, Globe, Plug, Plus, RefreshCw, ShieldCheck, Trash2, UserCheck } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../api";
import { DevGuide } from "../components/DevGuide";
import { Badge, Button, Card, Confirm, Empty, Field, Input, Modal, PlatformIcon, Select, cx } from "../components/ui";
import { useStore } from "../store";
import type { Account, Platform } from "../types";

const PLATFORM_NAMES: Record<Platform, string> = { instagram: "Instagram", tiktok: "TikTok" };
const PLATFORM_BG: Record<Platform, string> = {
  instagram: "bg-gradient-to-br from-amber-400 via-pink-500 to-purple-600",
  tiktok: "bg-gradient-to-br from-cyan-400 via-ink-900 to-pink-500",
};
const PRIVACY: { value: string; label: string }[] = [
  { value: "SELF_ONLY", label: "Moi uniquement (obligatoire tant que l'app n'est pas auditée)" },
  { value: "MUTUAL_FOLLOW_FRIENDS", label: "Amis" },
  { value: "FOLLOWER_OF_CREATOR", label: "Abonnés" },
  { value: "PUBLIC_TO_EVERYONE", label: "Tout le monde" },
];

export function AccountsPage() {
  const accounts = useStore((s) => s.accounts);
  const [adding, setAdding] = useState(false);
  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Comptes</h1>
          <p className="mt-1 text-sm text-ink-300">Tes comptes Instagram et TikTok, leur connexion et leurs règles de publication.</p>
        </div>
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
          Ajouter un compte
        </Button>
      </header>
      {accounts.length ? (
        <div className="grid items-start gap-5 xl:grid-cols-2">
          {accounts.map((a) => (
            <AccountCard key={a.id} account={a} />
          ))}
        </div>
      ) : (
        <Empty icon={<UserCheck className="size-6" />} title="Aucun compte">
          Ajoute un compte Instagram ou TikTok pour programmer la publication de tes clips.
        </Empty>
      )}
      {adding && <AddAccountModal onClose={() => setAdding(false)} />}
    </div>
  );
}

function Avatar({ account, size = "size-14" }: { account: Account; size?: string }) {
  const [broken, setBroken] = useState(false);
  if (account.avatar_url && !broken)
    return <img src={account.avatar_url} onError={() => setBroken(true)} className={cx(size, "rounded-2xl object-cover ring-2 ring-ink-700")} alt="" />;
  return (
    <div className={cx(size, "flex items-center justify-center rounded-2xl text-lg font-semibold text-white", PLATFORM_BG[account.platform])}>
      {account.name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function StatusBadge({ account }: { account: Account }) {
  if (account.status === "connected") return <Badge color="green">● Connecté</Badge>;
  if (account.status === "reconnect") return <Badge color="amber">● À reconnecter</Badge>;
  return <Badge>● Non connecté</Badge>;
}

function AccountCard({ account }: { account: Account }) {
  const toast = useStore((s) => s.toast);
  const upsert = useStore((s) => s.upsertAccount);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [paste, setPaste] = useState(false);
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const loginOpen = account.mode === "browser" && account.status_message?.startsWith("Fenêtre de connexion");

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true);
    try {
      await fn();
      if (ok) toast(ok, "info");
    } catch (e) {
      const msg = (e as Error).message;
      toast(msg, "error");
      if (msg.includes("Paramètres")) setGuide(true);
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    await run(async () => {
      const r = await api.post<{ mode: string; auth_url?: string }>(`/api/accounts/${account.id}/connect`);
      if (r.mode === "api") toast("Page d'autorisation ouverte dans ton navigateur. Accepte les autorisations puis reviens ici.", "info");
      else toast("Une fenêtre de navigateur s'ouvre : connecte-toi à ton compte, puis clique sur « J'ai terminé ».", "info");
    });
  }

  async function uploadAvatar(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    const res = await fetch(`/api/accounts/${account.id}/avatar`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) toast(data.detail, "error");
    else upsert({ ...data, avatar_url: data.avatar_url + "?t=" + Date.now() });
  }

  return (
    <Card className="animate-fade-up overflow-hidden">
      <div className="flex items-start gap-4 p-5">
        <div className="group relative">
          <Avatar account={account} />
          <button
            onClick={() => fileRef.current?.click()}
            className="absolute inset-0 flex items-center justify-center rounded-2xl bg-black/60 opacity-0 transition group-hover:opacity-100 cursor-pointer"
            title="Changer l'avatar"
          >
            <Camera className="size-5 text-white" />
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadAvatar(e.target.files[0])} />
          <span className={cx("absolute -right-1.5 -bottom-1.5 rounded-lg p-1 text-white ring-2 ring-ink-850", PLATFORM_BG[account.platform])}>
            <PlatformIcon platform={account.platform} className="size-3.5" />
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold">{account.name}</h3>
            <StatusBadge account={account} />
            <Badge color={account.mode === "api" ? "violet" : "blue"}>
              {account.mode === "api" ? <ShieldCheck className="size-3" /> : <Globe className="size-3" />}
              {account.mode === "api" ? "API officielle" : "Navigateur"}
            </Badge>
          </div>
          <p className="mt-0.5 text-sm text-ink-300">
            {PLATFORM_NAMES[account.platform]}
            {account.username && <> · @{account.username}</>}
          </p>
          {account.status_message && (
            <p className={cx("mt-1.5 flex items-start gap-1.5 text-xs", account.status === "connected" ? "text-ink-300" : "text-amber-300")}>
              <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {account.status_message}
            </p>
          )}
        </div>
      </div>

      {account.pending_choices && (
        <div className="mx-5 mb-4 rounded-xl border border-brand-500/30 bg-brand-500/5 p-3">
          <p className="mb-2 text-sm font-medium">Plusieurs comptes Instagram trouvés : lequel utiliser ?</p>
          <div className="flex flex-wrap gap-2">
            {account.pending_choices.map((c) => (
              <Button
                key={c.id}
                size="sm"
                variant="secondary"
                onClick={() => run(async () => upsert(await api.post<Account>(`/api/accounts/${account.id}/choose`, { external_id: c.id })))}
              >
                @{c.username}
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-ink-700 bg-ink-900/40 px-5 py-3">
        {loginOpen ? (
          <Button size="sm" variant="primary" icon={<UserCheck className="size-3.5" />} onClick={() => run(() => api.post(`/api/accounts/${account.id}/login-done`))}>
            J'ai terminé
          </Button>
        ) : (
          <Button size="sm" variant={account.status === "connected" ? "secondary" : "primary"} icon={<Plug className="size-3.5" />} loading={busy} onClick={connect}>
            {account.status === "connected" ? "Reconnecter" : "Se connecter"}
          </Button>
        )}
        {account.status !== "disconnected" && (
          <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => run(() => api.post(`/api/accounts/${account.id}/check`), "Vérification en cours…")}>
            Vérifier
          </Button>
        )}
        {account.mode === "api" && account.status !== "connected" && (
          <Button size="sm" variant="ghost" icon={<ClipboardPaste className="size-3.5" />} onClick={() => setPaste(true)}>
            Coller l'adresse de retour
          </Button>
        )}
        <Button size="sm" variant="ghost" icon={<ChevronDown className={cx("size-3.5 transition", rulesOpen && "rotate-180")} />} onClick={() => setRulesOpen(!rulesOpen)}>
          Règles de publication
        </Button>
        <Button size="sm" variant="ghost" className="ml-auto text-red-300 hover:text-red-200" aria-label="Supprimer" icon={<Trash2 className="size-3.5" />} onClick={() => setConfirmDel(true)} />
      </div>
      {rulesOpen && <RulesEditor account={account} />}

      <Confirm
        open={confirmDel}
        onClose={() => setConfirmDel(false)}
        title={`Supprimer « ${account.name} » ?`}
        message="Les jetons de connexion, le profil de navigateur et les publications programmées de ce compte seront supprimés. L'historique des posts publiés est conservé."
        danger
        confirmLabel="Supprimer"
        onConfirm={() => run(() => api.del(`/api/accounts/${account.id}`), "Compte supprimé")}
      />
      {paste && <PasteModal account={account} onClose={() => setPaste(false)} />}
      {guide && <DevGuide platform={account.platform} onClose={() => setGuide(false)} />}
    </Card>
  );
}

function RulesEditor({ account }: { account: Account }) {
  const toast = useStore((s) => s.toast);
  const upsert = useStore((s) => s.upsertAccount);
  const [r, setR] = useState({
    auto_publish: account.auto_publish,
    require_approval: account.require_approval,
    min_score: account.min_score,
    max_per_day: account.max_per_day,
    time_windows: account.time_windows.map((w) => [...w]) as [string, string][],
    delay_min_minutes: account.delay_min_minutes,
    delay_max_minutes: account.delay_max_minutes,
    privacy_level: account.privacy_level ?? "SELF_ONLY",
  });
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof typeof r>(k: K, v: (typeof r)[K]) => setR((x) => ({ ...x, [k]: v }));

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = { ...r };
      if (account.platform !== "tiktok") delete body.privacy_level;
      upsert(await api.patch<Account>(`/api/accounts/${account.id}`, body));
      toast("Règles enregistrées", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="animate-fade-up space-y-5 border-t border-ink-700 p-5">
      <p className="text-xs text-ink-400">Ces règles fixent le rythme des publications lancées depuis l'onglet Publier.</p>
      <div className="grid gap-4 md:grid-cols-4">
        <Field label={`Score minimal : ${r.min_score.toFixed(1)}/10`}>
          <input type="range" min={0} max={10} step={0.5} value={r.min_score} onChange={(e) => set("min_score", +e.target.value)} className="mt-2 w-full accent-brand-500" />
        </Field>
        <Field label="Posts max / jour">
          <Input type="number" min={1} max={50} value={r.max_per_day} onChange={(e) => set("max_per_day", +e.target.value)} />
        </Field>
        <Field label="Délai min (minutes)">
          <Input type="number" min={0} value={r.delay_min_minutes} onChange={(e) => set("delay_min_minutes", +e.target.value)} />
        </Field>
        <Field label="Délai max (minutes)" hint="Délai aléatoire entre deux posts.">
          <Input type="number" min={0} value={r.delay_max_minutes} onChange={(e) => set("delay_max_minutes", +e.target.value)} />
        </Field>
      </div>
      <Field label="Plages horaires de publication">
        <div className="space-y-2">
          {r.time_windows.map((w, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input type="time" value={w[0]} className="w-32" onChange={(e) => set("time_windows", r.time_windows.map((x, j) => (j === i ? [e.target.value, x[1]] : x)) as [string, string][])} />
              <span className="text-ink-400">→</span>
              <Input type="time" value={w[1]} className="w-32" onChange={(e) => set("time_windows", r.time_windows.map((x, j) => (j === i ? [x[0], e.target.value] : x)) as [string, string][])} />
              <Button size="sm" variant="ghost" aria-label="Retirer" icon={<Trash2 className="size-3.5" />} onClick={() => set("time_windows", r.time_windows.filter((_, j) => j !== i))} />
            </div>
          ))}
          <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => set("time_windows", [...r.time_windows, ["18:00", "22:00"]])}>
            Ajouter une plage
          </Button>
        </div>
      </Field>
      {account.platform === "tiktok" && account.mode === "api" && (
        <Field label="Visibilité des vidéos TikTok" className="max-w-md">
          <Select value={r.privacy_level} onChange={(e) => set("privacy_level", e.target.value)}>
            {PRIVACY.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Button variant="primary" loading={saving} onClick={save}>
        Enregistrer les règles
      </Button>
    </div>
  );
}

function PasteModal({ account, onClose }: { account: Account; onClose: () => void }) {
  const toast = useStore((s) => s.toast);
  const upsert = useStore((s) => s.upsertAccount);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Terminer la connexion manuellement" width="max-w-lg">
      <p className="text-sm text-ink-300">
        Si la page de retour ne s'est pas chargée (adresse de redirection différente), copie l'adresse complète de cette page depuis la barre d'adresse de ton navigateur et colle-la ici.
      </p>
      <Input className="mt-4 font-mono text-xs" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/callback?code=…&state=…" />
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Annuler
        </Button>
        <Button
          variant="primary"
          loading={busy}
          disabled={!url.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              upsert(await api.post<Account>(`/api/accounts/${account.id}/oauth-code`, { url }));
              toast("Connexion terminée", "success");
              onClose();
            } catch (e) {
              toast((e as Error).message, "error");
            } finally {
              setBusy(false);
            }
          }}
        >
          Valider
        </Button>
      </div>
    </Modal>
  );
}

function AddAccountModal({ onClose }: { onClose: () => void }) {
  const toast = useStore((s) => s.toast);
  const upsert = useStore((s) => s.upsertAccount);
  const settings = useStore((s) => s.settings);
  const [platform, setPlatform] = useState<Platform>("instagram");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"api" | "browser">("api");
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState(false);
  const appMissing = settings && (platform === "instagram" ? !settings.meta_app_id || !settings.secrets.meta_app_secret : !settings.tiktok_client_key || !settings.secrets.tiktok_client_secret);

  async function create() {
    setBusy(true);
    try {
      const a = await api.post<Account>("/api/accounts", { platform, name: name || PLATFORM_NAMES[platform], mode });
      upsert(a);
      toast(
        mode === "browser"
          ? "Compte ajouté : une fenêtre de navigateur s'ouvre (quelques secondes). Connecte-toi, puis clique sur « J'ai terminé »."
          : "Compte ajouté : clique sur « Se connecter ».",
        "success",
      );
      onClose();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Ajouter un compte">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3">
          {(["instagram", "tiktok"] as Platform[]).map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={cx(
                "flex items-center gap-3 rounded-xl border p-4 text-left transition cursor-pointer",
                platform === p ? "border-brand-500 bg-brand-500/10" : "border-ink-600 hover:border-ink-500",
              )}
            >
              <span className={cx("rounded-xl p-2.5 text-white", PLATFORM_BG[p])}>
                <PlatformIcon platform={p} className="size-5" />
              </span>
              <div>
                <div className="font-medium">{PLATFORM_NAMES[p]}</div>
                <div className="text-xs text-ink-400">{p === "instagram" ? "Reels" : "Vidéos"}</div>
              </div>
            </button>
          ))}
        </div>
        <Field label="Nom affiché dans Live Clipper">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={`Mon ${PLATFORM_NAMES[platform]}`} autoFocus />
        </Field>
        <Field label="Mode de connexion">
          <div className="grid gap-3 md:grid-cols-2">
            <ModeCard active={mode === "api"} onClick={() => setMode("api")} icon={<ShieldCheck className="size-4" />} title="API officielle (recommandé)">
              {platform === "instagram" ? "Graph API : compte professionnel relié à une Page Facebook." : "Content Posting API de TikTok."} Nécessite ton app développeur.
            </ModeCard>
            <ModeCard active={mode === "browser"} onClick={() => setMode("browser")} icon={<Globe className="size-4" />} title="Navigateur (secours)">
              Profil de navigateur dédié : tu te connectes toi-même une fois.
            </ModeCard>
          </div>
        </Field>
        {mode === "api" && appMissing && (
          <div className="flex items-start justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-200">
            <span>Les identifiants de ton app {platform === "instagram" ? "Meta" : "TikTok"} ne sont pas encore renseignés dans les Paramètres.</span>
            <Button size="sm" variant="ghost" icon={<BookOpen className="size-3.5" />} onClick={() => setGuide(true)}>
              Guide
            </Button>
          </div>
        )}
        {mode === "browser" && (
          <p className="rounded-xl border border-ink-600 bg-ink-900 p-3 text-xs text-ink-300">
            ⚠ Publier via un navigateur automatisé est contraire aux conditions d'utilisation d'Instagram et de TikTok. Live Clipper ne contourne jamais un captcha ni une vérification : si l'une
            d'elles apparaît, la publication est mise en pause et tu es prévenu.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Annuler
          </Button>
          <Button variant="primary" loading={busy} onClick={create}>
            Ajouter
          </Button>
        </div>
      </div>
      {guide && <DevGuide platform={platform} onClose={() => setGuide(false)} />}
    </Modal>
  );
}

function ModeCard({ active, onClick, icon, title, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx("rounded-xl border p-3 text-left transition cursor-pointer", active ? "border-brand-500 bg-brand-500/10" : "border-ink-600 hover:border-ink-500")}
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        {icon}
        {title}
      </div>
      <p className="mt-1 text-xs text-ink-400">{children}</p>
    </button>
  );
}
