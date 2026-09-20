export interface Position {
  symbol: string
  exchange: string
  product: 'MIS' | 'NRML' | 'CNC'
  quantity: number
  average_price: number
  ltp: number
  pnl: number
  pnlpercent: number
  lot_size?: number // contract_value multiplier (e.g. 0.01 for ETHUSD.P)
  today_realized_pnl?: number // Sandbox: today's realized P&L from closed partial trades
}

export interface Order {
  symbol: string
  exchange: string
  action: 'BUY' | 'SELL'
  quantity: number
  price: number
  trigger_price: number
  pricetype: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  product: 'MIS' | 'NRML' | 'CNC'
  orderid: string
  order_status: 'complete' | 'rejected' | 'cancelled' | 'open' | 'pending' | 'trigger pending'
  timestamp: string
}

export interface Trade {
  symbol: string
  exchange: string
  action: 'BUY' | 'SELL'
  quantity: number
  average_price: number
  trade_value: number
  product: string
  orderid: string
  timestamp: string
}

export interface Holding {
  symbol: string
  exchange: string
  quantity: number
  product: string
  pnl: number
  pnlpercent: number
  ltp?: number
  average_price?: number
}

export interface PortfolioStats {
  totalholdingvalue: number
  totalinvvalue: number
  totalprofitandloss: number
  totalpnlpercentage: number
}

// Alias for consistency
export type HoldingsStats = PortfolioStats

export interface MarginData {
  availablecash: number
  collateral: number
  m2munrealized: number
  m2mrealized: number
  utiliseddebits: number
}

export interface OrderStats {
  total_buy_orders: number
  total_sell_orders: number
  total_completed_orders: number
  total_open_orders: number
  total_rejected_orders: number
}

// -----------------------------------------------------------------------------
// GTT (Good Till Triggered)
// -----------------------------------------------------------------------------

export interface GttLeg {
  action: string // "BUY" | "SELL"
  quantity: number
  price: number
  pricetype: string // usually "LIMIT"
  product: string // "MIS" | "NRML" | "CNC"
  triggered_order_id?: string | null // the order this leg placed when it fired (sandbox)
}

export type GttStatus =
  | 'active'
  | 'triggered'
  | 'disabled'
  | 'expired'
  | 'cancelled'
  | 'rejected'
  | 'deleted'
  | string // broker-specific statuses passed through as-is

export interface GttOrder {
  trigger_id: string
  trigger_type: 'single' | 'two-leg' | string
  status: GttStatus
  symbol: string
  exchange: string
  trigger_prices: number[]
  last_price: number
  legs: GttLeg[]
  created_at?: string
  updated_at?: string
  expires_at?: string
}

export interface PlaceOrderRequest {
  apikey: string
  strategy: string
  exchange: string
  symbol: string
  action: 'BUY' | 'SELL'
  quantity: number
  pricetype?: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  product?: 'MIS' | 'NRML' | 'CNC'
  price?: number
  trigger_price?: number
  disclosed_quantity?: number
}

export interface ApiResponse<T> {
  status: 'success' | 'error' | 'info'
  message?: string
  data?: T
}

// -----------------------------------------------------------------------------
// Strategy-attributed Positions & Broker Reconciliation
// -----------------------------------------------------------------------------

export interface StrategyPositionItem {
  strategy: string
  symbol: string
  exchange: string
  product: 'MIS' | 'NRML' | 'CNC' | string
  signed_quantity: number
  side: 'LONG' | 'SHORT' | 'FLAT'
  quantity: number
  average_price: number
  ltp: number
  realized_pnl: number
  today_realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
  pnlpercent: number
  broker_quantity: number
  tracked_quantity: number
  residual_quantity: number
  reconciliation_status: string
}

export interface ContractReconciliation {
  symbol: string
  exchange: string
  product: string
  broker_quantity: number
  tracked_quantity: number
  residual_quantity: number
  has_residual: boolean
  strategies_count: number
  reconciliation_status: string
}

export interface AttributedSummary {
  total_broker_positions: number
  total_tracked_positions: number
  total_residual_positions: number
  total_realized_pnl: number
  total_unrealized_pnl: number
  total_pnl: number
  reconciliation_status: string
}

export interface ClosedPosition {
  strategy: string
  symbol: string
  exchange: string
  product: string
  direction: 'LONG' | 'SHORT'
  quantity: number
  entry_average: number
  exit_average: number
  entry_time: string
  exit_time: string
  realized_pnl: number
  status: 'CLOSED'
  exit_reason?: string
}

export interface AttributedPositionsData {
  positions: StrategyPositionItem[]
  contracts: ContractReconciliation[]
  closed_positions?: ClosedPosition[]
  summary: AttributedSummary
}

