import { useCallback, useEffect, useRef, useState } from 'react'
import { analyzeReplay } from './api'
import { bookmarkletCode, bookmarkletHref, isColonistOrigin, MSG } from './bookmarklet'
import GameView from './GameView'
import type { GameAnalysis } from './types'

const importUrl = () => `${window.location.origin}${window.location.pathname}#/import`

export default function ImportView() {
  const [game, setGame] = useState<GameAnalysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const link = useRef<HTMLAnchorElement>(null)
  const fromBookmarklet = Boolean(window.opener)

  useEffect(() => {
    // React refuses javascript: URLs in JSX, so the bookmarklet's href is set directly.
    link.current?.setAttribute('href', bookmarkletHref(importUrl()))
  }, [game])

  const inflight = useRef<AbortController | null>(null)
  const replayRef = useRef<unknown>(null)
  const analyze = useCallback((r: unknown, focus: number | null) => {
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    replayRef.current = r
    setBusy(true)
    setError(null)
    analyzeReplay(r, focus, ctrl.signal)
      .then((g) => setGame(g))
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setBusy(false)
      })
  }, [])

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (!isColonistOrigin(e.origin) || !e.data || typeof e.data !== 'object') return
      if (e.data.type === MSG.replay) {
        ;(e.source as Window | null)?.postMessage({ type: MSG.ack }, e.origin)
        if (replayRef.current == null) analyze(e.data.replay, null)
      } else if (e.data.type === MSG.error) {
        setError(String(e.data.message))
      }
    }
    window.addEventListener('message', onMessage)
    return () => {
      window.removeEventListener('message', onMessage)
      inflight.current?.abort()
    }
  }, [analyze])

  const onFile = async (f: File | undefined) => {
    if (!f) return
    setGame(null)
    let parsed: unknown
    try {
      parsed = JSON.parse(await f.text())
    } catch {
      setError(`${f.name} isn't a JSON replay file.`)
      return
    }
    analyze(parsed, null)
  }

  const reset = () => {
    inflight.current?.abort()
    replayRef.current = null
    setBusy(false)
    setGame(null)
    setError(null)
  }

  if (game && !busy) {
    return (
      <>
        <div className="import-bar">
          <span className="muted">Viewing as</span>
          {game.players.map((p) => (
            <button
              key={p.color}
              type="button"
              className={p.color === game.focus ? '' : 'secondary'}
              onClick={() => analyze(replayRef.current, p.color)}
              disabled={p.color === game.focus}
            >
              {p.name}
            </button>
          ))}
        </div>
        <GameView game={game} onBack={reset} backLabel="← Import another game" />
      </>
    )
  }

  return (
    <section className="import">
      <h1>Analyze one of your Colonist games</h1>
      {busy && (
        <div className="state" role="status">
          <span className="loading-die" aria-hidden="true">⚄</span>
          Replaying your game turn by turn...
        </div>
      )}
      {error && !busy && (
        <div className="state error" role="alert">
          <div>{error}</div>
          <button type="button" className="secondary retry" onClick={reset}>
            Start over
          </button>
        </div>
      )}
      {!busy && !error && fromBookmarklet && (
        <div className="state" role="status">
          <span className="loading-die" aria-hidden="true">⚄</span>
          Waiting for the replay from your Colonist tab...
        </div>
      )}
      <div className="home-cards import-steps">
        <div className="card">
          <span className="feature-step">01 / ONE-TIME SETUP</span>
          <h2>Add the bookmark</h2>
          <p>
            Drag this button to your bookmarks bar:{' '}
            <a ref={link} className="bookmarklet" onClick={(e) => e.preventDefault()} draggable>
              Analyze in Catan Analyzer
            </a>
          </p>
          <button
            type="button"
            className="link"
            onClick={() => navigator.clipboard.writeText(bookmarkletCode(importUrl())).then(() => setCopied(true))}
          >
            {copied ? 'Copied: paste it as a new bookmark’s URL after typing javascript:' : 'Or copy the code'}
          </button>
        </div>
        <div className="card">
          <span className="feature-step">02 / ON COLONIST</span>
          <h2>Open your game</h2>
          <p>
            Log in on colonist.io, open the game's replay from your profile's game history, then click the bookmark. Your
            login stays on Colonist: only the replay comes here.
          </p>
        </div>
        <div className="card">
          <span className="feature-step">03 / HERE</span>
          <h2>Read the story</h2>
          <p>
            A new tab opens with the turn-by-turn timeline, luck vs. decisions, and turning points. If the hand-off fails,
            the bookmark saves the replay as a file to upload instead:
          </p>
          <label className="upload">
            <input type="file" accept="application/json,.json" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
        </div>
      </div>
    </section>
  )
}
