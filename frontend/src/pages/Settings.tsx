import { BookOpen, Cpu, Eye, EyeOff, FolderOpen, KeyRound, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, openFolder, pickFolder } from "../api";
import { DevGuide } from "../components/DevGuide";
import { Badge, Button, Card, ExtLink, Field, Input, Select, Segmented } from "../components/ui";
import { useStore } from "../store";
import type { Settings, SystemInfo } from "../types";

const MODEL_LABELS: Record<string, string> = {
  tiny: "tiny — très rapide, qualité faible (75 Mo)",
  base: "base — rapide (145 Mo)",
  small: "small — bon compromis (480 Mo)",
  medium: "medium — précis (1,5 Go)",
  "large-v3": "large-v3 — le plus précis, idéal avec un GPU (3 Go)",
  "large-v3-turbo": "large-v3-turbo — presque aussi précis, 3× plus rapide (1,6 Go)",
};
const AI_LABELS: Record<string, string> = {
  "claude-sonnet-5-5": "Claude Sonnet 5.5 — recommandé (rapide, économique)",
  "claude-opus-5-5": "Claude Opus 5.5 — le plus fin, plus cher",
  "claude-haiku-5-5": "Claude Haiku 5.5 — très économique",
};

export function SettingsPage() {
  const settings = useStore((s) => s.settings);
  const toast = useStore((s) => s.toast);
  const [form, setForm] = useState<Partial<Settings> & Record<string, unknown>>({});
  const [secretsForm, setSecretsForm] = useState({ anthropic_api_key: "", meta_app_secret: "", tiktok_client_secret: "" });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [guide, setGuide] = useState<null | "instagram" | "tiktok">(null);

  useEffect(() => {
    if (settings) setForm({ ...settings, default_hashtags: settings.default_hashtags.join(" ") as unknown as string[] });
  }, [settings]);
  useEffect(() => {
    api.get<SystemInfo>("/api/system").then(setSys).catch(() => undefined);
  }, []);

  if (!settings) return null;
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = { ...form };
      for (const k of ["secrets", "choices", "oauth_redirects", "data_dir", "output_dir_effective"]) delete body[k];
      Object.assign(body, secretsForm);
      const s = await api.put<Settings>("/api/settings", body);
      useStore.setState({ settings: s });
      setSecretsForm({ anthropic_api_key: "", meta_app_secret: "", tiktok_client_secret: "" });
      toast("Paramètres enregistrés", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function removeSecret(name: string) {
    const s = await api.del<Settings>(`/api/settings/secret/${name}`);
    useStore.setState({ settings: s });
    toast("Secret supprimé", "success");
  }

  async function testKey() {
    setTesting(true);
    try {
      if (secretsForm.anthropic_api_key) await save();
      const r = await api.post<{ message: string }>("/api/settings/test-anthropic");
      toast(r.message, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-6 pb-24">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Paramètres</h1>
        <p className="mt-1 text-sm text-ink-300">Les clés et secrets sont stockés dans le Gestionnaire d'identification Windows, jamais en clair.</p>
      </header>

      <Section icon={<KeyRound className="size-4" />} title="Intelligence artificielle" subtitle="Le repérage des moments forts utilise l'API Anthropic (Claude).">
        <div className="grid gap-4 md:grid-cols-2">
          <SecretField
            label="Clé API Anthropic"
            placeholder="sk-ant-…"
            stored={settings.secrets.anthropic_api_key}
            value={secretsForm.anthropic_api_key}
            onChange={(v) => setSecretsForm((s) => ({ ...s, anthropic_api_key: v }))}
            onRemove={() => removeSecret("anthropic_api_key")}
            hint={
              <>
                Crée une clé sur <ExtLink href="https://console.anthropic.com/settings/keys">console.anthropic.com</ExtLink>.
              </>
            }
            extra={
              <Button size="sm" variant="secondary" loading={testing} onClick={testKey} disabled={!settings.secrets.anthropic_api_key && !secretsForm.anthropic_api_key}>
                Tester
              </Button>
            }
          />
          <Field label="Modèle IA">
            <Select value={String(form.ai_model ?? "")} onChange={(e) => set("ai_model", e.target.value)}>
              {settings.choices.ai_model.map((m) => (
                <option key={m} value={m}>
                  {AI_LABELS[m] ?? m}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Section>

      <Section icon={<Cpu className="size-4" />} title="Transcription" subtitle="Whisper tourne sur ta carte graphique NVIDIA si elle est disponible, sinon sur le processeur.">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Modèle Whisper" hint="Les modèles manquants sont téléchargés automatiquement.">
            <Select value={String(form.whisper_model ?? "")} onChange={(e) => set("whisper_model", e.target.value)}>
              {settings.choices.whisper_model.map((m) => (
                <option key={m} value={m}>
                  {MODEL_LABELS[m] ?? m}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Langue des lives">
            <Select value={String(form.language ?? "fr")} onChange={(e) => set("language", e.target.value)}>
              {settings.choices.language.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Processeur de calcul"
            hint={sys ? (sys.gpu.available ? <span className="text-emerald-300">✔ {sys.gpu.detail}</span> : <span>{sys.gpu.detail} → CPU (int8)</span>) : undefined}
          >
            <Segmented
              value={String(form.device ?? "auto")}
              onChange={(v) => set("device", v)}
              options={[
                { value: "auto", label: "Automatique" },
                { value: "cuda", label: "GPU" },
                { value: "cpu", label: "CPU" },
              ]}
            />
          </Field>
        </div>
      </Section>

      <Section title="Montage" subtitle="Valeurs par défaut des nouveaux clips.">
        <div className="grid gap-4 md:grid-cols-4">
          <Field label="Encodeur vidéo" hint="NVENC encode sur le GPU NVIDIA (repli automatique sur libx264).">
            <Select value={String(form.encoder ?? "libx264")} onChange={(e) => set("encoder", e.target.value)}>
              <option value="libx264">libx264 (CPU, universel)</option>
              <option value="h264_nvenc">h264_nvenc (GPU NVIDIA)</option>
            </Select>
          </Field>
          <Field label="Police des sous-titres" hint="Nom d'une police installée sur Windows.">
            <Input value={String(form.font ?? "")} onChange={(e) => set("font", e.target.value)} list="fonts" />
            <datalist id="fonts">
              {["Arial Black", "Impact", "Montserrat", "Bebas Neue", "Segoe UI Black", "Verdana"].map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </Field>
          <Field label="Mots par ligne">
            <Input type="number" min={1} max={6} value={Number(form.words_per_line ?? 3)} onChange={(e) => set("words_per_line", +e.target.value)} />
          </Field>
          <Field label="Mise en page par défaut">
            <Segmented
              value={String(form.layout ?? "blur")}
              onChange={(v) => set("layout", v)}
              options={[
                { value: "blur", label: "Fond flou" },
                { value: "crop", label: "Recadrage" },
              ]}
            />
          </Field>
          <Field label="Clips max par live">
            <Input type="number" min={1} max={30} value={Number(form.max_clips ?? 5)} onChange={(e) => set("max_clips", +e.target.value)} />
          </Field>
          <Field label="Durée min (s)">
            <Input type="number" min={3} max={180} value={Number(form.min_len ?? 15)} onChange={(e) => set("min_len", +e.target.value)} />
          </Field>
          <Field label="Durée max (s)">
            <Input type="number" min={3} max={180} value={Number(form.max_len ?? 60)} onChange={(e) => set("max_len", +e.target.value)} />
          </Field>
          <Field label="Hashtags par défaut" hint="Ajoutés à chaque légende.">
            <Input value={String(form.default_hashtags ?? "")} onChange={(e) => set("default_hashtags", e.target.value)} placeholder="#live #clip #fyp" />
          </Field>
        </div>
      </Section>

      <Section icon={<FolderOpen className="size-4" />} title="Dossier de sortie" subtitle="Où sont enregistrés les clips montés.">
        <div className="flex gap-2">
          <Input value={String(form.output_dir ?? "")} onChange={(e) => set("output_dir", e.target.value)} placeholder={settings.output_dir_effective} />
          <Button
            variant="secondary"
            onClick={async () => {
              const p = await pickFolder(String(form.output_dir || settings.output_dir_effective));
              if (p) set("output_dir", p);
              else if (p === undefined) toast("Saisis le chemin du dossier dans le champ.", "info");
            }}
          >
            Parcourir…
          </Button>
          <Button variant="ghost" icon={<FolderOpen className="size-4" />} onClick={() => openFolder(settings.output_dir_effective)}>
            Ouvrir
          </Button>
        </div>
      </Section>

      <Section icon={<ShieldCheck className="size-4" />} title="Applications développeur" subtitle="Nécessaires pour publier via les API officielles d'Instagram et de TikTok.">
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-3 rounded-xl border border-ink-700 p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium">Meta (Instagram)</span>
              <Button size="sm" variant="ghost" icon={<BookOpen className="size-3.5" />} onClick={() => setGuide("instagram")}>
                Guide pas à pas
              </Button>
            </div>
            <Field label="ID de l'app">
              <Input value={String(form.meta_app_id ?? "")} onChange={(e) => set("meta_app_id", e.target.value)} placeholder="123456789012345" />
            </Field>
            <SecretField
              label="Clé secrète de l'app"
              stored={settings.secrets.meta_app_secret}
              value={secretsForm.meta_app_secret}
              onChange={(v) => setSecretsForm((s) => ({ ...s, meta_app_secret: v }))}
              onRemove={() => removeSecret("meta_app_secret")}
            />
            <RedirectHint url={settings.oauth_redirects.instagram} />
          </div>
          <div className="space-y-3 rounded-xl border border-ink-700 p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium">TikTok</span>
              <Button size="sm" variant="ghost" icon={<BookOpen className="size-3.5" />} onClick={() => setGuide("tiktok")}>
                Guide pas à pas
              </Button>
            </div>
            <Field label="Client key">
              <Input value={String(form.tiktok_client_key ?? "")} onChange={(e) => set("tiktok_client_key", e.target.value)} placeholder="aw1b2c3d4e5f…" />
            </Field>
            <SecretField
              label="Client secret"
              stored={settings.secrets.tiktok_client_secret}
              value={secretsForm.tiktok_client_secret}
              onChange={(v) => setSecretsForm((s) => ({ ...s, tiktok_client_secret: v }))}
              onRemove={() => removeSecret("tiktok_client_secret")}
            />
            <RedirectHint url={settings.oauth_redirects.tiktok} />
          </div>
        </div>
        <div className="mt-4 max-w-sm">
          <Field label="Navigateur du mode secours" hint="Edge est installé sur tous les PC Windows.">
            <Select value={String(form.browser_channel ?? "msedge")} onChange={(e) => set("browser_channel", e.target.value)}>
              <option value="msedge">Microsoft Edge</option>
              <option value="chrome">Google Chrome</option>
              <option value="chromium">Chromium (Playwright)</option>
            </Select>
          </Field>
        </div>
      </Section>

      <Section title="Système">
        <div className="grid gap-3 text-sm md:grid-cols-2">
          <Info label="Version">{sys?.version ?? "…"}</Info>
          <Info label="GPU">{sys ? sys.gpu.available ? <Badge color="green">{sys.gpu.detail}</Badge> : <Badge>{sys.gpu.detail}</Badge> : "…"}</Info>
          <Info label="ffmpeg">{sys?.ffmpeg ?? <span className="text-red-300">introuvable</span>}</Info>
          <Info label="yt-dlp">{sys?.yt_dlp ?? <span className="text-red-300">introuvable</span>}</Info>
          <Info label="Données">
            <button className="text-brand-400 hover:underline cursor-pointer" onClick={() => openFolder(settings.data_dir)}>
              {settings.data_dir}
            </button>
          </Info>
          <Info label="Journaux">
            {sys && (
              <button className="text-brand-400 hover:underline cursor-pointer" onClick={() => openFolder(sys.logs_dir)}>
                {sys.logs_dir}
              </button>
            )}
          </Info>
        </div>
      </Section>

      <div className="fixed right-8 bottom-6 z-40">
        <Button variant="primary" size="lg" icon={<Save className="size-4" />} loading={saving} onClick={save}>
          Enregistrer
        </Button>
      </div>
      {guide && <DevGuide platform={guide} onClose={() => setGuide(null)} />}
    </div>
  );
}

function Section({ icon, title, subtitle, children }: { icon?: ReactNode; title: string; subtitle?: string; children: ReactNode }) {
  return (
    <Card className="p-6">
      <div className="mb-5 flex items-start gap-3">
        {icon && <div className="rounded-lg bg-brand-500/15 p-2 text-brand-400">{icon}</div>}
        <div>
          <h2 className="font-semibold">{title}</h2>
          {subtitle && <p className="text-sm text-ink-300">{subtitle}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}

function SecretField({ label, stored, value, onChange, onRemove, placeholder, hint, extra }: { label: string; stored: boolean; value: string; onChange: (v: string) => void; onRemove: () => void; placeholder?: string; hint?: ReactNode; extra?: ReactNode }) {
  const [show, setShow] = useState(false);
  return (
    <Field label={label} hint={hint}>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={show ? "text" : "password"}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={stored ? "•••••••••••• (enregistrée — saisis pour remplacer)" : placeholder ?? "Non configuré"}
            className="pr-9"
            autoComplete="off"
          />
          <button type="button" onClick={() => setShow(!show)} className="absolute top-2 right-2 text-ink-400 hover:text-ink-100 cursor-pointer" aria-label="Afficher">
            {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
        {extra}
        {stored && <Button variant="ghost" aria-label="Supprimer" icon={<Trash2 className="size-4" />} onClick={onRemove} />}
      </div>
      {stored && <Badge color="green" className="mt-1.5">Enregistrée dans le coffre Windows</Badge>}
    </Field>
  );
}

function RedirectHint({ url }: { url: string }) {
  return (
    <p className="text-xs text-ink-400">
      URL de redirection à déclarer : <code className="rounded bg-ink-900 px-1.5 py-0.5 text-ink-200 select-all">{url}</code>
    </p>
  );
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-ink-900/60 px-3 py-2">
      <span className="w-20 shrink-0 text-xs text-ink-400 uppercase">{label}</span>
      <span className="min-w-0 truncate text-ink-200">{children}</span>
    </div>
  );
}
