import type { ReactNode } from 'react'

export type Resource = 'lumber' | 'brick' | 'wool' | 'grain' | 'ore' | 'desert'

// Original, deliberately simple game-piece illustrations. No third-party assets.
export function ResourceGlyph({ resource }: { resource: string }) {
  const shapes: Record<Resource, ReactNode> = {
    lumber: <><path d="M-3 11h6v12h-6z" fill="#72452d" /><path d="M0-25 17-3H9L23 15H-23L-9-3H-17Z" fill="#225c48" /><path d="M0-25V15H-23L-9-3H-17Z" fill="#32765a" /></>,
    brick: <><path d="M-23-3 8-15 25-5-6 8Z" fill="#f4a079" /><path d="M-23-3-6 8V24L-23 13Z" fill="#b74d3c" /><path d="M-6 8 25-5V11L-6 24Z" fill="#d76a4f" /><path d="M-9-8 8 3M8 3V18" fill="none" stroke="#fff0cc" strokeWidth="2" /></>,
    wool: <><path d="M-14 9-15 23M9 9 10 23" stroke="#3d4945" strokeWidth="5" strokeLinecap="round" /><path d="M-20 0C-28-10-18-19-10-15-7-26 6-23 10-16 23-17 26-5 20 2 20 15 4 18-3 13-15 18-25 10-20 0Z" fill="#fff9e6" /><ellipse cx="19" cy="5" rx="9" ry="12" fill="#3d4945" /><circle cx="22" cy="1" r="2" fill="#fff9e6" /><path d="M17-7 10-11M24-5 29-9" stroke="#3d4945" strokeWidth="5" strokeLinecap="round" /></>,
    grain: <><path d="M0 24V-23M-13 24V-7M13 24V-7" fill="none" stroke="#91601b" strokeWidth="3" strokeLinecap="round" />{[-12, 0, 12].map((x) => <g key={x} transform={`translate(${x} ${x === 0 ? -9 : 6})`} fill="#ffe38b"><ellipse cx="-5" cy="-5" rx="4" ry="8" transform="rotate(-35 -5 -5)" /><ellipse cx="5" cy="-5" rx="4" ry="8" transform="rotate(35 5 -5)" /><ellipse cx="-5" cy="7" rx="4" ry="8" transform="rotate(-35 -5 7)" /><ellipse cx="5" cy="7" rx="4" ry="8" transform="rotate(35 5 7)" /></g>)}</>,
    ore: <><path d="M-25 19-11-15 3 2 14-24 29 19Z" fill="#667b8a" /><path d="M-11-15 3 2 14-24 16 19H-7Z" fill="#91a5ac" /><path d="M-11-15-17 0-9-3-3 2ZM14-24 7-8 15-12 21-6Z" fill="#e5ede7" /></>,
    desert: <><circle cy="-12" r="10" fill="#fff1b7" /><path d="M-27 19Q-7-7 8 12Q19-3 30 19Z" fill="#c6914e" /></>,
  }
  return <g>{shapes[resource as Resource] ?? shapes.desert}</g>
}

