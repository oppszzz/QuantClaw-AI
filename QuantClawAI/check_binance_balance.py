#!/usr/bin/env python3
import time, hmac, hashlib, json, requests
from datetime import datetime

# 读取配置
with open('/Users/opps/.openclaw/credentials/binance.json', 'r') as f:
    cfg = json.load(f)

api_key = cfg['apiKey']
api_secret = cfg['secretKey']
testnet = cfg.get('testnet', False)

base_url = 'https://fapi.binance.com' if not testnet else 'https://testnet.binancefuture.com'

print(f"🔑 使用 API Key: {api_key[:8]}...")
print(f"🌐 环境: {'测试网' if testnet else '主网'}")

timestamp = int(time.time() * 1000)
recv = f'timestamp={timestamp}'
signature = hmac.new(api_secret.encode('utf-8'), recv.encode('utf-8'), hashlib.sha256).hexdigest()

headers = {'X-MBX-APIKEY': api_key}
params = {'timestamp': timestamp, 'signature': signature}

url = base_url + '/fapi/v2/balance'
try:
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    print(f"\n📡 请求: {url}")
    print(f"📊 HTTP 状态码: {resp.status_code}\n")
    if resp.status_code == 200:
        data = resp.json()
        print("✅ 成功连接到币安合约账户！\n")
        print("=== 原始数据 ===")
        print(json.dumps(data, indent=2)[:2000])  # 打印前2000字符
        print("\n=== 资产余额 ===")
        total_usdt = 0
        for asset in data:
            # 兼容不同字段名
            wallet_bal = float(asset.get('walletBalance', asset.get('balance', 0)))
            available = float(asset.get('availableBalance', asset.get('available', 0)))
            if wallet_bal > 0:
                print(f"  {asset['asset']}: {wallet_bal:.4f} (可用: {available:.4f})")
                if asset['asset'] == 'USDT':
                    total_usdt = wallet_bal
        print(f"\n💰 总计 USDT: {total_usdt:.2f}")
        print(f"⏰ 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("❌ API 错误:")
        print(resp.text)
except Exception as e:
    print(f"❌ 请求异常: {e}")
