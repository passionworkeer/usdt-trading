# P1-17: 交易所健康检查和熔断机制

## 概述

实现了交易所健康检查和熔断机制，用于应对黑盒事件（交易所宕机、网络故障等）。

## 核心组件

### 1. 健康检查器 (`health_checker.py`)

**功能**:
- REST API 可用性检查
- 交易权限验证
- 订单簿流动性检查
- API 延迟监控

**使用方式**:
```python
from src.utils.health_checker import ExchangeHealthChecker

# 初始化
health_checker = ExchangeHealthChecker(exchange.exchange)

# 执行健康检查
result = await health_checker.health_check()

# 检查结果
if result.is_healthy():
    # 交易所健康，继续交易
    pass
else:
    # 交易所不健康，暂停交易
    logger.warning(f"交易所状态: {result.status.value}")
```

**健康状态**:
- `HEALTHY`: 完全健康
- `DEGRADED`: 部分降级（延迟较高）
- `UNHEALTHY`: 不健康（功能受限）
- `CRITICAL`: 严重故障

### 2. 熔断器 (`circuit_breaker.py`)

**功能**:
- 连续失败达到阈值后触发熔断
- 熔断期间拒绝请求
- 冷却时间后进入半开状态
- 半开状态连续成功后恢复

**使用方式**:
```python
from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# 创建熔断器
breaker = CircuitBreaker(
    name="trading",
    config=CircuitBreakerConfig(
        failure_threshold=3,      # 连续 3 次失败触发熔断
        success_threshold=2,      # 连续 2 次成功恢复
        cooldown_seconds=300,     # 冷却 5 分钟
    )
)

# 使用熔断器保护 API 调用
if breaker.check():
    try:
        # 执行 API 调用
        result = await api_call()
        breaker.on_success()
    except Exception as e:
        breaker.on_failure()
        raise
else:
    # 熔断器开启，拒绝请求
    raise CircuitBreakerOpenError("熔断器开启中")
```

**熔断器状态**:
- `CLOSED`: 正常工作
- `OPEN`: 熔断中，拒绝请求
- `HALF_OPEN`: 尝试恢复

### 3. 降级策略 (`degradation_strategy.py`)

**功能**:
- 根据健康状态自动调整运行策略
- 只读模式：停止新开仓
- 降低频率：减少 API 调用
- 紧急平仓：严重故障时平仓

**使用方式**:
```python
from src.utils.degradation_strategy import DegradationStrategy

# 初始化
strategy = DegradationStrategy()

# 更新策略
action = strategy.update_strategy(health_status="UNHEALTHY")

# 检查是否允许操作
if strategy.can_open_position():
    # 允许开仓
    pass
else:
    # 禁止开仓
    logger.warning("降级策略禁止新开仓")
```

**降级级别**:
- `NORMAL`: 正常运行
- `REDUCED_FREQUENCY`: 降低频率（DEGRADED）
- `READ_ONLY`: 只读模式（UNHEALTHY）
- `EMERGENCY_CLOSE`: 紧急平仓（CRITICAL）

### 4. 紧急处理器 (`degradation_strategy.py`)

**功能**:
- 处理严重故障
- 执行紧急平仓
- 发送紧急预警

**使用方式**:
```python
from src.utils.degradation_strategy import EmergencyHandler

# 初始化
emergency_handler = EmergencyHandler(position_manager, alerter)

# 处理严重故障
await emergency_handler.handle_critical_failure(
    reason="交易所严重故障",
    force_close=True
)
```

## 集成到 SniperTrader

### 主循环集成

```python
async def run(self, check_interval_minutes: int = 15):
    # 定期健康检查（每分钟）
    while self.running:
        health_result = await self.health_checker.health_check()

        # 更新降级策略
        self.degradation_strategy.update_strategy(health_result.status.value)

        # 检查是否允许开仓
        if not self.degradation_strategy.can_open_position():
            logger.warning("降级策略禁止新开仓")
            continue

        # 正常交易逻辑...
```

### 开仓流程保护

```python
async def check_and_trade(self, symbol: str):
    # 1. 健康检查
    health_result = await self.health_checker.health_check()
    if not health_result.is_healthy():
        return "交易所不健康"

    # 2. 熔断器检查
    if not self.trading_breaker.check():
        return "熔断器开启中"

    # 3. 正常交易逻辑
    # ...

async def _execute_open_position(self, position, price, fill_type):
    try:
        # 熔断器保护的 API 调用
        if not self.trading_breaker.check():
            return "熔断器拒绝"

        order = await self.exchange_info.exchange.create_order(...)
        self.trading_breaker.on_success()
    except Exception as e:
        self.trading_breaker.on_failure()
        raise
```

## 配置参数

### 熔断器配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `failure_threshold` | 3 | 连续失败阈值 |
| `success_threshold` | 2 | 恢复成功阈值 |
| `cooldown_seconds` | 300 | 冷却时间（秒） |

### 健康检查配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `check_interval` | 30 | 检查间隔（秒） |
| `rest_api_latency` | 1000 | REST API 延迟阈值（ms） |
| `order_book_latency` | 500 | 订单簿延迟阈值（ms） |

### 降级策略配置

| 健康状态 | 降级级别 | 允许开仓 | 检查间隔 |
|----------|----------|----------|----------|
| HEALTHY | NORMAL | ✅ | 1x |
| DEGRADED | REDUCED_FREQUENCY | ✅ | 2x |
| UNHEALTHY | READ_ONLY | ❌ | 3x |
| CRITICAL | EMERGENCY_CLOSE | ❌ | 5x |

## 测试

运行测试套件验证功能：

```bash
# 运行测试
python tests/test_health_circuit_breaker.py
```

测试内容包括：
1. 熔断器状态转换
2. 降级策略切换
3. 健康检查器功能
4. 熔断器管理器

## 监控面板集成

健康状态会自动广播到 Redis：

```python
# 健康状态广播
await state_broadcaster.broadcast_health(
    health_checker.get_status_summary()
)
```

监控面板可以显示：
- 当前健康状态
- API 延迟
- 熔断器状态
- 降级级别
- 失败率统计

## 最佳实践

1. **定期健康检查**: 每分钟执行一次健康检查
2. **熔断器保护**: 所有关键 API 调用都应使用熔断器保护
3. **降级策略**: 根据健康状态自动调整运行策略
4. **紧急预案**: 严重故障时考虑紧急平仓
5. **预警通知**: 所有关键事件都应发送预警

## 故障处理流程

```
交易所故障
    ↓
健康检查检测到异常
    ↓
触发降级策略
    ├─ DEGRADED: 降低 API 频率
    ├─ UNHEALTHY: 禁止新开仓
    └─ CRITICAL: 考虑紧急平仓
    ↓
熔断器保护 API 调用
    ↓
连续失败触发熔断
    ↓
冷却后尝试恢复
    ↓
恢复正常交易
```

## 文件清单

- `src/utils/health_checker.py`: 健康检查器
- `src/utils/circuit_breaker.py`: 熔断器实现
- `src/utils/degradation_strategy.py`: 降级策略和紧急处理器
- `src/exchange/exchange_info_manager.py`: 添加健康检查方法
- `scripts/sniper_trader.py`: 集成所有功能
- `tests/test_health_circuit_breaker.py`: 测试套件
