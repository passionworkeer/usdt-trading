#!/usr/bin/env python
"""测试 simple_trader.py 的功能"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio

# 导入需要测试的类
from simple_trader import RSICalculator, MACDCalculator, BollingerBandsCalculator, SimpleSignalGenerator


def test_rsi_calculator():
    """测试 RSI 计算器"""
    print("\n" + "="*50)
    print("测试 1: RSICalculator")
    print("="*50)

    rsi = RSICalculator(period=14)

    # 模拟上涨价格序列
    prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 111, 110, 112, 114, 115]

    print("输入价格序列:", prices)

    for i, price in enumerate(prices):
        result = rsi.calculate(price)
        print(f"  价格 {price}: RSI = {result:.2f}")

    # 最终 RSI 验证
    final_rsi = rsi.calculate(116)
    print(f"\n最终 RSI: {final_rsi:.2f}")

    # 验证 RSI 范围
    if 0 <= final_rsi <= 100:
        print("PASS - RSI 在 0-100 范围内")
    else:
        print(f"FAIL - RSI 超出范围: {final_rsi}")

    return 0 <= final_rsi <= 100


def test_macd_calculator():
    """测试 MACD 计算器"""
    print("\n" + "="*50)
    print("测试 2: MACDCalculator")
    print("="*50)

    macd = MACDCalculator(fast=12, slow=26, signal=9)

    # 模拟价格序列
    base_price = 100
    prices = [base_price + i * 0.5 for i in range(40)]

    print(f"输入价格数量: {len(prices)}")

    for i, price in enumerate(prices):
        result = macd.calculate(price)
        if i >= 25:  # 只打印后面几个
            print(f"  价格 {price:.1f}: MACD={result['macd']:.4f}, Signal={result['signal']:.4f}, Hist={result['histogram']:.4f}, Ready={result['ready']}")

    # 验证返回结构
    final_result = macd.calculate(120)
    print(f"\n最终结果结构:")
    print(f"  - macd: {final_result['macd']} (type: {type(final_result['macd']).__name__})")
    print(f"  - signal: {final_result['signal']} (type: {type(final_result['signal']).__name__})")
    print(f"  - histogram: {final_result['histogram']} (type: {type(final_result['histogram']).__name__})")
    print(f"  - ready: {final_result['ready']} (type: {type(final_result['ready']).__name__})")

    # 验证结构完整性
    required_keys = ['macd', 'signal', 'histogram', 'ready']
    has_all_keys = all(k in final_result for k in required_keys)

    if has_all_keys:
        print("[PASS] MACD 返回结构正确")
    else:
        print("[FAIL] MACD 返回结构不完整")

    return has_all_keys


def test_bollinger_bands_calculator():
    """测试布林带计算器"""
    print("\n" + "="*50)
    print("测试 3: BollingerBandsCalculator")
    print("="*50)

    bb = BollingerBandsCalculator(period=20, std_dev=2.0)

    # 模拟价格序列（包含波动）
    import random
    random.seed(42)  # 固定随机种子
    base_price = 100
    prices = [base_price + random.uniform(-3, 3) for _ in range(25)]

    print(f"输入价格数量: {len(prices)}")

    for i, price in enumerate(prices):
        result = bb.calculate(price)
        if i >= 19:  # 只打印后面几个
            print(f"  价格 {price:.2f}: Upper={result['upper']:.2f}, Middle={result['middle']:.2f}, Lower={result['lower']:.2f}, Position={result['position']:.2f}, Ready={result['ready']}")

    # 验证返回结构
    final_result = bb.calculate(102)
    print(f"\n最终结果结构:")
    print(f"  - upper: {final_result['upper']}")
    print(f"  - middle: {final_result['middle']}")
    print(f"  - lower: {final_result['lower']}")
    print(f"  - bandwidth: {final_result['bandwidth']}")
    print(f"  - position: {final_result['position']}")
    print(f"  - ready: {final_result['ready']}")

    # 验证逻辑：upper > middle > lower
    if final_result['ready']:
        if final_result['upper'] > final_result['middle'] > final_result['lower']:
            print("[PASS] 布林带逻辑正确 (Upper > Middle > Lower)")
        else:
            print("[FAIL] 布林带逻辑错误")

    # 验证 position 范围
    if 0 <= final_result['position'] <= 1:
        print("[PASS] Position 在 0-1 范围内")
    else:
        print(f"[FAIL] Position 超出范围: {final_result['position']}")

    required_keys = ['upper', 'middle', 'lower', 'bandwidth', 'position', 'ready']
    has_all_keys = all(k in final_result for k in required_keys)

    if has_all_keys:
        print("[PASS] 布林带返回结构正确")
    else:
        print("[FAIL] 布林带返回结构不完整")

    return has_all_keys


def test_signal_generator():
    """测试信号生成器"""
    print("\n" + "="*50)
    print("测试 4: SimpleSignalGenerator 多重确认")
    print("="*50)

    generator = SimpleSignalGenerator()

    # 模拟上涨趋势
    prices = [100 + i * 0.5 for i in range(30)]

    print(f"模拟 {len(prices)} 个价格上涨数据点")

    for price in prices[-5:]:
        result = generator.generate_signal('BTC/USDT', {'price': price})
        print(f"\n价格: {result['price']:.2f}")
        print(f"  Signal: {result['signal']} ({result['reason']})")
        print(f"  RSI: {result['rsi']:.2f}")
        print(f"  MACD Histogram: {result['macd_histogram']:.4f}")
        print(f"  BB Position: {result['bb_position']*100:.1f}%")
        print(f"  Trend: {result['trend']}")
        print(f"  Confirmations: {result['confirmations']}")

    # 模拟超卖后反弹（做多信号）
    print("\n--- 模拟超卖反弹 ---")
    # 先下跌
    for price in [100, 98, 96, 94, 92, 90, 88, 86]:
        generator.generate_signal('BTC/USDT', {'price': price})

    # 反弹
    for price in [88, 90, 92, 94, 96]:
        result = generator.generate_signal('BTC/USDT', {'price': price})
        if result['signal'] != 0:
            print(f"\n*** 信号触发 ***")
            print(f"  Signal: {result['signal']} ({result['reason']})")
            print(f"  Confirm count: {result['confirm_count']}")
            print(f"  Confirmations: {result['confirmations']}")

    return True


def check_code_duplication():
    """检查代码重复问题"""
    print("\n" + "="*50)
    print("检查: 代码重复问题")
    print("="*50)

    # 读取文件检查 RSICalculator 重复定义
    file_path = Path(__file__).parent / "simple_trader.py"
    content = file_path.read_text(encoding='utf-8')

    # 查找 RSICalculator 定义
    class_start = content.find("class RSICalculator:")
    if class_start == -1:
        print("[FAIL] 未找到 RSICalculator 类")
        return False

    # 查找第二个 RSICalculator 定义
    second_start = content.find("class RSICalculator:", class_start + 1)

    if second_start != -1:
        print("[FAIL] 发现代码重复: RSICalculator 被定义了两次!")
        print(f"  第一次定义位置: 第 {content[:class_start].count(chr(10)) + 1} 行")
        print(f"  第二次定义位置: 第 {content[:second_start].count(chr(10)) + 1} 行")

        # 显示重复的代码片段
        print("\n重复的代码片段 (第二次定义):")
        repeat_content = content[second_start:second_start+500]
        print(repeat_content[:300])
        return False
    else:
        print("[PASS] RSICalculator 没有重复定义")
        return True


def main():
    """主测试函数"""
    print("\n" + "#"*50)
    print("# simple_trader.py 功能测试")
    print("#"*50)

    results = []

    # 1. 检查代码重复
    results.append(("代码重复检查", check_code_duplication()))

    # 2. 测试 RSI
    results.append(("RSI 计算器", test_rsi_calculator()))

    # 3. 测试 MACD
    results.append(("MACD 计算器", test_macd_calculator()))

    # 4. 测试布林带
    results.append(("布林带计算器", test_bollinger_bands_calculator()))

    # 5. 测试信号生成器
    results.append(("信号生成器", test_signal_generator()))

    # 汇总结果
    print("\n" + "#"*50)
    print("# 测试结果汇总")
    print("#"*50)

    for name, passed in results:
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + ("全部测试通过!" if all_passed else "存在测试失败项"))
    print("#"*50 + "\n")

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
