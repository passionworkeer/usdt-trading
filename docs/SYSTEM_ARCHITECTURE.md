# v7.1 系统架构与状态机可视化（System Architecture & State Machine Visualization）

本文档包含两个核心 Mermaid 图：
1. 订单状态机（Order State Machine）
2. 异步并发架构（Asynchronous Architecture）

---

## 1. 核心订单状态机（Order State Machine）

```mermaid
stateDiagram-v2
    [*] --> PENDING: 创建订单

    PENDING --> NEW: 提交到币安
    PENDING --> REJECTED: 参数验证失败

    NEW --> PARTIALLY_FILLED: 部分成交
    NEW --> FILLED: 完全成交
    NEW --> CANCELED: 用户撤销/超时
    NEW --> EXPIRED: GTX Post-Only 过期

    PARTIALLY_FILLED --> PARTIALLY_FILLED: 继续部分成交
    PARTIALLY_FILLED --> FILLED: 完全成交
    PARTIALLY_FILLED --> CANCELED: 超时撤销（5分钟）

    FILLED --> [*]: 订单完成
    CANCELED --> [*]: 订单取消
    REJECTED --> [*]: 订单拒绝
    EXPIRED --> [*]: 订单过期

    note right of PENDING
        初始状态
        - 验证参数
        - 检查余额
        - Post-Only 检查
    end note

    note right of PARTIALLY_FILLED
        关键状态
        - 记录已成交数量
        - 重新计算仓位
        - 5分钟超时撤销
    end note

    note right of NEW
        等待成交
        - 订单进入订单簿
        - Maker 费率保证
        - 监控 OBI 拦截
    end note
```

### 状态流转说明

| 状态 | 触发条件 | 处理逻辑 |
|------|----------|----------|
| PENDING → NEW | 订单提交成功 | 进入订单簿等待成交 |
| NEW → PARTIALLY_FILLED | 部分成交 | 记录已成交数量，启动 5 分钟超时计时器 |
| PARTIALLY_FILLED → CANCELED | 超时 5 分钟 | 撤销剩余挂单，保留已成交部分 |
| PARTIALLY_FILLED → FILLED | 完全成交 | 计算平均成交价，更新仓位 |
| NEW → CANCELED | OBI 拦截触发 | 立即撤销，避免接飞刀 |

---

## 2. 异步并发架构（Asynchronous Architecture）

```mermaid
graph TB
    subgraph "币安服务器 (Binance Server)"
        WS_Ticker[WebSocket Ticker 流]
        WS_Depth[WebSocket Depth 流]
        REST_API[REST API]
    end

    subgraph "网络层 (Network Layer)"
        Internet[互联网<br/>延迟: 10-50ms]
        TLS[TLS 握手<br/>首次: 50-100ms<br/>复用: 0ms]
    end

    subgraph "数据接收层 (Data Reception)"
        WS_Client[WebSocket 客户端<br/>自动重连池]
        Latency_Check{延迟检测<br/>&lt;100ms?}
        Stale_Protector[数据陈旧保护器]
    end

    subgraph "数据处理层 (Data Processing)"
        JSON_Parser[JSON 解析<br/>耗时: 1-5ms]
        Ticker_Buffer[Ticker 缓冲队列<br/>asyncio.Queue]
        Depth_Buffer[Depth 缓冲队列]
    end

    subgraph "策略层 (Strategy Layer)"
        Smart_Screener[智能扫描器<br/>前置过滤]
        OBI_Calculator[OBI 计算器<br/>耗时: 0.5-1ms]
        OBI_Check{OBI 检查<br/>是否接飞刀?}
        MTF_Lock[MTF 三重共振锁]
    end

    subgraph "执行层 (Execution Layer)"
        Fibonacci_Entry[斐波那契 0.382<br/>入场价计算]
        Post_Only_Check{Post-Only 检查<br/>会吃单?}
        Order_State_Machine[订单状态机]
        Order_Executor[订单执行器<br/>aiohttp POST]
    end

    subgraph "风控层 (Risk Control)"
        Funding_Guard[资金费结算守护]
        Time_Sync[时间同步管理器]
        Position_Manager[仓位管理器]
    end

    %% 数据流
    WS_Ticker --> Internet
    WS_Depth --> Internet
    Internet --> TLS
    TLS --> WS_Client

    WS_Client --> Latency_Check
    Latency_Check -->|是| JSON_Parser
    Latency_Check -->|否| Stale_Protector
    Stale_Protector -->|静默锁定| WS_Client

    JSON_Parser --> Ticker_Buffer
    JSON_Parser --> Depth_Buffer

    Ticker_Buffer --> Smart_Screener
    Depth_Buffer --> OBI_Calculator

    Smart_Screener -->|满足条件| MTF_Lock
    MTF_Lock -->|三重共振| Fibonacci_Entry

    Fibonacci_Entry --> OBI_Check
    OBI_Calculator --> OBI_Check
    OBI_Check -->|安全| Post_Only_Check
    OBI_Check -->|危险| Order_State_Machine

    Post_Only_Check -->|安全| Order_State_Machine
    Post_Only_Check -->|会吃单| Order_State_Machine

    Order_State_Machine --> Order_Executor
    Order_Executor --> TLS
    TLS --> Internet
    Internet --> REST_API

    %% 风控流
    Funding_Guard -.->|结算前15分钟熔断| Order_Executor
    Time_Sync -.->|时间戳修正| Order_Executor
    Position_Manager -.->|仓位检查| Order_State_Machine

    %% 样式
    classDef critical fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px;
    classDef warning fill:#ffd43b,stroke:#fab005,stroke-width:2px;
    classDef safe fill:#51cf66,stroke:#37b24d,stroke-width:2px;

    class Stale_Protector,OBI_Check,Post_Only_Check critical;
    class Latency_Check,OBI_Calculator,Time_Sync warning;
    class Order_State_Machine,Position_Manager safe;
```

