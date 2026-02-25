# v7.1 毫秒级延迟预算表（Latency Budget Profiling）

从币安服务器发出数据到订单执行的完整延迟分析

---

## 1. 延迟预算总表

| 阶段 | 组件 | 理论延迟 | 实测延迟 | 占比 | 监控埋点 |
|------|------|----------|----------|------|----------|
| **1. 网络传输** | 币安 → 本地 | 10-50ms | 20-80ms | 35% | `event_time` vs `local_time` |
| **2. TLS 握手** | 首次连接 | 50-100ms | 60-120ms | - | Session 复用后 0ms |
| **3. Python 事件循环** | asyncio 调度 | 0.1-0.5ms | 0.2-1ms | 2% | `loop.time()` |
| **4. JSON 解析** | json.loads() | 1-5ms | 2-8ms | 10% | 解析前后时间戳 |
| **5. 数据验证** | Schema 检查 | 0.1-0.3ms | 0.2-0.5ms | 1% | 验证耗时 |
| **6. Ticker 缓存** | 字典更新 | 0.05-0.1ms | 0.1-0.2ms | <1% | 缓存操作 |
| **7. 前置过滤** | 成交量+波动率 | 0.2-0.5ms | 0.3-1ms | 2% | 过滤耗时 |
| **8. OBI 计算** | NumPy 向量化 | 0.5-1ms | 1-2ms | 5% | 计算前后 |
| **9. MTF 检查** | 三重共振 | 5-15ms | 10-30ms | 30% | API 请求耗时 |
| **10. 入场价计算** | 斐波那契 0.382 | 0.1-0.2ms | 0.2-0.5ms | <1% | 计算耗时 |
| **11. 订单提交** | aiohttp POST | 5-20ms | 10-40ms | 15% | HTTP 请求耗时 |
| **总计（首次）** | - | **72-193ms** | **104-283ms** | 100% | - |
| **总计（复用）** | - | **22-93ms** | **44-163ms** | 100% | TLS 复用后 |

---

## 2. 关键路径延迟分解

### 2.1 WebSocket Ticker 流路径

```python
# 延迟监控埋点示例
import time
from datetime import datetime, timezone

class LatencyProfiler:
    """延迟分析器"""

    def __init__(self):
        self.stages = {}

    def record(self, stage: str, start_time: float, end_time: float):
        """记录阶段耗时"""
        latency_ms = (end_time - start_time) * 1000
        self.stages[stage] = latency_ms
        logger.debug(f"[{stage}] 延迟: {latency_ms:.2f} ms")

    def get_total_latency(self) -> float:
        """获取总延迟"""
        return sum(self.stages.values())

# 使用示例
profiler = LatencyProfiler()

# 1. 网络传输延迟
event_time = data['E']  # 币安事件时间（毫秒）
local_time = int(datetime.now(timezone.utc).timestamp() * 1000)
network_latency = local_time - event_time
profiler.stages['network'] = network_latency

# 2. JSON 解析
start = time.perf_counter()
parsed_data = json.loads(raw_message)
end = time.perf_counter()
profiler.record('json_parse', start, end)

# 3. OBI 计算
start = time.perf_counter()
obi = calculate_obi(bids, asks)
end = time.perf_counter()
profiler.record('obi_calc', start, end)

# 打印延迟报告
print(f"总延迟: {profiler.get_total_latency():.2f} ms")
for stage, latency in profiler.stages.items():
    print(f"  {stage}: {latency:.2f} ms ({latency/profiler.get_total_latency()*100:.1f}%)")
```

### 2.2 订单提交路径

```python
# 订单提交通路延迟分解
async def submit_order_with_profiling(symbol, side, price, quantity):
    profiler = LatencyProfiler()

    # 1. 参数验证
    start = time.perf_counter()
    validate_order_params(symbol, side, price, quantity)
    end = time.perf_counter()
    profiler.record('param_validation', start, end)

    # 2. Post-Only 检查
    start = time.perf_counter()
    is_post_only_safe = check_post_only(symbol, side, price)
    end = time.perf_counter()
    profiler.record('post_only_check', start, end)

    # 3. 签名计算
    start = time.perf_counter()
    timestamp = get_timestamp()  # 使用时间同步管理器
    signature = sign_request(params, timestamp)
    end = time.perf_counter()
    profiler.record('signing', start, end)

    # 4. HTTP 请求
    start = time.perf_counter()
    response = await session.post(url, json=params, headers=headers)
    end = time.perf_counter()
    profiler.record('http_request', start, end)

    # 5. 响应解析
    start = time.perf_counter()
    result = await response.json()
    end = time.perf_counter()
    profiler.record('response_parse', start, end)

    return result, profiler
```

---

## 3. 延迟监控埋点方案

### 3.1 装饰器埋点

```python
import functools
import time
import logging

logger = logging.getLogger(__name__)

def latency_monitor(stage_name: str):
    """
    延迟监控装饰器

    用法：
    @latency_monitor('obi_calculation')
    def calculate_obi(bids, asks):
        ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                end = time.perf_counter()
                latency_ms = (end - start) * 1000
                logger.debug(f"[{stage_name}] 延迟: {latency_ms:.2f} ms")

                # 如果延迟超过阈值，发出警告
                if latency_ms > 100:
                    logger.warning(f"⚠️ [{stage_name}] 延迟过高: {latency_ms:.2f} ms")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end = time.perf_counter()
                latency_ms = (end - start) * 1000
                logger.debug(f"[{stage_name}] 延迟: {latency_ms:.2f} ms")

        # 根据函数类型返回不同的 wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# 使用示例
@latency_monitor('obi_calculation')
def calculate_obi(bids, asks):
    """计算订单簿失衡率"""
    bid_total = sum([float(bid[1]) for bid in bids[:5]])
    ask_total = sum([float(ask[1]) for ask in asks[:5]])
    obi = (bid_total - ask_total) / (bid_total + ask_total)
    return obi
```

