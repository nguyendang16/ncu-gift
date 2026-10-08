import { getLang } from "../i18n";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

export async function api<T>(path: string, opts: { method?: string; params?: Params; body?: unknown; form?: FormData } = {}): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(opts.params ?? {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  // The server translates every message it generates into the language of the request.
  const headers: Record<string, string> = { "Accept-Language": getLang() };
  const init: RequestInit = { method: opts.method ?? (opts.body || opts.form ? "POST" : "GET"), headers };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText, code: string | undefined;
    try {
      const j = await res.json();
      code = j.code;
      detail = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : detail;
    } catch { /* keep status text */ }
    throw new ApiError(res.status, detail, code);
  }
  return res.json() as Promise<T>;
}
