export type Account = {
  id: number;
  name: string;
  initial_cash: string;
  status: string;
  base_currency: string;
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
};

export type CreateOrderInput = {
  symbol: string;
  side: OrderSide;
  quantity: number;
  limit_price: string;
  trade_date: string;
  idempotency_key?: string;
};

export type CreateMatchingRunInput = {
  trade_date: string;
  account_id?: number;
};
