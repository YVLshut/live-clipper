import { create } from "zustand";
import { api } from "./api";
import type { Account, Campaign, Clip, Job, Publication, Settings, Source, Toast } from "./types";

type Tab = "clipping" | "accounts" | "publishing" | "settings";

interface State {
  tab: Tab;
  connected: boolean;
  jobs: Job[];
  clips: Clip[];
  sources: Source[];
  accounts: Account[];
  publications: Publication[];
  campaigns: Campaign[];
  settings: Settings | null;
  toasts: Toast[];
  setTab: (t: Tab) => void;
  toast: (message: string, level?: Toast["level"]) => void;
  dismiss: (id: number) => void;
  loadAll: () => Promise<void>;
  loadJobs: () => Promise<void>;
  loadClips: () => Promise<void>;
  loadSources: () => Promise<void>;
  loadAccounts: () => Promise<void>;
  loadPublications: () => Promise<void>;
  loadCampaigns: () => Promise<void>;
  loadSettings: () => Promise<void>;
  upsertClip: (c: Clip) => void;
  upsertAccount: (a: Account) => void;
}

let toastId = 1;

function upsert<T extends { id: unknown }>(list: T[], item: T, prepend = true): T[] {
  const i = list.findIndex((x) => x.id === item.id);
  if (i === -1) return prepend ? [item, ...list] : [...list, item];
  const copy = list.slice();
  copy[i] = { ...copy[i], ...item };
  return copy;
}

export const useStore = create<State>((set, get) => ({
  tab: "clipping",
  connected: false,
  jobs: [],
  clips: [],
  sources: [],
  accounts: [],
  publications: [],
  campaigns: [],
  settings: null,
  toasts: [],
  setTab: (tab) => set({ tab }),
  toast: (message, level = "info") => {
    const id = toastId++;
    set((s) => ({ toasts: [...s.toasts.slice(-4), { id, message, level }] }));
    setTimeout(() => get().dismiss(id), level === "error" ? 9000 : 5000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  loadAll: async () => {
    await Promise.all([
      get().loadSettings(),
      get().loadJobs(),
      get().loadClips(),
      get().loadSources(),
      get().loadAccounts(),
      get().loadPublications(),
      get().loadCampaigns(),
    ]);
  },
  loadJobs: async () => set({ jobs: await api.get<Job[]>("/api/jobs") }),
  loadClips: async () => set({ clips: await api.get<Clip[]>("/api/clips") }),
  loadSources: async () => set({ sources: await api.get<Source[]>("/api/sources") }),
  loadAccounts: async () => {
    try {
      set({ accounts: await api.get<Account[]>("/api/accounts") });
    } catch {
      /* route absente */
    }
  },
  loadPublications: async () => {
    try {
      set({ publications: await api.get<Publication[]>("/api/publications") });
    } catch {
      /* route absente */
    }
  },
  loadCampaigns: async () => {
    try {
      set({ campaigns: await api.get<Campaign[]>("/api/campaigns") });
    } catch {
      /* route absente */
    }
  },
  loadSettings: async () => set({ settings: await api.get<Settings>("/api/settings") }),
  upsertClip: (c) => set((s) => ({ clips: upsert(s.clips, c) })),
  upsertAccount: (a) => set((s) => ({ accounts: upsert(s.accounts, a, false) })),
}));

// ------------------------------------------------------------------ WebSocket temps réel
let refreshTimer: number | undefined;
function debounced(fn: () => void) {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(fn, 250);
}

export function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const st = useStore;
  ws.onopen = () => {
    st.setState({ connected: true });
    st.getState().loadAll().catch(() => undefined);
  };
  ws.onclose = () => {
    st.setState({ connected: false });
    setTimeout(connectWs, 1500);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data) as { type: string; data: any };
    const s = st.getState();
    switch (msg.type) {
      case "job.updated": {
        const job = msg.data as Job;
        st.setState((x) => {
          const old = x.jobs.find((j) => j.id === job.id);
          return { jobs: upsert(x.jobs, { ...job, source: job.source ?? old?.source ?? null }) };
        });
        if (job.source_id && !s.sources.some((x) => x.id === job.source_id)) debounced(() => s.loadSources());
        break;
      }
      case "job.deleted":
        st.setState((x) => ({ jobs: x.jobs.filter((j) => j.id !== msg.data.id) }));
        break;
      case "jobs.cleared":
        s.loadJobs();
        break;
      case "source.updated":
        st.setState((x) => ({ sources: upsert(x.sources, msg.data as Source) }));
        st.setState((x) => ({
          jobs: x.jobs.map((j) => (j.source_id === msg.data.id ? { ...j, source: msg.data } : j)),
        }));
        break;
      case "clip.created":
      case "clip.updated":
        if (msg.data?.final_caption) s.upsertClip(msg.data as Clip);
        else {
          api.get<Clip>(`/api/clips/${msg.data.id}`).then(s.upsertClip).catch(() => undefined);
        }
        break;
      case "clip.deleted":
        st.setState((x) => ({ clips: x.clips.filter((c) => c.id !== msg.data.id) }));
        break;
      case "account.updated":
        s.upsertAccount(msg.data as Account);
        break;
      case "account.deleted":
        st.setState((x) => ({ accounts: x.accounts.filter((a) => a.id !== msg.data.id) }));
        break;
      case "publication.updated":
      case "campaign.updated":
        debounced(() => {
          s.loadPublications();
          s.loadClips();
          s.loadCampaigns();
        });
        break;
      case "settings.updated":
        s.loadSettings();
        break;
      case "notification":
        s.toast(msg.data.message, msg.data.level);
        break;
    }
  };
}
