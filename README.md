# Claude Session Export

导出并分析 Claude Code 会话记录，生成自包含 HTML 可视化报告。

## 功能

- **会话解析**：从 `~/.claude/projects/` 提取指定项目的所有 JSONL 会话记录
- **AI 总结**：由 Claude 自动分析开发历程、核心工作、问题与解决方案、技术决策
- **HTML 报告**：生成 SPA 风格的自包含 HTML，支持深色/浅色主题切换
- **统计面板**：会话数、消息数、Token 用量、工具使用排行等

## 安装

```bash
git clone <repo-url> ~/claude-session-export
bash ~/claude-session-export/install.sh
```

安装脚本会以**符号链接**方式将文件链接到 `~/.claude/` 目录，后续 `git pull` 即可自动更新。

## 使用

在 Claude Code 中执行：

```
/session-export              # 导出当前项目的会话记录
/session-export /path/to/dir # 导出指定项目的会话记录
```

生成的 HTML 报告保存在项目根目录下：`claude-session-report.html`

## 卸载

```bash
bash ~/claude-session-export/install.sh --uninstall
```

## 文件结构

```
claude-session-export/
├── commands/
│   └── session-export.md       # Skill 命令定义
├── scripts/
│   └── session-export/
│       └── parse_sessions.py   # 会话解析 & HTML 生成脚本
├── install.sh                  # 安装/卸载脚本
└── README.md
```

## 依赖

- Python 3.8+（仅使用标准库，无需 pip install）
- Claude Code CLI

## 报告内容

### 📊 总结页

- 统计卡片：会话数、消息数、Token 用量、时长
- AI 分析报告：开发历程、核心工作、问题与方案、技术决策、开发模式
- 工具使用排行榜

### 💬 会话页

- 完整对话记录（用户消息 + Claude 回复）
- 工具调用详情（文件读写、Bash 命令、搜索等）
- 每条消息的时间戳和 Token 统计
