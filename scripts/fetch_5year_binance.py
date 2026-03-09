#!/usr/bin/env python3
"""
尝试从 Binance 获取更长时间的历史数据
分批获取可以突破 1000 根限制
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai.data.free_klines import FreeKlineFetcher, SYMBOL_MAP
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


async def fetch_with_binance分段(fetcher: FreeKlineFetcher, symbol: str, interval: str = '1d', years: int = 5):
    """
    分段从 Binance 获取多年数据

    由于 Binance 每次最多返回 1000 根 K 线
    对于日线：1000 天 ≈ 2.7 年
    需要分多段获取
    """
    from datetime import datetime, timedelta

    days = years * 365

    # 首先尝试从缓存加载
    cached = fetcher._load_from_sqlite(symbol, interval, days)
    if not cached.empty:
        logger.info(f"缓存已有 {len(cached)} 条 {symbol} {interval}")
        if len(cached) >= days * 0.9:  # 已经有 90% 的数据
            return cached

    # 尝试 Binance 直接获取
    logger.info(f"尝试从 Binance 获取: {symbol} {interval} ({years}年)")

    try:
        # 直接调用 Binance API 获取更多数据
        # 注意：这里我们需要绕过 fetcher 的限制
        import aiohttp

        spot = SYMBOL_MAP.get(symbol, {}).get('spot', symbol.replace('/', ''))

        async with fetcher._get_session() as session:
            # Binance 每次最多 1000 根
            # 分段获取：从不同的时间点开始

            all_records = []
            now = datetime.now()

            # 分 5 段获取（每段 365 天）
            for i in range(5):
                end_time = now - timedelta(days=i * 365)
                start_time = end_time - timedelta(days=400)  # 多取一点确保重叠

                url = "https://api.binance.com/api/v3/klines"
                params = {
                    'symbol': spot,
                    'interval': interval,
                    'startTime': int(start_time.timestamp() * 1000),
                    'endTime': int(end_time.timestamp() * 1000),
                    'limit': 1000
                }

                try:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            continue

                        klines = await response.json()
                        if not klines:
                            continue

                        for k in klines:
                            all_records.append({
                                'timestamp': pd.to_datetime(k[0], unit='ms'),
                                'open': float(k[1]),
                                'high': float(k[2]),
                                'low': float(k[3]),
                                'close': float(k[4]),
                                'volume': float(k[5])
                            })

                        logger.info(f"  段 {i+1}: 获取 {len(klines)} 条")

                except Exception as e:
                    logger.warning(f"  段 {i+1} 失败: {e}")
                    continue

            if all_records:
                import pandas as pd
                df = pd.DataFrame(all_records)
                df.set_index('timestamp', inplace=True)
                df = df[~df.index.duplicated(keep='first')]  # 去重
                df = df.sort_index()

                # 保存到 SQLite
                fetcher._save_to_sqlite(symbol, interval, df)

                logger.info(f"Binance 成功获取 {len(df)} 条 {symbol} {interval}")
                return df

    except Exception as e:
        logger.error(f"Binance 获取失败: {e}")

    return fetcher._load_from_sqlite(symbol, interval, days)


async def main():
    print("=" * 60)
    print("尝试获取 5 年历史数据 (Binance)")
    print("=" * 60)

    fetcher = FreeKlineFetcher(use_cache=True)

    # 要获取的币种
    symbols = list(SYMBOL_MAP.keys())[:15]  # 15 个主流币种

    for symbol in symbols:
        await fetch_with_binance分段(fetcher, symbol, '1d', years=5)
        await asyncio.sleep(0.5)

    # 统计
    print("\n" + "=" * 60)
    print("缓存统计:")
    print("=" * 60)

    import sqlite3
    from pathlib import Path
    from datetime import datetime

    DB_PATH = Path.home() / '.cache' / 'usdt_klines' / 'klines_cache.db'
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute('''
        SELECT symbol, interval, COUNT(*) as cnt, MIN(timestamp), MAX(timestamp)
        FROM klines_cache
        GROUP BY symbol, interval
        ORDER BY cnt DESC
    ''')

    total = 0
    for row in cursor.fetchall():
        symbol, interval, cnt, min_ts, max_ts = row
        min_date = datetime.fromtimestamp(min_ts).strftime('%Y-%m-%d')
        max_date = datetime.fromtimestamp(max_ts).strftime('%Y-%m-%d')
        print(f"  {symbol:12s} {interval:2s}: {cnt:4d} 条 ({min_date} ~ {max_date})")
        total += cnt

    print("-" * 60)
    print(f"总计: {total} 条数据")
    conn.close()


if __name__ == '__main__':
    import pandas as pd  # 上面需要
    asyncio.run(main())
