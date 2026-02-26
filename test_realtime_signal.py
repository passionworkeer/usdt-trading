"""
实时信号测试 - v5.2 MTF 三重共振
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.quantitative.mtf_resonance_lock import MTFResonanceLock


async def test_realtime_signals():
    """测试实时信号"""
    print("=" * 60)
    print("Real-time MTF Triple Resonance Signal Test (v5.2)")
    print("=" * 60)
    
    lock = MTFResonanceLock()
    
    # 测试多个交易对
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    results = []
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Testing: {symbol}")
        print(f"{'='*60}")
        
        try:
            signal = await lock.check_triple_resonance(symbol)
            
            results.append({
                'symbol': symbol,
                'signal': signal.signal,
                'confidence': signal.confidence,
                'is_locked': signal.is_locked,
                'rsi': signal.rsi,
                'atr': signal.atr,
                'stop_loss': signal.stop_loss_price,
                'take_profit': signal.take_profit_price,
                'risk_reward': signal.risk_reward_ratio,
            })
            
        except Exception as e:
            print(f"Error: {e}")
            results.append({
                'symbol': symbol,
                'error': str(e)
            })
    
    # 汇总
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    print(f"{'Symbol':<12} {'Signal':<8} {'Conf':<10} {'Locked':<6} {'RSI':<8} {'ATR':<10} {'SL':<12} {'TP':<12} {'R:R':<8}")
    print("-" * 100)
    
    for r in results:
        if 'error' in r:
            print(f"{r['symbol']:<12} ERROR: {r['error'][:50]}")
        else:
            signal_name = {1: 'LONG', -1: 'SHORT', 0: 'HOLD'}.get(r['signal'], 'N/A')
            locked = 'YES' if r['is_locked'] else 'NO'
            rsi = f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'
            atr = f"{r['atr']:.2f}" if r['atr'] else 'N/A'
            sl = f"{r['stop_loss']:.2f}" if r['stop_loss'] else 'N/A'
            tp = f"{r['take_profit']:.2f}" if r['take_profit'] else 'N/A'
            rr = f"{r['risk_reward']:.1f}:1" if r['risk_reward'] else 'N/A'
            
            print(f"{r['symbol']:<12} {signal_name:<8} {r['confidence']:<10.0%} {locked:<6} {rsi:<8} {atr:<10} {sl:<12} {tp:<12} {rr:<8}")
    
    print("\nTest Complete")
    return results


if __name__ == '__main__':
    asyncio.run(test_realtime_signals())
