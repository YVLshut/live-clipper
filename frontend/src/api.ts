export class ApiError extends Error {}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Le moteur de Live Clipper ne répond pas. Redémarre l'application.");
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError(data?.detail || `Erreur ${res.status}`);
  }
  return data as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body: unknown = {}) => request<T>("POST", url, body),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  patch: <T>(url: string, body: unknown) => request<T>("PATCH", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
};

/** Ouvre un lien dans le navigateur du système (la fenêtre de l'app n'est pas un navigateur). */
export function openExternal(url: string) {
  api.post("/api/open", { url }).catch(() => window.open(url, "_blank"));
}

export function openFolder(path: string) {
  return api.post("/api/open", { path });
}

declare global {
  interface Window {
    pywebview?: { api: { pick_folder: (initial?: string) => Promise<string | null> } };
  }
}

/** Sélecteur de dossier natif (fenêtre pywebview) ; null si indisponible. */
export async function pickFolder(initial?: string): Promise<string | null | undefined> {
  if (window.pywebview?.api?.pick_folder) {
    return window.pywebview.api.pick_folder(initial);
  }
  return undefined;
}
