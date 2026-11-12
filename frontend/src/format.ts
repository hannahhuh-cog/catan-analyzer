export const pct = (x: number | undefined | null) => (x == null ? '-' : `${Math.round(x * 100)}%`)
export const signed = (x: number, digits = 1) => `${x >= 0 ? '+' : ''}${x.toFixed(digits)}`

export const PLAYER_COLORS: Record<number, string> = {
  1: '#2563eb',
  2: '#dc2626',
  3: '#ea580c',
  4: '#92400e',
  5: '#64748b',
  6: '#16a34a',
  7: '#7c3aed',
  8: '#db2777',
  9: '#0891b2',
  10: '#4b5563',
  11: '#ca8a04',
}

export const STRATEGY_LABELS: Record<string, string> = {
  city_rush: 'Ore/Wheat city rush',
  expansion: 'Road & settlement expansion',
  dev_cards: 'Development cards',
  balanced: 'Balanced',
}

export const VERDICT_TONE: Record<string, 'good' | 'bad' | 'luck' | 'neutral'> = {
  'Earned win': 'good',
  'Good play, good dice': 'good',
  'Scrappy win': 'good',
  'Lucky win': 'luck',
  'Lost to RNG': 'luck',
  'Unlucky and outplayed': 'bad',
  'Unlucky loss': 'luck',
  Outplayed: 'bad',
  'Strategic loss': 'bad',
  'Close call': 'neutral',
}

export const LOSS_VERDICTS = [
  'Lost to RNG',
  'Unlucky loss',
  'Unlucky and outplayed',
  'Outplayed',
  'Strategic loss',
  'Close call',
]

export const RESOURCE_COLORS: Record<string, string> = {
  lumber: '#4d7c0f',
  brick: '#b45309',
  wool: '#a3e635',
  grain: '#facc15',
  ore: '#94a3b8',
  desert: '#e7d7b1',
}

export function timeAgo(ms: number) {
  if (!ms) return ''
  const d = new Date(ms)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
