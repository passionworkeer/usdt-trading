# OpenClaw Lobster 工作流引擎完整配置指南

## 目录
- [什么是 Lobster](#什么是-lobster)
- [核心价值](#核心价值)
- [适用场景](#适用场景)
- [安装与配置](#安装与配置)
- [使用示例](#使用示例)
- [工作流文件语法](#工作流文件语法)
- [命令参考](#命令参考)
- [常见问题](#常见问题)

---

## 什么是 Lobster

**Lobster** 是 OpenClaw 的**类型化工作流运行时 (typed workflow runtime)**，用于将多步骤的工具调用组合成单个、可控、可暂停的流程，中间带有**显式审批检查点**。

简单来说，Lobster 让你能够：
- 把复杂的多步骤任务封装成一个"宏"
- 在关键步骤加入人工审批
- 节省 LLM tokens（一次调用完成整个流程）
- 确保任务执行的确定性和可审计性

---

## 核心价值

### 1. 多步工作流变成一条调用 🔄

**传统方式**：复杂操作需要 LLM 不断来回调用工具，每步都消耗 tokens
```
AI: 调用工具 A (消耗 tokens)
AI: 分析结果 (消耗 tokens)
AI: 调用工具 B (消耗 tokens)
AI: 分析结果 (消耗 tokens)
AI: 调用工具 C (消耗 tokens)
...
```

**Lobster 方式**：只需一次调用就能执行整个工作流程
```
AI: 调用 Lobster 工作流 (一次调用)
    → 工具 A → 工具 B → 工具 C → 完成
```

**节省成本**：大幅减少 LLM tokens 消耗

---

### 2. 内置审批机制 ✅

某些操作有副作用（例如发送邮件、发帖子、修改数据），Lobster 会在此类副作用前**自动停下并请求审批**。

```
步骤 1: 收集邮件 ✅
步骤 2: 分类邮件 ✅
步骤 3: [需要审批] 发送邮件 ⏸️
        ↓
    用户批准
        ↓
步骤 4: 执行发送 ✅
```

---

### 3. 暂停/恢复执行 🔄

如果流程因为审批而停下，Lobster 会返回一个 **resumeToken（恢复令牌）**。

用户批准后，只需带着这个令牌重新发起请求即可继续，整个过程**不会重复前面的步骤**。

这类似"状态机可恢复执行"，特别适合长流程或需人工干预的场景。

---

## 适用场景

| 场景 | 是否适合 Lobster | 说明 |
|------|-----------------|------|
| ✅ 自动化邮件处理 | **非常适合** | 收件 → 分类 → 审批 → 发送 |
| ✅ 多步骤任务（需审批） | **非常适合** | 有安全/审计要求的自动化任务 |
| ✅ CLI 工具链自动执行 | **非常适合** | 管道式数据处理流程 |
| ✅ 定期监控任务 | **非常适合** | 检查 PR 状态、监控变更 |
| ❌ 简单单次操作 | 不适合 | 直接调用工具更简单 |
| ❌ 不需要审批的流程 | 可选 | Lobster 也能用，但优势不明显 |

---

## 安装与配置

### 步骤 1: 确保 OpenClaw 已安装

```bash
# 检查 OpenClaw 版本
openclaw --version

# 如果未安装，运行
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

---

### 步骤 2: 在 OpenClaw 配置中启用 Lobster

编辑 OpenClaw 配置文件：

```bash
# 配置文件位置
# macOS/Linux: ~/.openclaw/openclaw.json
# Windows: C:\Users\<用户名>\.openclaw\openclaw.json
```

在配置文件中添加 `tools.alsoAllow` 字段：

```json
{
  "tools": {
    "alsoAllow": ["lobster"]
  }
}
```

**完整配置示例**：

```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "anthropic": {
        "apiKey": "your-api-key-here"
      }
    }
  },
  "tools": {
    "alsoAllow": ["lobster"],
    "deny": []
  },
  "gateway": {
    "port": 18789,
    "bind": "loopback"
  }
}
```

---

### 步骤 3: 重启 Gateway

```bash
# 重启 OpenClaw Gateway
openclaw gateway restart

# 验证 Gateway 状态
openclaw gateway status
```

---

### 步骤 4: 验证 Lobster 可用

在 OpenClaw 对话中询问：

```
你有哪些工具可用？
```

如果看到 `lobster` 工具，说明配置成功。

---

## 使用示例

### 示例 1: 邮件收件箱处理

**场景**：自动处理邮件，需要人工审批后才能发送

#### 方式 A: 直接命令

```json
{
  "action": "run",
  "pipeline": "inbox-list | inbox-categorize | approve --prompt 'Apply changes?' | inbox-apply",
  "timeoutMs": 30000
}
```

#### 方式 B: 工作流文件

创建文件 `~/.openclaw/workflows/inbox-triage.lobster`:

```yaml
name: inbox-triage

steps:
  - id: collect
    command: inbox list --json

  - id: categorize
    command: inbox categorize --json
    stdin: $collect.stdout

  - id: approve
    command: inbox apply --approve
    stdin: $categorize.stdout
    approval: required

  - id: execute
    command: inbox apply --execute
    stdin: $categorize.stdout
    condition: $approve.approved
```

运行工作流：

```bash
lobster run ~/.openclaw/workflows/inbox-triage.lobster
```

---

### 示例 2: GitHub PR 监控

**场景**：监控 PR 状态变更

```bash
# 命令行调用
lobster "workflows.run --name github.pr.monitor --args-json '{\"repo\":\"openclaw/openclaw\",\"pr\":1152}'"
```

**返回结果示例**：

```json
[
  {
    "kind": "github.pr.monitor",
    "repo": "openclaw/openclaw",
    "prNumber": 1152,
    "changed": false,
    "summary": {
      "changedFields": [],
      "changes": {}
    },
    "prSnapshot": {
      "author": {
        "login": "vignesh07",
        "name": "Vignesh"
      },
      "baseRefName": "main",
      "headRefName": "feat/lobster-plugin",
      "isDraft": false,
      "mergeable": "MERGEABLE",
      "number": 1152,
      "reviewDecision": "",
      "state": "OPEN",
      "title": "feat: Add optional lobster plugin tool",
      "updatedAt": "2026-01-18T20:16:56Z",
      "url": "https://github.com/openclaw/openclaw/pull/1152"
    }
  }
]
```

---

### 示例 3: 数据处理管道

```bash
# JSON 数据处理
lobster "exec --json --shell 'echo [1,2,3]' | where '0>=0' | json"
```

---

## 工作流文件语法

### 基本结构

```yaml
name: workflow-name

# 可选：环境变量
env:
  API_KEY: ${env.MY_API_KEY}
  DEBUG: "true"

steps:
  - id: step1
    command: command --arg value
    # 可选：从上一步接收 stdin
    stdin: $previous_step.stdout

  - id: step2
    command: another-command
    stdin: $step1.stdout
    # 可选：审批检查点
    approval: required

  - id: step3
    command: final-command
    stdin: $step2.stdout
    # 可选：条件执行
    condition: $step2.approved
```

---

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 工作流名称 |
| `env` | object | ❌ | 环境变量 |
| `steps` | array | ✅ | 步骤列表 |
| `steps[].id` | string | ✅ | 步骤唯一标识 |
| `steps[].command` | string | ✅ | 要执行的命令 |
| `steps[].stdin` | string | ❌ | 从哪个步骤的 stdout 获取输入 |
| `steps[].approval` | string | ❌ | 设为 `required` 启用审批 |
| `steps[].condition` | string | ❌ | 条件表达式 |

---

### 变量引用

```yaml
steps:
  - id: step1
    command: echo "hello"

  - id: step2
    command: process-data
    stdin: $step1.stdout        # 引用上一步的输出

  - id: step3
    command: finalize
    condition: $step2.approved  # 引用审批结果
```

---

## 命令参考

### 核心命令

| 命令 | 说明 |
|------|------|
| `lobster run <file>` | 运行工作流文件 |
| `lobster exec` | 执行 OS 命令 |
| `lobster where` | 数据过滤 |
| `lobster pick` | 选择字段 |
| `lobster head` | 限制输出行数 |
| `lobster json` | JSON 格式输出 |
| `lobster table` | 表格格式输出 |
| `lobster approve` | 审批检查点 |
| `lobster doctor` | 诊断命令 |

---

### 常用参数

```bash
# 执行命令并输出 JSON
lobster exec --json --shell 'echo [1,2,3]'

# 从 stdin 读取数据
lobster exec --stdin json

# 审批检查点
lobster approve --prompt "Continue?"

# 运行工作流并传递参数
lobster run workflow.lobster --args-json '{"tag":"family"}'
```

---

## 在 OpenClaw 中调用 Lobster

### 方式 1: 直接对话

```
用户: 帮我运行邮件处理工作流

AI: 好的，我来调用 Lobster 执行邮件处理...
[调用 lobster 工具]
→ 收件完成
→ 分类完成
→ 需要审批：是否发送 2 封草稿邮件？
用户: 批准
→ 发送完成
```

---

### 方式 2: 在 Skill 中使用

在你的 Skill 代码中调用 Lobster：

```typescript
// 在 skill 的 tool 实现中
async function runWorkflow(context, params) {
  const result = await context.tools.lobster({
    action: "run",
    pipeline: "step1 | step2 | approve | step3",
    timeoutMs: 60000
  });

  if (result.status === "needs_approval") {
    // 处理审批逻辑
    return {
      needsApproval: true,
      prompt: result.requiresApproval.prompt,
      resumeToken: result.requiresApproval.resumeToken
    };
  }

  return result;
}
```

---

## 审批机制详解

### 审批流程

```
1. 工作流执行到 approval: required 的步骤
   ↓
2. Lobster 暂停并返回
   {
     "status": "needs_approval",
     "requiresApproval": {
       "prompt": "Send 2 draft replies?",
       "resumeToken": "abc123..."
     }
   }
   ↓
3. 用户审批
   ↓
4. 带着 resumeToken 继续执行
   lobster resume --token "abc123..." --approved true
```

---

### OpenClaw 集成的审批

当 OpenClaw 调用 Lobster 时，审批会通过对话界面呈现：

```
AI: 我需要你的批准才能继续：
    "是否发送 2 封草稿邮件？"
    [批准] [拒绝]
```

---

## 与 OpenClaw 的协同

### 架构关系

```
用户消息
   ↓
OpenClaw Agent (LLM)
   ↓
判断是否需要多步骤工作流
   ↓
调用 lobster 工具
   ↓
Lobster 执行工作流
   ↓
返回结果给 Agent
   ↓
Agent 回复用户
```

---

### 配置位置

| 配置项 | 文件位置 |
|--------|---------|
| Lobster 启用 | `~/.openclaw/openclaw.json` |
| 工作流文件 | `~/.openclaw/workflows/*.lobster` |
| 工作区 Skills | `~/.openclaw/workspace/skills/` |
| 共享 Skills | `~/.openclaw/skills/` |

---

## 常见问题

### Q1: Lobster 工具不可用？

**检查步骤**：

1. 确认配置正确：
   ```bash
   cat ~/.openclaw/openclaw.json | grep -A 5 "tools"
   ```

2. 确认包含 `"alsoAllow": ["lobster"]`

3. 重启 Gateway：
   ```bash
   openclaw gateway restart
   ```

---

### Q2: 工作流执行失败？

**排查步骤**：

1. 检查命令是否可用：
   ```bash
   lobster doctor
   ```

2. 检查工作流语法：
   ```bash
   lobster run --dry-run workflow.lobster
   ```

3. 查看详细日志：
   ```bash
   openclaw logs --tail 100
   ```

---

### Q3: 如何调试工作流？

**方法 1**: 单步执行
```bash
# 只运行第一步
lobster "inbox-list"
```

**方法 2**: 查看中间结果
```yaml
steps:
  - id: debug
    command: cat
    stdin: $previous_step.stdout
```

---

### Q4: 审批后如何恢复？

**OpenClaw 自动处理**：当你批准后，OpenClaw 会自动使用 resumeToken 继续执行。

**手动恢复**：
```bash
lobster resume --token "your-resume-token" --approved true
```

---

### Q5: Lobster 与普通工具有什么区别？

| 特性 | 普通工具 | Lobster |
|------|---------|---------|
| 单次调用 | ✅ | ✅ |
| 多步骤编排 | ❌ 需 LLM 反复调用 | ✅ 一次调用 |
| 审批检查点 | ❌ | ✅ |
| 暂停/恢复 | ❌ | ✅ |
| Token 消耗 | 高（多次调用） | 低（一次调用） |
| 确定性 | 中等 | 高 |

---

## 最佳实践

### 1. 何时使用 Lobster

**使用 Lobster**：
- 需要 3+ 步骤的流程
- 需要人工审批
- 需要可审计性
- 需要节省 tokens

**不使用 Lobster**：
- 简单单次操作
- 不需要编排
- 临时性任务

---

### 2. 工作流设计原则

- **单一职责**：每个工作流只做一件事
- **幂等性**：工作流可以重复执行
- **清晰命名**：使用描述性的步骤 ID
- **合理审批**：只在真正需要的地方加审批

---

### 3. 安全建议

- 审批敏感操作（发送、删除、修改）
- 使用 `condition` 控制执行
- 限制工作流文件权限
- 定期审计工作流日志

---

## 相关资源

- 📖 官方文档: https://docs.openclaw.ai/tools/lobster
- 🐙 GitHub 仓库: https://github.com/openclaw/lobster
- 🦞 OpenClaw 主项目: https://github.com/openclaw/openclaw
- 💬 社区讨论: https://discord.gg/openclaw

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-02-09 | Lobster 作为可选插件工具发布 |
| v1.1 | 2026-02-15 | 支持工作流文件 |
| v1.2 | 2026-02-20 | 增强 OpenClaw 集成 |

---

## 总结

**Lobster 是什么**：
- OpenClaw 的工作流引擎
- 类型化、可暂停、可审批
- 节省 tokens、提高确定性

**核心优势**：
- 一次调用完成多步骤
- 内置审批机制
- 暂停/恢复执行

**何时使用**：
- 多步骤自动化任务
- 需要人工审批的流程
- 需要节省 tokens 的场景

**如何启用**：
```json
{
  "tools": {
    "alsoAllow": ["lobster"]
  }
}
```

---

**祝你使用愉快！🦞**
