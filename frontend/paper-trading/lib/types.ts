export type Account = {
  id: number;
  name: string;
  initial_cash: string;
  status: string;
  base_currency: string;
  fee_preset: string;
  commission_rate: string;
  min_commission: string;
  stamp_duty_rate: string;
  transfer_fee_rate: string;
  share_count: string;
  net_asset_value: string;
  cumulative_deposit: string;
  cumulative_withdrawal: string;
};

export type MetricValue = {
  value: string | null;
  reason: string | null;
};

export type ActivityBucket = {
  period: string;
  order_count: number;
  trade_count: number;
  filled_count: number;
  rejected_count: number;
};

export type RejectReasonBucket = {
  reason: string;
  count: number;
};

export type OverviewAnalytics = {
  total_assets: string | null;
  cash_available: string | null;
  market_value: string | null;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  net_asset_value: string | null;
  share_count: string | null;
  total_return: MetricValue;
  simple_asset_return: MetricValue | null;
};

export type ExecutionAnalytics = {
  order_count: number;
  filled_count: number;
  rejected_count: number;
  fill_rate: MetricValue;
  rejection_rate: MetricValue;
  reject_reasons: RejectReasonBucket[];
};

export type RoundTrip = {
  id: number;
  symbol: string;
  open_trade_date: string;
  close_trade_date: string | null;
  entry_amount: string;
  exit_amount: string;
  fees: string;
  realized_pnl: string;
  return_pct: string | null;
  holding_days: number | null;
  status: string;
};

export type TradeQualityAnalytics = {
  closed_count: number;
  win_rate: MetricValue;
  avg_win: MetricValue;
  avg_loss: MetricValue;
  payoff_ratio: MetricValue;
  profit_factor: MetricValue;
  consecutive_wins: number;
  consecutive_losses: number;
  avg_holding_days: MetricValue;
  round_trips: RoundTrip[];
};

export type RiskAnalytics = {
  max_drawdown: MetricValue;
  current_drawdown: MetricValue;
  sharpe: MetricValue;
  sortino: MetricValue;
  calmar: MetricValue;
};

export type AnalyticsResponse = {
  overview: OverviewAnalytics;
  activity_daily: ActivityBucket[];
  activity_weekly: ActivityBucket[];
  activity_monthly: ActivityBucket[];
  execution: ExecutionAnalytics;
  trade_quality: TradeQualityAnalytics;
  risk: RiskAnalytics;
};

export type Position = {
  symbol: string;
  total_quantity: number;
  frozen_quantity: number;
  cost_amount: string;
  realized_pnl: string;
};

export type CashLedgerEntry = {
  id: number;
  account_id: number;
  event_type: string;
  amount: string;
  trade_date: string | null;
  net_asset_value: string | null;
  share_delta: string | null;
  note: string | null;
};

export type OrderSide = "buy" | "sell";

export type Order = {
  id: number;
  account_id: number;
  symbol: string;
  side: OrderSide;
  quantity: number;
  limit_price: string;
  trade_date: string;
  status: string;
  filled_quantity: number;
  frozen_cash: string;
  frozen_quantity: number;
  rejection_code: string | null;
  rejection_reason: string | null;
  comment: string | null;
};

export type Trade = {
  id: number;
  order_id: number;
  account_id: number;
  symbol: string;
  side: OrderSide;
  quantity: number;
  price: string;
  amount: string;
  fees: string;
  trade_date: string;
  comment: string | null;
};

export type Snapshot = {
  id: number;
  account_id: number;
  trade_date: string;
  cash_available: string;
  cash_frozen: string;
  market_value: string;
  total_assets: string;
  realized_pnl: string;
  unrealized_pnl: string;
  net_asset_value: string | null;
  share_count: string | null;
  cumulative_deposit: string | null;
  cumulative_withdrawal: string | null;
  net_cash_flow: string | null;
  position_count: number;
  order_count: number;
  trade_count: number;
};

export type MatchingRun = {
  id: number;
  trade_date: string;
  account_id: number | null;
  status: string;
  processed_count: number;
  filled_count: number;
  skipped_count: number;
  rejected_count: number;
  failed_count: number;
};

export type CreateAccountInput = {
  name: string;
  initial_cash: string;
  fee_preset?: string;
  commission_rate?: string;
  min_commission?: string;
  stamp_duty_rate?: string;
  transfer_fee_rate?: string;
};

export type UpdateAccountFeesInput = {
  commission_rate?: string;
  min_commission?: string;
  stamp_duty_rate?: string;
  transfer_fee_rate?: string;
};

export type CreateOrderInput = {
  symbol: string;
  side: OrderSide;
  quantity: number;
  limit_price: string;
  trade_date: string;
  idempotency_key?: string;
  comment?: string | null;
};

export type CreateMatchingRunInput = {
  trade_date: string;
  account_id?: number;
};

export type ImportPositionInput = {
  symbol: string;
  quantity: number;
  cost_price: string;
  buy_trade_date: string;
};

export type ImportPositionsInput = {
  positions: ImportPositionInput[];
};

export type ImportPositionsResult = {
  imported_count: number;
  lots_count: number;
};

export type CashFlowInput = { amount: string; trade_date: string; note?: string };
export type CashFlowResult = { account_id: number; cash_available: string; net_asset_value: string; share_count: string; ledger: CashLedgerEntry };
