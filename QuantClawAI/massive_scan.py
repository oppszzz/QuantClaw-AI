#!/usr/bin/env python3
"""
MASSIVE strategy scan: 100+ combinations on 6-month 15m BTC.
Goal: Find any strategy with 200-1000 trades and positive PnL/Sharpe.
"""
import requests, json, time
from datetime import datetime
import math

def fetch_binance_15m(symbol, limit):
    base = "https://fapi.binance.com/fapi/v1/klines"
    s = symbol.replace('/USDT:USDT', '') + 'USDT'
    candles = []
    end_ts = None
    remaining = limit
    while remaining > 0:
        fetch = min(1000, remaining)
        params = {"symbol": s, "interval": "15m", "limit": fetch}
        if end_ts is not None:
            params["endTime"] = end_ts
        r = requests.get(base, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        batch = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in data]
        candles.extend(batch)
        remaining -= len(batch)
        if len(data) < fetch:
            break
        end_ts = batch[0]['t'] - 1
        time.sleep(0.2)
    uniq = {c['t']: c for c in candles}
    sorted_candles = [uniq[k] for k in sorted(uniq.keys())]
    return sorted_candles

def calc_sma(vals, period):
    sma = [None]*(period-1)
    for i in range(period-1, len(vals)):
        sma.append(sum(vals[i-period+1:i+1])/period)
    return sma

def calc_ema(vals, span):
    ema = [vals[0]]
    k = 2/(span+1)
    for x in vals[1:]:
        ema.append(x*k + ema[-1]*(1-k))
    return ema

def calc_rsi(close, period=14):
    if len(close) < period+1:
        return [50.0]*len(close)
    deltas = [close[i]-close[i-1] for i in range(1, len(close))]
    rsi = [50.0]*period
    gains = [max(d,0) for d in deltas[:period]]
    losses = [max(-d,0) for d in deltas[:period]]
    avg_gain = sum(gains)/period
    avg_loss = sum(losses)/period if sum(losses) > 0 else 0
    for i in range(period, len(deltas)):
        d = deltas[i]
        avg_gain = (avg_gain*(period-1) + max(d,0))/period
        avg_loss = (avg_loss*(period-1) + max(-d,0))/period if (avg_loss*(period-1) + max(-d,0)) > 0 else 0
        rs = avg_gain/avg_loss if avg_loss else float('inf')
        rsi.append(100 - (100/(1+rs)) if rs != float('inf') else 100)
    while len(rsi) < len(close):
        rsi.append(rsi[-1] if rsi else 50.0)
    return rsi

def calc_stoch(high, low, close, k_period=14, d_period=3):
    stoch_k = [50.0]*k_period
    for i in range(k_period, len(close)):
        hh = max(high[i-k_period+1:i+1])
        ll = min(low[i-k_period+1:i+1])
        if hh == ll:
            stoch_k.append(50.0)
        else:
            stoch_k.append(100 * (close[i] - ll) / (hh - ll))
    stoch_d = [None]*(k_period+d_period-2)
    for i in range(k_period+d_period-1, len(stoch_k)+1):
        stoch_d.append(sum(stoch_k[i-d_period+1:i])/d_period)
    while len(stoch_d) < len(close):
        stoch_d.append(None)
    return stoch_k, stoch_d

def calc_cci(high, low, close, period=20):
    tp = [(h + l + c)/3 for h,l,c in zip(high, low, close)]
    sma_tp = calc_sma(tp, period)
    cci = [0]*period
    for i in range(period, len(close)):
        mean = sma_tp[i]
        if mean is None:
            cci.append(0)
            continue
        md = sum(abs(tp[j] - mean) for j in range(i-period+1, i+1))/period
        cci_val = (tp[i] - mean) / (0.015 * md) if md else 0
        cci.append(cci_val)
    while len(cci) < len(close):
        cci.append(0)
    return cci

def calc_roc(close, period=12):
    roc = [0]*period
    for i in range(period, len(close)):
        roc.append((close[i] - close[i-period])/close[i-period] * 100)
    while len(roc) < len(close):
        roc.append(0)
    return roc

