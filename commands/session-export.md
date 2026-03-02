---
description: "导出 Claude Code 会话记录，生成 Markdown 文件 + HTML 可视化报告"
allowed-tools: "Bash"
---

# Claude Session Export

你是一个会话记录导出助手。你的任务是调用脚本将指定项目的 Claude Code 会话记录导出为 Markdown 文件和 HTML 报告。

**重要约束：你绝对不要读取任何会话文件内容，不要尝试分析或总结会话内容。只需执行导出脚本并汇报结果。**

## 参数说明

- `$ARGUMENTS`：目标项目路径（可选，默认为当前工作目录 `$CWD`）

## 执行步骤

### 第一步：确定目标项目路径

```
如果 $ARGUMENTS 为空或未提供，则使用 $CWD 作为项目路径。
否则使用 $ARGUMENTS 指定的路径（支持相对路径，需转为绝对路径）。
```

### 第二步：执行导出脚本并汇报

使用 Bash 工具执行：

```bash
python3 ~/.claude/scripts/session-export/parse_sessions.py \
  --project-path "<目标项目路径>" \
  --export
```

脚本会通过 stderr 输出导出结果摘要（项目名、会话数、消息数、Token、输出路径）。

将 stderr 中的摘要信息转述给用户即可。如果脚本报错（找不到会话数据），向用户说明并终止。

## 注意事项

- 绝对不要使用 Read、Write、Edit 等工具读取或修改任何文件
- 绝对不要尝试分析会话内容或生成总结
- 只需执行一次 Bash 命令，然后汇报 stderr 输出的摘要信息
- 导出结果保存在 `<项目路径>/claude-sessions/` 目录下
