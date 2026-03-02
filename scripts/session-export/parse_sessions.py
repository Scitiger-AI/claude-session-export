#!/usr/bin/env python3
"""Claude Code 会话解析器 - 从 JSONL 文件提取结构化会话数据并导出。

用法:
    python3 parse_sessions.py --project-path /path/to/project [--json]
    python3 parse_sessions.py --project-path /path/to/project --html -o report.html
    python3 parse_sessions.py --project-path /path/to/project --export [-d output_dir]
    python3 parse_sessions.py --project-path /path/to/project --export-md [-d output_dir]

输出模式:
    --json        输出结构化 JSON 到 stdout（默认）
    --html        生成自包含 HTML 报告文件
    --export      导出 Markdown 会话文件 + HTML 报告
    --export-md   仅导出 Markdown 会话文件
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── 常量 ───────────────────────────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# 工具调用显示名称映射
TOOL_DISPLAY = {
    "Read": "📖 Read",
    "Write": "📝 Write",
    "Edit": "✏️ Edit",
    "Bash": "💻 Bash",
    "Grep": "🔍 Grep",
    "Glob": "📂 Glob",
    "Task": "🤖 Task",
    "WebFetch": "🌐 WebFetch",
    "WebSearch": "🔎 WebSearch",
    "AskUserQuestion": "❓ AskUser",
}


# ─── 工具函数 ─────────────────────────────────────────────────────────────

def encode_project_path(project_path: str) -> str:
    """将项目绝对路径编码为 Claude 存储目录名。"""
    return project_path.replace("/", "-")


def parse_timestamp(ts: str | int | float | None) -> datetime | None:
    """解析时间戳（ISO 字符串或毫秒级 Unix 时间戳）。"""
    if ts is None:
        return None
    try:
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def format_ts(dt: datetime | None) -> str:
    """格式化时间戳为本地可读格式。"""
    if dt is None:
        return ""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_ts_iso(dt: datetime | None) -> str:
    """格式化为 ISO8601。"""
    if dt is None:
        return ""
    return dt.isoformat()


def extract_text_and_tools(content: list | str) -> tuple[str, list[dict]]:
    """从 message.content 提取文本和工具调用信息。

    Returns:
        (text, tools) - 纯文本内容 和 工具调用列表
    """
    if isinstance(content, str):
        return content, []

    text_parts: list[str] = []
    tools: list[dict] = []

    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type == "text":
            t = block.get("text", "").strip()
            if t:
                text_parts.append(t)

        elif block_type == "thinking":
            thinking = block.get("thinking", "").strip()
            if thinking:
                # 截断过长的思考内容
                if len(thinking) > 500:
                    thinking = thinking[:500] + "..."
                text_parts.append(f"[思考] {thinking}")

        elif block_type == "tool_use":
            tool_name = block.get("name", "unknown")
            tool_input = block.get("input", {})
            tool_info = _summarize_tool_call(tool_name, tool_input)
            tools.append(tool_info)

    return "\n\n".join(text_parts), tools


def _summarize_tool_call(name: str, inp: dict) -> dict:
    """生成工具调用的摘要信息。"""
    summary = ""

    if name == "Task":
        summary = inp.get("description", inp.get("prompt", "")[:100])
    elif name in ("Read", "Write", "Edit"):
        summary = inp.get("file_path", "")
    elif name == "Bash":
        cmd = inp.get("command", "")
        summary = cmd[:150] + ("..." if len(cmd) > 150 else "")
    elif name in ("Grep", "Glob"):
        summary = inp.get("pattern", "")
    elif name == "WebFetch":
        summary = inp.get("url", "")
    elif name == "WebSearch":
        summary = inp.get("query", "")
    elif name == "AskUserQuestion":
        questions = inp.get("questions", [])
        if questions:
            q = questions[0]
            if isinstance(q, dict):
                summary = q.get("question", "")[:100]
            elif isinstance(q, str):
                summary = q[:100]
    else:
        # 通用：取第一个有值的字段
        for v in inp.values():
            if isinstance(v, str) and v:
                summary = v[:100]
                break

    return {
        "name": name,
        "display": TOOL_DISPLAY.get(name, f"🔧 {name}"),
        "summary": summary,
    }


# ─── 会话解析 ─────────────────────────────────────────────────────────────

def parse_session_file(jsonl_path: Path) -> dict | None:
    """解析单个 JSONL 会话文件，返回结构化数据。"""
    messages: list[dict] = []
    session_id = jsonl_path.stem
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    git_branch: str | None = None
    model_used: str | None = None
    total_input_tokens = 0
    total_output_tokens = 0
    tool_counter: Counter = Counter()
    version: str | None = None

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")

            # 跳过非核心类型
            if entry_type in ("file-history-snapshot", "progress", "summary", "result"):
                continue

            # 提取元信息
            if not git_branch and entry.get("gitBranch"):
                git_branch = entry["gitBranch"]
            if not version and entry.get("version"):
                version = entry["version"]

            # 时间戳
            ts = parse_timestamp(entry.get("timestamp"))
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            # 用户消息
            if entry_type == "user":
                msg = entry.get("message", {})
                content = msg.get("content", "")
                text, tools = extract_text_and_tools(content)
                if text:
                    messages.append({
                        "role": "user",
                        "content": text,
                        "tools": tools,
                        "timestamp": format_ts_iso(ts),
                        "timestamp_display": format_ts(ts),
                    })

            # 助手消息
            elif entry_type == "assistant":
                msg = entry.get("message", {})
                content = msg.get("content", [])
                text, tools = extract_text_and_tools(content)

                # 统计 token
                usage = msg.get("usage", {})
                total_input_tokens += usage.get("input_tokens", 0)
                total_input_tokens += usage.get("cache_creation_input_tokens", 0)
                total_input_tokens += usage.get("cache_read_input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)

                # 统计工具使用
                for tool in tools:
                    tool_counter[tool["name"]] += 1

                # 模型信息
                if not model_used and msg.get("model"):
                    model_used = msg["model"]

                if text or tools:
                    # 合并连续助手消息
                    if messages and messages[-1]["role"] == "assistant":
                        prev = messages[-1]
                        if text and text not in prev["content"]:
                            prev["content"] = (prev["content"] + "\n\n" + text).strip()
                        prev["tools"].extend(tools)
                        if ts:
                            prev["timestamp"] = format_ts_iso(ts)
                            prev["timestamp_display"] = format_ts(ts)
                    else:
                        messages.append({
                            "role": "assistant",
                            "content": text,
                            "tools": tools,
                            "timestamp": format_ts_iso(ts),
                            "timestamp_display": format_ts(ts),
                        })

    if not messages:
        return None

    # 计算会话持续时间（分钟）
    duration_minutes = 0
    if first_ts and last_ts:
        duration_minutes = round((last_ts - first_ts).total_seconds() / 60, 1)

    return {
        "session_id": session_id,
        "start_time": format_ts_iso(first_ts),
        "end_time": format_ts_iso(last_ts),
        "start_time_display": format_ts(first_ts),
        "end_time_display": format_ts(last_ts),
        "duration_minutes": duration_minutes,
        "git_branch": git_branch or "unknown",
        "model": model_used or "unknown",
        "version": version,
        "message_count": len(messages),
        "user_message_count": sum(1 for m in messages if m["role"] == "user"),
        "assistant_message_count": sum(1 for m in messages if m["role"] == "assistant"),
        "token_usage": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "total": total_input_tokens + total_output_tokens,
        },
        "tools_summary": dict(tool_counter.most_common()),
        "messages": messages,
    }



# ─── 项目级解析 ───────────────────────────────────────────────────────────

def parse_project(project_path: str) -> dict:
    """解析指定项目的所有会话，返回完整的结构化数据。"""
    abs_path = os.path.abspath(project_path)
    dir_name = encode_project_path(abs_path)
    project_dir = PROJECTS_DIR / dir_name

    if not project_dir.exists():
        return {
            "error": f"未找到项目会话数据: {project_dir}",
            "project_path": abs_path,
            "encoded_dir": dir_name,
        }

    jsonl_files = sorted(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return {
            "error": f"项目目录中没有会话记录: {project_dir}",
            "project_path": abs_path,
        }

    sessions: list[dict] = []
    for jsonl_path in jsonl_files:
        session = parse_session_file(jsonl_path)
        if session:
            sessions.append(session)

    # 按开始时间排序
    sessions.sort(key=lambda s: s["start_time"] or "")

    # 全局统计
    total_input = sum(s["token_usage"]["input"] for s in sessions)
    total_output = sum(s["token_usage"]["output"] for s in sessions)
    all_tools: Counter = Counter()
    for s in sessions:
        all_tools.update(s["tools_summary"])

    total_messages = sum(s["message_count"] for s in sessions)
    date_range = []
    if sessions:
        first = sessions[0]["start_time_display"][:10] if sessions[0]["start_time_display"] else ""
        last = sessions[-1]["end_time_display"][:10] if sessions[-1]["end_time_display"] else ""
        date_range = [first, last]

    return {
        "project_path": abs_path,
        "project_name": Path(abs_path).name,
        "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_dir": str(project_dir),
        "sessions": sessions,
        "stats": {
            "total_sessions": len(sessions),
            "total_messages": total_messages,
            "total_user_messages": sum(s["user_message_count"] for s in sessions),
            "total_assistant_messages": sum(s["assistant_message_count"] for s in sessions),
            "date_range": date_range,
            "total_duration_minutes": round(sum(s["duration_minutes"] for s in sessions), 1),
            "token_usage": {
                "input": total_input,
                "output": total_output,
                "total": total_input + total_output,
            },
            "tools_ranking": all_tools.most_common(20),
        },
    }


# ─── HTML 生成 ────────────────────────────────────────────────────────────

def generate_html(data: dict) -> str:
    """生成自包含的 SPA 风格 HTML 报告。"""
    project_name = data.get("project_name", "Unknown")
    export_time = data.get("export_time", "")
    stats = data.get("stats", {})
    sessions = data.get("sessions", [])

    # 将会话数据序列化为 JSON 嵌入 HTML
    # 关键：必须转义 </script> 和 <!-- ，否则浏览器 HTML 解析器
    # 会在 <script> 块内部误判标签边界，导致 JS SyntaxError
    def escape_for_script_tag(s: str) -> str:
        return s.replace("</", "<\\/").replace("<!--", "<\\!--")

    sessions_json = escape_for_script_tag(
        json.dumps(sessions, ensure_ascii=False, indent=None)
    )
    stats_json = escape_for_script_tag(
        json.dumps(stats, ensure_ascii=False, indent=None)
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Session Report - {project_name}</title>
<style>
:root {{
  --bg-primary: #0f1117;
  --bg-secondary: #1a1d27;
  --bg-tertiary: #242736;
  --bg-hover: #2a2d3e;
  --text-primary: #e4e6ed;
  --text-secondary: #9095a6;
  --text-muted: #6b7084;
  --border-color: #2e3144;
  --accent: #6c8cff;
  --accent-soft: rgba(108,140,255,0.12);
  --user-bg: #1e2a3a;
  --user-border: #2d4a6f;
  --assistant-bg: #1a2520;
  --assistant-border: #2d5a3f;
  --tool-bg: #262335;
  --tool-border: #3d3560;
  --system-bg: #2a2520;
  --system-border: #5a4530;
  --tag-bg: rgba(108,140,255,0.15);
  --tag-text: #8aa4ff;
  --scrollbar-track: #1a1d27;
  --scrollbar-thumb: #3a3d50;
}}

[data-theme="light"] {{
  --bg-primary: #ffffff;
  --bg-secondary: #f5f6f8;
  --bg-tertiary: #ecedf0;
  --bg-hover: #e8e9ed;
  --text-primary: #1a1d27;
  --text-secondary: #5a5f72;
  --text-muted: #8a8fa2;
  --border-color: #dcdee5;
  --accent: #4a6cf7;
  --accent-soft: rgba(74,108,247,0.08);
  --user-bg: #eef3ff;
  --user-border: #c5d5f7;
  --assistant-bg: #eef8f3;
  --assistant-border: #b8dcc8;
  --tool-bg: #f3f0fa;
  --tool-border: #d5cef0;
  --system-bg: #fef8ee;
  --system-border: #e8d5a8;
  --tag-bg: rgba(74,108,247,0.1);
  --tag-text: #4a6cf7;
  --scrollbar-track: #f5f6f8;
  --scrollbar-thumb: #cccfd8;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  height: 100vh;
  overflow: hidden;
}}

/* 滚动条 */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: var(--scrollbar-track); }}
::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 3px; }}

/* 布局 */
.app {{ display: flex; height: 100vh; }}

.sidebar {{
  width: 280px;
  min-width: 280px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

.sidebar-header {{
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}}

.sidebar-header h2 {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}}

.sidebar-header .project-name {{
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
}}

.sidebar-stats {{
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}}

.stat-badge {{
  font-size: 11px;
  padding: 3px 8px;
  background: var(--tag-bg);
  color: var(--tag-text);
  border-radius: 10px;
  white-space: nowrap;
}}

.sidebar-nav {{
  padding: 8px;
  display: flex;
  gap: 4px;
}}

.nav-btn {{
  flex: 1;
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}}

.nav-btn:hover {{ background: var(--bg-hover); }}
.nav-btn.active {{
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}}

.session-list {{
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
}}

.session-item {{
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
  border: 1px solid transparent;
}}

.session-item:hover {{ background: var(--bg-hover); }}
.session-item.active {{
  background: var(--accent-soft);
  border-color: var(--accent);
}}

.session-item .session-title {{
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.session-item .session-meta {{
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}}

.main-content {{
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

.content-header {{
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-secondary);
}}

.content-header h3 {{
  font-size: 15px;
  font-weight: 600;
}}

.header-actions {{
  display: flex;
  gap: 8px;
  align-items: center;
}}

.theme-toggle {{
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}}
.theme-toggle:hover {{ background: var(--bg-hover); }}

.content-body {{
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}}

/* 总结报告 */
.summary-report {{
  max-width: 900px;
  margin: 0 auto;
}}

.summary-report h2 {{
  font-size: 20px;
  margin-bottom: 16px;
  color: var(--accent);
}}

.summary-report h3 {{
  font-size: 16px;
  margin: 20px 0 10px;
  color: var(--text-primary);
}}

.summary-section {{
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 16px;
}}

.summary-text {{
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
}}

.summary-text p {{ margin-bottom: 12px; }}
.summary-text ul, .summary-text ol {{ padding-left: 20px; margin-bottom: 12px; }}
.summary-text li {{ margin-bottom: 6px; }}
.summary-text code {{
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}}
.summary-text pre {{
  background: var(--bg-tertiary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 10px 0;
}}
.summary-text pre code {{ background: none; padding: 0; }}
.summary-text strong {{ color: var(--accent); }}
.summary-text h4 {{ font-size: 15px; margin: 16px 0 8px; color: var(--text-primary); }}

/* 统计卡片 */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}}

.stats-card {{
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}}

.stats-card .stats-value {{
  font-size: 28px;
  font-weight: 700;
  color: var(--accent);
}}

.stats-card .stats-label {{
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}}

/* 工具排行 */
.tools-bar {{
  display: flex;
  align-items: center;
  margin-bottom: 6px;
  font-size: 13px;
}}

.tools-bar .tool-name {{
  width: 100px;
  color: var(--text-secondary);
  text-align: right;
  padding-right: 10px;
  flex-shrink: 0;
}}

.tools-bar .tool-bar-track {{
  flex: 1;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}}

.tools-bar .tool-bar-fill {{
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width 0.3s;
  min-width: 2px;
}}

.tools-bar .tool-count {{
  width: 40px;
  text-align: right;
  color: var(--text-muted);
  padding-left: 8px;
  flex-shrink: 0;
}}

/* 消息列表 */
.message-list {{
  max-width: 900px;
  margin: 0 auto;
}}

.message {{
  margin-bottom: 12px;
  border-radius: 10px;
  padding: 14px 18px;
  border: 1px solid;
}}

.message.user {{
  background: var(--user-bg);
  border-color: var(--user-border);
}}

.message.assistant {{
  background: var(--assistant-bg);
  border-color: var(--assistant-border);
}}

.message.system {{
  background: var(--system-bg);
  border-color: var(--system-border);
  font-style: italic;
}}

.message-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}}

.message-role {{
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}

.message.user .message-role {{ color: #6cacff; }}
.message.assistant .message-role {{ color: #6ccc8c; }}
.message.system .message-role {{ color: #ccaa6c; }}

.message-time {{
  font-size: 11px;
  color: var(--text-muted);
}}

.message-content {{
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}}

.message-content code {{
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}}

.message-content pre {{
  background: var(--bg-primary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
  border: 1px solid var(--border-color);
}}

.message-content pre code {{
  background: none;
  padding: 0;
}}

/* 工具调用 */
.tool-calls {{
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}}

.tool-call {{
  background: var(--tool-bg);
  border: 1px solid var(--tool-border);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  gap: 8px;
  align-items: baseline;
}}

.tool-call .tool-label {{
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}}

.tool-call .tool-detail {{
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

/* 占位 */
.placeholder {{
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 16px;
}}

/* 响应式 */
@media (max-width: 768px) {{
  .sidebar {{ width: 100%; min-width: auto; max-height: 40vh; }}
  .app {{ flex-direction: column; }}
}}

/* 会话概览卡片 */
.session-overview-item {{
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s;
}}
.session-overview-item:hover {{
  background: var(--bg-hover);
  border-color: var(--accent);
}}
.session-overview-item .soi-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}}
.session-overview-item .soi-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}}
.session-overview-item .soi-date {{
  font-size: 12px;
  color: var(--text-muted);
}}
.session-overview-item .soi-meta {{
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}}
.session-overview-item .soi-tools {{
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}}
.session-overview-item .soi-tool-tag {{
  font-size: 11px;
  padding: 2px 6px;
  background: var(--tag-bg);
  color: var(--tag-text);
  border-radius: 8px;
}}
</style>
</head>
<body data-theme="dark">
<div class="app">
  <!-- 侧边栏 -->
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Claude Session Report</h2>
      <div class="project-name">{project_name}</div>
    </div>
    <div class="sidebar-stats" id="sidebarStats"></div>
    <div class="sidebar-nav">
      <button class="nav-btn active" data-view="summary" onclick="switchView('summary')">📊 总览</button>
      <button class="nav-btn" data-view="sessions" onclick="switchView('sessions')">💬 会话</button>
    </div>
    <div class="session-list" id="sessionList"></div>
  </div>

  <!-- 主内容 -->
  <div class="main-content">
    <div class="content-header">
      <h3 id="contentTitle">统计总览</h3>
      <div class="header-actions">
        <span style="font-size:11px;color:var(--text-muted)">导出于 {export_time}</span>
        <button class="theme-toggle" onclick="toggleTheme()" title="切换主题">🌓</button>
      </div>
    </div>
    <div class="content-body" id="contentBody">
      <div class="placeholder">加载中...</div>
    </div>
  </div>
</div>

<script>
// ─── 数据 ──────────────────────────────────────────────
const SESSIONS = {sessions_json};
const STATS = {stats_json};

let currentView = 'summary';
let currentSessionIdx = -1;

// ─── 初始化 ────────────────────────────────────────────
function init() {{
  renderSidebarStats();
  renderSessionList();
  showSummary();
}}

function renderSidebarStats() {{
  const el = document.getElementById('sidebarStats');
  const s = STATS;
  el.innerHTML = `
    <span class="stat-badge">${{s.total_sessions}} 个会话</span>
    <span class="stat-badge">${{s.total_messages}} 条消息</span>
    <span class="stat-badge">${{formatTokens(s.token_usage?.total || 0)}} tokens</span>
    <span class="stat-badge">${{s.total_duration_minutes || 0}} 分钟</span>
  `;
}}

function renderSessionList() {{
  const el = document.getElementById('sessionList');
  el.innerHTML = SESSIONS.map((s, i) => `
    <div class="session-item ${{i === currentSessionIdx ? 'active' : ''}}"
         onclick="showSession(${{i}})" data-idx="${{i}}">
      <div class="session-title">#${{i+1}} ${{getSessionTitle(s)}}</div>
      <div class="session-meta">
        <span>${{s.start_time_display?.slice(0,16) || ''}}</span>
        <span>${{s.message_count}}条</span>
        <span>${{s.duration_minutes}}分钟</span>
        <span>${{s.git_branch}}</span>
      </div>
    </div>
  `).join('');
}}

function getSessionTitle(s) {{
  // 取第一条用户消息的前30字作为标题
  const firstUser = s.messages?.find(m => m.role === 'user');
  if (firstUser) {{
    let text = firstUser.content.replace(/\\n/g, ' ').trim();
    return text.length > 40 ? text.slice(0, 40) + '...' : text;
  }}
  return s.session_id.slice(0, 8);
}}

// ─── 视图切换 ──────────────────────────────────────────
function switchView(view) {{
  currentView = view;
  document.querySelectorAll('.nav-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.view === view);
  }});
  if (view === 'summary') {{
    currentSessionIdx = -1;
    updateSessionListActive();
    showSummary();
  }}
}}

function showSummary() {{
  document.getElementById('contentTitle').textContent = '统计总览';
  const body = document.getElementById('contentBody');
  const s = STATS;

  let toolsHtml = '';
  const maxCount = s.tools_ranking?.[0]?.[1] || 1;
  if (s.tools_ranking) {{
    toolsHtml = s.tools_ranking.slice(0, 10).map(([name, count]) => `
      <div class="tools-bar">
        <span class="tool-name">${{name}}</span>
        <div class="tool-bar-track">
          <div class="tool-bar-fill" style="width:${{(count/maxCount*100).toFixed(1)}}%"></div>
        </div>
        <span class="tool-count">${{count}}</span>
      </div>
    `).join('');
  }}

  // 会话概览列表
  const sessionsOverviewHtml = SESSIONS.map((sess, i) => {{
    const topTools = Object.entries(sess.tools_summary || {{}}).sort((a,b) => b[1]-a[1]).slice(0,3);
    const toolTags = topTools.map(([name, count]) => `<span class="soi-tool-tag">${{name}} ${{count}}</span>`).join('');
    return `
      <div class="session-overview-item" onclick="showSession(${{i}})">
        <div class="soi-header">
          <span class="soi-title">#${{i+1}} ${{getSessionTitle(sess)}}</span>
          <span class="soi-date">${{sess.start_time_display?.slice(0,10) || ''}}</span>
        </div>
        <div class="soi-meta">
          <span>⏱ ${{sess.duration_minutes}} 分钟</span>
          <span>💬 ${{sess.message_count}} 条消息</span>
          <span>📊 ${{formatTokens(sess.token_usage?.total || 0)}} tokens</span>
          <span>🌿 ${{sess.git_branch}}</span>
        </div>
        ${{toolTags ? `<div class="soi-tools">${{toolTags}}</div>` : ''}}
      </div>
    `;
  }}).join('');

  body.innerHTML = `
    <div class="summary-report">
      <div class="stats-grid">
        <div class="stats-card">
          <div class="stats-value">${{s.total_sessions}}</div>
          <div class="stats-label">会话总数</div>
        </div>
        <div class="stats-card">
          <div class="stats-value">${{s.total_messages}}</div>
          <div class="stats-label">消息总数</div>
        </div>
        <div class="stats-card">
          <div class="stats-value">${{formatTokens(s.token_usage?.total || 0)}}</div>
          <div class="stats-label">Token 用量</div>
        </div>
        <div class="stats-card">
          <div class="stats-value">${{s.total_duration_minutes || 0}}</div>
          <div class="stats-label">总时长(分钟)</div>
        </div>
        <div class="stats-card">
          <div class="stats-value">${{s.date_range?.[0] || '-'}}</div>
          <div class="stats-label">首次会话</div>
        </div>
        <div class="stats-card">
          <div class="stats-value">${{s.date_range?.[1] || '-'}}</div>
          <div class="stats-label">最近会话</div>
        </div>
      </div>

      <div class="summary-section">
        <h3 style="margin-bottom:12px">🔧 工具使用排行</h3>
        ${{toolsHtml}}
      </div>

      <div class="summary-section">
        <h3 style="margin-bottom:12px">📋 会话概览</h3>
        ${{sessionsOverviewHtml}}
      </div>
    </div>
  `;
}}

function showSession(idx) {{
  currentView = 'sessions';
  currentSessionIdx = idx;
  document.querySelectorAll('.nav-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.view === 'sessions');
  }});
  updateSessionListActive();

  const s = SESSIONS[idx];
  document.getElementById('contentTitle').textContent = `#${{idx+1}} ${{getSessionTitle(s)}}`;

  const body = document.getElementById('contentBody');
  const metaHtml = `
    <div style="margin-bottom:16px;padding:12px 16px;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;font-size:12px;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:16px">
      <span>🕐 ${{s.start_time_display}} → ${{s.end_time_display}}</span>
      <span>⏱ ${{s.duration_minutes}} 分钟</span>
      <span>💬 ${{s.message_count}} 条消息</span>
      <span>🌿 ${{s.git_branch}}</span>
      <span>🤖 ${{s.model}}</span>
      <span>📊 ${{formatTokens(s.token_usage?.total || 0)}} tokens</span>
    </div>
  `;

  const msgsHtml = s.messages.map(m => {{
    const roleClass = m.role;
    const roleLabel = m.role === 'user' ? '👤 USER' : m.role === 'assistant' ? '🤖 CLAUDE' : '⚙️ SYSTEM';

    let toolsHtml = '';
    if (m.tools && m.tools.length > 0) {{
      toolsHtml = `<div class="tool-calls">${{
        m.tools.map(t => `
          <div class="tool-call">
            <span class="tool-label">${{t.display}}</span>
            <span class="tool-detail">${{escapeHtml(t.summary)}}</span>
          </div>
        `).join('')
      }}</div>`;
    }}

    return `
      <div class="message ${{roleClass}}">
        <div class="message-header">
          <span class="message-role">${{roleLabel}}</span>
          <span class="message-time">${{m.timestamp_display || ''}}</span>
        </div>
        <div class="message-content">${{renderMarkdown(m.content)}}</div>
        ${{toolsHtml}}
      </div>
    `;
  }}).join('');

  body.innerHTML = `<div class="message-list">${{metaHtml}}${{msgsHtml}}</div>`;
  body.scrollTop = 0;
}}

function updateSessionListActive() {{
  document.querySelectorAll('.session-item').forEach(el => {{
    el.classList.toggle('active', parseInt(el.dataset.idx) === currentSessionIdx);
  }});
}}

// ─── 工具函数 ──────────────────────────────────────────
function formatTokens(n) {{
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toString();
}}

function escapeHtml(str) {{
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

function renderMarkdown(text) {{
  if (!text) return '';
  let html = escapeHtml(text);

  // 代码块
  html = html.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre><code>$2</code></pre>');
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 加粗
  html = html.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
  // 标题
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 style="font-size:16px;margin:16px 0 8px">$1</h2>');
  // 列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^(\\d+)\\. (.+)$/gm, '<li>$2</li>');
  // 段落
  html = html.replace(/\\n\\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  html = html.replace(/<p><\\/p>/g, '');

  return html;
}}

function toggleTheme() {{
  const body = document.body;
  const current = body.getAttribute('data-theme');
  body.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
}}

// ─── 启动 ──────────────────────────────────────────────
init();
</script>
</body>
</html>"""
    return html


