export type Bucket = {
  key?: string | number
  label?: string
  games: number
  wins: number
  win_rate: number
  expected_rate?: number
  z?: number
}

export type Insight = {
  kind: 'strength' | 'weakness' | 'luck' | 'info'
  title: string
  detail: string
}

export type GameSummary = {
  id: string
  start_ms: number
  duration_min: number
  turns: number
  players: number
  won: boolean
  rank: number
  points: number
  vp_to_win: number
  winner_points: number
  play_order: number | null
  finished?: boolean
  quit: boolean
  bots: number
  has_replay: boolean
  analyzed?: boolean
  verdict?: string
  luck_index?: number
  decision_score?: number
  decision_edge?: number
  strategy?: string
  opponents: { name: string; rank: number; points: number; human: boolean }[]
}

export type DeepStats = {
  games: number
  verdicts: Record<string, number>
  strategies: Bucket[]
  luck_split: Record<'lucky' | 'neutral' | 'unlucky', Bucket>
  avg_luck: { wins: number; losses: number }
  avg_decision: { wins: number; losses: number }
  scatter: { id: string; luck: number; decision: number; won: boolean; seat: string }[]
  insights: Insight[]
}

export type Profile = {
  username: string
  source: 'colonist' | 'demo'
  games: GameSummary[]
  stats: {
    overall: Bucket & {
      skill_ratio: number
      avg_vp_share: number
      quits: number
      close_losses: number
      losses: number
      avg_rank: number
      fetched?: number
      unfinished?: number
      bot_games?: number
      play_order_known?: number
      first_ms?: number
      last_ms?: number
    }
    breakdowns: Record<string, Bucket[]>
    insights: Insight[]
    trend: { index: number; id: string; won: boolean; rolling_win_rate: number; rolling_expected: number }[]
    opponents: (Bucket & { name: string })[]
    deep?: DeepStats
  }
}

export type Moment = {
  turn: number
  kind: 'decision' | 'luck'
  player: number
  polarity: 1 | -1
  magnitude: number
  title: string
  detail: string
  mine: boolean
  loc?: string
  hex?: string
}

export type BoardData = {
  tiles: { id: string; resource: string; number: number | null; center: [number, number] }[]
  corners: { id: string; point: [number, number] }[]
  edges: { id: string; a: string; b: string }[]
  ports: { edge: string; kind: string }[]
  robber: string | null
}

export type GamePlayer = {
  color: number
  name: string
  final_vp: number
  strategy: string
  luck_z: number
  decision_score: number
  setup_pct: number
}

export type GameAnalysis = {
  id: string
  summary: GameSummary
  color_names: Record<string, string>
  focus: number
  won: boolean
  winner: number
  players: GamePlayer[]
  play_order: number[]
  seat: number
  turns: number
  verdict: string
  verdict_detail: string
  luck_index: number
  decision_score: number
  opp_decision_score: number
  decision_edge: number
  components: Record<string, number | null>
  luck: {
    dice_z: number
    opp_dice_z: number
    roll_income: number
    roll_expected: number
    robber_blocked: number
    stolen_from: number
    stole: number
    sevens: number
  }
  stats: {
    discarded: number
    bank_trades: number
    dev_bought: number
    knights: number
    first_city: number | null
    first_settlement: number | null
    cities: number
    settlements: number
    awards: string[]
    vp_cards: number
  }
  strategy: string
  dice_histogram: { total: number; count: number; expected: number }[]
  timeline: Record<string, number>[]
  moments: Moment[]
  critical: Moment[]
  board: BoardData
  buildings: Record<string, { settlements: string[]; cities: string[]; roads: string[] }>
}
