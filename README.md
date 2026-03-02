# Claude Session Export

导出 Claude Code 会话记录，生成 Markdown 文件 + 自包含 HTML 可视化报告。

## 功能

- **会话解析**：从 `~/.claude/projects/` 提取指定项目的所有 JSONL 会话记录
- **Markdown 导出**：每个会话生成独立 `.md` 文件（含 YAML front matter），附带 `index.md` 索引
- **HTML 报告**：生成 SPA 风格的自包含 HTML，支持深色/浅色主题切换
- **统计面板**：会话数、消息数、Token 用量、工具使用排行、会话概览列表

## 安装

```bash
git clone <repo-url> ~/claude-session-export
bash ~/claude-session-export/install.sh
```

安装脚本会以**符号链接**方式将文件链接到 `~/.claude/` 目录，后续 `git pull` 即可自动更新。

## 使用

### 在 Claude Code 中使用（推荐）

```
/session-export              # 导出当前项目的会话记录
/session-export /path/to/dir # 导出指定项目的会话记录
```

### 命令行直接使用

```bash
# 完整导出（Markdown + HTML）
python3 scripts/session-export/parse_sessions.py -p /path/to/project --export

# 仅导出 Markdown
python3 scripts/session-export/parse_sessions.py -p /path/to/project --export-md

# 仅生成 HTML 报告
python3 scripts/session-export/parse_sessions.py -p /path/to/project --html -o report.html

# 指定输出目录
python3 scripts/session-export/parse_sessions.py -p /path/to/project --export -d /tmp/my-sessions/

# 输出 JSON 格式数据到 stdout
python3 scripts/session-export/parse_sessions.py -p /path/to/project
```

### 输出目录结构

```
<project-path>/claude-sessions/
├── index.md                          # 索引：统计概览 + 工具排行 + 会话列表
├── 001_2025-02-28_初始化项目结构.md   # 会话 Markdown 文件
├── 002_2025-03-01_修复登录Bug.md
├── ...
└── report.html                       # 自包含 HTML 可视化报告
```

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
│       └── parse_sessions.py   # 会话解析 & 导出脚本
├── install.sh                  # 安装/卸载脚本
└── README.md
```

## 依赖

- Python 3.8+（仅使用标准库，无需 pip install）
- Claude Code CLI

## 报告内容

### 📊 总览页

- 统计卡片：会话数、消息数、Token 用量、时长
- 工具使用排行榜
- 会话概览列表：每个会话显示日期、时长、消息数、Token、Top 工具，点击跳转详情

### 💬 会话页

- 完整对话记录（用户消息 + Claude 回复）
- 工具调用详情（文件读写、Bash 命令、搜索等）
- 每条消息的时间戳和 Token 统计
