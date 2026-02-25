# 文档归档（Archive）

此目录存放项目历史版本的过时文档，仅供参考。

## 归档列表

| 文件 | 版本 | 说明 |
|------|------|------|
| `1.md` | - | 临时测试文件（空文件） |
| `CHANGELOG_v7.2.md` | v7.2 | v7.2 监控面板更新日志（已废弃） |
| `QUICKSTART_MONITORING.md` | v7.2 | v7.2 监控面板快速启动（已废弃） |
| `CRITICAL_FIXES_V3.1.md` | v3.1 | v3.1 关键修复文档 |
| `LESSONS_LEARNED.md` | v3.1 | v3.1 经验总结 |
| `PROFESSIONAL_USAGE_GUIDE.md` | v3.0 | v3.0 专业使用指南 |
| `PROFESSIONAL_V3_UPDATE.md` | v3.0 | v3.0 专业版更新说明 |
| `PROJECT_COMPLETION_REPORT.md` | v3.0 | v3.0 项目完成报告 |
| `PROJECT_DOCUMENTATION.md` | v3.0 | v3.0 项目完整文档 |
| `PROJECT_SUMMARY.md` | v3.0 | v3.0 项目总结 |

## 版本演进

- **v3.0-v3.1**: 早期版本（基础功能）
- **v5.0-v6.0**: 狙击手模式 + 掠夺者模式
- **v7.0**: 华尔街微观执行层
- **v7.1**: 机构级工程交付
- **v7.2**: 实时监控面板（❌ 已废弃 - 架构灾难）
- **v7.3**: 进程隔离架构（✅ 当前版本）

## 重要说明

⚠️ **v7.2 监控面板已废弃**

原因：
1. **事件循环投毒** - FastAPI 与交易引擎耦合导致延迟飙升
2. **攻击面扩大** - 默认绑定 0.0.0.0 带来安全风险
3. **心理视角退化** - "盯着看"设计诱发 FOMO 情绪

解决方案：
- **v7.3 进程隔离架构** - Redis Pub/Sub + 独立监控进程
- 详见：[../ARCHITECTURE_ISOLATION_v7.3.md](../ARCHITECTURE_ISOLATION_v7.3.md)
