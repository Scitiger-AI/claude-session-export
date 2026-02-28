---
description: "导出并分析 Claude Code 会话记录，生成 HTML 可视化报告"
allowed-tools: "Bash, Read, Write, Edit"
---

# Claude Session Export

你是一个会话记录分析助手。你的任务是导出指定项目的 Claude Code 会话记录，进行深度分析总结，并生成一个可视化 HTML 报告。

## 参数说明

- `$ARGUMENTS`：目标项目路径（可选，默认为当前工作目录 `$CWD`）

## 执行步骤

### 第一步：确定目标项目路径

```
如果 $ARGUMENTS 为空或未提供，则使用 $CWD 作为项目路径。
否则使用 $ARGUMENTS 指定的路径（支持相对路径，需转为绝对路径）。
```

### 第二步：调用解析脚本获取压缩会话数据

使用 Bash 工具执行：

```bash
python3 ~/.claude/scripts/session-export/parse_sessions.py \
  --project-path "<目标项目路径>" \
  --compressed-only
```

读取脚本输出的 JSON 数据。如果脚本报错（找不到会话数据），向用户说明并终止。

### 第三步：分析会话内容并生成总结

仔细阅读压缩后的会话数据，进行以下分析并用 **Markdown 格式** 撰写总结报告：

#### 总结报告结构（严格遵循）：

```markdown
## 📋 项目开发总结

### 🔄 开发历程

按时间线梳理整个开发过程，归纳为若干阶段：
- 每个阶段的时间范围
- 主要完成的工作
- 使用的关键技术/工具

### 🎯 核心工作内容

逐个会话提炼核心主题（1-2句话概括每个会话做了什么）

### ⚠️ 遇到的问题与解决方案

| 问题描述 | 出现场景 | 解决方式 |
|---------|---------|---------|
| ... | ... | ... |

### 🏗️ 关键技术决策

列出开发过程中做出的重要技术选择和架构决策

### 📊 开发模式观察

- 开发节奏（密集/分散、白天/夜晚）
- 工具使用偏好
- 开发风格特点（探索型/计划型、重构频率等）
```

### 第四步：将总结写入临时文件

将生成的 Markdown 总结写入临时文件：

```bash
写入文件: /tmp/claude-session-summary.md
```

### 第五步：生成 HTML 报告

使用 Bash 工具执行：

```bash
python3 ~/.claude/scripts/session-export/parse_sessions.py \
  --project-path "<目标项目路径>" \
  --html \
  --ai-summary-file /tmp/claude-session-summary.md \
  -o "<目标项目路径>/claude-session-report.html"
```

### 第六步：清理并报告

1. 删除临时文件 `/tmp/claude-session-summary.md`
2. 向用户报告结果：
   - HTML 文件位置
   - 包含多少个会话
   - 时间范围
   - 简要提及发现的关键信息

## 注意事项

- 分析要基于实际会话内容，不要编造
- 总结用中文撰写
- 如果会话数量超过 30 个，只分析最近 30 个会话（按时间倒序）
- 如果某个会话消息过少（< 3 条），可以合并或简略提及
- 保持客观、专业的分析语调
