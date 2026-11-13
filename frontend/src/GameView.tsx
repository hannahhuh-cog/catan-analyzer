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
import type { Cause, GameAnalysis, Moment, Swing } from './types'

type KeyMoment = { m: Moment; swing: Swing | null; impact: number | null }

const CAUSE_LABEL: Record<Cause, string> = { decision: 'Your decision', luck: 'Dice & robber', opponent: "Opponent's move" }
const POLARITY_LABEL: Record<Cause, [string, string]> = {
  decision: ['Good move', 'Error'],
  luck: ['Good luck', 'Bad luck'],
  opponent: ['Helped you', 'Hurt you'],
}
const GOOD = '#16a34a'
const BAD = '#dc2626'
const pts = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(Math.round(x * 100))} pts`

export default function GameView({
  game,
  onBack,
  backLabel = '← Back to profile',
}: {
  game: GameAnalysis
  onBack: () => void
  backLabel?: string
}) {
  const [selected, setSelected] = useState<KeyMoment | null>(null)
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
  const keyMoments = useMemo<KeyMoment[]>(() => {
    const swings = game.swings ?? []
    const items: KeyMoment[] = game.critical.map((m, i) => {
      const swing = swings.find((s) => s.moment === i) ?? null
      return { m, swing, impact: m.wp_delta ?? swing?.wp_delta ?? null }
    })
    for (const s of swings) if (s.moment == null) items.push({ m: s, swing: s, impact: s.wp_delta })
    return items.sort((a, b) => a.m.turn - b.m.turn)
  }, [game])
  const [chartWidth, setChartWidth] = useState(0)
  const highlights = useMemo(() => {
    const scored = keyMoments.filter((k) => k.impact != null && Math.sign(k.impact) === k.m.polarity && Math.abs(k.impact) >= 0.005)
    const pick = (f: (k: KeyMoment) => boolean, dir: 1 | -1) =>
      scored.filter(f).sort((a, b) => dir * (b.impact! - a.impact!))[0]
    return [
      { label: 'Costliest error', k: pick((k) => k.m.kind === 'decision' && k.impact! < 0, -1) },
      { label: 'Best move', k: pick((k) => k.m.kind === 'decision' && k.impact! > 0, 1) },
      { label: 'Worst luck', k: pick((k) => k.m.kind === 'luck' && k.impact! < 0, -1) },
      { label: 'Best luck', k: pick((k) => k.m.kind === 'luck' && k.impact! > 0, 1) },
    ].filter((h) => h.k)
  }, [keyMoments])
  const causePts = useMemo(() => {
    const imp = game.impact
    if (!imp) return null
    const net = Math.round(imp.end * 100) - Math.round(imp.start * 100)
    const decision = Math.round(imp.decision * 100)
    const luck = Math.round(imp.luck * 100)
    return { decision, luck, opponent: net - decision - luck } as Record<Cause, number>
  }, [game])
  const wpAt = (turn: number) => wpAtTurn(game.timeline, wpKey, turn)

  const markerLayout = useMemo(() => {
    const maxTurn = Math.max(1, ...game.timeline.map((r) => r.turn))
    const plotW = Math.max(0, chartWidth - TIMELINE_X_INSET)
    const plotH = TIMELINE_HEIGHT - TIMELINE_Y_INSET - (chartWidth < 500 ? 48 : 24)
    const scale = chartWidth ? Math.max(0.6, Math.min(1, plotW / 600)) : 1
    const placed: { x: number; y: number; r: number }[] = []
    const out: { dy: number; r: number }[] = []
    const order = keyMoments.map((_, i) => i).sort((a, b) => Math.abs(keyMoments[b].impact ?? 0) - Math.abs(keyMoments[a].impact ?? 0))
    for (const i of order) {
      const k = keyMoments[i]
      const r = markerSize(k) * scale
      const hit = r * (k.m.kind === 'decision' ? 1 : 1.2) + 1
      const wp = wpAtTurn(game.timeline, wpKey, k.m.turn)
      const x = (k.m.turn / maxTurn) * plotW
      const y = (1 - wp) * plotH
      const toward = wp > 0.5 ? 1 : -1
      let dy = 0
      for (let step = 0; step <= 100; step++) {
        const cand = step === 0 ? 0 : (step % 2 ? toward : -toward) * Math.ceil(step / 2) * 3
        if (step > 0 && (y + cand < hit || y + cand > plotH - hit)) continue
        dy = cand
        if (!placed.some((p) => Math.hypot(p.x - x, p.y - (y + dy)) < p.r + hit + 1)) break
      }
      placed.push({ x, y: y + dy, r: hit })
      out[i] = { dy, r }
    }
    return out
  }, [keyMoments, chartWidth, game, wpKey])

  return (
    <div className="game">
      <button className="link" onClick={onBack}>
        {backLabel}
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
        {game.impact && causePts && (
          <div className="glance">
            <div className="glance-net">
              Your win chance: <b>{pct(game.impact.start)}</b> after setup → <b>{pct(game.impact.end)}</b> at the end
            </div>
            <div className="glance-causes">
              {(['decision', 'luck', 'opponent'] as Cause[]).map((c) => (
                <span key={c} className={`cause-chip cause-${c}`} title="Sum of every change in your win chance caused by this">
                  <CauseIcon cause={c} polarity={causePts[c] >= 0 ? 1 : -1} size={14} />
                  {c === 'decision' ? 'Your decisions' : c === 'luck' ? 'Dice & robber' : "Opponents' moves"}{' '}
                  <b className={causePts[c] >= 0 ? 'pos' : 'neg'}>{pts(causePts[c] / 100)}</b>
                </span>
              ))}
            </div>
            <div className="glance-highlights">
              {highlights.map(({ label, k }) => (
                <button key={label} className="highlight" onClick={() => setSelected(k!)}>
                  <span className="muted">{label}</span> T{k!.m.turn} {k!.m.title}{' '}
                  <b className={k!.impact! >= 0 ? 'pos' : 'neg'}>{pts(k!.impact!)}</b>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="marker-legend muted small">
          <span><CauseIcon cause="decision" polarity={1} /> <CauseIcon cause="decision" polarity={-1} /> your decision</span>
          <span><CauseIcon cause="luck" polarity={1} /> <CauseIcon cause="luck" polarity={-1} /> dice &amp; robber</span>
          <span><CauseIcon cause="opponent" polarity={1} /> <CauseIcon cause="opponent" polarity={-1} /> opponent&apos;s move</span>
          <span>green = helped you, red = hurt you, bigger = larger swing · click a marker for details</span>
        </div>
        <ResponsiveContainer width="100%" height={TIMELINE_HEIGHT} onResize={(w) => setChartWidth(w)}>
          <LineChart
            data={timeline}
            margin={{ top: 16, right: 16, left: 0, bottom: 8 }}
            title="Win probability by turn for each player"
            onClick={(state) => {
              const turn = Number(state?.activeLabel)
              if (!Number.isFinite(turn) || keyMoments.length === 0) return
              const nearest = keyMoments.reduce((a, b) => (Math.abs(b.m.turn - turn) < Math.abs(a.m.turn - turn) ? b : a))
              if (Math.abs(nearest.m.turn - turn) <= 3) setSelected(nearest)
            }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="turn"
              type="number"
              domain={[0, 'dataMax']}
              padding={{ left: 12, right: 12 }}
              label={{ value: 'Turn', position: 'insideBottomRight', offset: -4 }}
            />
            <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} />
            <Tooltip
              content={({ active, label, payload }) =>
                active && payload?.length ? (
                  <div className="chart-tip">
                    <div className="chart-tip-title">Turn {label}</div>
                    {payload.map((p) => (
                      <div key={String(p.dataKey)} style={{ color: p.color }}>
                        {p.name}: {pct(Number(p.value))}
                      </div>
                    ))}
                    {keyMoments
                      .filter((k) => k.m.turn === label)
                      .map((k, i) => (
                        <div key={i} className="chart-tip-moment">
                          <CauseIcon cause={k.m.kind} polarity={k.m.polarity} size={11} /> {k.m.title}
                          {k.impact != null && <b className={k.impact >= 0 ? 'pos' : 'neg'}> {pts(k.impact)}</b>}
                        </div>
                      ))}
                  </div>
                ) : null
              }
            />
            <Legend />
            {selected && <ReferenceLine x={selected.m.turn} stroke="#111827" strokeDasharray="4 4" />}
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
            {keyMoments.map((k, i) => {
              const { dy, r: size } = markerLayout[i] ?? { dy: 0, r: markerSize(k) }
              return (
                <ReferenceDot
                  key={i}
                  x={k.m.turn}
                  y={wpAt(k.m.turn)}
                  r={size}
                  ifOverflow="extendDomain"
                  zIndex={1000}
                  shape={(props: { cx?: number; cy?: number }) => (
                    <g
                      className="moment-marker"
                      role="button"
                      aria-label={`Turn ${k.m.turn}: ${k.m.title}`}
                      transform={`translate(${props.cx ?? 0},${(props.cy ?? 0) + dy})`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelected(k)
                      }}
                    >
                      {Math.abs(dy) > 3 && (
                        <g pointerEvents="none">
                          <line x1={0} y1={0} x2={0} y2={-dy} stroke="#6b7280" strokeWidth={1.25} />
                          <circle cx={0} cy={-dy} r={2.5} fill="#6b7280" />
                        </g>
                      )}
                      <CauseShape cause={k.m.kind} polarity={k.m.polarity} size={size} selected={selected === k} />
                    </g>
                  )}
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Key moments</h2>
          <ol className="moments">
            {keyMoments.map((k, i) => (
              <li key={i}>
                <button
                  type="button"
                  className={`moment cause-${k.m.kind} ${k.m.polarity > 0 ? 'up' : 'down'} ${selected === k ? 'selected' : ''}`}
                  aria-pressed={selected === k}
                  onClick={() => setSelected(selected === k ? null : k)}
                >
                  <span className="moment-turn">
                    <span className="sr-only">Turn </span>
                    <span aria-hidden="true">T</span>
                    {k.m.turn}
                  </span>
                  <span className="moment-body">
                    <span className="moment-title">
                      <span className="tag">
                        {CAUSE_LABEL[k.m.kind]} · {POLARITY_LABEL[k.m.kind][k.m.polarity > 0 ? 0 : 1]}
                      </span>
                      {k.m.title}
                    </span>
                    {k.m.detail && <span className="moment-detail">{k.m.detail}</span>}
                    {k.swing && <span className="moment-detail">{swingText(k.swing)}</span>}
                    {k.impact == null && k.m.turn === 0 && (
                      <span className="moment-detail">Opening choice: its cost shows up over the whole game, not on one turn.</span>
                    )}
                  </span>
                  {k.impact != null && (
                    <span
                      className={`impact ${Math.sign(k.impact) !== k.m.polarity ? 'mixed' : k.impact >= 0 ? 'pos' : 'neg'}`}
                      title={
                        Math.sign(k.impact) !== k.m.polarity
                          ? 'Net change in your win chance: other effects of the same turn outweighed this one'
                          : 'Change in your win chance, percentage points'
                      }
                    >
                      {Math.sign(k.impact) !== k.m.polarity && 'net '}
                      {pts(k.impact)}
                    </span>
                  )}
                </button>
              </li>
            ))}
            {keyMoments.length === 0 && <li className="muted">No standout moments in this game.</li>}
          </ol>
        </section>
        <section className="panel">
          <h2>Final board</h2>
          <BoardMap board={game.board} buildings={game.buildings} highlight={selected?.m.loc ?? selected?.m.hex ?? null} />
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
            <ComposedChart data={timeline} title="Cumulative cards received vs. expected, by turn">
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
            <ComposedChart data={game.dice_histogram} title="Dice rolls vs. expected 2d6 distribution">
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
        <div className="table-wrap" role="region" aria-label="Players" tabIndex={0}>
        <table className="table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Seat</th>
              <th>Final VP</th>
              <th className="opt">Strategy</th>
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
                  {p.color === game.winner && (
                    <span role="img" aria-label="winner">
                      {' '}
                      🏆
                    </span>
                  )}
                </td>
                <td>{game.play_order.indexOf(p.color) + 1}</td>
                <td>{p.final_vp}</td>
                <td className="opt">{STRATEGY_LABELS[p.strategy]}</td>
                <td className={p.luck_z >= 0 ? 'pos' : 'neg'}>{signed(p.luck_z)}</td>
                <td>{pct(p.setup_pct)}</td>
                <td>{p.decision_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>
    </div>
  )
}

const COMPONENT_LABELS: Record<string, string> = {
  opening: 'Opening placements',
  tempo: 'Tempo (time at or above median VP; outcome, not scored)',
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
      <div className="meter-track" role="presentation">
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

function swingText(s: Swing) {
  const parts = (['decision', 'luck', 'opponent'] as Cause[])
    .filter((c) => Math.abs(s.parts[c]) >= 0.01)
    .map((c) => `${c === 'decision' ? 'your moves' : c === 'luck' ? 'dice & robber' : 'opponents'} ${pts(s.parts[c])}`)
  return `Win chance ${pct(s.wp_before)} → ${pct(s.wp_after)} this turn${parts.length > 1 ? ` (${parts.join(', ')})` : ''}.`
}

const TIMELINE_HEIGHT = 340
// Timeline LineChart left + right margin plus the default 60px YAxis width.
const TIMELINE_X_INSET = 0 + 16 + 60
// Top + bottom margin plus the default 30px XAxis height (the legend is added on top).
const TIMELINE_Y_INSET = 16 + 8 + 30

function wpAtTurn(timeline: GameAnalysis['timeline'], key: string, turn: number) {
  let v = timeline[0]?.[key] ?? 0
  for (const r of timeline) {
    if (r.turn <= turn) v = r[key]
    else break
  }
  return v
}

function markerSize(k: KeyMoment) {
  return 7 + 7 * Math.min(1, Math.abs(k.impact ?? 0.1) / 0.35)
}

function CauseShape({ cause, polarity, size, selected }: { cause: Cause; polarity: number; size: number; selected?: boolean }) {
  const fill = polarity > 0 ? GOOD : BAD
  const stroke = selected ? '#111827' : '#fff'
  const r = size
  const body =
    cause === 'decision' ? (
      <circle r={r} fill={fill} stroke={stroke} strokeWidth={2} />
    ) : cause === 'luck' ? (
      <rect x={-r * 0.85} y={-r * 0.85} width={r * 1.7} height={r * 1.7} transform="rotate(45)" fill={fill} stroke={stroke} strokeWidth={2} />
    ) : (
      <rect x={-r * 0.85} y={-r * 0.85} width={r * 1.7} height={r * 1.7} rx={2} fill="#fff" stroke={selected ? '#111827' : fill} strokeWidth={selected ? 3 : 2.5} />
    )
  const a = r * 0.45
  const arrow = polarity > 0 ? `M${-a},${a * 0.6} L0,${-a * 0.8} L${a},${a * 0.6} Z` : `M${-a},${-a * 0.6} L0,${a * 0.8} L${a},${-a * 0.6} Z`
  return (
    <g>
      {body}
      <path d={arrow} fill={cause === 'opponent' ? fill : '#fff'} />
    </g>
  )
}

function CauseIcon({ cause, polarity, size = 9 }: { cause: Cause; polarity: number; size?: number }) {
  const box = size * 2 + 6
  return (
    <svg width={box} height={box} viewBox={`${-box / 2} ${-box / 2} ${box} ${box}`} style={{ verticalAlign: 'middle' }}>
      <CauseShape cause={cause} polarity={polarity} size={size} />
    </svg>
  )
}
