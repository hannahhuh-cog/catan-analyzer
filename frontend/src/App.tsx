import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchDemo, fetchDemoGame, fetchProfile, usernameProblem } from './api'
import GameView from './GameView'
import IslandArt, { FeatureIcon } from './GameArt'
import ProfileView from './ProfileView'
import type { GameAnalysis, Profile } from './types'

type Route = { kind: 'home' } | { kind: 'profile'; user: string } | { kind: 'demo' } | { kind: 'game'; id: string }

function parseHash(): Route {
  const h = decodeURIComponent(window.location.hash.replace(/^#\/?/, ''))
  if (h === 'demo') return { kind: 'demo' }
  if (h.startsWith('demo/')) return { kind: 'game', id: h.slice(5) }
  if (h.startsWith('u/')) return { kind: 'profile', user: h.slice(2) }
  return { kind: 'home' }
}

function go(hash: string) {
  window.location.hash = hash
}

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [game, setGame] = useState<GameAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryable, setRetryable] = useState(false)
  const [slow, setSlow] = useState(false)
  const inflight = useRef<AbortController | null>(null)
  const [query, setQuery] = useState(route.kind === 'profile' ? route.user : '')

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const load = useCallback(async (r: Route) => {
    // A newer search always wins: abort the previous request so its late response can't replace this one.
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    const { signal } = ctrl
    setError(null)
    setSlow(false)
    if (r.kind === 'home') {
      setLoading(false)
      return
    }
    if (r.kind === 'profile') {
      setProfile(null)
      const problem = usernameProblem(r.user)
      if (problem) {
        setLoading(false)
        setRetryable(false)
        setError(problem)
        return
      }
    }
    setLoading(true)
    const slowTimer = setTimeout(() => setSlow(true), 5000)
    try {
      if (r.kind === 'profile') {
        const p = await fetchProfile(r.user, signal)
        if (!signal.aborted) setProfile(p)
      } else if (r.kind === 'demo') {
        if (profile?.source !== 'demo') {
          const p = await fetchDemo(signal)
          if (!signal.aborted) setProfile(p)
        }
      } else {
        setGame(null)
        const [g, p] = await Promise.all([
          fetchDemoGame(r.id, signal),
          profile?.source === 'demo' ? profile : fetchDemo(signal),
        ])
        if (!signal.aborted) {
          setGame(g)
          setProfile(p)
        }
      }
    } catch (e) {
      if (signal.aborted) return
      setRetryable(e instanceof ApiError ? e.retryable : true)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      clearTimeout(slowTimer)
      if (!signal.aborted) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load(route)
    window.scrollTo(0, 0)
  }, [route, load])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const u = query.trim()
    if (!u) return
    // Searching the name already on screen (e.g. after an error) retries instead of doing nothing.
    if (route.kind === 'profile' && route.user === u) load(route)
    else go(`/u/${encodeURIComponent(u)}`)
  }

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          <img className="brand-mark" src="/favicon.svg" alt="" width={24} height={24} />
          Catan Analyzer
        </a>
        {route.kind === 'home' && <span className="topbar-note">Roll. Reflect. Level up.</span>}
        {route.kind !== 'home' && (
          <form className="search" onSubmit={submit}>
            <input
              type="search"
              enterKeyHint="search"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              aria-label="Colonist.io username"
              placeholder="Colonist.io username"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={40}
            />
            <button type="submit" disabled={!query.trim()}>
              Analyze
            </button>
            <button type="button" className="secondary" onClick={() => go('/demo')}>
              Demo
            </button>
          </form>
        )}
      </header>
      <main className="content">
        {route.kind === 'home' && (
          <Home query={query} setQuery={setQuery} onSubmit={submit} onDemo={() => go('/demo')} />
        )}
        {loading && (
          <div className="state" role="status">
            <span className="loading-die" aria-hidden="true">⚄</span>
            Gathering{route.kind === 'profile' ? ` ${route.user}'s games from Colonist.io` : ' the game pieces'}...
            {slow && <div className="small">Colonist.io is slow to respond. Still trying (up to 15 seconds).</div>}
          </div>
        )}
        {error && !loading && (
          <div className="state error" role="alert">
            <div>{error}</div>
            {retryable && (
              <button type="button" className="secondary retry" onClick={() => load(route)}>
                Try again
              </button>
            )}
          </div>
        )}
        {!loading && !error && (route.kind === 'profile' || route.kind === 'demo') && profile && (
          <ProfileView profile={profile} onOpenGame={(id) => go(`/demo/${id}`)} />
        )}
        {!loading && !error && route.kind === 'game' && game && (
          <GameView game={game} onBack={() => go('/demo')} />
        )}
      </main>
      <footer className="footer">
        Unofficial tool. Game history comes from Colonist.io's public profile API; not affiliated with Colonist.io or
        CATAN GmbH.{' '}
        <a href="https://hannahhuh.devinenterprise.com/sessions/96a3ae48a4d243fd832ede5048b82895" target="_blank" rel="noreferrer">
          Request changes
        </a>
      </footer>
    </div>
  )
}

