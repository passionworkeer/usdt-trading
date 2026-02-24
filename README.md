# OpenClaw Crypto Trader

基于 Ship Project 改造的 OpenClaw 自动加密货币交易系统。

## 特性

- ✅ 基于 CCXT 的多交易所支持
- ✅ Confluence 分析机制（多源信号打分）
- ✅ 完整的风控系统
- ✅ 自动止损止盈
- ✅ Binance 测试网支持

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

### 3. 运行测试

```bash
python -m pytest tests/ -v
```

### 4. 启动自动交易

```bash
python scripts/auto_trade.py
```

## 项目结构

```
openclaw-crypto-trader/
├── src/
│   ├── exchange/         # 交易所集成和订单执行
│   ├── analysis/         # Confluence 分析
│   ├── data_sources/     # 数据源集成
│   └── utils/            # 工具函数
├── tests/                # 测试文件
├── scripts/              # 执行脚本
└── docs/                 # 文档
```

## 安全注意事项

⚠️ **重要**：
- 始终在测试网先验证
- 使用 IP 白名单
- 设置严格的止损
- 从小金额开始

## License

MIT
