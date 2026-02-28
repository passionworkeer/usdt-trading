#!/usr/bin/env python3
"""
下载历史K线数据到本地文件
"""
import asyncio
import json
from pathlib import Path
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
INTERVALS = ['1h', '4h', '1d', '1w']

# 数据目录
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


class DataDownloader:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=self.connector)
        return self.session

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 1500) -> list:
        """获取K线数据"""
        url = "https://fapi.binance.com/fapi/v1/klines"
        session = await self._get_session()

        all_data = []
        end_time = None

        # 分批获取，每次1500根
        for _ in range(10):  # 最多10批
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            if end_time:
                params['endTime'] = end_time

            try:
                async with session.get(url, params=params,
                                      timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    data = await resp.json()

                if not data:
                    break

                all_data.extend(data)
                # 找到最早的时间戳，继续往前获取
                end_time = data[0][0] - 1

                # 如果获取的不足limit，说明已经到头了
                if len(data) < limit:
                    break

                print(f"  {symbol} {interval}: 获取 {len(all_data)} 根...")

            except Exception as e:
                print(f"  Error: {e}")
                break

        return all_data

    async def download_all(self):
        """下载所有数据"""
        for symbol in SYMBOLS:
            for interval in INTERVALS:
                print(f"下载 {symbol} {interval}...")

                # 检查是否已有数据
                file_path = DATA_DIR / f"{symbol}_{interval}.json"
                if file_path.exists():
                    print(f"  已存在，跳过")
                    continue

                data = await self.fetch_klines(symbol, interval)

                if data:
                    # 转换为简洁格式
                    candles = []
                    for d in data:
                        candles.append({
                            'time': d[0] // 1000,
                            'open': float(d[1]),
                            'high': float(d[2]),
                            'low': float(d[3]),
                            'close': float(d[4]),
                            'volume': float(d[5])
                        })

                    # 保存
                    with open(file_path, 'w') as f:
                        json.dump(candles, f)

                    print(f"  保存 {len(candles)} 根到 {file_path.name}")

        await self.session.close()
        print("\n下载完成!")


async def main():
    downloader = DataDownloader()
    await downloader.download_all()


if __name__ == '__main__':
    asyncio.run(main())