### 3.2 上下文管理器埋点

```python
from contextlib import contextmanager

@contextmanager
def latency_context(stage_name: str):
    """延迟监控上下文管理器"""
    start = time.perf_counter()
    try:
        yield
    finally:
        end = time.perf_counter()
        latency_ms = (end - start) * 1000
        logger.debug(f"[{stage_name}] 延迟: {latency_ms:.2f} ms")

# 使用示例
async def process_ticker(ticker):
    with latency_context('ticker_processing'):
        # 前置过滤
        with latency_context('prefilter'):
            passes = prefilter_ticker(ticker)

        if passes:
            # 深度验证
            with latency_context('deep_verify'):
                signal = await deep_verify(ticker['symbol'])
```

---

## 4. 延迟预算分配策略

### 4.1 100ms 预算分配

| 组件 | 预算 | 优化目标 | 优化措施 |
|------|------|----------|----------|
| 网络传输 | 50ms | < 30ms | DNS 缓存、CDN |
| TLS 握手 | 0ms | 0ms | Session 复用 |
| JSON 解析 | 5ms | < 3ms | 使用 orjson |
| OBI 计算 | 2ms | < 1ms | NumPy 向量化 |
| asyncio | 1ms | < 0.5ms | 事件循环优化 |
| MTF 检查 | 30ms | < 20ms | 并发请求 |
| 订单提交 | 12ms | < 10ms | 连接复用 |
| **总计** | **100ms** | **< 65ms** | - |

### 4.2 超时熔断策略

```python
# 延迟超时熔断
class LatencyCircuitBreaker:
    """延迟熔断器"""

    def __init__(self, threshold_ms: float = 100):
        self.threshold_ms = threshold_ms
        self.latency_history = []
        self.max_history = 100

    def check_latency(self, latency_ms: float) -> bool:
        """
        检查延迟是否超限

        Returns:
            True: 允许交易
            False: 熔断
        """
        self.latency_history.append(latency_ms)

        # 保留最近 100 次记录
        if len(self.latency_history) > self.max_history:
            self.latency_history.pop(0)

        # 计算平均延迟
        avg_latency = sum(self.latency_history) / len(self.latency_history)

        # 检查是否超过阈值
        if avg_latency > self.threshold_ms:
            logger.critical(f"🚨 延迟熔断触发: 平均延迟 {avg_latency:.2f} ms > {self.threshold_ms} ms")
            return False

        return True
```

---

## 5. 延迟监控仪表板

### 5.1 Prometheus 指标

```python
from prometheus_client import Histogram, Gauge

# 延迟直方图
LATENCY_HISTOGRAM = Histogram(
    'trading_latency_seconds',
    'Trading latency in seconds',
    ['stage'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# 当前延迟
CURRENT_LATENCY = Gauge(
    'current_latency_ms',
    'Current latency in milliseconds',
    ['stage']
)

# 使用示例
def record_latency(stage: str, latency_ms: float):
    LATENCY_HISTOGRAM.labels(stage=stage).observe(latency_ms / 1000)
    CURRENT_LATENCY.labels(stage=stage).set(latency_ms)
```

### 5.2 Grafana 仪表板配置

```json
{
  "dashboard": {
    "title": "Trading Latency Dashboard",
    "panels": [
      {
        "title": "End-to-End Latency",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(trading_latency_seconds_bucket[5m]))",
            "legendFormat": "P95 Latency"
          },
          {
            "expr": "histogram_quantile(0.99, rate(trading_latency_seconds_bucket[5m]))",
            "legendFormat": "P99 Latency"
          }
        ],
        "thresholds": [
          {
            "value": 0.1,
            "color": "yellow"
          },
          {
            "value": 0.2,
            "color": "red"
          }
        ]
      },
      {
        "title": "Latency by Stage",
        "targets": [
          {
            "expr": "current_latency_ms",
            "legendFormat": "{{stage}}"
          }
        ]
      }
    ]
  }
}
```

---

## 6. 延迟优化最佳实践

### 6.1 网络层优化

| 优化项 | 效果 | 实施难度 |
|--------|------|----------|
| DNS 缓存（5 分钟）| 节省 10-20ms | 低 |
| Session Keep-Alive | 节省 50-100ms | 低 |
| TCP Fast Open | 节省 5-10ms | 中 |
| 地理位置优化 | 节省 20-50ms | 高 |

### 6.2 代码层优化

| 优化项 | 效果 | 实施难度 |
|--------|------|----------|
| 使用 orjson | 节省 1-3ms | 低 |
| NumPy 向量化 | 节省 0.5-1ms | 低 |
| 异步并发 | 节省 30-50ms | 中 |
| 避免深拷贝 | 节省 0.1-0.5ms | 低 |

---

**版本**: v7.1

**更新日期**: 2026-02-25

**用途**: 性能优化、延迟监控、熔断策略
