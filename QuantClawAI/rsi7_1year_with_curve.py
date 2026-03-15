#!/usr/bin/env python3
"""
Backtest RSI(7) + 40/60 strategy on 12-month 15m BTC data, saving equity curve.
"""
import requests, json, time, pickle
from datetime import datetime

def fetch_binance_15m(symbol, months=12):
    base = "https://fapi.binance.com/fapi/v1/klines"
    s = symbol.replace('/USDT:USDT', '') + 'USDT'
    candles = []
    end_ts = None
    limit = 35040
    remaining = limit
    print(f"开始抓取 {months} 个月15分钟K线...")
    while remaining > 0:
        fetch = min(1000, remaining)
        params = {"symbol": s, "interval": "15m", "limit": fetch}
        if end_ts is not None:
            params["endTime"] = end_ts
        try:
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
        except Exception as e:
            print(f"请求出错: {e}")
            break
    uniq = {c['t']: c for c in candles}
    sorted_candles = [uniq[k] for k in sorted(uniq.keys())]
    return sorted_candles

def calc_rsi(close, period=7):
    if len(close) < period+1:
        return [50.0]*len(close)
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
    return rsi

def backtest_rsi_with_equity(close, period=7, oversold=40, overbought=60, commission=0.0007):
    rsi_vals = calc_rsi(close, period)
    pos, entry, equity = 0, 0, 10000
    trades = []
    equity_curve = [10000]
    dates = []  # not needed but could track

    for i in range(period, len(close)):
        if i < 1:
            continue
        r, pr = rsi_vals[i], rsi_vals[i-1]
        price = close[i]
        if r > oversold and pr <= oversold and pos == 0:
            pos = 1; entry = price
        elif r < overbought and pr >= overbought and pos == 1:
            pos = 0
            pnl = (price - entry) * (equity / entry)
            pnl -= equity * commission
            equity += pnl
            trades.append(pnl)
            equity_curve.append(equity)
        else:
            # still record equity point even if no trade
            equity_curve.append(equity)

    # Ensure equity_curve same length as close (for plotting)
    # We have recorded after each trade and also when no trade (equity unchanged)
    # Actually, we need to align: one equity point per close price index
    # Already done: we append equity every loop, so len(equity_curve) should equal len(close)
    while len(equity_curve) < len(close):
        equity_curve.append(equity_curve[-1] if equity_curve else 10000)
    return equity_curve, trades

def calculate_metrics(trades, equity_curve):
    if not trades:
        return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0, 'pnl_pct': 0,
                'profit_factor': 0, 'avg_win': 0, 'avg_loss': 0, 'max_drawdown': 0,
                'sharpe_ratio': 0, 'final_balance': 10000}
    wins = [t for t in trades if t > 0]
    losses = [abs(t) for t in trades if t < 0]
    total_pnl = sum(trades)
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    win_rate = len(wins) / len(trades) * 100
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Max drawdown from equity curve
    peak = equity_curve[0]
    max_dd = 0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualized, using daily-like returns approximation)
    returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] for i in range(1, len(equity_curve)) if equity_curve[i-1] > 0]
    if returns:
        avg_ret = sum(returns) / len(returns)
        std_ret = (sum((r - avg_ret)**2 for r in returns) / len(returns))**0.5 if len(returns) > 1 else 0
        periods_per_year = len(equity_curve) / (365*24*4)  # 15min bars per year
        sharpe = (avg_ret / std_ret) * (365*24*4)**0.5 if std_ret > 0 else 0
    else:
        sharpe = 0

    final_balance = equity_curve[-1]
    pnl_pct = (final_balance - 10000) / 10000 * 100

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

def main():
    symbol = 'BTC/USDT:USDT'
    data = fetch_binance_15m(symbol, months=12)
    print(f"\n✅ 获取到 {len(data)} 根K线")
    if len(data) == 0:
        print("错误：未获取到数据")
        return
    start_dt = datetime.fromtimestamp(data[0]['t']/1000)
    end_dt = datetime.fromtimestamp(data[-1]['t']/1000)
    print(f"   时间范围: {start_dt.date()} 至 {end_dt.date()}")

    close = [c['c'] for c in data]
    commission = 0.0007

    print("\n回测 RSI(7) + 40/60 策略...")
    equity_curve, trades = backtest_rsi_with_equity(close, period=7, oversold=40, overbought=60, commission=commission)
    metrics = calculate_metrics(trades, equity_curve)

    print("\n=== 回测结果 ===")
    print(f"策略: RSI(7) 40/60")
    print(f"交易次数: {metrics['total_trades']}")
    print(f"胜率: {metrics['win_rate']:.1f}%")
    print(f"总盈亏: ${metrics['total_pnl']:,.2f} ({metrics['pnl_pct']:.2f}%)")
    print(f"最大回撤: {metrics['max_drawdown']:.1f}%")
    print(f"盈利因子: {metrics['profit_factor']:.2f}")
    print(f"平均盈利: ${metrics['avg_win']:,.2f}")
    print(f"平均亏损: ${metrics['avg_loss']:,.2f}")
    print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    print(f"最终余额: ${metrics['final_balance']:,.2f}")

    # Plot simple ASCII equity curve (text representation)
    print("\n=== 收益曲线（ASCII 简版）===")
    max_equity = max(equity_curve)
    min_equity = min(equity_curve)
    width = 80
    height = 20
    scale = (max_equity - min_equity) / (height-1) if max_equity > min_equity else 1
    step = max(1, len(equity_curve) // width)
    points = equity_curve[::step][:width]
    for row in range(height-1, -1, -1):
        line = ""
        threshold = min_equity + row * scale
        for val in points:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        print(line)
    print(f"时间 (左=开始, 右=结束) | 收益范围: ${min_equity:,.0f} → ${max_equity:,.0f}")

    # Save full data
    out = {
        'strategy': 'RSI(7) 40/60',
        'symbol': symbol,
        'period': f"{start_dt.date()} to {end_dt.date()}",
        'candles': len(close),
        'commission': commission,
        'metrics': metrics,
        'equity_curve': equity_curve,
        'trades': trades
    }
    with open('/tmp/rsi7_1year_full.json','w') as f:
        json.dump(out, f, indent=2)
    print(f"\n完整数据已保存至 /tmp/rsi7_1year_full.json")

    # Also save a simple CSV for external plotting
    csv_path = '/tmp/equity_curve.csv'
    with open(csv_path, 'w') as f:
        f.write('index,equity\n')
        for i, e in enumerate(equity_curve):
            f.write(f'{i},{e}\n')
    print(f"CSV 格式收益曲线已保存至 {csv_path}")

if __name__ == '__main__':
    main()
