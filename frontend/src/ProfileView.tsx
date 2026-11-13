import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { daysSince, LOSS_VERDICTS, monthYear, pct, signed, sinceText, STRATEGY_LABELS, timeAgo, VERDICT_TONE, zText } from './format'
import type { Bucket, GameSummary, Insight, Profile } from './types'

const DIMENSIONS: [string, string][] = [
  ['play_order', 'Win rate by placement order'],
  ['player_count', 'Win rate by player count'],
  ['length', 'Win rate by game length'],
  ['vp_target', 'Win rate by VP target'],
  ['ranked', 'Win rate: ranked vs casual'],
  ['dice', 'Win rate by dice type'],
]

const MIN_SAMPLE = 8

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

export default function ProfileView({ profile, onOpenGame }: { profile: Profile; onOpenGame: (id: string) => void }) {
  const { stats, games } = profile
  const o = stats.overall
  const deep = stats.deep
  const insights = [...(deep?.insights ?? []), ...stats.insights]
  return (
    <div className="profile">
      <div className="page-head">
        <div>
          <div className="eyebrow">Your seat at the strategy table</div>
          <h1>{profile.username}</h1>
          <p className="muted">
            {profile.source === 'demo'
              ? 'Demo profile: 40 simulated games with full replays, analyzed end to end.'
              : coverageText(o)}
          </p>
          {profile.source === 'colonist' && o.games < MIN_SAMPLE && (
            <p className="notice small">
              Only {plural(o.games, 'game')} to go on, so these numbers are mostly noise. Patterns by seat, player count
              and game length show up after {MIN_SAMPLE}+ games in a slice.
            </p>
          )}
        </div>
      </div>

      {profile.source === 'colonist' && <DataNotes profile={profile} />}

      <div className="kpis">
        <Kpi
          label="Games"
          value={String(o.games)}
          sub={o.bot_games_excluded ? `vs humans; ${o.bot_games_excluded} bot games left out` : undefined}
        />
        <Kpi label="Win rate" value={pct(o.win_rate)} sub={`${pct(o.expected_rate)} expected by seat count`} />
        <Kpi
          label="Vs. average player"
          value={`${o.skill_ratio.toFixed(2)}x`}
          sub={zText(o.z ?? 0)}
          title={`Wins relative to an average player in the same games (z = ${signed(o.z ?? 0)})`}
        />
        <Kpi label="Average finish" value={o.avg_rank.toFixed(2)} sub="1 = first place" />
        <Kpi
          label="Close losses"
          value={`${o.close_losses}/${o.margin_losses ?? o.losses}`}
          sub="within 2 VP of the winner (3 at 15 VP)"
        />
        {deep && <Kpi label="Losses mostly RNG" value={rngLosses(deep.verdicts)} sub="out-decided the table, dice ran cold" />}
      </div>

      <section className="panel">
        <h2>Strengths, weaknesses and luck</h2>
        <div className="insights">
          {insights.map((i, k) => (
            <InsightCard key={k} insight={i} />
          ))}
        </div>
      </section>

      {deep && (
        <div className="grid-2">
          <section className="panel">
            <h2>Luck vs. decisions, every game</h2>
            <p className="muted small">
              Right = dice and robber favored you. Up = your decision score beat the table's average. Green = win.
            </p>
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart
                margin={{ top: 10, right: 16, bottom: 30, left: 0 }}
                title="Luck index vs. decision edge for every game"
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="luck" name="Luck index" domain={[-3, 3]} label={{ value: 'Luck index (SD)', position: 'bottom' }} />
                <YAxis type="number" dataKey="decision" name="Decision edge" label={{ value: 'Decision edge', angle: -90, position: 'insideLeft' }} />
                <ZAxis range={[70, 70]} />
                <ReferenceLine x={0} stroke="#94a3b8" />
                <ReferenceLine y={0} stroke="#94a3b8" />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                <Scatter
                  data={deep.scatter}
                  onClick={(d: { payload?: { id: string } }) => d?.payload && onOpenGame(d.payload.id)}
                  style={{ cursor: 'pointer' }}
                >
                  {deep.scatter.map((s) => (
                    <Cell key={s.id} fill={s.won ? '#16a34a' : '#dc2626'} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </section>
          <section className="panel">
            <h2>Win rate by strategy</h2>
            <p className="muted small">Strategy is inferred from what you built: cities, settlements and roads, or dev cards.</p>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={deep.strategies} layout="vertical" margin={{ left: 0, right: 36 }} title="Win rate by strategy">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => pct(v)} />
                <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => pct(Number(v))} />
                <Bar dataKey="win_rate" name="Win rate" fill="#2563eb" label={{ position: 'right', formatter: (v: unknown) => pct(Number(v)) }} />
              </BarChart>
            </ResponsiveContainer>
          </section>
        </div>
      )}

      <div className="grid-2">
        {DIMENSIONS.map(([key, title]) => {
          const rows = stats.breakdowns[key] ?? []
          if (rows.length < 2) return null
          const known = o.play_order_known
          const note =
            key === 'play_order' && known != null && known < o.games
              ? `Colonist only records placement order for ${known} of these ${o.games} games.`
              : undefined
          return <BreakdownChart key={key} title={title} rows={rows} note={note} />
        })}
      </div>

      {stats.trend.length > 5 && (
        <section className="panel">
          <h2>Form over time</h2>
          <p className="muted small">Rolling 10-game win rate vs. what you'd expect from seat count alone.</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={stats.trend} title="Rolling 10-game win rate vs. seat baseline">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="index" />
              <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Legend />
              <Line dataKey="rolling_win_rate" name="Win rate" stroke="#2563eb" dot={false} strokeWidth={2} />
              <Line dataKey="rolling_expected" name="Seat baseline" stroke="#94a3b8" dot={false} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        </section>
      )}

      {stats.opponents.length > 0 && (
        <section className="panel">
          <h2>Frequent opponents</h2>
          <div className="table-wrap" role="region" aria-label="Frequent opponents" tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th>Opponent</th>
                <th>Games</th>
                <th>Your wins</th>
                <th>Win rate</th>
              </tr>
            </thead>
            <tbody>
              {stats.opponents.map((r) => (
                <tr key={r.name}>
                  <td>{r.name}</td>
                  <td>{r.games}</td>
                  <td>{r.wins}</td>
                  <td>{pct(r.win_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      <GamesTable games={games} source={profile.source} onOpenGame={onOpenGame} />
    </div>
  )
}

function rngLosses(v: Record<string, number>) {
  const losses = LOSS_VERDICTS.reduce(
    (s, k) => s + (v[k] ?? 0),
    0,
  )
  return `${v['Lost to RNG'] ?? 0}/${losses}`
}

type Overall = Profile['stats']['overall']

function coverageText(o: Overall) {
  const range =
    o.first_ms && o.last_ms
      ? o.first_ms === o.last_ms || monthYear(o.first_ms) === monthYear(o.last_ms)
        ? ` from ${monthYear(o.last_ms)}`
        : ` from ${monthYear(o.first_ms)} to ${monthYear(o.last_ms)}`
      : ''
  const skipped = o.unfinished
    ? ` ${o.unfinished} unfinished ${o.unfinished === 1 ? 'game is' : 'games are'} listed but not counted.`
    : ''
  return `Based on ${o.games} finished ${o.games === 1 ? 'game' : 'games'}${range} from Colonist.io's public profile history.${skipped}`
}

const SMALL_SAMPLE = 30
const STALE_DAYS = 180

function DataNotes({ profile }: { profile: Profile }) {
  const o = profile.stats.overall
  const notes: string[] = []
  if (o.games < SMALL_SAMPLE) {
    notes.push(
      `Only ${o.games} games: one or two results can move these percentages a lot, so read strengths and weaknesses as hints, not verdicts.`,
    )
  }
  const bots = o.bot_games ?? 0
  if (bots && bots / o.games >= 0.25) {
    const humans = (profile.stats.breakdowns.opponents ?? []).find((r) => r.key === 'humans')
    notes.push(
      `${bots} of ${o.games} games included bots, which are easier to beat than people.` +
        (humans
          ? ` Against humans only: ${pct(humans.win_rate)} wins in ${humans.games} ${humans.games === 1 ? 'game' : 'games'}.`
          : ' None were against humans only.'),
    )
  }
  if (o.last_ms && daysSince(o.last_ms) > STALE_DAYS) {
    notes.push(
      `The latest game in this history is from ${timeAgo(o.last_ms)} (${sinceText(o.last_ms)}), so this may not reflect how ${profile.username} plays today.`,
    )
  }
  if (!notes.length) return null
  return (
    <div className="data-notes" role="note">
      <strong>Before you read the numbers</strong>
      <ul>
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </div>
  )
}

function Kpi({ label, value, sub, title }: { label: string; value: string; sub?: string; title?: string }) {
  return (
    <div className="kpi" title={title}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}

function InsightCard({ insight }: { insight: Insight }) {
  const label = { strength: 'Strength', weakness: 'Weakness', luck: 'Luck', info: 'Note' }[insight.kind]
  return (
    <div className={`insight ${insight.kind}`}>
      <span className="tag">{label}</span>
      <div className="insight-title">{insight.title}</div>
      <div className="insight-detail">{insight.detail}</div>
    </div>
  )
}

function BreakdownChart({ title, rows, note }: { title: string; rows: Bucket[]; note?: string }) {
  const data = rows.map((r) => ({ ...r, label: `${r.label} (${r.games})` }))
  return (
    <section className="panel">
      <h2>{title}</h2>
      <p className="muted small">Bars: your win rate. Grey: what your overall level predicts for these games. (n) = games.</p>
      {note && <p className="chart-note small">{note}</p>}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} title={title} margin={{ top: 5, right: 8, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" interval={0} height={44} tick={<WrappedTick />} />
          <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} />
          <Tooltip formatter={(v) => pct(Number(v))} />
          <Legend />
          <Bar dataKey="win_rate" name="Win rate" fill="#2563eb" />
          <Bar dataKey="expected_rate" name="Expected" fill="#cbd5e1" />
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}

function GamesTable({
  games,
  source,
  onOpenGame,
}: {
  games: GameSummary[]
  source: string
  onOpenGame: (id: string) => void
}) {
  return (
    <section className="panel">
      <h2>Games</h2>
      {source === 'colonist' && (
        <p className="muted small">
          Turn-by-turn replays on Colonist.io require a logged-in session, so per-game luck/decision analysis is shown on
          the demo profile. Profile-level stats above use the public history.
        </p>
      )}
      {games.length === 0 ? (
        <div className="state">No games.</div>
      ) : (
        <div className="table-wrap" role="region" aria-label="Games" tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Result</th>
                {source === 'demo' && <th>Verdict</th>}
                <th>VP</th>
                <th className="opt">Seat</th>
                <th className="opt">Players</th>
                <th className="opt">Turns</th>
                {source === 'demo' && (
                  <>
                    <th>Luck</th>
                    <th>Decision edge</th>
                    <th className="opt">Strategy</th>
                  </>
                )}
                <th>Opponents</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr
                  key={g.id}
                  className={g.analyzed ? 'clickable' : g.finished === false && !g.quit ? 'not-counted' : ''}
                  onClick={() => g.analyzed && onOpenGame(g.id)}
                >
                  <td>
                    {g.analyzed ? (
                      <a href={`#/demo/${encodeURIComponent(g.id)}`} onClick={(e) => e.stopPropagation()}>
                        {timeAgo(g.start_ms)}
                      </a>
                    ) : (
                      timeAgo(g.start_ms)
                    )}
                  </td>
                  <td>
                    {g.finished === false && !g.quit ? (
                      <span className="pill" title="Game never finished: not counted in the stats">
                        Unfinished
                      </span>
                    ) : (
                      <span className={`pill ${g.won ? 'win' : 'loss'}`}>
                        {g.won ? 'Won' : g.quit ? 'Quit' : `#${g.rank}`}
                      </span>
                    )}
                  </td>
                  {source === 'demo' && (
                    <td>
                      <span className={`pill tone-${VERDICT_TONE[g.verdict ?? ''] ?? 'neutral'}`}>{g.verdict}</span>
                    </td>
                  )}
                  <td>
                    {g.points}/{g.winner_points}
                  </td>
                  <td className="opt">{g.play_order ?? '-'}</td>
                  <td className="opt">{g.players}</td>
                  <td className="opt">{g.turns}</td>
                  {source === 'demo' && (
                    <>
                      <td className={(g.luck_index ?? 0) >= 0 ? 'pos' : 'neg'}>{signed(g.luck_index ?? 0)}</td>
                      <td className={(g.decision_edge ?? 0) >= 0 ? 'pos' : 'neg'}>{signed(g.decision_edge ?? 0, 0)}</td>
                      <td className="opt">{STRATEGY_LABELS[g.strategy ?? ''] ?? '-'}</td>
                    </>
                  )}
                  <td className="muted small">{g.opponents.map((p) => p.name).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function WrappedTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const lines = (payload?.value ?? '').replace(/ to place/, '').split(/ (?=\()/)
  return (
    <text x={x} y={y} dy={12} textAnchor="middle" fontSize={12} fill="#4b5563">
      {lines.map((l, i) => (
        <tspan key={i} x={x} dy={i ? 14 : 4}>
          {l}
        </tspan>
      ))}
    </text>
  )
}
