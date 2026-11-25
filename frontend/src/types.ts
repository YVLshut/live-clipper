export interface Source {
  id: string;
  url: string;
  author: string;
  author_url: string | null;
  title: string | null;
  platform: string | null;
  date: string | null;
  was_live: boolean;
  duration: number | null;
  credit: string;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type Step = "download" | "transcribe" | "detect" | "render" | "record";

export interface Job {
  id: number;
  kind: "clip" | "rerender" | "live";
  url: string | null;
  options: Record<string, unknown>;
  status: JobStatus;
  step: Step | null;
  progress: number;
  message: string | null;
  error: string | null;
  warnings: string[];
  source_id: string | null;
  clip_id: string | null;
  clips_count: number;
  stream_id: number | null;
  extra: { recorded?: number; segments?: number; started?: number; source?: Partial<Source> } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  source: Source | null;
}

export type PubStatus = "scheduled" | "running" | "published" | "failed" | "paused" | "cancelled";

export interface Publication {
  id: number;
  clip_id: string;
  account_id: number;
  status: PubStatus;
  scheduled_at: string;
  published_at: string | null;
  post_url: string | null;
  error: string | null;
  screenshot: string | null;
  screenshot_url?: string | null;
  caption: string | null;
  attempts: number;
  auto: boolean;
  created_at: string;
  clip?: { id: string; title: string; hook: string; score: number | null; video_url: string; thumb_url: string } | null;
  account?: { id: number; name: string; platform: Platform; mode: string; avatar_url: string | null } | null;
}

export interface Clip {
  id: string;
  source_id: string;
  job_id: number | null;
  file: string;
  start: number;
  end: number;
  duration: number;
  score: number | null;
  title: string;
  hook: string;
  caption: string;
  hashtags: string[];
  layout: string;
  status: "pending" | "approved" | "rejected";
  rendering: boolean;
  version: number;
  created_at: string;
  source: Source;
  final_caption: string;
  video_url: string;
  thumb_url: string;
  publications: Publication[];
}

export type Platform = "instagram" | "tiktok";

export interface Account {
  id: number;
  platform: Platform;
  name: string;
  mode: "api" | "browser";
  avatar: string | null;
  avatar_url: string | null;
  status: "connected" | "reconnect" | "disconnected";
  status_message: string | null;
  external_id: string | null;
  username: string | null;
  auto_publish: boolean;
  require_approval: boolean;
  min_score: number;
  max_per_day: number;
  time_windows: [string, string][];
  delay_min_minutes: number;
  delay_max_minutes: number;
  privacy_level: string | null;
  pending_choices: { id: string; username: string; picture?: string }[] | null;
  created_at: string;
}

export interface Settings {
  whisper_model: string;
  device: string;
  language: string;
  min_len: number;
  max_len: number;
  max_clips: number;
  layout: string;
  font: string;
  words_per_line: number;
  encoder: string;
  default_hashtags: string[];
  output_dir: string;
  output_dir_effective: string;
  ai_model: string;
  browser_channel: string;
  meta_app_id: string;
  tiktok_client_key: string;
  setup_done: boolean;
  secrets: { anthropic_api_key: boolean; meta_app_secret: boolean; tiktok_client_secret: boolean };
  choices: {
    whisper_model: string[];
    ai_model: string[];
    encoder: string[];
    layout: string[];
    device: string[];
    language: { value: string; label: string }[];
  };
  oauth_redirects: { instagram: string; tiktok: string };
  data_dir: string;
}

export interface Toast {
  id: number;
  message: string;
  level: "info" | "success" | "warning" | "error";
}

export interface SystemInfo {
  version: string;
  gpu: { available: boolean; detail: string };
  ffmpeg: string | null;
  yt_dlp: string | null;
  data_dir: string;
  logs_dir: string;
  platform: string;
}

export interface CampaignAccount {
  account_id: number;
  name: string;
  platform: Platform | null;
  connected: boolean;
  max_per_day: number | null;
  published: number;
  scheduled: number;
  running: number;
  paused: number;
  failed: number;
  target: number;
  blocked: boolean;
  next_at: string | null;
  last_published_at: string | null;
  last_post_url: string | null;
  last_error: string | null;
}

export interface Campaign {
  id: number;
  count: number;
  account_ids: number[];
  interval_minutes: number;
  status: "active" | "done" | "cancelled";
  created_at: string;
  finished_at: string | null;
  accounts: CampaignAccount[];
  published_total: number;
  progress: number;
}

export interface Stream {
  id: number;
  url: string;
  enabled: boolean;
  author: string | null;
  title: string | null;
  platform: string | null;
  last_checked: string | null;
  last_live_at: string | null;
  created_at: string;
  state: "paused" | "live" | "processing" | "watching" | "failed" | "done";
  label: string;
  clips: number;
  channel: boolean;
  recorded: number;
}
