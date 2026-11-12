import { useMemo, useState } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import BoardMap from './BoardMap'
import { pct, PLAYER_COLORS, signed, STRATEGY_LABELS, VERDICT_TONE } from './format'
import type { GameAnalysis, Moment } from './types'

export default function GameView({ game, onBack }: { game: GameAnalysis; onBack: () => void }) {
  const [selected, setSelected] = useState<Moment | null>(null)
  const me = game.players.find((p) => p.color === game.focus)!
  const others = game.players.filter((p) => p.color !== game.focus)
  const tone = VERDICT_TONE[game.verdict] ?? 'neutral'
  const wpKey = `wp_${game.focus}`

  const timeline = useMemo(
    () =>
      game.timeline.map((r) => {
        const row: Record<string, number> = { turn: r.turn }
        for (const p of game.players) {
          row[p.name] = r[`wp_${p.color}`]
          row[`${p.name} VP`] = r[`vp_${p.color}`]
        }
        row.luck = r[`luck_${game.focus}`]
        return row
      }),
    [game],
  )
  const wpAt = (turn: number) => {
    let v = game.timeline[0]?.[wpKey] ?? 0
    for (const r of game.timeline) {
      if (r.turn <= turn) v = r[wpKey]
      else break
    }
    return v
  }

  return (
    <div className="game">
      <button className="link" onClick={onBack}>
        ← Back to profile
      </button>
      <div className={`verdict-banner tone-${tone}`}>
        <div>
          <div className="verdict-kicker">
            {game.won ? 'Won' : 'Lost'} · seat {game.seat} of {game.players.length} · {game.turns} turns ·{' '}
            {STRATEGY_LABELS[game.strategy]}
          </div>
          <h1>{game.verdict}</h1>
          <p>{game.verdict_detail}</p>
        </div>
        <div className="verdict-scores">
          <Score label="Luck index" value={signed(game.luck_index)} hint="SD vs. opponents; + = dice favored you" good={game.luck_index >= 0} />
          <Score
            label="Decision score"
            value={`${game.decision_score}`}
            hint={`table avg ${game.opp_decision_score} (${signed(game.decision_edge, 0)})`}
            good={game.decision_edge >= 0}
          />
        </div>
      </div>

      <section className="panel">
        <h2>Win probability timeline</h2>
        <p className="muted small">
          Estimated from VP, expected production, cards in hand and dev cards after every turn. Markers are your critical
          moments: ▲ green = good decision, ▼ red = error, ◆ = luck (dice or robber). Click one for details.
        </p>
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={timeline} margin={{ top: 16, right: 20, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="turn" type="number" domain={[0, 'dataMax']} label={{ value: 'Turn', position: 'insideBottomRight', offset: -4 }} />
            <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} />
            <Tooltip formatter={(v) => pct(Number(v))} labelFormatter={(l) => `Turn ${l}`} />
            <Legend />
            {selected && <ReferenceLine x={selected.turn} stroke="#111827" strokeDasharray="4 4" />}
            {game.players.map((p) => (
              <Line
                key={p.color}
                dataKey={p.name}
                stroke={PLAYER_COLORS[p.color]}
                strokeWidth={p.color === game.focus ? 3 : 1.25}
                strokeOpacity={p.color === game.focus ? 1 : 0.55}
                dot={false}
                isAnimationActive={false}
              />
            ))}
            {game.critical.map((m, i) => (
              <ReferenceDot
                key={i}
                x={m.turn}
                y={wpAt(m.turn)}
                r={8}
                fill={m.kind === 'luck' ? '#a855f7' : m.polarity > 0 ? '#16a34a' : '#dc2626'}
                stroke="#fff"
                strokeWidth={2}
                onClick={() => setSelected(m)}
                style={{ cursor: 'pointer' }}
                label={{ value: m.kind === 'luck' ? '◆' : m.polarity > 0 ? '▲' : '▼', fill: '#fff', fontSize: 9 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Critical moments</h2>
          <ol className="moments">
            {game.critical.map((m, i) => (
              <li
                key={i}
                className={`moment ${m.kind} ${m.polarity > 0 ? 'up' : 'down'} ${selected === m ? 'selected' : ''}`}
                onClick={() => setSelected(m)}
              >
                <span className="moment-turn">T{m.turn}</span>
                <div>
                  <div className="moment-title">
                    <span className="tag">{m.kind === 'luck' ? 'Luck' : m.polarity > 0 ? 'Good decision' : 'Error'}</span>
                    {m.title}
                  </div>
                  <div className="moment-detail">{m.detail}</div>
                </div>
              </li>
            ))}
            {game.critical.length === 0 && <li className="muted">No standout moments in this game.</li>}
          </ol>
        </section>
        <section className="panel">
          <h2>Final board</h2>
          <BoardMap board={game.board} buildings={game.buildings} highlight={selected?.loc ?? selected?.hex ?? null} />
          <div className="legend-row">
            {game.players.map((p) => (
              <span key={p.color} className="legend-item">
                <span className="swatch" style={{ background: PLAYER_COLORS[p.color] }} />
                {p.name} {p.color === game.winner ? '(winner)' : ''}
              </span>
            ))}
          </div>
        </section>
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>Dice luck</h2>
          <p className="muted small">
            Cumulative cards received from rolls minus what your buildings should have produced (robber included).
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="turn" type="number" domain={[0, 'dataMax']} />
              <YAxis />
              <Tooltip formatter={(v) => Number(v).toFixed(1)} labelFormatter={(l) => `Turn ${l}`} />
              <ReferenceLine y={0} stroke="#94a3b8" />
              <ReferenceArea y1={0} y2={1000} fill="#16a34a" fillOpacity={0.04} ifOverflow="hidden" />
              <ReferenceArea y1={-1000} y2={0} fill="#dc2626" fillOpacity={0.04} ifOverflow="hidden" />
              <Area dataKey="luck" name="Cards vs. expected" stroke="#7c3aed" fill="#ddd6fe" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="facts">
            <Fact label="Roll income" value={`${game.luck.roll_income} (exp. ${game.luck.roll_expected})`} />
            <Fact label="Dice z-score" value={`${signed(game.luck.dice_z)} (table ${signed(game.luck.opp_dice_z)})`} />
            <Fact label="Lost to robber blocks" value={`${game.luck.robber_blocked} cards`} />
            <Fact label="Steals" value={`${game.luck.stole} by you / ${game.luck.stolen_from} from you`} />
          </div>
        </section>
        <section className="panel">
          <h2>Dice distribution</h2>
          <p className="muted small">All rolls this game vs. the expected 2d6 distribution ({game.luck.sevens} sevens).</p>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={game.dice_histogram}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="total" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="count" name="Rolled" fill="#2563eb" />
              <Line dataKey="expected" name="Expected" stroke="#f59e0b" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="panel">
        <h2>Decision breakdown</h2>
        <div className="grid-2 tight">
          <div>
            {Object.entries(game.components).map(([k, v]) => (
              <Meter key={k} label={COMPONENT_LABELS[k] ?? k} value={v} />
            ))}
          </div>
          <div className="facts">
            <Fact label="Opening placement" value={`${pct(me.setup_pct)} percentile (table ${pct(avg(others.map((o) => o.setup_pct)))})`} />
            <Fact label="First city" value={game.stats.first_city != null ? `turn ${game.stats.first_city}` : 'never'} />
            <Fact label="First new settlement" value={game.stats.first_settlement != null ? `turn ${game.stats.first_settlement}` : 'never'} />
            <Fact label="Cards discarded to 7s" value={String(game.stats.discarded)} />
            <Fact label="Bank trades" value={String(game.stats.bank_trades)} />
            <Fact label="Dev cards bought / knights" value={`${game.stats.dev_bought} / ${game.stats.knights}`} />
            <Fact label="Awards" value={game.stats.awards.map((a) => (a === 'longest_road' ? 'Longest Road' : 'Largest Army')).join(', ') || 'none'} />
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Players</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Seat</th>
              <th>Final VP</th>
              <th>Strategy</th>
              <th>Dice z</th>
              <th>Opening pct.</th>
              <th>Decision score</th>
            </tr>
          </thead>
          <tbody>
            {game.players.map((p) => (
              <tr key={p.color} className={p.color === game.focus ? 'me' : ''}>
                <td>
                  <span className="swatch" style={{ background: PLAYER_COLORS[p.color] }} /> {p.name}
                  {p.color === game.winner && ' 🏆'}
                </td>
                <td>{game.play_order.indexOf(p.color) + 1}</td>
                <td>{p.final_vp}</td>
                <td>{STRATEGY_LABELS[p.strategy]}</td>
                <td className={p.luck_z >= 0 ? 'pos' : 'neg'}>{signed(p.luck_z)}</td>
                <td>{pct(p.setup_pct)}</td>
                <td>{p.decision_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

const COMPONENT_LABELS: Record<string, string> = {
  opening: 'Opening placements',
  tempo: 'Tempo (time at or above median VP)',
  robber: 'Robber targeting (hit the leader)',
  hand_management: 'Hand management (no 7 discards)',
  awards: 'Longest Road / Largest Army',
}

const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)

function Score({ label, value, hint, good }: { label: string; value: string; hint: string; good: boolean }) {
  return (
    <div className="score">
      <div className="score-label">{label}</div>
      <div className={`score-value ${good ? 'pos' : 'neg'}`}>{value}</div>
      <div className="score-hint">{hint}</div>
    </div>
  )
}

function Meter({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span>{value == null ? 'n/a' : pct(value)}</span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${(value ?? 0) * 100}%` }} />
      </div>
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  )
}
