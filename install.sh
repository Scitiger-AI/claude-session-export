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

# ─── cleanupPeriodDays 配置 ──────────────────────────────────────────────

configure_cleanup_period() {
    echo ""
    info "检查 cleanupPeriodDays 配置..."
    info "（该设置控制 Claude Code 会话记录保留天数，默认 30 天会自动清理）"
    echo ""

    # 收集所有 settings 文件
    local files=()
    local labels=()
    local statuses=()   # "ok" | "missing" | "low"
    local current_values=()

    for f in "${CLAUDE_DIR}"/settings*.json; do
        [[ -f "$f" ]] || continue
        files+=("$f")

        # 提取文件显示名
        local basename
        basename="$(basename "$f")"
        labels+=("$basename")

        # 用 python3 读取当前值和提供者信息
        local result
        result="$(python3 -c "
import json, sys
try:
    with open('$f') as fh:
        data = json.load(fh)
    val = data.get('cleanupPeriodDays', None)
    # 提取提供者标签
    env = data.get('env', {})
    base_url = env.get('ANTHROPIC_BASE_URL', env.get('CLAUDE_CODE_USE_BEDROCK', ''))
    model = env.get('ANTHROPIC_MODEL', '')
    desc_parts = []
    if 'duckcoding' in base_url: desc_parts.append('DuckCoding')
    elif 'dashscope' in base_url: desc_parts.append('阿里云')
    elif 'openclaudecode' in base_url: desc_parts.append('OpenClaudeCode')
    elif 'bytecat' in base_url: desc_parts.append('ByteCat')
    elif base_url: desc_parts.append(base_url.split('//')[1].split('/')[0] if '//' in base_url else base_url[:30])
    if model: desc_parts.append(model)
    desc = ' - '.join(desc_parts) if desc_parts else 'Claude Default'
    print(f'{val}|||{desc}')
except Exception as e:
    print(f'error|||{e}')
" 2>/dev/null)"

        local val="${result%%|||*}"
        local desc="${result##*|||}"

        if [[ "$val" == "None" ]]; then
            statuses+=("missing")
            current_values+=("")
            labels[${#labels[@]}-1]="${basename}  (${desc})  ⚠️  未配置"
        elif [[ "$val" -ge 365 ]] 2>/dev/null; then
            statuses+=("ok")
            current_values+=("$val")
            labels[${#labels[@]}-1]="${basename}  (${desc})  ✅ ${val}天"
        else
            statuses+=("low")
            current_values+=("$val")
            labels[${#labels[@]}-1]="${basename}  (${desc})  ⚠️  仅${val}天"
        fi
    done

    # 没有 settings 文件
    if [[ ${#files[@]} -eq 0 ]]; then
        warn "未检测到 ~/.claude/settings*.json 文件，跳过配置。"
        return
    fi

    # 检查是否全部已配置
    local need_config=0
    for s in "${statuses[@]}"; do
        [[ "$s" != "ok" ]] && need_config=1 && break
    done

    if [[ $need_config -eq 0 ]]; then
        ok "所有配置文件的 cleanupPeriodDays 均已设置（≥365天），无需修改。"
        return
    fi

    # 显示文件列表
    echo -e "  📋 检测到以下 Claude Code 配置文件：\n"
    for i in "${!labels[@]}"; do
        local num=$((i + 1))
        echo -e "    ${BLUE}${num})${NC} ${labels[$i]}"
    done
    echo ""
    echo -e "    ${BLUE}a)${NC} 全部选择"
    echo -e "    ${BLUE}n)${NC} 跳过，不配置"
    echo ""
    echo -e "  ${YELLOW}⚙️  为防止会话记录被自动清理（默认30天），建议设置 cleanupPeriodDays=9999${NC}"
    echo -n "  请选择要配置的文件 [a/1-${#files[@]}/逗号分隔/n跳过]: "
    read -r choice

    # 解析用户选择
    local selected=()
    case "$choice" in
        n|N|"")
            info "跳过 cleanupPeriodDays 配置。"
            return
            ;;
        a|A)
            for i in "${!files[@]}"; do
                [[ "${statuses[$i]}" != "ok" ]] && selected+=("$i")
            done
            ;;
        *)
            # 解析逗号分隔的数字
            IFS=',' read -ra nums <<< "$choice"
            for num in "${nums[@]}"; do
                num="$(echo "$num" | tr -d ' ')"
                if [[ "$num" =~ ^[0-9]+$ ]] && [[ "$num" -ge 1 ]] && [[ "$num" -le ${#files[@]} ]]; then
                    local idx=$((num - 1))
                    if [[ "${statuses[$idx]}" == "ok" ]]; then
                        info "$(basename "${files[$idx]}") 已配置（${current_values[$idx]}天），跳过。"
                    else
                        selected+=("$idx")
                    fi
                else
                    warn "无效选项: $num，跳过。"
                fi
            done
            ;;
    esac

    if [[ ${#selected[@]} -eq 0 ]]; then
        info "没有需要修改的文件。"
        return
    fi

    # 执行修改
    echo ""
    for idx in "${selected[@]}"; do
        local f="${files[$idx]}"
        local basename
        basename="$(basename "$f")"

        python3 -c "
import json
with open('$f', 'r') as fh:
    data = json.load(fh)
data['cleanupPeriodDays'] = 9999
with open('$f', 'w') as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write('\n')
" 2>/dev/null

        if [[ $? -eq 0 ]]; then
            ok "${basename}: cleanupPeriodDays = 9999 ✅"
        else
            error "${basename}: 修改失败"
        fi
    done

    echo ""
    ok "配置完成！会话记录将长期保留（约 27 年）。"
}

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

    # 配置 cleanupPeriodDays
    configure_cleanup_period

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