type HomeProps = {
  query: string
  setQuery: (q: string) => void
  onSubmit: (e: React.FormEvent) => void
  onDemo: () => void
}

function Home({ query, setQuery, onSubmit, onDemo }: HomeProps) {
  return (
    <section className="home">
      <div className="hero-layout">
        <div className="hero-copy">
          <div className="eyebrow"><span /> Your next move starts here</div>
          <h1>Bad dice?<br />Or <span>bad decisions?</span></h1>
          <p className="lede">
            Every game has a story. Find your strengths, spot your patterns, and bring a better plan to the board.
          </p>
          <label className="hero-label" htmlFor="hero-username">Your Colonist.io username</label>
          <form className="hero-search" onSubmit={onSubmit}>
            <input
              id="hero-username"
              type="search"
              enterKeyHint="search"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              aria-label="Colonist.io username"
              placeholder="e.g. thebestsettler"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={40}
            />
            <button type="submit" className="primary-lg" disabled={!query.trim()}>
              Analyze my games <span aria-hidden="true">→</span>
            </button>
          </form>
          <p className="muted small hero-hint">
            No login. Just your public game history. Include your #1234 tag if you have one; capitalization doesn't matter.
          </p>
          <button type="button" className="demo-invite" onClick={onDemo}>
            Just exploring? <strong>Try the demo <span aria-hidden="true">↗</span></strong>
          </button>
        </div>
        <IslandArt />
      </div>
      <div className="section-intro"><span className="eyebrow">Less guessing. Better settling.</span><h2>Get to know your game.</h2></div>
      <div className="home-cards">
        <div className="card feature-profile">
          <div className="feature-icon"><FeatureIcon kind="profile" /></div>
          <span className="feature-step">01 / THE BIG PICTURE</span>
          <h2>Profile analysis</h2>
          <p>Up to 100 recent games from Colonist.io's public history: no login needed.</p>
        </div>
        <div className="card feature-dice">
          <div className="feature-icon"><FeatureIcon kind="dice" /></div>
          <span className="feature-step">02 / THE DICE CHECK</span>
          <h2>
            Luck vs. strategy <span className="demo-tag">Demo</span>
          </h2>
          <p>Actual dice income vs. what your buildings should produce, robber damage, and decision quality.</p>
        </div>
        <div className="card feature-timeline">
          <div className="feature-icon"><FeatureIcon kind="timeline" /></div>
          <span className="feature-step">03 / THE TURNING POINTS</span>
          <h2>
            Game timeline <span className="demo-tag">Demo</span>
          </h2>
          <p>Win probability turn by turn, with your critical errors and best decisions marked.</p>
        </div>
      </div>
      <p className="muted demo-explainer">
        Per-game luck and decision analysis needs full replays, which Colonist only shares with logged-in players.{' '}
        <button type="button" className="link inline" onClick={onDemo}>
          See it on the demo profile
        </button>
      </p>
    </section>
  )
}
