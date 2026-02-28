#!/usr/bin/env bash
# Claude Session Export - 安装脚本
# 将 Skill 文件安装到 ~/.claude/ 目录

set -euo pipefail

# ─── 常量 ─────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
COMMANDS_DIR="${CLAUDE_DIR}/commands"
SCRIPTS_DIR="${CLAUDE_DIR}/scripts/session-export"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── 工具函数 ─────────────────────────────────────────────────────────────

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─── 安装 ─────────────────────────────────────────────────────────────────

install() {
    info "开始安装 Claude Session Export..."
    echo ""

    # 检查 ~/.claude 是否存在
    if [[ ! -d "${CLAUDE_DIR}" ]]; then
        error "未找到 ~/.claude 目录。请确认已安装 Claude Code。"
        exit 1
    fi

    # 检查 Python3
    if ! command -v python3 &>/dev/null; then
        error "未找到 python3。请先安装 Python 3.8+。"
        exit 1
    fi

    # 创建目标目录
    mkdir -p "${COMMANDS_DIR}"
    mkdir -p "${SCRIPTS_DIR}"

    # 安装 Skill 命令文件
    local src_cmd="${SCRIPT_DIR}/commands/session-export.md"
    local dst_cmd="${COMMANDS_DIR}/session-export.md"

    if [[ -f "${dst_cmd}" ]]; then
        if [[ -L "${dst_cmd}" ]]; then
            info "移除已有符号链接: ${dst_cmd}"
            rm "${dst_cmd}"
        else
            warn "已存在 ${dst_cmd}，备份为 ${dst_cmd}.bak"
            mv "${dst_cmd}" "${dst_cmd}.bak"
        fi
    fi
    ln -s "${src_cmd}" "${dst_cmd}"
    ok "Skill 命令: ${dst_cmd} -> ${src_cmd}"

    # 安装 Python 脚本
    local src_py="${SCRIPT_DIR}/scripts/session-export/parse_sessions.py"
    local dst_py="${SCRIPTS_DIR}/parse_sessions.py"

    if [[ -f "${dst_py}" ]]; then
        if [[ -L "${dst_py}" ]]; then
            info "移除已有符号链接: ${dst_py}"
            rm "${dst_py}"
        else
            warn "已存在 ${dst_py}，备份为 ${dst_py}.bak"
            mv "${dst_py}" "${dst_py}.bak"
        fi
    fi
    ln -s "${src_py}" "${dst_py}"
    ok "解析脚本: ${dst_py} -> ${src_py}"

    echo ""
    ok "安装完成！"
    echo ""
    info "使用方法："
    echo "  在 Claude Code 中执行: /session-export [项目路径]"
    echo "  不指定路径时，将导出当前工作目录的会话记录。"
    echo ""
    info "卸载方法："
    echo "  bash ${SCRIPT_DIR}/install.sh --uninstall"
}

# ─── 卸载 ─────────────────────────────────────────────────────────────────

uninstall() {
    info "开始卸载 Claude Session Export..."
    echo ""

    local cmd_file="${COMMANDS_DIR}/session-export.md"
    local py_file="${SCRIPTS_DIR}/parse_sessions.py"

    # 移除 Skill 命令
    if [[ -L "${cmd_file}" ]]; then
        rm "${cmd_file}"
        ok "已移除符号链接: ${cmd_file}"
    elif [[ -f "${cmd_file}" ]]; then
        warn "${cmd_file} 不是符号链接，跳过（请手动删除）"
    else
        info "未找到 ${cmd_file}，跳过"
    fi

    # 移除 Python 脚本
    if [[ -L "${py_file}" ]]; then
        rm "${py_file}"
        ok "已移除符号链接: ${py_file}"
    elif [[ -f "${py_file}" ]]; then
        warn "${py_file} 不是符号链接，跳过（请手动删除）"
    else
        info "未找到 ${py_file}，跳过"
    fi

    # 尝试移除空目录
    if [[ -d "${SCRIPTS_DIR}" ]] && [[ -z "$(ls -A "${SCRIPTS_DIR}")" ]]; then
        rmdir "${SCRIPTS_DIR}"
        info "已移除空目录: ${SCRIPTS_DIR}"
    fi

    # 恢复备份
    if [[ -f "${cmd_file}.bak" ]]; then
        mv "${cmd_file}.bak" "${cmd_file}"
        info "已恢复备份: ${cmd_file}"
    fi
    if [[ -f "${py_file}.bak" ]]; then
        mv "${py_file}.bak" "${py_file}"
        info "已恢复备份: ${py_file}"
    fi

    echo ""
    ok "卸载完成！"
}

# ─── 主入口 ───────────────────────────────────────────────────────────────

case "${1:-}" in
    --uninstall|-u)
        uninstall
        ;;
    --help|-h)
        echo "Claude Session Export 安装脚本"
        echo ""
        echo "用法:"
        echo "  bash install.sh            安装 Skill（符号链接方式）"
        echo "  bash install.sh --uninstall 卸载 Skill"
        echo "  bash install.sh --help      显示帮助"
        ;;
    *)
        install
        ;;
esac
