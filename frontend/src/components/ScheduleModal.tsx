import { AlertTriangle, CalendarClock, Send } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import type { Clip } from "../types";
import { Badge, Button, Field, Input, Modal, PlatformIcon, Segmented, Textarea, cx } from "./ui";

function localInputValue(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ScheduleModal({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  const accounts = useStore((s) => s.accounts);
  const toast = useStore((s) => s.toast);
  const setTab = useStore((s) => s.setTab);
  const taken = new Set(clip.publications.filter((p) => ["scheduled", "running", "published", "paused"].includes(p.status)).map((p) => p.account_id));
  const [selected, setSelected] = useState<number[]>(accounts.filter((a) => a.status === "connected" && !taken.has(a.id)).map((a) => a.id));
  const [when, setWhen] = useState<"now" | "later">("now");
  const [date, setDate] = useState(localInputValue(new Date(Date.now() + 3600_000)));
  const [caption, setCaption] = useState(clip.final_caption);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const r = await api.post<{ created: number }>("/api/publications", {
        clip_id: clip.id,
        account_ids: selected,
        scheduled_at: when === "later" ? new Date(date).toISOString() : null,
        caption: caption !== clip.final_caption ? caption : null,
      });
      toast(`${r.created} publication(s) programmée(s)`, "success");
      onClose();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Programmer « ${clip.title || clip.id} »`} width="max-w-xl">
      {!accounts.length ? (
        <div className="text-sm text-ink-300">
          Aucun compte configuré.{" "}
          <button
            className="text-brand-400 hover:underline cursor-pointer"
            onClick={() => {
              onClose();
              setTab("accounts");
            }}
          >
            Ajoute un compte
          </button>{" "}
          pour publier tes clips.
        </div>
      ) : (
        <div className="space-y-5">
          <Field label="Comptes">
            <div className="space-y-2">
              {accounts.map((a) => {
                const already = taken.has(a.id);
                const checked = selected.includes(a.id);
                return (
                  <label
                    key={a.id}
                    className={cx(
                      "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition",
                      already ? "cursor-not-allowed opacity-50" : "cursor-pointer",
                      checked ? "border-brand-500 bg-brand-500/10" : "border-ink-600 hover:border-ink-500",
                    )}
                  >
                    <input
                      type="checkbox"
                      disabled={already}
                      checked={checked}
                      onChange={(e) => setSelected((s) => (e.target.checked ? [...s, a.id] : s.filter((x) => x !== a.id)))}
                      className="size-4 accent-brand-500"
                    />
                    <PlatformIcon platform={a.platform} />
                    <span className="flex-1 text-sm font-medium">{a.name}</span>
                    {already ? (
                      <Badge>Déjà programmé</Badge>
                    ) : a.status === "connected" ? (
                      <Badge color="green">Connecté</Badge>
                    ) : (
                      <Badge color="amber">
                        <AlertTriangle className="size-3" /> À connecter
                      </Badge>
                    )}
                  </label>
                );
              })}
            </div>
          </Field>
          <Field label="Quand ?">
            <div className="flex flex-wrap items-center gap-3">
              <Segmented
                value={when}
                onChange={setWhen}
                options={[
                  { value: "now", label: "Dès que possible" },
                  { value: "later", label: "À une date précise" },
                ]}
              />
              {when === "later" && <Input type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} className="w-56" />}
            </div>
          </Field>
          <Field label="Légende publiée" hint="Le crédit de la source est inclus automatiquement.">
            <Textarea rows={6} value={caption} onChange={(e) => setCaption(e.target.value)} className="text-xs" />
          </Field>
          {selected.some((id) => accounts.find((a) => a.id === id)?.status !== "connected") && (
            <p className="text-xs text-amber-300">Les comptes non connectés publieront dès qu'ils seront reconnectés.</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Annuler
            </Button>
            <Button variant="primary" loading={busy} disabled={!selected.length} icon={when === "now" ? <Send className="size-4" /> : <CalendarClock className="size-4" />} onClick={submit}>
              {when === "now" ? "Publier" : "Programmer"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
