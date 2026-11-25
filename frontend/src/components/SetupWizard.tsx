import { Check, Cpu, Download, KeyRound, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import { Badge, Button, ExtLink, Input, ProgressBar, cx } from "./ui";

interface SetupStatus {
  setup_done: boolean;
  whisper_model: string;
  models: { name: string; size: string; installed: boolean }[];
  gpu: { present: boolean; name: string | null; windows: boolean; cuda_libs: boolean; cuda_ok: boolean; detail: string };
  has_anthropic_key: boolean;
  task: { task: string | null; label: string | null; progress: number; done_bytes: number; total_bytes: number; status: string; error: string | null };
}

const DESCR: Record<string, string> = {
  tiny: "Test rapide, qualité faible",
  base: "Rapide, qualité moyenne",
  small: "Bon compromis sur processeur",
  medium: "Précis, plus lent sur processeur",
  "large-v3": "Le plus précis (GPU conseillé)",
  "large-v3-turbo": "Presque aussi précis, bien plus rapide (GPU conseillé)",
};

function fmtBytes(n: number) {
  if (n > 1e9) return `${(n / 1e9).toFixed(2)} Go`;
  return `${(n / 1e6).toFixed(0)} Mo`;
}

export function SetupWizard() {
  const toast = useStore((s) => s.toast);
  const [st, setSt] = useState<SetupStatus | null>(null);
  const [step, setStep] = useState(0);
  const [model, setModel] = useState<string>("");
  const [key, setKey] = useState("");

  const refresh = () => api.get<SetupStatus>("/api/setup/status").then((s) => {
    setSt(s);
    setModel((m) => m || (s.gpu.present ? "large-v3-turbo" : "small"));
    return s;
  });

  useEffect(() => {
    refresh();
    // la progression arrive par WebSocket (événement setup.progress) : on rafraîchit régulièrement
    const t = window.setInterval(() => refresh().catch(() => undefined), 1000);
    return () => window.clearInterval(t);
  }, []);

  if (!st) return null;
  const task = st.task;
  const running = task.status === "running";

  async function finish() {
    try {
      if (key.trim()) await api.put("/api/settings", { anthropic_api_key: key.trim() });
      await api.put("/api/settings", { whisper_model: model });
      await api.post("/api/setup/finish");
      await useStore.getState().loadSettings();
      toast("Live Clipper est prêt ! Colle ton premier lien de live.", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  const steps = ["Bienvenue", "Transcription", "Carte graphique", "Intelligence artificielle"];
  const modelOk = st.models.find((m) => m.name === model)?.installed;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/90 p-6 backdrop-blur">
      <div className="animate-fade-up w-full max-w-3xl overflow-hidden rounded-3xl border border-ink-600 bg-ink-850 shadow-2xl">
        <div className="relative overflow-hidden border-b border-ink-700 px-8 pt-7 pb-5">
          <div className="pointer-events-none absolute -top-20 -right-10 size-64 rounded-full bg-pink-500/10 blur-3xl" />
          <div className="flex items-center gap-3">
            <img src="/icon.svg" className="size-10" alt="" />
            <div>
              <h2 className="text-xl font-semibold">Bienvenue dans Live Clipper</h2>
              <p className="text-sm text-ink-300">Quelques réglages avant ton premier clip.</p>
            </div>
            <button onClick={finish} className="ml-auto rounded-md p-1 text-ink-400 hover:bg-ink-700 hover:text-white cursor-pointer" title="Passer">
              <X className="size-5" />
            </button>
          </div>
          <div className="mt-6 flex gap-2">
            {steps.map((s, i) => (
              <div key={s} className="flex-1">
                <div className={cx("h-1 rounded-full", i <= step ? "gradient-bg" : "bg-ink-700")} />
                <div className={cx("mt-1.5 text-xs", i === step ? "text-ink-100" : "text-ink-400")}>{s}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="min-h-[340px] px-8 py-6">
          {step === 0 && (
            <div className="space-y-4 text-sm text-ink-200">
              <p className="text-base">Live Clipper transforme tes lives Twitch, YouTube et Kick en clips verticaux prêts à publier :</p>
              <ul className="space-y-2.5">
                {[
                  ["Télécharge", "le live (ou un passage précis)"],
                  ["Transcrit", "la parole avec Whisper, sur ta carte graphique si possible"],
                  ["Repère", "les moments forts grâce à l'IA Claude et aux pics de volume"],
                  ["Monte", "des clips 9:16 sous-titrés avec une accroche, en créditant la source"],
                  ["Publie", "sur Instagram et TikTok selon tes règles, après ta validation"],
                ].map(([a, b]) => (
                  <li key={a} className="flex items-start gap-2.5">
                    <Check className="mt-0.5 size-4 text-emerald-400" />
                    <span>
                      <b className="text-ink-100">{a}</b> {b}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-ink-400">Ne clippe que des créateurs qui t'ont donné leur accord : le crédit en légende ne suffit pas en cas de réclamation.</p>
            </div>
          )}

          {step === 1 && (
            <div>
              <p className="mb-4 text-sm text-ink-300">Choisis le modèle de transcription. Il est téléchargé une seule fois.</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {st.models.map((m) => (
                  <button
                    key={m.name}
                    disabled={running}
                    onClick={() => setModel(m.name)}
                    className={cx(
                      "flex items-start gap-3 rounded-xl border p-3 text-left transition cursor-pointer disabled:cursor-not-allowed",
                      model === m.name ? "border-brand-500 bg-brand-500/10" : "border-ink-600 hover:border-ink-500",
                    )}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        {m.name}
                        {m.name === (st.gpu.present ? "large-v3-turbo" : "small") && <Badge color="violet">Recommandé</Badge>}
                      </div>
                      <div className="text-xs text-ink-400">
                        {DESCR[m.name]} · {m.size}
                      </div>
                    </div>
                    {m.installed && <Badge color="green">Installé</Badge>}
                  </button>
                ))}
              </div>
              <DownloadBox task={task} kind="whisper" />
              <div className="mt-4 flex gap-2">
                {!modelOk && (
                  <Button
                    variant="primary"
                    icon={<Download className="size-4" />}
                    loading={running && task.task === "whisper"}
                    disabled={running}
                    onClick={() => api.post("/api/setup/whisper", { model }).then(refresh).catch((e) => toast(e.message, "error"))}
                  >
                    Télécharger {model}
                  </Button>
                )}
                {running && (
                  <Button variant="ghost" onClick={() => api.post("/api/setup/cancel")}>
                    Annuler
                  </Button>
                )}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center gap-3 rounded-xl border border-ink-600 p-4">
                <Cpu className={cx("size-6", st.gpu.present ? "text-emerald-400" : "text-ink-400")} />
                <div>
                  <div className="font-medium">{st.gpu.present ? `Carte NVIDIA détectée : ${st.gpu.name}` : "Aucune carte graphique NVIDIA détectée"}</div>
                  <div className="text-xs text-ink-400">
                    {st.gpu.present
                      ? st.gpu.cuda_ok
                        ? "Le GPU est prêt pour la transcription (float16)."
                        : "Il manque les bibliothèques CUDA pour utiliser le GPU."
                      : "La transcription utilisera le processeur (int8) : c'est plus lent mais ça marche."}
                  </div>
                </div>
              </div>
              {st.gpu.present && st.gpu.windows && !st.gpu.cuda_libs && (
                <>
                  <p className="text-ink-300">Pour transcrire jusqu'à 10× plus vite, télécharge les bibliothèques NVIDIA cuBLAS et cuDNN (environ 1 Go, une seule fois).</p>
                  <DownloadBox task={task} kind="cuda" />
                  <Button
                    variant="primary"
                    icon={<Download className="size-4" />}
                    loading={running && task.task === "cuda"}
                    disabled={running}
                    onClick={() => api.post("/api/setup/cuda").then(refresh).catch((e) => toast(e.message, "error"))}
                  >
                    Télécharger les bibliothèques GPU
                  </Button>
                </>
              )}
              {st.gpu.cuda_libs && <Badge color="green">Bibliothèques GPU installées</Badge>}
              <p className="text-xs text-ink-400">L'encodeur vidéo NVENC (GPU) peut aussi être activé dans les Paramètres.</p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4 text-sm">
              <div className="flex items-start gap-3">
                <Sparkles className="mt-0.5 size-5 text-brand-400" />
                <p className="text-ink-300">
                  Le repérage des moments forts utilise Claude (API Anthropic). Crée une clé sur <ExtLink href="https://console.anthropic.com/settings/keys">console.anthropic.com</ExtLink> et colle-la
                  ci-dessous. Elle est rangée dans le Gestionnaire d'identification Windows.
                </p>
              </div>
              {st.has_anthropic_key ? (
                <Badge color="green">Clé déjà enregistrée</Badge>
              ) : (
                <div className="flex items-center gap-2">
                  <KeyRound className="size-4 text-ink-400" />
                  <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…" autoComplete="off" />
                </div>
              )}
              <p className="text-xs text-ink-400">Sans clé, Live Clipper se base uniquement sur les pics de volume (rires, cris).</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-ink-700 px-8 py-4">
          <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
            Retour
          </Button>
          {step < steps.length - 1 ? (
            <Button variant="primary" onClick={() => setStep(step + 1)}>
              {step === 1 && !modelOk ? "Plus tard" : "Continuer"}
            </Button>
          ) : (
            <Button variant="primary" icon={<Check className="size-4" />} onClick={finish}>
              Terminer
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function DownloadBox({ task, kind }: { task: SetupStatus["task"]; kind: string }) {
  if (task.task !== kind || task.status === "idle") return null;
  return (
    <div className="mt-4 rounded-xl border border-ink-600 bg-ink-900 p-4">
      <div className="mb-2 flex justify-between text-xs text-ink-300">
        <span className="truncate">{task.label}</span>
        <span className="tabular-nums">
          {task.total_bytes ? `${fmtBytes(task.done_bytes)} / ${fmtBytes(task.total_bytes)} · ` : ""}
          {Math.round(task.progress * 100)} %
        </span>
      </div>
      <ProgressBar value={task.progress} active={task.status === "running"} />
      {task.status === "done" && <p className="mt-2 text-xs text-emerald-300">✔ Téléchargement terminé</p>}
      {task.error && <p className="mt-2 text-xs text-red-300">{task.error}</p>}
    </div>
  );
}