# ─── Markdown 导出 ─────────────────────────────────────────────────────


def _session_filename(idx: int, session: dict) -> str:
    """生成会话文件名：{序号:03d}_{日期}_{首条消息摘要}.md"""
    date_part = ""
    start = session.get("start_time_display", "")
    if start:
        date_part = start[:10]  # YYYY-MM-DD

    # 取第一条用户消息作为摘要
    summary = ""
    for msg in session.get("messages", []):
        if msg["role"] == "user":
            text = msg["content"].replace("\n", " ").strip()
            summary = text[:30]
            break

    if not summary:
        summary = session.get("session_id", "unknown")[:8]

    # 清理文件名中的非法字符
    summary = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', summary)
    summary = summary.strip('. ')
    if not summary:
        summary = "session"

    return f"{idx + 1:03d}_{date_part}_{summary}.md"


def _format_session_markdown(idx: int, session: dict) -> str:
    """生成单个会话的 Markdown 内容。"""
    lines: list[str] = []

    # YAML front matter
    lines.append("---")
    lines.append(f"session_id: {session.get('session_id', '')}")
    lines.append(f"start_time: {session.get('start_time_display', '')}")
    lines.append(f"end_time: {session.get('end_time_display', '')}")
    lines.append(f"duration_minutes: {session.get('duration_minutes', 0)}")
    lines.append(f"message_count: {session.get('message_count', 0)}")
    token = session.get("token_usage", {})
    lines.append(f"tokens_input: {token.get('input', 0)}")
    lines.append(f"tokens_output: {token.get('output', 0)}")
    lines.append(f"tokens_total: {token.get('total', 0)}")
    lines.append(f"model: {session.get('model', 'unknown')}")
    lines.append(f"git_branch: {session.get('git_branch', 'unknown')}")

    tools_summary = session.get("tools_summary", {})
    if tools_summary:
        top_tools = sorted(tools_summary.items(), key=lambda x: -x[1])[:5]
        tools_str = ", ".join(f"{name}({count})" for name, count in top_tools)
        lines.append(f"top_tools: {tools_str}")

    lines.append("---")
    lines.append("")

    # 标题
    # 取第一条用户消息作为标题
    title = f"会话 #{idx + 1}"
    for msg in session.get("messages", []):
        if msg["role"] == "user":
            text = msg["content"].replace("\n", " ").strip()
            title_text = text[:60] + ("..." if len(text) > 60 else "")
            title = f"会话 #{idx + 1}: {title_text}"
            break
    lines.append(f"# {title}")
    lines.append("")

    # 消息体
    for msg in session.get("messages", []):
        role = msg["role"]
        ts = msg.get("timestamp_display", "")

        if role == "user":
            lines.append(f"## 👤 User {f'({ts})' if ts else ''}")
        elif role == "assistant":
            lines.append(f"## 🤖 Assistant {f'({ts})' if ts else ''}")
        else:
            lines.append(f"## ⚙️ System {f'({ts})' if ts else ''}")

        lines.append("")
        lines.append(msg.get("content", ""))
        lines.append("")

        # 工具调用
        tools = msg.get("tools", [])
        if tools:
            lines.append("**工具调用：**")
            for t in tools:
                display = t.get("display", t.get("name", ""))
                summary = t.get("summary", "")
                if summary:
                    lines.append(f"- {display}: `{summary}`")
                else:
                    lines.append(f"- {display}")
            lines.append("")

    return "\n".join(lines)


