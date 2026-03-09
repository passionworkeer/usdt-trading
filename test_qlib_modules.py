"""
测试 qlib 风格的数据模块

用法: python test_qlib_modules.py
"""
import sys
import pandas as pd
import numpy as np

# 添加项目路径
sys.path.insert(0, 'E:/desktop/usdt')

from src.ai.data.expression_engine import ExpressionEngine, ExpressionTemplates
from src.ai.data.processors import ZscoreNorm, CSRankNorm, ProcessorPipeline, create_standard_pipeline
from src.ai.data.alpha_factors import get_alpha_library, calculate_factors


def create_sample_data() -> pd.DataFrame:
    """创建样本数据"""
    np.random.seed(42)

    n = 100
    dates = pd.date_range('2024-01-01', periods=n, freq='D')

    # 生成模拟价格数据
    close = 50000 + np.cumsum(np.random.randn(n) * 500)
    open_prices = close + np.random.randn(n) * 100
    high = np.maximum(close, open_prices) + np.abs(np.random.randn(n) * 200)
    low = np.minimum(close, open_prices) - np.abs(np.random.randn(n) * 200)
    volume = np.random.randint(1000, 10000, n) * 1000

    df = pd.DataFrame({
        'open': open_prices,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)

    return df


def test_expression_engine():
    """Test expression engine"""
    print("\n" + "=" * 60)
    print("Test 1: Expression Engine")
    print("=" * 60)

    df = create_sample_data()

    engine = ExpressionEngine(df)

    # Test basic fields
    print("\n1.1 Basic field reference:")
    result = engine.evaluate('$close')
    print(f"   $close latest: {result.iloc[-1]:.2f}")

    # Test Ref function
    print("\n1.2 Ref function (historical value):")
    result = engine.evaluate('Ref($close, 5)')
    print(f"   Ref($close, 5) latest: {result.iloc[-1]:.2f}")

    # Test EMA function
    print("\n1.3 EMA function (exponential moving average):")
    result = engine.evaluate('EMA($close, 20)')
    print(f"   EMA($close, 20) latest: {result.iloc[-1]:.2f}")

    # Test momentum factor
    print("\n1.4 Momentum factor:")
    result = engine.evaluate('Ref($close, -5) / $close - 1')
    print(f"   5-day momentum: {result.iloc[-1]:.4f}")

    # Test mean reversion
    print("\n1.5 Mean reversion factor:")
    result = engine.evaluate('$close / Mean($close, 20) - 1')
    print(f"   Deviation from 20-day MA: {result.iloc[-1]:.4f}")

    # Test volatility
    print("\n1.6 Volatility factor:")
    result = engine.evaluate('Std(Log($close/Ref($close, 1)), 20)')
    print(f"   20-day volatility: {result.iloc[-1]:.6f}")

    print("\n[OK] Expression engine test passed!")


def test_processors():
    """Test data processors"""
    print("\n" + "=" * 60)
    print("Test 2: Data Processors")
    print("=" * 60)

    df = create_sample_data()

    # Create data with N/A and outliers
    df_with_na = df.copy()
    df_with_na.iloc[10, 2] = np.nan
    df_with_na.iloc[20, 3] = np.nan
    df_with_na.iloc[30, 4] = 10000000  # outlier

    print(f"\n2.1 Original data shape: {df_with_na.shape}")
    print(f"   N/A count: {df_with_na.isna().sum().sum()}")

    # Test ZscoreNorm
    print("\n2.2 Z-Score normalization:")
    processor = ZscoreNorm()
    processor.fit(df_with_na)
    result = processor.transform(df_with_na)
    print(f"   Mean after norm (should be ~0): {result['close'].mean():.4f}")
    print(f"   Std after norm (should be ~1): {result['close'].std():.4f}")

    # Test CSRankNorm
    print("\n2.3 Cross-section rank normalization:")
    # Create cross-section data (need more columns)
    df_multi = pd.concat([df_with_na[['close']], df_with_na[['close']] * 1.1], axis=1)
    df_multi.columns = ['close', 'close_2']
    cs_rank = CSRankNorm()
    cs_rank.fit(df_multi)
    ranked = cs_rank.transform(df_multi)
    print(f"   Rank range: [{ranked['close'].min():.2f}, {ranked['close'].max():.2f}]")

    # Test pipeline
    print("\n2.4 Standard preprocessing pipeline:")
    pipeline = create_standard_pipeline()
    result = pipeline.fit_transform(df_with_na)
    print(f"   Pipeline output shape: {result.shape}")
    print(f"   N/A count: {result.isna().sum().sum()}")

    print("\n[OK] Data processors test passed!")


def test_alpha_factors():
    """Test Alpha factor library"""
    print("\n" + "=" * 60)
    print("Test 3: Alpha Factor Library")
    print("=" * 60)

    df = create_sample_data()

    # Get factor library
    library = get_alpha_library()

    print(f"\n3.1 Factor library stats:")
    print(f"   Total factors: {len(library.factors)}")

    # Count by category
    categories = {}
    for factor in library.factors.values():
        if factor.category not in categories:
            categories[factor.category] = []
        categories[factor.category].append(factor.name)

    print("\n   Factor categories:")
    for cat, names in categories.items():
        print(f"   - {cat}: {len(names)}")

    # Calculate some factors
    print("\n3.2 Calculate momentum factors:")
    factors = calculate_factors(df, ['momentum_5d', 'momentum_20d', 'momentum_60d'])
    print(f"   momentum_5d latest: {factors['momentum_5d'].iloc[-1]:.4f}")
    print(f"   momentum_20d latest: {factors['momentum_20d'].iloc[-1]:.4f}")
    print(f"   momentum_60d latest: {factors['momentum_60d'].iloc[-1]:.4f}")

    # Calculate volatility factors
    print("\n3.3 Calculate volatility factors:")
    factors = calculate_factors(df, ['volatility_5d', 'volatility_20d', 'volatility_60d'])
    print(f"   volatility_5d latest: {factors['volatility_5d'].iloc[-1]:.6f}")
    print(f"   volatility_20d latest: {factors['volatility_20d'].iloc[-1]:.6f}")

    # Calculate trend factors
    print("\n3.4 Calculate trend factors:")
    factors = calculate_factors(df, ['ma_cross_5_20', 'ma_cross_20_200'])
    print(f"   ma_cross_5_20 latest: {factors['ma_cross_5_20'].iloc[-1]:.4f}")
    print(f"   ma_cross_20_200 latest: {factors['ma_cross_20_200'].iloc[-1]:.4f}")

    print("\n[OK] Alpha factor library test passed!")


def test_expression_templates():
    """Test expression templates"""
    print("\n" + "=" * 60)
    print("Test 4: Expression Templates")
    print("=" * 60)

    df = create_sample_data()

    # Test templates
    print("\n4.1 Momentum templates:")
    print(f"   momentum(5):  {ExpressionTemplates.momentum(5)}")
    print(f"   momentum(20): {ExpressionTemplates.momentum(20)}")

    print("\n4.2 Mean reversion templates:")
    print(f"   mean_reversion(20): {ExpressionTemplates.mean_reversion(20)}")

    print("\n4.3 Volatility templates:")
    print(f"   volatility(20): {ExpressionTemplates.volatility(20)}")

    print("\n4.4 Trend templates:")
    print(f"   trend_strength(20): {ExpressionTemplates.trend_strength(20)}")

    print("\n[OK] Expression templates test passed!")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("QLIB Style Data Module Test")
    print("=" * 60)

    test_expression_engine()
    test_processors()
    test_alpha_factors()
    test_expression_templates()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == '__main__':
    main()
