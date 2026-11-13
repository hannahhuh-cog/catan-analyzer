/** Message types shared by the bookmarklet (running on colonist.io) and the import page. */
export const MSG = {
  replay: 'catan-analyzer:replay',
  ack: 'catan-analyzer:ack',
  error: 'catan-analyzer:error',
} as const

export const isColonistOrigin = (origin: string) => /^https:\/\/([a-z0-9-]+\.)*colonist\.io$/.test(origin)

/**
 * Runs on a Colonist.io page: fetches the replay with the page's own login cookies (nothing leaves
 * Colonist except the replay JSON), opens the import page and hands the replay over via postMessage.
 * Falls back to saving the replay as a file when the tab can't be reached (popup blocked, COOP).
 */
function bookmarklet(importUrl: string, msg: typeof MSG) {
  const target = new URL(importUrl).origin
  if (!/(^|\.)colonist\.io$/.test(location.hostname)) {
    alert('Open your game on Colonist.io (its replay page or game link), then click this bookmark again.')
    return
  }
  const tab = window.open(importUrl, '_blank')
  const parse = (s: string) => {
    let u: URL
    try {
      u = new URL(s, location.href)
    } catch {
      return {}
    }
    const slug = (u.pathname.match(/\/replay\/([A-Za-z0-9_-]{6,})/) || [])[1]
    const gameId =
      u.searchParams.get('gameId') || u.searchParams.get('gameid') || (u.hash.match(/^#(\d{5,})$/) || [])[1] ||
      (/^\d{5,}$/.test(s.trim()) ? s.trim() : undefined)
    return { slug, gameId, color: u.searchParams.get('playerColor') || undefined }
  }
  const getJson = async (path: string) => {
    const r = await fetch(path, { credentials: 'include', headers: { accept: 'application/json' } })
    if (!r.ok) throw new Error(`Colonist answered HTTP ${r.status} for ${path.split('?')[0]}`)
    return r.json()
  }
  const fetchReplay = async () => {
    let ref = parse(location.href)
    if (!ref.slug && !ref.gameId) {
      const answer = prompt('Paste the replay link or game ID of the game to analyze (from your Colonist profile → game history):')
      if (!answer) throw new Error('No game picked.')
      ref = parse(answer)
      if (!ref.slug && !ref.gameId) throw new Error(`Couldn't find a game ID or replay link in "${answer}".`)
    }
    if (ref.slug) return getJson(`/api/replay/data-from-slug?replayUrlSlug=${encodeURIComponent(ref.slug)}`)
    let last: unknown
    for (const c of ref.color ? [ref.color] : ['1', '2', '3', '4', '5', '6', '7', '8']) {
      try {
        return await getJson(`/api/replay/data-from-game-id?gameId=${encodeURIComponent(ref.gameId!)}&playerColor=${c}`)
      } catch (e) {
        last = e
      }
    }
    throw last instanceof Error && /HTTP 401/.test(last.message)
      ? new Error('Colonist says you are not logged in. Log in on colonist.io in this browser, then try again.')
      : last
  }
  const save = (replay: unknown, why: string) => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(replay)], { type: 'application/json' }))
    a.download = 'colonist-replay.json'
    a.click()
    alert(`${why} The replay was saved as colonist-replay.json: upload it on ${importUrl}`)
  }
  // The tab may still be loading (or on its sign-in page), so re-post until it acknowledges.
  const deliver = (payload: object, onFail: () => void) => {
    if (!tab || tab.closed) return onFail()
    let done = false
    const onMsg = (e: MessageEvent) => {
      if (e.origin === target && e.data && e.data.type === msg.ack) {
        done = true
        window.removeEventListener('message', onMsg)
      }
    }
    window.addEventListener('message', onMsg)
    const started = Date.now()
    const send = () => {
      if (done) return
      if (tab.closed || Date.now() - started > 120000) {
        window.removeEventListener('message', onMsg)
        return onFail()
      }
      try {
        tab.postMessage(payload, target)
      } catch {
        /* not loaded yet: keep trying */
      }
      setTimeout(send, 700)
    }
    send()
  }
  fetchReplay().then(
    (replay) => deliver({ type: msg.replay, replay }, () => save(replay, "Couldn't reach the analyzer tab (pop-up blocked?).")),
    (e: unknown) => {
      const message = e instanceof Error ? e.message : String(e)
      deliver({ type: msg.error, message }, () => {})
      alert(`Catan Analyzer: ${message}`)
    },
  )
}

export function bookmarkletCode(importUrl: string): string {
  return `(${bookmarklet.toString()})(${JSON.stringify(importUrl)},${JSON.stringify(MSG)})`
}

export const bookmarkletHref = (importUrl: string) => `javascript:${encodeURIComponent(bookmarkletCode(importUrl))}`
