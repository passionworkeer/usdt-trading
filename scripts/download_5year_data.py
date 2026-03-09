#!/usr/bin/env python3
"""
下载最近5年的K线数据到本地SQLite缓存
支持多种币种和多个时间间隔
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai.data.free_klines import FreeKlineFetcher, SYMBOL_MAP
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 要下载的币种（扩展到更多主流币种）
SYMBOLS = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'BNB/USDT',
    'XRP/USDT',
    'ADA/USDT',
    'DOGE/USDT',
    'AVAX/USDT',
    'DOT/USDT',
    'MATIC/USDT',
    'LINK/USDT',
    'UNI/USDT',
    'ATOM/USDT',
    'LTC/USDT',
    'ETC/USDT',
    'XLM/USDT',
    'NEAR/USDT',
    'APT/USDT',
    'ARB/USDT',
    'OP/USDT',
]

# 时间间隔：1d = 日线，1h = 小时线
INTERVALS = ['1d']  # 5年日线数据

# 下载年数
YEARS = 5
DAYS = YEARS * 365


async def download_symbol_data(fetcher: FreeKlineFetcher, symbol: str, interval: str, days: int):
    """下载单个币种的数据"""
    logger.info(f"开始下载: {symbol} {interval} ({days}天)")

    try:
        # 使用离线缓存模式（先检查缓存，没有再下载）
        df = await fetcher.fetch_free_klines(
            symbol=symbol,
            interval=interval,
            days=days,
            use_offline_cache=True  # 启用离线缓存
        )

        if df.empty:
            logger.error(f"  获取失败: {symbol}")
            return False

        logger.info(f"  成功: {symbol} {interval} - {len(df)} 条数据")
        return True

    except Exception as e:
        logger.error(f"  错误: {symbol} - {e}")
        return False


async def main():
    print("=" * 60)
    print("5年历史K线数据下载器")
    print("=" * 60)
    print(f"币种数量: {len(SYMBOLS)}")
    print(f"时间间隔: {INTERVALS}")
    print(f"数据天数: {DAYS} 天 (约 {DAYS//365} 年)")
    print("=" * 60)

    # 创建 fetcher
    fetcher = FreeKlineFetcher(use_cache=True)

    # 统计
    success_count = 0
    fail_count = 0

    # 下载每个币种的数据
    for symbol in SYMBOLS:
        # 检查是否在支持列表中
        if symbol not in SYMBOL_MAP:
            logger.warning(f"不支持的币种: {symbol}")
            fail_count += 1
            continue

        for interval in INTERVALS:
            success = await download_symbol_data(fetcher, symbol, interval, DAYS)
            if success:
                success_count += 1
            else:
                fail_count += 1

            # 避免请求过快
            await asyncio.sleep(1)

    # 打印摘要
    print("\n" + "=" * 60)
    print("下载完成!")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print("=" * 60)

    # 显示缓存统计
    try:
        from src.ai.data.free_klines import DB_CACHE_PATH
        import sqlite3

        conn = sqlite3.connect(str(DB_CACHE_PATH))
        cursor = conn.execute("""
            SELECT symbol, interval, COUNT(*) as count
            FROM klines_cache
            GROUP BY symbol, interval
            ORDER BY symbol, interval
        """)

        print("\n本地缓存统计:")
        print("-" * 40)
        total = 0
        for row in cursor.fetchall():
            symbol, interval, count = row
            print(f"  {symbol} {interval}: {count} 条")
            total += count

        print("-" * 40)
        print(f"总计: {total} 条数据")
        conn.close()

    except Exception as e:
        print(f"统计缓存失败: {e}")


if __name__ == '__main__':
    asyncio.run(main())
