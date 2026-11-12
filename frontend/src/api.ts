import type { GameAnalysis, Profile } from './types'

const USERNAME_RE = /^[\p{L}\p{N}_#.\- ]{1,40}$/u

/** Mirrors the backend check, so typos like "bad/name" get a clear message instead of a broken request. */
export function usernameProblem(username: string): string | null {
  const u = username.trim()
  if (!u) return 'Enter a Colonist.io username.'
  if (u.length > 40) return 'Colonist.io usernames are at most 40 characters.'
  if (!USERNAME_RE.test(u) || !/[\p{L}\p{N}]/u.test(u))
    return `"${u}" isn't a valid Colonist.io username: use letters, numbers, spaces, _ . - or #.`
  return null
}

export class ApiError extends Error {
  readonly retryable: boolean
  constructor(message: string, retryable: boolean) {
    super(message)
    this.retryable = retryable
  }
}

async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, { signal })
  } catch (e) {
    if (signal?.aborted) throw e
    throw new ApiError("Couldn't reach the Catan Analyzer server. Check your connection and try again.", true)
  }
  let body: unknown
  try {
    body = await res.json()
  } catch (e) {
    if (signal?.aborted) throw e
    body = undefined
  }
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | undefined)?.detail
    const msg = typeof detail === 'string' ? detail : `The server had a problem (HTTP ${res.status}). Try again in a minute.`
    throw new ApiError(msg, res.status >= 500 || res.status === 429)
  }
  if (body === undefined) throw new ApiError('The server sent an unexpected response. Try again in a minute.', true)
  return body as T
}

export const fetchProfile = (username: string, signal?: AbortSignal) =>
  get<Profile>(`/api/profile/${encodeURIComponent(username.trim())}`, signal)
export const fetchDemo = (signal?: AbortSignal) => get<Profile>('/api/demo', signal)
export const fetchDemoGame = (id: string, signal?: AbortSignal) =>
  get<GameAnalysis>(`/api/demo/games/${encodeURIComponent(id)}`, signal)