def calc_adx(high, low, close, period=14):
    tr = []
    for i in range(1, len(close)):
        h = high[i] - high[i-1]
        l = low[i-1] - low[i]
        tr.append(max(high[i]-low[i], abs(h), abs(l)))
    tr_smooth = [sum(tr[:period])/period]
    for i in range(period, len(tr)):
        tr_smooth.append((tr_smooth[-1]*(period-1) + tr[i])/period)

    plus_dm = []
    minus_dm = []
    for i in range(1, len(close)):
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)

    plus_di = [50.0]*period
    minus_di = [50.0]*period
    if period <= len(plus_dm):
        plus_smooth = sum(plus_dm[:period])/period
        minus_smooth = sum(minus_dm[:period])/period
        for i in range(period, len(plus_dm)):
            plus_smooth = (plus_smooth*(period-1) + plus_dm[i])/period
            minus_smooth = (minus_smooth*(period-1) + minus_dm[i])/period
            denom = tr_smooth[i-period+1]
            plus_di.append(100 * (plus_smooth/denom) if denom else 0)
            minus_di.append(100 * (minus_smooth/denom) if denom else 0)

    dx = []
    for i in range(period, len(plus_di)):
        denom = plus_di[i] + minus_di[i]
        dx.append(100 * abs(plus_di[i] - minus_di[i]) / denom if denom else 0)

    adx = [None]*(2*period)
    if dx:
        adx_start = period + period - 1
        adx_val = sum(dx[:period])/period
        adx = [None]*adx_start + [adx_val]
        for i in range(period, len(dx)):
            adx_val = (adx_val*(period-1) + dx[i])/period
            adx.append(adx_val)
    while len(adx) < len(close):
        adx.append(None)
    return adx

def calc_atr(high, low, close, period=14):
    tr = []
    for i in range(1, len(close)):
        tr.append(max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])))
    atr = [None]*period
    for i in range(period, len(tr)):
        atr.append(sum(tr[i-period+1:i+1])/period)
    while len(atr) < len(close):
        atr.append(None)
    return atr

def donchian_channel(high, low, period):
    upper = [None]*(period-1)
    lower = [None]*(period-1)
    for i in range(period-1, len(high)):
        upper.append(max(high[i-period+1:i+1]))
        lower.append(min(low[i-period+1:i+1]))
    return upper, lower

def calculate_metrics(trades, initial_capital=10000):
    if not trades:
        return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0, 'pnl_pct': 0,
                'profit_factor': 0, 'avg_win': 0, 'avg_loss': 0, 'max_drawdown': 0,
                'sharpe_ratio': 0, 'final_balance': initial_capital}
    wins = [t for t in trades if t > 0]
    losses = [abs(t) for t in trades if t < 0]
    total_pnl = sum(trades)
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    equity = [initial_capital]
    for pnl in trades:
        equity.append(equity[-1] + pnl)
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity)) if equity[i-1] > 0]
    if returns:
        avg_ret = sum(returns) / len(returns)
        std_ret = (sum((r - avg_ret)**2 for r in returns) / len(returns))**0.5 if len(returns) > 1 else 0
        periods_per_year = len(trades) / 0.5
        sharpe = (avg_ret / std_ret) * math.sqrt(periods_per_year) if std_ret > 0 else 0
    else:
        sharpe = 0

    final_balance = equity[-1]
    pnl_pct = (final_balance - initial_capital) / initial_capital * 100

    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'pnl_pct': pnl_pct,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'final_balance': final_balance
    }

# --- Strategy implementations ---

