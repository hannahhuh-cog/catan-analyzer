import type { GameAnalysis, Profile } from './types'

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) msg = String(body.detail)
    } catch {
      /* not JSON */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const fetchProfile = (username: string) =>
  get<Profile>(`/api/profile/${encodeURIComponent(username.trim())}`)
export const fetchDemo = () => get<Profile>('/api/demo')
export const fetchDemoGame = (id: string) => get<GameAnalysis>(`/api/demo/games/${encodeURIComponent(id)}`)