export function FeatureIcon({ kind }: { kind: 'profile' | 'dice' | 'timeline' }) {
  return (
    <svg viewBox="0 0 48 48" width="44" height="44" fill="none" aria-hidden="true">
      {kind === 'profile' ? <><path d="M9 38V25h8v13M21 38V17h8v21M33 38V8h8v30" fill="#4b9f77" stroke="#254e43" strokeWidth="2.5" strokeLinejoin="round" /><path d="m8 17 12-7 6 3L38 3" stroke="#254e43" strokeWidth="2.5" strokeLinecap="round" /></> : kind === 'dice' ? <g transform="rotate(-10 24 24)"><rect x="8" y="7" width="33" height="34" rx="7" fill="#fff9e9" stroke="#8c5b35" strokeWidth="2.5" />{[[17, 16], [32, 16], [24, 24], [17, 32], [32, 32]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.5" fill="#b85c36" />)}</g> : <><path d="M6 8v31h36" stroke="#315d7b" strokeWidth="2.5" strokeLinecap="round" /><path d="m10 29 10-10 10 5L40 9" stroke="#4a8fb4" strokeWidth="4" strokeLinejoin="round" />{[[10, 29], [20, 19], [30, 24], [40, 9]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="3.5" fill="#fff9e9" stroke="#315d7b" strokeWidth="2" />)}</>}
    </svg>
  )
}

export default function IslandArt() {
  const tiles: { x: number; y: number; resource: Resource; fill: string; number: number }[] = [
    { x: 202, y: 111, resource: 'lumber', fill: '#78ab79', number: 6 },
    { x: 328, y: 111, resource: 'ore', fill: '#bccbca', number: 3 },
    { x: 139, y: 220, resource: 'grain', fill: '#e9bb56', number: 8 },
    { x: 265, y: 220, resource: 'wool', fill: '#a8cb77', number: 5 },
    { x: 391, y: 220, resource: 'lumber', fill: '#78ab79', number: 9 },
    { x: 202, y: 329, resource: 'brick', fill: '#dc8b66', number: 4 },
    { x: 328, y: 329, resource: 'grain', fill: '#e9bb56', number: 10 },
  ]
  return (
    <div className="island-art">
      <svg viewBox="0 0 530 455" fill="none" aria-hidden="true">
        <ellipse cx="265" cy="239" rx="246" ry="207" fill="#d0e9e7" />
        <ellipse cx="265" cy="239" rx="224" ry="187" stroke="#b2d8d5" strokeWidth="2" strokeDasharray="6 10" />
        <g transform="translate(0 7)" opacity=".16">{tiles.map((t) => <path key={t.number} transform={`translate(${t.x} ${t.y})`} d="M0-70 61-35V35L0 70-61 35V-35Z" fill="#284d4c" />)}</g>
        {tiles.map((t) => <g key={t.number} transform={`translate(${t.x} ${t.y})`}>
          <path d="M0-70 61-35V35L0 70-61 35V-35Z" fill={t.fill} stroke="#fff4d9" strokeWidth="5" strokeLinejoin="round" />
          <g transform="translate(0 -16)"><ResourceGlyph resource={t.resource} /></g>
          <circle cy="35" r="18" fill="#fff4d9" stroke="#8c714a" strokeWidth="1.5" />
          <text y="41" fill={t.number === 6 || t.number === 8 ? '#a94732' : '#304843'} textAnchor="middle" fontSize="19" fontWeight="800">{t.number}</text>
          <path d="M-43 10h8M35-31h6" stroke="#fff4d9" strokeOpacity=".4" strokeWidth="3" strokeLinecap="round" />
        </g>)}
        <path d="m202 181 62-35 62 35" stroke="#7d4432" strokeWidth="13" strokeLinecap="round" />
        <path d="m202 178 62-35 62 35" stroke="#e4794f" strokeWidth="8" strokeLinecap="round" />
        <g transform="translate(264 143)"><path d="M-16 4 0-12 16 4V23H-16Z" fill="#f9ab69" stroke="#734a35" strokeWidth="3" strokeLinejoin="round" /><path d="M-20 4 0-16 20 4" stroke="#734a35" strokeWidth="4" strokeLinecap="round" /><path d="M-4 23V11H4V23" fill="#734a35" /></g>
        <path d="m329 290 61-35" stroke="#315a78" strokeWidth="13" strokeLinecap="round" /><path d="m329 287 61-35" stroke="#68a7c9" strokeWidth="8" strokeLinecap="round" />
        <g transform="translate(390 251)"><path d="M-15 22V-6L-2-17 10-6V4H21V22Z" fill="#8ec4dd" stroke="#315a78" strokeWidth="3" strokeLinejoin="round" /><path d="M-7-2H0M-7 7H0M10 13H16" stroke="#315a78" strokeWidth="3" /></g>
        <g transform="translate(55 85) rotate(-14)"><rect x="-25" y="-25" width="54" height="54" rx="11" fill="#244f59" opacity=".14" transform="translate(0 5)" /><rect x="-25" y="-25" width="54" height="54" rx="11" fill="#fff9e9" stroke="#315451" strokeWidth="2.5" />{[[-12,-12],[12,-12],[0,0],[-12,12],[12,12]].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="3.7" fill="#365752" />)}</g>
        <path d="m449 84 3 9 9 3-9 3-3 9-3-9-9-3 9-3ZM72 326l3 9 9 3-9 3-3 9-3-9-9-3 9-3Z" fill="#c58c34" />
        <path d="M425 368q8-9 16 0t16 0M57 230q8-9 16 0t16 0" stroke="#75b6b7" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="island-caption"><span className="caption-dot" /> A little less “bad dice.” A little more insight.</div>
    </div>
  )
}
