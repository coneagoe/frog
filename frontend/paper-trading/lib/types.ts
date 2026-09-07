export type AuthIdentity = {
  id: number;
  email: string;
  email_verified_at: string | null;
};

export type AuthInput = {
  email: string;
  password: string;
};

export type ForgotPasswordInput = { email: string };
export type ResetPasswordInput = { token: string; password: string };
export type ResendVerificationEmailInput = { email: string };

export type Account = {
  id: number;
  name: string;
  initial_cash: string;
  cash_available: string;
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

export type ActivitySummary = {
  total_orders: string;
  successful_orders: string;
  failed_orders: string;
};

export type ActivityAnalytics = {
  coverage_start: string;
  coverage_end: string;
  daily: ActivitySummary;
  weekly: ActivitySummary;
  monthly: ActivitySummary;
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

export type SnapshotAnalyticsEvent = {
  event_type: "snapshot";
  id: number;
  event_at: string;
  trade_date: string;
  point_type: "initial" | "trading";
  quality: "valid" | "invalid";
  timezone: "UTC";
  quality_status: "valid" | "invalid";
  invalid_reason: string | null;
  nav: string | null;
  /** Legacy clients use `share`; both fields carry the same share count. */
  shares: string | null;
  share: string | null;
  valuation_quality?: "current" | "stale_suspended" | null;
  valuation_details?: Array<Record<string, unknown>> | null;
};

export type CashFlowAnalyticsEvent = {
  event_type: "deposit" | "withdrawal";
  id: number;
  occurred_at: string;
  amount: string;
  effective_nav: string | null;
  share_delta: string | null;
};

export type CorporateActionImpact = {
  cash_delta: string;
  quantity_delta: string;
  before_quantity: string;
  after_quantity: string;
  before_cost_amount: string;
  after_cost_amount: string;
  before_cash_available: string;
  after_cash_available: string;
  affected_start_date: string | null;
  affected_end_date: string | null;
};

export type CorporateActionEvent = {
  event_type: CorporateActionType;
  id: number;
  account_id: number;
  market: Market;
  symbol: string;
  event_at: string;
  idempotency_key: string;
  parameters: Record<string, string>;
  processing_status: string;
  processed_at: string | null;
  processing_metadata: Record<string, unknown> | null;
  error_details: string | null;
  cash_delta: string;
  quantity_delta: string;
  before_quantity: string;
  after_quantity: string;
  before_cost_amount: string;
  after_cost_amount: string;
  before_cash_available: string;
  after_cash_available: string;
  affected_start_date: string | null;
  affected_end_date: string | null;
  created_at: string;
};

export type AnalyticsCorporateActionEvent = {
  event_type: "corporate_action";
  id: number;
  event_at: string;
  symbol: string;
  action_type: CorporateActionType;
  parameters: Record<string, string>;
  impact: CorporateActionImpact;
  created_at: string;
};

export type AnalyticsEvent = SnapshotAnalyticsEvent | CashFlowAnalyticsEvent | AnalyticsCorporateActionEvent;

export type AvailableAnalyticsResponse = {
  available: true;
  overview: OverviewAnalytics;
  activity: ActivityAnalytics | null;
  execution: ExecutionAnalytics;
  trade_quality: TradeQualityAnalytics;
  risk: RiskAnalytics;
  valuation_gaps: ValuationGap[];
  event_series: AnalyticsEvent[];
};

export type ValuationGap = {
  trade_date: string;
  missing_symbols: string[];
  details: Array<Record<string, unknown>>;
  resolved: boolean;
};

export type UnavailableAnalyticsResponse = {
  available: false;
  reason: AnalyticsUnavailableReason;
  valuation_gaps: ValuationGap[] | null;
};

export type AnalyticsResponse = AvailableAnalyticsResponse | UnavailableAnalyticsResponse;

export type AnalyticsUnavailableReason =
  | "missing_initial"
  | "invalid_initial"
  | "replay_unavailable"
  | "valuation_gap"
  | "insufficient_data"
  | "legacy_ordering_uncertain";

export type Position = {
  symbol: string;
  stock_name: string | null;
  total_quantity: number;
  frozen_quantity: number;
  cost_amount: string;
  realized_pnl: string;
  mark_price: string | null;
  price_source: "real_time" | "db_close" | null;
  unrealized_pnl: string | null;
};

export type CashLedgerEntry = {
  id: number;
  account_id: number;
  event_type: string;
  amount: string;
  occurred_at: string;
  trade_date: string | null;
  net_asset_value: string | null;
  share_delta: string | null;
  note: string | null;
  rounding_residual?: string | null;
};

export type OrderSide = "buy" | "sell";
export type Market = "a_share" | "hk_connect" | "etf";

export type Order = {
  id: number;
  account_id: number;
  symbol: string;
  stock_name: string | null;
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

export type OrderPage = {
  items: Order[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
};

export type ListOrdersParams = {
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
};

export type Trade = {
  id: number;
  order_id: number;
  account_id: number;
  symbol: string;
  stock_name: string | null;
  side: OrderSide;
  quantity: number;
  price: string;
  amount: string;
  fees: string;
  trade_date: string;
  comment: string | null;
};

export type TradePage = {
  items: Trade[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
};

export type ListTradesParams = {
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
};

export type Snapshot = {
  id: number;
  account_id: number;
  trade_date: string;
  point_type: "initial" | "trading";
  event_at: string;
  quality_status: "valid" | "invalid";
  invalid_reason: string | null;
  valuation_quality: "current" | "stale_suspended" | null;
  valuation_details: Array<Record<string, unknown>> | null;
  timezone: "UTC";
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
  pending_settlement: string;
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
  error_details: string | null;
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
  market: Market;
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
  market: Market;
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

export type CorporateActionType = "dividend" | "split" | "reverse_split" | "bonus_share" | "rights_issue";
export type CorporateActionParameters =
  | { per_share_amount: string }
  | { ratio: string }
  | { bonus_ratio: string }
  | { subscription_ratio: string; subscription_price: string };
export type CorporateActionInput = {
  symbol: string;
  market?: Market;
  event_type: CorporateActionType;
  event_at: string;
  idempotency_key: string;
  parameters: CorporateActionParameters;
};
export type CorporateActionResult = {
  event: CorporateActionEvent;
  impact: CorporateActionImpact;
  recalculation: { account_id: number; updated_dates: string[]; unavailable_dates: string[]; failed_dates: string[]; errors: string[] };
};
export type ListCorporateActionsParams = {
  symbol?: string;
  event_type?: CorporateActionType;
  start_at?: string;
  end_at?: string;
};

export type MonitorCondition =
  | { type: "price_threshold"; direction: "above" | "below"; value: number }
  | { type: "ma_cross"; direction: "golden" | "death"; fast: number; slow: number }
  | { type: "change_pct"; direction: "above" | "below"; value: number }
  | { type: "price_cross_ma"; direction: "above" | "below"; period: number }
  | { type: "close_cross_ma"; direction: "above"; period: number }
  | { type: "rsi"; direction: "above" | "below"; value: number; period?: number };

export type MonitorMarket = "A" | "HK" | "ETF";
export type MonitorFrequency = "daily" | "intraday";
export type MonitorResetMode = "auto" | "manual";

export type MonitorTarget = {
  id: number;
  stock_code: string;
  market: MonitorMarket;
  condition: MonitorCondition;
  note: string | null;
  frequency: MonitorFrequency;
  reset_mode: MonitorResetMode;
  enabled: boolean;
  last_state: boolean;
  triggered_at: string | null;
  created_at: string | null;
};

export type ListMonitorTargetsParams = {
  frequency?: MonitorFrequency;
  enabled?: boolean;
  market?: MonitorMarket;
  condition_type?: MonitorCondition["type"];
};

export type CreateMonitorTargetInput = {
  stock_code: string;
  market: MonitorMarket;
  condition: MonitorCondition;
  note?: string | null;
  frequency?: MonitorFrequency;
  reset_mode?: MonitorResetMode;
  enabled?: boolean;
};

export type UpdateMonitorTargetInput = Partial<CreateMonitorTargetInput>;

export type MonitorEvaluationErrorKind = "market_data" | "condition" | "workflow_guard" | "notification" | "storage" | "unknown";
export type MonitorOperationalState = "running" | "paused" | "disabled";
export type MonitorTargetHealthError = { kind: MonitorEvaluationErrorKind; summary: string; detail: string | null; occurred_at: string };
export type MonitorTargetHealthSummary = { total: number; running: number; paused: number; disabled: number; triggered: number; daily: number; intraday: number };
export type MonitorTargetHealthItem = { id: number; stock_code: string; market: MonitorMarket; frequency: MonitorFrequency; workflow: string | null; enabled: boolean; paused: boolean; operational_state: MonitorOperationalState; last_state: boolean; last_checked_at: string | null; triggered_at: string | null; latest_error: MonitorTargetHealthError | null };
export type MonitorTargetHealth = { summary: MonitorTargetHealthSummary; targets: MonitorTargetHealthItem[] };