def backtest_ma(close, fast, slow, commission=0.0007):
    fast_ma = calc_sma(close, fast)
    slow_ma = calc_sma(close, slow)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(slow, len(close)):
        if fast_ma[i] is None or slow_ma[i] is None or fast_ma[i-1] is None or slow_ma[i-1] is None:
            continue
        f, s = fast_ma[i], slow_ma[i]
        pf, ps = fast_ma[i-1], slow_ma[i-1]
        if pf <= ps and f > s and pos == 0:
            pos = 1; entry = close[i]
        elif pf >= ps and f < s and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_ema(close, fast, slow, commission=0.0007):
    fast_ema = calc_ema(close, fast)
    slow_ema = calc_ema(close, slow)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(slow, len(close)):
        f, s = fast_ema[i], slow_ema[i]
        pf, ps = fast_ema[i-1], slow_ema[i-1]
        if pf <= ps and f > s and pos == 0:
            pos = 1; entry = close[i]
        elif pf >= ps and f < s and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_macd(close, fast=12, slow=26, signal=9, commission=0.0007):
    ema_f = calc_ema(close, fast)
    ema_s = calc_ema(close, slow)
    macd = [f - s for f,s in zip(ema_f, ema_s)]
    sig = calc_ema(macd[slow:], signal)
    sig = [0.0]*slow + sig
    hist = [m - s for m,s in zip(macd, sig)]
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(slow+signal, len(close)):
        if hist[i-1] <= 0 and hist[i] > 0 and pos == 0:
            pos = 1; entry = close[i]
        elif hist[i-1] >= 0 and hist[i] < 0 and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_rsi(close, period=14, oversold=30, overbought=70, commission=0.0007):
    if len(close) < period+1:
        return calculate_metrics([])
    deltas = [close[i]-close[i-1] for i in range(1, len(close))]
    rsi = [50.0]*period
    avg_gain = sum(max(d,0) for d in deltas[:period])/period
    avg_loss = sum(max(-d,0) for d in deltas[:period])/period if sum(max(-d,0) for d in deltas[:period]) > 0 else 0
    for i in range(period, len(deltas)):
        d = deltas[i]
        avg_gain = (avg_gain*(period-1) + max(d,0))/period
        avg_loss = (avg_loss*(period-1) + max(-d,0))/period if (avg_loss*(period-1) + max(-d,0)) > 0 else 0
        rs = avg_gain/avg_loss if avg_loss else float('inf')
        rsi.append(100 - (100/(1+rs)) if rs != float('inf') else 100)
    while len(rsi) < len(close):
        rsi.append(rsi[-1] if rsi else 50.0)

    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period, len(close)):
        if i < 1:
            continue
        r, pr = rsi[i], rsi[i-1]
        if r > oversold and pr <= oversold and pos == 0:
            pos = 1; entry = close[i]
        elif r < overbought and pr >= overbought and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_stoch(high, low, close, k_period=14, d_period=3, oversold=20, overbought=80, commission=0.0007):
    stoch_k, stoch_d = calc_stoch(high, low, close, k_period, d_period)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(k_period+d_period-1, len(close)):
        if stoch_k[i] is None or stoch_d[i] is None or stoch_k[i-1] is None or stoch_d[i-1] is None:
            continue
        k, d = stoch_k[i], stoch_d[i]
        pk, pd = stoch_k[i-1], stoch_d[i-1]
        # Oversold exit: Stoch %K crosses above oversold
        if k > oversold and pk <= oversold and pos == 0:
            pos = 1; entry = close[i]
        # Overbought exit: Stoch %K crosses below overbought
        elif k < overbought and pk >= overbought and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_cci(high, low, close, period=20, oversold=-100, overbought=100, commission=0.0007):
    cci = calc_cci(high, low, close, period)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period, len(close)):
        if i < 1:
            continue
        c, pc = cci[i], cci[i-1]
        if c > oversold and pc <= oversold and pos == 0:
            pos = 1; entry = close[i]
        elif c < overbought and pc >= overbought and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_roc(close, period=12, threshold=0, commission=0.0007):
    roc = calc_roc(close, period)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period, len(close)):
        if i < 1:
            continue
        r, pr = roc[i], roc[i-1]
        if pr <= threshold and r > threshold and pos == 0:
            pos = 1; entry = close[i]
        elif pr >= threshold and r < threshold and pos == 1:
            pos = 0
            pnl = (close[i] - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_donchian(close, high, low, period=20, adx_threshold=0, adx_vals=None, commission=0.0007):
    upper, lower = donchian_channel(high, low, period)
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period, len(close)):
        price = close[i]
        if adx_vals and (adx_vals[i] is None or adx_vals[i] < adx_threshold):
            continue
        if price >= upper[i] and pos == 0:
            pos = 1; entry = price
        elif price <= lower[i] and pos == 1:
            pos = 0
            pnl = (price - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_vwap(close, high, low, volume, period=20, commission=0.0007):
    """VWAP crossover strategy"""
    vwap = [None]*period
    for i in range(period, len(close)):
        sum_pv = 0
        sum_v = 0
        for j in range(i-period+1, i+1):
            avg_price = (high[j] + low[j] + close[j])/3
            sum_pv += avg_price * volume[j]
            sum_v += volume[j]
        vwap.append(sum_pv/sum_v if sum_v else close[i])
    # Simple: price cross above/below VWAP
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period, len(close)):
        if vwap[i] is None:
            continue
        price = close[i]
        prev_vwap = vwap[i-1]
        if price > vwap[i] and close[i-1] <= prev_vwap and pos == 0:
            pos = 1; entry = price
        elif price < vwap[i] and close[i-1] >= prev_vwap and pos == 1:
            pos = 0
            pnl = (price - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def backtest_bbands(close, period=20, std=2.0, commission=0.0007):
    sma = calc_sma(close, period)
    upper = [None]*len(close)
    lower = [None]*len(close)
    for i in range(period, len(close)):
        if sma[i] is None:
            continue
        window = close[i-period+1:i+1]
        st = (sum((x - sma[i])**2 for x in window)/period)**0.5
        upper[i] = sma[i] + std * st
        lower[i] = sma[i] - std * st
    pos, entry, equity = 0, 0, 10000
    trades = []
    for i in range(period+1, len(close)):
        if lower[i] is None or upper[i] is None or lower[i-1] is None or upper[i-1] is None:
            continue
        price = close[i]
        if price <= lower[i] and close[i-1] > lower[i-1] and pos == 0:
            pos = 1; entry = price
        elif price >= upper[i] and close[i-1] < upper[i-1] and pos == 1:
            pos = 0
            pnl = (price - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
    return calculate_metrics(trades)

def main():
    limit = 17280
    print(f"Fetching {limit} 15m candles...")
    data = fetch_binance_15m('BTC/USDT:USDT', limit)
    print(f"Fetched {len(data)} candles (period: {datetime.fromtimestamp(data[0]['t']/1000).date()} to {datetime.fromtimestamp(data[-1]['t']/1000).date()})\n")
    close = [c['c'] for c in data]
    high = [c['h'] for c in data]
    low = [c['l'] for c in data]
    volume = [c['v'] for c in data]

    commission = 0.0007

    # Pre-calc ADX for filtering
    adx_vals = calc_adx(high, low, close, 14)

    strategies = []

    # 1. MA variations (wide grid)
    for f in range(8, 26):
        for s in range(f+5, f+40, 5):
            if s <= 60:
                strategies.append((f'MA{f}/{s}', ('ma', {'fast':f, 'slow':s})))

    # 2. EMA variations
    for f in [8,9,10,12,15,20,25,30]:
        for s in [f*1.5, f*2, f*2.5, f*3]:
            s_int = int(round(s))
            if s_int <= 100 and s_int > f:
                strategies.append((f'EMA{f}/{s_int}', ('ema', {'fast':f, 'slow':s_int})))

    # 3. MACD variations
    for f in [8,10,12,15,20]:
        for s in [f*2, f*2.5, f*3]:
            for sig in [9,12,15]:
                if s <= 80:
                    strategies.append((f'MACD{f}/{s}/{sig}', ('macd', {'fast':f, 'slow':s, 'signal':sig})))

    # 4. RSI variations
    for p in [7,10,14,21,28]:
        for buy in [20,25,30,35,40]:
            for sell in [60,65,70,75,80]:
                if buy < sell:
                    strategies.append((f'RSI{p}_{buy}/{sell}', ('rsi', {'period':p, 'oversold':buy, 'overbought':sell})))

    # 5. Stochastic variations
    for kp in [10,14,20]:
        for dp in [3,5,7]:
            for buy in [10,20,30]:
                for sell in [70,80,90]:
                    strategies.append((f'Stoch{kp}_{dp}_{buy}/{sell}', ('stoch', {'k_period':kp, 'd_period':dp, 'oversold':buy, 'overbought':sell})))

    # 6. CCI variations
    for p in [14,20,30]:
        for buy in [-150,-100,-80]:
            for sell in [80,100,150]:
                strategies.append((f'CCI{p}_{buy}/{sell}', ('cci', {'period':p, 'oversold':buy, 'overbought':sell})))

    # 7. ROC variations
    for p in [6,12,20,30]:
        for th in [-1,0,1]:
            strategies.append((f'ROC{p}_{th}', ('roc', {'period':p, 'threshold':th})))

    # 8. Donchian variations (WITH and WITHOUT ADX)
    for p in [10,15,20,25,30,40,50,60,80,100]:
        strategies.append((f'DC{p}', ('donchian', {'period':p, 'adx_threshold':0})))
        if p <= 50:
            strategies.append((f'DC{p}+ADX25', ('donchian', {'period':p, 'adx_threshold':25})))

    # 9. VWAP variations
    for p in [10,20,30,40]:
        strategies.append((f'VWAP{p}', ('vwap', {'period':p})))

    # 10. Bollinger Bands variations
    for p in [10,15,20,25,30]:
        for std in [1.5, 2.0, 2.5, 3.0]:
            strategies.append((f'BB{p}_{std}', ('bbands', {'period':p, 'std':std})))

    print(f"Total strategies to test: {len(strategies)}\n")

    results = []
    for idx, (name, (typ, params)) in enumerate(strategies, 1):
        try:
            if typ == 'ma':
                metrics = backtest_ma(close, **params, commission=commission)
            elif typ == 'ema':
                metrics = backtest_ema(close, **params, commission=commission)
            elif typ == 'macd':
                metrics = backtest_macd(close, **params, commission=commission)
            elif typ == 'rsi':
                metrics = backtest_rsi(close, **params, commission=commission)
            elif typ == 'stoch':
                metrics = backtest_stoch(high, low, close, **params, commission=commission)
            elif typ == 'cci':
                metrics = backtest_cci(high, low, close, **params, commission=commission)
            elif typ == 'roc':
                metrics = backtest_roc(close, **params, commission=commission)
            elif typ == 'donchian':
                adx_th = params.get('adx_threshold',0)
                metrics = backtest_donchian(close, high, low, period=params['period'],
                                           adx_threshold=adx_th,
                                           adx_vals=adx_vals if adx_th>0 else None,
                                           commission=commission)
            elif typ == 'vwap':
                metrics = backtest_vwap(close, high, low, volume, **params, commission=commission)
            elif typ == 'bbands':
                metrics = backtest_bbands(close, period=params['period'], std=params['std'], commission=commission)
            else:
                continue

            results.append({
                'strategy': name,
                'type': typ,
                'trades': metrics['total_trades'],
                'win_rate': metrics['win_rate'],
                'pnl': metrics['total_pnl'],
                'pnl_pct': metrics['pnl_pct'],
                'md': metrics['max_drawdown'],
                'pf': metrics['profit_factor'],
                'sharpe': metrics['sharpe_ratio']
            })

            # Progress every 20 strategies
            if idx % 20 == 0:
                print(f"Progress: {idx}/{len(strategies)} completed...")
        except Exception as e:
            # Silently skip errors to keep batch running
            continue

    # Sort by Sharpe
    valid = [r for r in results if not math.isnan(r['sharpe'])]
    valid.sort(key=lambda x: x['sharpe'], reverse=True)

    print("\n=== TOP 30 BY SHARPE ===")
    print(f"{'Rank':>4s} {'Strategy':25s} {'Trades':>6s} {'Win%':>6s} {'PnL%':>6s} {'MDD%':>6s} {'PF':>5s} {'Sharpe':>6s}")
    for i, r in enumerate(valid[:30], 1):
        print(f"{i:4d} {r['strategy']:25s} {r['trades']:6d} {r['win_rate']:6.1f} {r['pnl_pct']:6.2f} {r['md']:6.1f} {r['pf']:5.2f} {r['sharpe']:6.2f}")

    print("\n=== BEST PROFITABLE (>0 PnL) WITH 100+ TRADES ===")
    profitable = [r for r in valid if r['pnl'] > 0 and r['trades'] >= 100]
    if profitable:
        profitable.sort(key=lambda x: x['sharpe'], reverse=True)
        print(f"{'Strategy':25s} {'Trades':>6s} {'Win%':>6s} {'PnL%':>6s} {'MDD%':>6s} {'PF':>5s} {'Sharpe':>6s}")
        for r in profitable[:20]:
            print(f"{r['strategy']:25s} {r['trades']:6d} {r['win_rate']:6.1f} {r['pnl_pct']:6.2f} {r['md']:6.1f} {r['pf']:5.2f} {r['sharpe']:6.2f}")
    else:
        print("No profitable strategies with >=100 trades found.")

    print("\n=== BEST PROFITABLE (>0 PnL) WITH 50+ TRADES ===")
    profitable50 = [r for r in valid if r['pnl'] > 0 and r['trades'] >= 50]
    if profitable50:
        profitable50.sort(key=lambda x: x['sharpe'], reverse=True)
        for r in profitable50[:10]:
            print(f"{r['strategy']:25s} Trades={r['trades']}, Win={r['win_rate']:.1f}%, PnL={r['pnl_pct']:.2f}%, MDD={r['md']:.1f}%, PF={r['pf']:.2f}, Sharpe={r['sharpe']:.2f}")
    else:
        print("None.")

    out = {
        'period': f"{datetime.fromtimestamp(data[0]['t']/1000).date()} to {datetime.fromtimestamp(data[-1]['t']/1000).date()}",
        'candles': len(close),
        'commission': commission,
        'total_strategies': len(strategies),
        'top_sharpe': valid[:30],
        'profitable_100': profitable[:20] if profitable else [],
        'profitable_50': profitable50[:10] if profitable50 else [],
        'all_results': results
    }
    with open('/tmp/massive_scan_results.json','w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved full results to /tmp/massive_scan_results.json ({len(results)} strategies)")

if __name__ == '__main__':
    main()