### 关键队列机制

```mermaid
sequenceDiagram
    participant Binance as 币安服务器
    participant WS as WebSocket 客户端
    participant Queue as asyncio.Queue
    participant Screener as 智能扫描器
    participant Executor as 订单执行器

    Binance->>WS: Ticker 数据流（实时）
    WS->>Queue: put_nowait(ticker)
    Queue->>Screener: await queue.get()
    Screener->>Screener: 前置过滤（成交量+波动率）

    alt 满足条件
        Screener->>Executor: 触发深度验证
        Executor->>Binance: REST API（K线/OI）
        Binance-->>Executor: 返回数据
        Executor->>Executor: MTF 三重共振检查
        Executor->>Executor: 计算入场价（0.382）
        Executor->>Binance: 提交限价单（GTX）
    else 不满足
        Screener->>Queue: 继续监听
    end
```

---

## 3. 关键路径延迟分析

| 组件 | 理论延迟 | 实测延迟 | 优化措施 |
|------|----------|----------|----------|
| 网络传输 | 10-50ms | 20-80ms | DNS 缓存 5 分钟 |
| TLS 握手 | 50-100ms（首次）| 0ms（复用）| Session Keep-Alive |
| JSON 解析 | 1-5ms | 2-8ms | 使用 orjson（可选） |
| OBI 计算 | 0.5-1ms | 1-2ms | NumPy 向量化 |
| asyncio 调度 | 0.1-0.5ms | 0.2-1ms | 事件循环优化 |
| **总计** | **62-157ms** | **24-92ms** | **复用连接后** |

**关键优化点：**
- TLS Keep-Alive：节省 50-100ms
- DNS 缓存：节省 10-20ms
- 并发处理：节省 30-50ms

---

## 4. 熔断机制流程图

```mermaid
graph TD
    Start[系统启动] --> Check1{延迟检测}

    Check1 -->|< 100ms| Check2{OBI 检查}
    Check1 -->|> 100ms| Lock1[静默锁定]

    Check2 -->|OBI 正常| Check3{资金费结算}
    Check2 -->|OBI 异常| Lock2[撤销挂单]

    Check3 -->|不在静默期| Check4{Post-Only}
    Check3 -->|在静默期| Lock3[全局熔断]

    Check4 -->|Post-Only 通过| Execute[执行交易]
    Check4 -->|会吃单| Reject[拒绝订单]

    Lock1 --> Wait1[等待恢复]
    Lock2 --> Wait2[等待 OBI 恢复]
    Lock3 --> Wait3[等待结算完成]

    Wait1 --> Check1
    Wait2 --> Check2
    Wait3 --> Check3

    Execute --> Monitor[监控订单状态]
    Monitor -->|部分成交| Partial[5分钟超时撤销]
    Monitor -->|完全成交| Success[更新仓位]

    classDef lock fill:#ff6b6b,stroke:#c92a2a;
    classDef check fill:#ffd43b,stroke:#fab005;
    classDef success fill:#51cf66,stroke:#37b24d;

    class Lock1,Lock2,Lock3,Reject lock;
    class Check1,Check2,Check3,Check4 check;
    class Execute,Success success;
```

---

**版本**: v7.1

**更新日期**: 2026-02-25

**用途**: 工程交付文档、系统架构评审、团队沟通
