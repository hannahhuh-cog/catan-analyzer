import { PLAYER_COLORS, RESOURCE_COLORS } from './format'
import type { BoardData, GameAnalysis } from './types'

const R = 1

function hexPoints([cx, cy]: [number, number]) {
  return Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (60 * i - 30)
    return `${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`
  }).join(' ')
}

export default function BoardMap({
  board,
  buildings,
  highlight,
}: {
  board: BoardData
  buildings: GameAnalysis['buildings']
  highlight?: string | null
}) {
  const corners = new Map(board.corners.map((c) => [c.id, c.point]))
  const edges = new Map(board.edges.map((e) => [e.id, e]))
  const pts = board.tiles.map((t) => t.center)
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  const pad = 1.6
  const vb = [Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) - Math.min(...xs) + 2 * pad, Math.max(...ys) - Math.min(...ys) + 2 * pad]
  return (
    <svg className="board" viewBox={vb.join(' ')} role="img" aria-label="Final board position">
      {board.tiles.map((t) => (
        <g key={t.id}>
          <polygon
            points={hexPoints(t.center)}
            fill={RESOURCE_COLORS[t.resource] ?? '#cbd5e1'}
            stroke={highlight === t.id ? '#111827' : '#f8fafc'}
            strokeWidth={highlight === t.id ? 0.12 : 0.06}
          />
          {t.number && (
            <>
              <circle cx={t.center[0]} cy={t.center[1]} r={0.32} fill="#fffbeb" />
              <text
                x={t.center[0]}
                y={t.center[1] + 0.12}
                textAnchor="middle"
                fontSize={0.34}
                fontWeight={700}
                fill={t.number === 6 || t.number === 8 ? '#b91c1c' : '#1f2937'}
              >
                {t.number}
              </text>
            </>
          )}
        </g>
      ))}
      {board.ports.map((p) => {
        const e = edges.get(p.edge)
        if (!e) return null
        const a = corners.get(e.a)!
        const b = corners.get(e.b)!
        const mx = (a[0] + b[0]) / 2
        const my = (a[1] + b[1]) / 2
        const len = Math.hypot(mx, my) || 1
        const ox = mx + (mx / len) * 0.45
        const oy = my + (my / len) * 0.45
        return (
          <g key={p.edge}>
            <line x1={a[0]} y1={a[1]} x2={ox} y2={oy} stroke="#a16207" strokeWidth={0.05} />
            <line x1={b[0]} y1={b[1]} x2={ox} y2={oy} stroke="#a16207" strokeWidth={0.05} />
            <circle cx={ox} cy={oy} r={0.26} fill="#fff" stroke="#a16207" strokeWidth={0.04} />
            <text x={ox} y={oy + 0.08} textAnchor="middle" fontSize={0.2} fill="#78350f">
              {p.kind === '3:1' ? '3:1' : p.kind.slice(0, 2)}
            </text>
          </g>
        )
      })}
      {Object.entries(buildings).map(([color, b]) => {
        const fill = PLAYER_COLORS[Number(color)] ?? '#000'
        return (
          <g key={color}>
            {b.roads.map((id) => {
              const e = edges.get(id)
              if (!e) return null
              const a = corners.get(e.a)!
              const c = corners.get(e.b)!
              return <line key={id} x1={a[0]} y1={a[1]} x2={c[0]} y2={c[1]} stroke={fill} strokeWidth={0.16} strokeLinecap="round" />
            })}
            {b.settlements.map((id) => {
              const p = corners.get(id)!
              return <circle key={id} cx={p[0]} cy={p[1]} r={0.2} fill={fill} stroke={highlight === id ? '#111827' : '#fff'} strokeWidth={highlight === id ? 0.1 : 0.05} />
            })}
            {b.cities.map((id) => {
              const p = corners.get(id)!
              return <rect key={id} x={p[0] - 0.26} y={p[1] - 0.26} width={0.52} height={0.52} rx={0.08} fill={fill} stroke={highlight === id ? '#111827' : '#fff'} strokeWidth={highlight === id ? 0.1 : 0.05} />
            })}
          </g>
        )
      })}
      {board.robber &&
        (() => {
          const t = board.tiles.find((x) => x.id === board.robber)
          return t ? <circle cx={t.center[0] - 0.45} cy={t.center[1]} r={0.15} fill="#111827" /> : null
        })()}
    </svg>
  )
}
