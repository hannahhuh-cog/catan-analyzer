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
import { LOSS_VERDICTS, pct, signed, STRATEGY_LABELS, timeAgo, VERDICT_TONE } from './format'
import type { Bucket, GameSummary, Insight, Profile } from './types'

const DIMENSIONS: [string, string][] = [
  ['play_order', 'Win rate by placement order'],
  ['player_count', 'Win rate by player count'],
  ['length', 'Win rate by game length'],
  ['vp_target', 'Win rate by VP target'],
  ['ranked', 'Win rate: ranked vs casual'],
  ['dice', 'Win rate by dice type'],
]

export default function ProfileView({ profile, onOpenGame }: { profile: Profile; onOpenGame: (id: string) => void }) {
  const { stats, games } = profile
  const o = stats.overall
  const deep = stats.deep
  const insights = [...(deep?.insights ?? []), ...stats.insights]
  return (
    <div className="profile">
      <div className="page-head">
        <div>
          <h1>{profile.username}</h1>
          <p className="muted">
            {profile.source === 'demo'
              ? 'Demo profile: 40 simulated games with full replays, analyzed end to end.'
              : `${games.length} most recent Colonist.io games from the public profile history.`}
          </p>
        </div>
      </div>

      <div className="kpis">
        <Kpi
          label="Games"
          value={String(o.games)}
          sub={o.bot_games_excluded ? `vs humans; ${o.bot_games_excluded} bot games left out` : undefined}
        />
        <Kpi label="Win rate" value={pct(o.win_rate)} sub={`${pct(o.expected_rate)} expected by seat count`} />
        <Kpi label="Vs. average player" value={`${o.skill_ratio.toFixed(2)}x`} sub={`z = ${signed(o.z ?? 0)}`} />
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
              <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 0 }}>
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
              <BarChart data={deep.strategies} layout="vertical" margin={{ left: 40, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => pct(v)} />
                <YAxis type="category" dataKey="label" width={150} />
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
          return <BreakdownChart key={key} title={title} rows={rows} />
        })}
      </div>

      {stats.trend.length > 5 && (
        <section className="panel">
          <h2>Form over time</h2>
          <p className="muted small">Rolling 10-game win rate vs. what you'd expect from seat count alone.</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={stats.trend}>
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

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="kpi">
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

function BreakdownChart({ title, rows }: { title: string; rows: Bucket[] }) {
  const data = rows.map((r) => ({ ...r, label: `${r.label} (${r.games})` }))
  return (
    <section className="panel">
      <h2>{title}</h2>
      <p className="muted small">Bars: your win rate. Grey: what your overall level predicts for these games. (n) = games.</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
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
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Result</th>
                <th>VP</th>
                <th>Seat</th>
                <th>Players</th>
                <th>Turns</th>
                {source === 'demo' && (
                  <>
                    <th>Strategy</th>
                    <th>Luck</th>
                    <th>Decision edge</th>
                    <th>Verdict</th>
                  </>
                )}
                <th>Opponents</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr
                  key={g.id}
                  className={g.analyzed ? 'clickable' : ''}
                  onClick={() => g.analyzed && onOpenGame(g.id)}
                  tabIndex={g.analyzed ? 0 : undefined}
                  onKeyDown={(e) => e.key === 'Enter' && g.analyzed && onOpenGame(g.id)}
                >
                  <td>{timeAgo(g.start_ms)}</td>
                  <td>
                    <span className={`pill ${g.won ? 'win' : 'loss'}`}>{g.won ? 'Won' : g.quit ? 'Quit' : `#${g.rank}`}</span>
                  </td>
                  <td>
                    {g.points}/{g.winner_points}
                  </td>
                  <td>{g.play_order ?? '-'}</td>
                  <td>{g.players}</td>
                  <td>{g.turns}</td>
                  {source === 'demo' && (
                    <>
                      <td>{STRATEGY_LABELS[g.strategy ?? ''] ?? '-'}</td>
                      <td className={(g.luck_index ?? 0) >= 0 ? 'pos' : 'neg'}>{signed(g.luck_index ?? 0)}</td>
                      <td className={(g.decision_edge ?? 0) >= 0 ? 'pos' : 'neg'}>{signed(g.decision_edge ?? 0, 0)}</td>
                      <td>
                        <span className={`pill tone-${VERDICT_TONE[g.verdict ?? ''] ?? 'neutral'}`}>{g.verdict}</span>
                      </td>
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
