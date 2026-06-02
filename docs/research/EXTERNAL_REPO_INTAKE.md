# EXTERNAL REPO INTAKE — kucoin-lane
_Last updated: 2026-06-02_  
_Scope: 4 cloned repos in `/home/we4free/agent/repos/kucoin-lane/external/`_  
_Constraints: SPOT LONG-ONLY, BTC/USDT + ETH/USDT, $110 capital, 0.1% KuCoin fees, round-trip ≥ 0.35%, paper-live mode, no external repo holds API keys, research-only usage._

---

## Table of Contents
1. [Freqtrade](#1-freqtrade)
2. [Freqtrade Strategies](#2-freqtrade-strategies)
   - [Top 5 Strategies for $110 Micro-Account](#top-5-strategies-for-110-micro-account)
3. [VectorBT](#3-vectorbt)
4. [CCXT](#4-ccxt)
5. [Cross-Repo Recommendations](#cross-repo-recommendations)

---

## 1. Freqtrade

| Field | Value |
|-------|-------|
| **Repo name** | freqtrade |
| **URL** | https://github.com/freqtrade/freqtrade |
| **License** | **GPL-3.0** (copyleft — derivative works must also be GPL-3) |

### Summary
Freqtrade is a full-featured Python crypto trading bot framework supporting multi-exchange spot and futures trading. It includes a persistent SQLite trade store, dry-run (paper-live) mode, vector-based backtesting, hyperopt parameter optimization, FreqAI adaptive ML, Telegram/web UI control, and a protection manager (Cooldown, MaxDrawdown, StoplossGuard). KuCoin is explicitly listed as a community-confirmed exchange.

### Key Patterns Useful for kucoin-lane

| Pattern | Where in Code | Why It Matters |
|---------|---------------|----------------|
| **Fee-aware backtesting** | `freqtrade/optimize/backtesting.py:243-256` — `set_fee()` picks worst-case taker/maker from exchange; `Trade.update_fee()` records per-order fee_open/fee_close rates. | Shows canonical approach: record fee_rate per fill (not just flat pct), so P&L math stays correct even when tier upgrades. |
| **Paper-live wallet isolation** | `constants.py:DEFAULT_DB_DRYRUN_URL`, `freqtradebot.py:FreqtradeBot.main()` dry-run branch. | Separate SQLite DB (`tradesv3.dryrun.sqlite`) ensures paper trades never pollute production history. |
| **Protection manager** | Strategy-level `protections` list (Cooldown, StoplossGuard, MaxDrawdown, PartialCollateral, etc.). | Our $110 account needs circuit-breakers; this pattern is directly reusable. |
| **Stoploss-on-exchange (SoE)** | `freqtrade/exchange/exchange.py:1212-1378` — `add_dry_order_fee`, stoploss_on_exchange flag. | For spot long-only at $110, SoE guarantees the stop executes even if our bot crashes. |
| **Informative pairs / multi-TF** | `strategy/interface.py` — `informative_pairs()`, `merge_informative_pair()`. | Same signal logic across 1h, 4h, 1d without multiple strategy instances. |
| **FtPrecise decimal arithmetic** | `persistence/trade_model.py` — `_calc_base_close()` uses `FtPrecise`. | Prevents float shenanigans on $110 where $0.01 rounding matters. |
| **Minimal ROI as per-minute table** | Every strategy — `minimal_roi = {"0": 0.05, "60": 0.30, "120": 0}`. | Directly maps to our "take profit at X% after Y candles" rule. |
| **Custom exit / Trailing stop** | `reinforced_smooth_scalp`-style trailing with `trailing_stop_positive`, `trailing_stop_positive_offset`. | Especially relevant given our ≤0.35% friction: a 0.3% trailing stop doesn't clear fees. |

### Fee-Awareness
Yes — extensive. Freqtrade:
- Fetches exchange taker/maker fee via `Exchange.get_fee()` at startup (`backtesting.py:249-253`).
- Records `fee_open`, `fee_close`, `fee_open_cost`, `fee_close_cost`, `funding_fees` on each `Trade` and `Order` row.
- Computes real P&L via `_calc_base_close()` which subtracts fee from exit value: `close_value = close_value * FtPrecise(fee)` for buys.
- Requires explicit `fee` config override if exchange-reported rate is unavailable.
- Dry-run injects simulated fee via `add_dry_order_fee(..., taker_or_maker)`.

### Micro-Account Suitability
- `DRY_RUN_WALLET = 1000` is the built-in paper-live default. Our $110 would need `stake_amount: "unlimited"` or a percentage-based stake.
- Single-pair, single-trade-at-a-time configs work. Multi-pair hyperopt strategies over-split capital.
- `minimal_roi` tables in community strategies assume $1k+ accounts; ROI targets must be re-optimized.
- Stoploss of -5% to -26% is normal; at $110 capital ($110 × 0.05 = $5.50), minimum order size on KuCoin (~$5 USDT) constrains this.
- **Modifications needed**: reduce `stake_amount` to floor of min-order-size (≈$5-10), set `max_open_trades: 1`, lower ROI to break-even at 0.4%+ to clear fees, and tighten stoploss to -3% or use ATR-adaptive stops.

### Risk to Our System
- **GPL-3 copyleft**: if we import freqtrade modules or subclass its classes in kucoin-lane, our entire bot may need to be GPL-3. Reverse-engineering the fee math or protection manager code is a safer approach than direct subclassing.
- **Dependency bloat**: sqlalchemy, sqlite, flask, telegram-bot, sklearn, torch optional. Pulling in the full framework creates a large attack surface.
- **API key exposure**: freqtrade stores keys in `config.json` in plaintext. Never store our keys inside the cloned repo.
- **CEX counterparty risk**: freqtrade's exchange driver layer abstracts KuCoin details; if KuCoin changes their spot API, freqtrade must update first.

### Verdict: **EVALUATE**
> Extract fee-math patterns (`Trade.update_fee`, `_calc_base_close`), the protection manager's circuit-breaker logic, and the paper-live DB isolation pattern as reference implementations; do not directly inherit freqtrade classes unless legal review clears GPL copyleft for our codebase.

---

## 2. Freqtrade Strategies

| Field | Value |
|-------|-------|
| **Repo name** | freqtrade-strategies |
| **URL** | https://github.com/freqtrade/freqtrade-strategies |
| **License** | **GPL-3.0** |

### Summary
Community-contributed strategy library for Freqtrade. Contains ~25+ strategies spanning scalping, trend-following, breakout, and multi-indicator approaches. Each strategy exposes `populate_indicators`, `populate_entry_trend`, `populate_exit_trend`, and optional `custom_stoploss`. Most are hyperopt-optimized for specific pair/timeframe combos and stored as `.py` files ready to drop into Freqtrade's `user_data/strategies/` directory.

### Key Patterns Useful for kucoin-lane

| Pattern | Strategy | Why It Matters |
|---------|----------|----------------|
| **Trend confirmation via EMA + RSI + ADX** | TrendRiderStrategy | Multi-signal filter (trend strength via ADX > 18, momentum via RSI zone, direction via EMA cross) reduces false breakouts. |
| **Multi-timeframe informative cache** | TrendRiderStrategy — `informative_pairs()` pulls 4h + 1d + 1h BTC/USDT | Enables higher-TF trend filter without re-instantiating the strategy; our $110 bot can check 4h trend before entering on 1h pullback. |
| **ATR-adaptive custom stoploss** | TrendRiderStrategy uses ATR multipliers internally | Stop distance scales with volatility; critical when fees are a fixed percentage. |
| **Supertrend indicator (no parameters to hyperopt beyond multiplier/period)** | Supertrend | Built-in "STX" direction series; produces clean entry/exit binary signals with minimal computation. |
| **Pure price-action exponentiation** | PowerTower — `close.shift(0) > close.shift(2) ** buy_pow` | Encodes candlestick acceleration as a simple inequality; no indicator warm-up period, works on any timeframe. |
| **DNA-encoded buy/sell rule engine** | GodStra — operator-driven indicator comparison grid | Pattern for building a configurable signal DSL: operator + indicator + cross indicator + threshold = rule. Easier to maintain than if/elif chains. |
| **Trailing stop with asymmetric activation** | ReinforcedQuickie, Diamond: `trailing_stop_positive=0.05`, `trailing_only_offset_is_reached=True` | Trailing activates only after profit exceeds offset; prevents premature chasing. |
| **Protections baked into strategy** | TrendRiderStrategy `protections = [{method: "CooldownPeriod", ...}, {method: "MaxDrawdown", ...}]` | Moves circuit-breakers from config.json into the strategy for version control. |

### Fee-Awareness
Strategies themselves contain **no fee logic** — fees are entirely handled by the freqtrade framework (see §1).  
However:
- `minimal_roi` tables **implicitly assume fees are already netted** by the framework's P&L calc.
- Some strategies set `order_types: {'entry': 'limit', 'exit': 'limit'}` to minimize taker fees.
- None document a minimum viable profit target relative to round-trip friction; ROI floors are hyperopt artifacts, not fee-floor guarantees.

### Micro-Account Suitability
- **TrendRiderStrategy** (1h, EMA/RSI/ADX, protections, leverage_value=1) is the best-scoped strategy: single-pair, long-only, explicit ATR-aware stoploss, protections embedded.  
- **Supertrend** (1h) is indicator-minimal and easily parameter-tightened.
- **PowerTower** and **GodStra** use aggressive exponents and wide condition ranges — high overfit risk, needs fresh out-of-sample validation.
- **UniversalMACD** (5m) trades too frequently for $110 (fees would swamp gains).
- **General**: all strategies use `minimal_roi` targets of 3-35% — these must be clamped to ≥0.35% (round-trip friction) and realistically ≥0.5% for profit.

---

### Top 5 Strategies for $110 Micro-Account

| Rank | Strategy | File | Why Promising |
|------|----------|------|---------------|
| **1** | **TrendRiderStrategy** | `user_data/strategies/TrendRiderStrategy.py` | Single-pair, 1h, EMA + RSI + ADX + volume filter, ATR-aware stoploss, trailing stop (3%), protections in-code, `leverage_value=1` (spot-safe). Low trade frequency from ADX gate. **Best starting point.** |
| **2** | **Supertrend** | `user_data/strategies/Supertrend.py` | 3x supertrend confirmation (must all agree), 1h timeframe, trailing stop, zero indicator warm-up drama. Easy to test, intuitive stop distance. Requires stoploss retightening from -26.5% to ~-5%. |
| **3** | **GodStra** | `user_data/strategies/GodStra.py` | 12h timeframe = very low trading frequency, all-in TA-lib feature set, hyperopt showed 8/0/1 win/loss/draw ratio. Risk: massive overfit indicator set; extract just the crossover + threshold logic and reoptimize on recent BTC/USDT data. |
| **4** | **Diamond** | `user_data/strategies/Diamond.py` | Pure OHLCV pattern (no indicators at all), `trailing_stop_positive=0.011` (1.1% trail), 5m timeframe. As few moving parts as possible. Risk: horizontal/vertical push params are fragile. Good as a minimalist baseline. |
| **5** | **Strategy002** | `user_data/strategies/Strategy002.py` | Conservative ROI table (0.01-0.05 per-minute), -10% stoploss, `exit_profit_only=True`, `use_exit_signal=True`. 5m timeframe is too active for $110 but the profit-only-exit and limit order types are good patterns to keep; the absolute ROI targets make it useful as a strict-take-profit baseline test. |

**Honorable mention:** `PowerTower` — novel exponentiation signal, 5m, price-action only. Interesting concept but backtests show 26.5% stoploss, which is hazardous at this capital level.

---

## 3. VectorBT

| Field | Value |
|-------|-------|
| **Repo name** | vectorbt |
| **URL** | https://github.com/polakowo/vectorbt |
| **License** | **Apache-2.0 + Commons Clause** ("Commons Clause" forbids selling the software as a product or service; internal research use is generally acceptable but check jurisdiction.) |

### Summary
VectorBT is a high-performance, matrix-oriented vectorized backtesting library built on pandas, NumPy, and Numba (with optional Rust acceleration). It replaces row-by-row event loops with broadcasted NumPy arrays, enabling thousands of parameter configurations to be evaluated simultaneously. Outputs performance metrics, trade logs, drawdowns, and integrates with Plotly for visualization.

### Key Patterns Useful for kucoin-lane

| Pattern | Code Reference | Why It Matters |
|---------|---------------|----------------|
| **`Portfolio.from_orders(price, size, fees=0.001, direction='longonly')`** | `vectorbt/portfolio/base.py:80-100` | The simplest way to validate a signal series: provide price array and +1/-1 signal array, set `fees=0.001` (0.1%), and get full P&L + drawdown + stats in one call. |
| **`fixed_fees` parameter** | `portfolio/dispatch.py:546-547` | Add fixed cost per trade beyond percentage (e.g., KuCoin's minimum $0.0005 BTC fee floor). |
| **`from_signals()` mode** | Not read in detail, but referenced in README. | Allows signal arrays directly — most natural interface for our indicator→signal pipeline. |
| **Broadcasting multi-parameter sweeps** | README: "packs thousands of configurations into NumPy arrays" | We can sweep EMA windows (5-30), RSI thresholds, ATR multipliers overnight to find fee-surviving parameter sets. |
| **`entry_fees` / `exit_fees`** | `portfolio/trades.py:1151-1165` | Per-trade fee recording lets us compute net-of-fee returns — essential for our 0.35% friction constraint. |
| **`Portfolio.stats()` accessor** | Standard vbt API. | Returns Sharpe, Calmar, max drawdown, win rate, profit factor — all needed to prove edge exists before live deployment. |
| **Numba-compiled hot path** | `portfolio/nb.py` (referenced from base.py:8). | VectorBT's performance advantage comes from Numba-JIT compiled simulation loops. We don't need to touch this code; it runs transparently. |

### Fee-Awareness
Yes — first-class.
- `fees` (float, fraction per trade side).
- `fixed_fees` (float, constant added per order — useful for KuCoin's minimum fee floor).
- Fees are deducted from cash when order fills, and `pf.orders.records_readable` shows per-order fee totals.
- Supports separate entry/exit fee records (`entry_fees`, `exit_fees`) in trade models.
- **Gap**: no built-in slippage model; we'd need to add spread + slip manually or via custom fee arrays.

### Micro-Account Suitability
- Completely capital-agnostic: fee fractions apply equally to $5 and $500,000 positions.
- The broadcasted-array approach is ideal for micro-account edge-validation: sweep `fees=[0.001, 0.0015, 0.002]` (KuCoin taker, higher tiers) across hundreds of param sets in seconds.
- To model KuCoin's $0.0005 BTC minimum fee on $5 orders: use `fixed_fees=usd_fee / btc_price` per trade.
- **Modifications needed**: none fundamental. Add a `slippage` column in the order DataFrame if required.

### Risk to Our System
- **Apache-2 + Commons Clause**: internal/research use is widely considered acceptable (similar to Redis pre-license-change). Do NOT embed vectorbt inside a product we sell, distribute as SaaS, or use as a feature-gate in a commercial bot. Review license with legal counsel.
- **No built-in data sourcing**: vectorBT is a simulation engine; it doesn't fetch OHLCV. We still need ccxt or a CSV for price data.
- **API surface stability**: vbt.pro (paid tier) splits from open-source; the pro API tracks but does not replace the open-source namespace. Open-source API is stable as of 2024-2025 but check `CHANGELOG.md` before major upgrades.
- **Numba/Rust complexity**: `pip install vectorbt` works, but compiling from source for a minimal Docker image requires Numba and optionally Rust toolchain. Prebuilt wheels exist for most architectures.

### Verdict: **ADOPT**
> Use vectorbt as the primary backtest engine for all signal logic before paper-live deployment — its vectorized fee-aware simulation lets us validate whether a strategy clears our 0.35% friction floor across hundreds of parameter combinations in under a second. Keep research-only; do not distribute or build a commercial product on top of it without addressing Commons Clause.

---

## 4. CCXT

| Field | Value |
|-------|-------|
| **Repo name** | ccxt |
| **URL** | https://github.com/ccxt/ccxt |
| **License** | **MIT** (fully permissive) |

### Summary
CCXT is a unified cryptocurrency exchange API library covering 100+ exchanges in Python, JavaScript, TypeScript, Go, PHP, Java, and C#. It normalizes public methods (`fetch_ohlcv`, `fetch_ticker`, `fetch_order_book`, `create_order`, `fetch_balance`) and private methods (`fetch_trading_fees`, `fetch_deposits`, `fetch_withdrawals`) across exchanges. KuCoin is listed as a "CCXT Certified" exchange, meaning the API is well-maintained and tested.

### Key Patterns Useful for kucoin-lane

| Pattern | Code Reference | Why It Matters |
|---------|---------------|----------------|
| **`exchange.fetch_ohlcv(symbol, timeframe, since, limit)`** | `python/ccxt/kucoin.py` | Our primary market data path for BTC/USDT and ETH/USDT. |
| **`exchange.fetch_trading_fee(symbol)` / `fetch_trading_fees()`** | `python/ccxt/kucoin.py:takerFeeRate, makerFeeRate` | Fetches live per-pair taker/maker fee rates; our bot should cache this at startup and re-fetch daily (tier changes) rather than hard-coding 0.001. |
| **`exchange.create_order(symbol, type, side, amount, price, params)`** | Universal | For paper-live mode, we'd intercept this and record the order in our local DB instead of actually sending it. |
| **`exchange.fetch_balance()`** | Universal | Enables rich paper-live: track simulated balance against real balance to detect drift. |
| **`exchange.fetch_open_orders()`, `fetch_closed_orders()`** | Universal | Used to reconcile paper-live order book with exchange reality. |
| **Rate-limit decorator** | `BaseExchange:throttle, token bucket` | All exchanges share the same rate-limit handling; no KuCoin-specific timeout logic needed. |
| **`exchange.verbose = True`** | Debug logging | Cheap way to log every raw request/response for audit. |
| **Unified error hierarchy** | `Exchange*` exceptions | KuCoin-specific errors (`RateLimitExceeded`, `InsufficientFunds`, `InvalidOrder`) are normalized as `ccxt.*` exceptions our error handler can catch uniformly. |

### Fee-Awareness
Yes — explicit per-market fee support:
- `fetch_trading_fee(symbol)` returns `{taker: rate, maker: rate}` per market. KuCoin's implementation in ccxt parses `data['feeType']` and `data['feeRate']` from the real endpoint.
- `fetch_trades()` includes `takerOrMaker` flag on each fill, enabling back-tested fee reconstruction from real trade history.
- CCXT Pro adds tiered fee schedules per VIP level; our standard use pulls current active tier.
- Base fees are in `exchange.fees['trading'] = {taker: 0.001, maker: 0.001}` — hardcoded fallback used when live fetch fails.

### Micro-Account Suitability
- Account-agnostic; CCXT works at $110 capital without modification.
- The only $110-specific concern is KuCoin's minimum order size (typically ~$5 USDT for spot). Our trade-sizing logic must floor the order at the `info.minAmount` returned by `fetch_markets()`.
- Paper-live mode means CCXT is used only for public market-data endpoints (no private key needed for `fetch_ohlcv`, `fetch_ticker`, `fetch_order_book`). Private endpoints (`create_order`, `fetch_balance`) are **not** reached in paper-live.

### Risk to Our System
- **MIT license**: zero copyleft risk. No attribution required in compiled code, though repo best practice is to acknowledge ccxt in documentation.
- **KuCoin API rate limit**: ccxt handles it, but burst-exceeding limits can get the API key IP-banned. In paper-live with no API key, public endpoints only — minimal risk.
- **Data quality**: CCXT's `fetch_ohlcv` returns exchange-native candles (no quality guarantees). Validate bar completeness after fetch.
- **API key exposure**: we must **not** store KuCoin API keys in the ccxt config; use environment variables injected at runtime, never committed to git.
- **Breaking changes**: CCXT's unified API is stable but KuCoin-specific sub-class (`python/ccxt/kucoin.py`) can change endpoints between versions. Pin ccxt version in `requirements.txt`.

### Verdict: **ADOPT**
> CCXT is the correct market-data layer for kucoin-lane: MIT license, KuCoin certified, unified API surface. Use it for `fetch_ohlcv` + `fetch_ticker` only in paper-live. When transitioning to live, add strict API key management (env var only, never in repo) and rate-limit monitoring. Pin to a known-good version; review CHANGELOG before upgrading.

---

## Cross-Repo Recommendations

| Goal | Recommendation |
|------|----------------|
| **Signal design** | Translate TrendRiderStrategy's multi-TF filter + ATR adaptive stop into our indicator pipeline (no freqtrade class import — pure Python / pandas). |
| **Backtest engine** | Use vectorbt with `fees=0.001`, `fixed_fees=<min_fee_usd/btc_price>`, to validate every new signal passes the ≥0.35% net-of-cost test in backtests before paper-live. |
| **Market data + execution sandbox** | Use ccxt's KuCoin implementation for data. Paper-live execution can use a simple `execute_paper(order)` that records to a local SQLite DB (modeled on freqtrade's `Trade` schema) without calling `create_order`. |
| **Risk/circuit-breakers** | Encode Freqtrade's protection manager logic (CooldownPeriod, MaxDrawdown, StoplossGuard) as pure functions in our risk module — no GPL import required. |
| **Fee math** | Adapt freqtrade's `Trade._calc_base_close()` precision pattern (`FtPrecise`) into our P&L calculator to avoid float drift on $110. |
| **Version pinning** | Lock ccxt and (if used) vectorbt to major versions. CCXT: `ccxt==4.x`; vectorbt: `vectorbt==0.26.x` (or latest stable with Commons Clause acknowledged). |

---

_END OF INTAKE_