def _format_index_markdown(data: dict) -> str:
    """生成索引文件：统计概览 + 工具排行 + 会话列表。"""
    lines: list[str] = []
    stats = data.get("stats", {})
    sessions = data.get("sessions", [])

    lines.append(f"# Claude Sessions - {data.get('project_name', 'Unknown')}")
    lines.append("")
    lines.append(f"> 导出时间: {data.get('export_time', '')}")
    lines.append(f"> 项目路径: `{data.get('project_path', '')}`")
    lines.append("")

    # 统计概览
    lines.append("## 📊 统计概览")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 会话总数 | {stats.get('total_sessions', 0)} |")
    lines.append(f"| 消息总数 | {stats.get('total_messages', 0)} |")
    lines.append(f"| 用户消息 | {stats.get('total_user_messages', 0)} |")
    lines.append(f"| 助手消息 | {stats.get('total_assistant_messages', 0)} |")
    lines.append(f"| 总时长(分钟) | {stats.get('total_duration_minutes', 0)} |")
    token = stats.get("token_usage", {})
    lines.append(f"| Token 输入 | {token.get('input', 0):,} |")
    lines.append(f"| Token 输出 | {token.get('output', 0):,} |")
    lines.append(f"| Token 合计 | {token.get('total', 0):,} |")
    date_range = stats.get("date_range", [])
    if len(date_range) == 2:
        lines.append(f"| 时间范围 | {date_range[0]} ~ {date_range[1]} |")
    lines.append("")

    # 工具排行
    tools_ranking = stats.get("tools_ranking", [])
    if tools_ranking:
        lines.append("## 🔧 工具使用排行")
        lines.append("")
        lines.append("| 工具 | 次数 |")
        lines.append("|------|------|")
        for name, count in tools_ranking[:15]:
            display = TOOL_DISPLAY.get(name, name)
            lines.append(f"| {display} | {count} |")
        lines.append("")

    # 会话列表
    lines.append("## 📋 会话列表")
    lines.append("")
    lines.append("| # | 日期 | 时长 | 消息数 | Tokens | 文件 |")
    lines.append("|---|------|------|--------|--------|------|")
    for i, s in enumerate(sessions):
        date = s.get("start_time_display", "")[:10]
        dur = s.get("duration_minutes", 0)
        msgs = s.get("message_count", 0)
        tokens = s.get("token_usage", {}).get("total", 0)
        fname = _session_filename(i, s)
        # 取第一条用户消息的前30字
        title = ""
        for msg in s.get("messages", []):
            if msg["role"] == "user":
                title = msg["content"].replace("\n", " ").strip()[:30]
                break
        title = title or s.get("session_id", "")[:8]
        lines.append(f"| {i + 1} | {date} | {dur}min | {msgs} | {tokens:,} | [{fname}]({fname}) |")
    lines.append("")

    return "\n".join(lines)


