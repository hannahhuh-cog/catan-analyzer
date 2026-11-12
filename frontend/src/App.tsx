import { useCallback, useEffect, useState } from 'react'
import { fetchDemo, fetchDemoGame, fetchProfile } from './api'
import GameView from './GameView'
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
  const [query, setQuery] = useState(route.kind === 'profile' ? route.user : '')

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const load = useCallback(async (r: Route) => {
    setError(null)
    if (r.kind === 'home') return
    setLoading(true)
    try {
      if (r.kind === 'profile') {
        setProfile(null)
        setProfile(await fetchProfile(r.user))
      } else if (r.kind === 'demo') {
        if (profile?.source !== 'demo') setProfile(await fetchDemo())
      } else {
        setGame(null)
        const [g, p] = await Promise.all([fetchDemoGame(r.id), profile?.source === 'demo' ? profile : fetchDemo()])
        setGame(g)
        setProfile(p)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
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
    go(`/u/${encodeURIComponent(u)}`)
  }

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          <img className="brand-mark" src="/favicon.svg" alt="" width={24} height={24} />
          Catan Analyzer
        </a>
        <form className="search" onSubmit={submit}>
          <input
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
      </header>
      <main className="content">
        {route.kind === 'home' && <Home onDemo={() => go('/demo')} />}
        {loading && <div className="state">Loading{route.kind === 'profile' ? ` ${route.user}'s games from Colonist.io` : ''}...</div>}
        {error && !loading && (
          <div className="state error" role="alert">
            {error}
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

function Home({ onDemo }: { onDemo: () => void }) {
  return (
    <section className="home">
      <h1>Did you lose to the dice, or to your decisions?</h1>
      <p className="lede">
        Enter a Colonist.io username to analyze their recent games: win rate by placement order, player count and game
        length, compared against what seat luck alone would predict. Open the demo to see the full per-game analysis:
        luck vs. decision scores, a win-probability timeline with critical moments, and strategy strengths.
      </p>
      <div className="home-cards">
        <div className="card">
          <h3>Profile analysis</h3>
          <p>Up to 100 recent games from Colonist.io's public history: no login needed.</p>
        </div>
        <div className="card">
          <h3>Luck vs. strategy</h3>
          <p>Actual dice income vs. what your buildings should produce, robber damage, and decision quality.</p>
        </div>
        <div className="card">
          <h3>Game timeline</h3>
          <p>Win probability turn by turn, with your critical errors and best decisions marked.</p>
        </div>
      </div>
      <button className="primary-lg" onClick={onDemo}>
        Open the demo profile
      </button>
    </section>
  )
}