def export_markdown_sessions(data: dict, output_dir: str) -> str:
    """导出所有会话为 Markdown 文件，返回输出目录路径。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    sessions = data.get("sessions", [])

    # 生成每个会话的 Markdown 文件
    for i, session in enumerate(sessions):
        fname = _session_filename(i, session)
        content = _format_session_markdown(i, session)
        fpath = out / fname
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)

    # 生成索引文件
    index_content = _format_index_markdown(data)
    with open(out / "index.md", "w", encoding="utf-8") as f:
        f.write(index_content)

    return str(out)


def print_export_summary(data: dict, md_dir: str | None = None, html_path: str | None = None):
    """通过 stderr 输出结果摘要（Claude 唯一能看到的输出）。"""
    stats = data.get("stats", {})
    project_name = data.get("project_name", "Unknown")
    total_sessions = stats.get("total_sessions", 0)
    total_messages = stats.get("total_messages", 0)
    token_total = stats.get("token_usage", {}).get("total", 0)
    date_range = stats.get("date_range", [])

    lines = [
        f"✅ 导出完成: {project_name}",
        f"   会话数: {total_sessions}",
        f"   消息数: {total_messages}",
        f"   Token: {token_total:,}",
    ]
    if len(date_range) == 2:
        lines.append(f"   时间范围: {date_range[0]} ~ {date_range[1]}")
    if md_dir:
        lines.append(f"   Markdown: {md_dir}/")
    if html_path:
        lines.append(f"   HTML: {html_path}")

    print("\n".join(lines), file=sys.stderr)


def generate_and_write_html(data: dict, output_path: str):
    """封装 generate_html() + 文件写入。"""
    html = generate_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ─── 主入口 ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Claude Code 会话解析与导出")
    parser.add_argument(
        "--project-path", "-p",
        required=True,
        help="项目绝对路径",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="生成 HTML 报告文件",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="导出 Markdown 会话文件 + HTML 报告",
    )
    parser.add_argument(
        "--export-md",
        action="store_true",
        help="仅导出 Markdown 会话文件",
    )
    parser.add_argument(
        "--output", "-o",
        default="",
        help="输出文件路径（仅 --html 模式）",
    )
    parser.add_argument(
        "--output-dir", "-d",
        default="",
        help="输出目录路径（--export / --export-md 模式，默认为 <项目路径>/claude-sessions/）",
    )
    args = parser.parse_args()

    # 解析项目
    data = parse_project(args.project_path)

    if "error" in data:
        print(f"错误: {data['error']}", file=sys.stderr)
        sys.exit(1)

    # 确定输出目录
    output_dir = args.output_dir or os.path.join(args.project_path, "claude-sessions")

    if args.export:
        # 导出 Markdown + HTML
        md_dir = export_markdown_sessions(data, output_dir)
        html_path = os.path.join(output_dir, "report.html")
        generate_and_write_html(data, html_path)
        print_export_summary(data, md_dir=md_dir, html_path=html_path)

    elif args.export_md:
        # 仅导出 Markdown
        md_dir = export_markdown_sessions(data, output_dir)
        print_export_summary(data, md_dir=md_dir)

    elif args.html:
        # 仅生成 HTML
        output_path = args.output
        if not output_path:
            output_path = os.path.join(
                args.project_path,
                "claude-session-report.html"
            )
        generate_and_write_html(data, output_path)
        print_export_summary(data, html_path=output_path)

    else:
        # JSON 模式（默认）
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
