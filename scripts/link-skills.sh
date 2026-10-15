#!/usr/bin/env bash
set -euo pipefail

# 將 skills/*/ symlink 進本機 harness 的 skill 目錄：
#   - ~/.claude/skills  — Claude Code
#   - ~/.agents/skills  — Codex 等 Agent Skills 相容 harness
# `git pull` 後重跑即同步。行為：
#   - 已安裝 shuaigle plugin 時略過對應 harness；查詢失敗也略過，避免重複載入
#   - 沒有對應 CLI 時沿用連結；CLI 查詢使用 Python 3 解析 JSON
#   - 只認 skills/*/SKILL.md（不撈更深層的巢狀檔案）
#   - 先清掉「指向本 repo 但 skill 已刪除/改名」的 stale symlink
#   - 指向其他來源的同名 symlink：跳過並警告，不覆蓋
#   - 同名實體目錄：跳過並警告，不搬動（要切換請自行備份移除後重跑）

REPO="$(cd "$(dirname "$0")/.." && pwd)"

harness_links_needed() {
  local cli="$1" harness="$2" plugin_list plugin_state
  command -v "$cli" >/dev/null 2>&1 || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "warning: 找不到 Python 3，無法確認 shuaigle plugin；略過 $harness skills。" >&2
    return 1
  fi
  if ! plugin_list="$("$cli" plugin list --json 2>/dev/null)"; then
    echo "warning: 無法查詢已安裝的 $harness plugins；略過 $harness skills。" >&2
    return 1
  fi
  if ! plugin_state="$(printf '%s' "$plugin_list" | python3 -c '
import json, sys
registry = json.load(sys.stdin)
if sys.argv[1] == "codex":
    if not isinstance(registry, dict) or not isinstance(registry.get("installed"), list):
        raise ValueError("invalid installed plugin registry")
    plugins = registry["installed"]
    id_key = "pluginId"
    if any(not isinstance(plugin, dict) or not isinstance(plugin.get("installed"), bool) for plugin in plugins):
        raise ValueError("invalid installed plugin record")
else:
    plugins = registry
    id_key = "id"
if not isinstance(plugins, list) or any(
    not isinstance(plugin, dict)
    or not isinstance(plugin.get(id_key), str)
    or not plugin[id_key]
    for plugin in plugins
):
    raise ValueError("invalid installed plugin list")
print("installed" if any(
    plugin[id_key].startswith("shuaigle@") and (sys.argv[1] != "codex" or plugin["installed"])
    for plugin in plugins
) else "absent")
' "$cli" 2>/dev/null)"; then
    echo "warning: $harness plugin 清單不是可辨識的 JSON；略過 $harness skills。" >&2
    return 1
  fi
  if [ "$plugin_state" = installed ]; then
    echo "skip    $harness skills（已安裝 shuaigle plugin，保留既有連結）"
    return 1
  fi
  return 0
}

DESTS=()
if harness_links_needed claude Claude; then
  DESTS+=("$HOME/.claude/skills")
fi
if harness_links_needed codex Codex; then
  DESTS+=("$HOME/.agents/skills")
fi

names=()
srcs=()
while IFS= read -r -d '' skill_md; do
  src="$(dirname "$skill_md")"
  names+=("$(basename "$src")")
  srcs+=("$src")
done < <(find "$REPO/skills" -mindepth 2 -maxdepth 2 -name SKILL.md -print0)

if [ "${#names[@]}" -eq 0 ]; then
  echo "error: 找不到任何 skills/*/SKILL.md" >&2
  exit 1
fi

# Bash 3.2 在 nounset 下不能展開空陣列。
if [ "${#DESTS[@]}" -eq 0 ]; then
  exit 0
fi

in_current_set() {
  local x="$1" i
  for i in "${names[@]}"; do
    [ "$i" = "$x" ] && return 0
  done
  return 1
}

for DEST in "${DESTS[@]}"; do
  # 若 $DEST 本身是指回本 repo 的 symlink，寫入會污染 repo，先擋下。
  if [ -L "$DEST" ]; then
    resolved="$(readlink -f "$DEST" 2>/dev/null || true)"
    if [ -z "$resolved" ]; then
      echo "error: 無法解析 symlink ${DEST}，先手動處理再重跑。" >&2
      exit 1
    fi
    case "$resolved" in
      "$REPO"|"$REPO"/*)
        echo "error: $DEST 指向本 repo（${resolved}），先移除（rm \"$DEST\"）再重跑。" >&2
        exit 1
        ;;
    esac
  fi

  mkdir -p "$DEST"

  # 清 stale：指向本 repo、但已不在現行 skill 清單的 symlink
  for link in "$DEST"/*; do
    [ -L "$link" ] || continue
    case "$(readlink "$link")" in
      "$REPO/skills/"*)
        in_current_set "$(basename "$link")" || { rm "$link"; echo "pruned  $link"; }
        ;;
    esac
  done

  for i in "${!names[@]}"; do
    name="${names[$i]}"
    src="${srcs[$i]}"
    target="$DEST/$name"

    if [ -L "$target" ]; then
      case "$(readlink "$target")" in
        "$REPO/skills/"*) ;;  # 本 repo 的既有連結，直接更新
        *)
          echo "skip    ${name}（$target 指向其他來源，不覆蓋；要換成本 repo 版本請先手動移除）" >&2
          continue
          ;;
      esac
    elif [ -e "$target" ]; then
      echo "skip    ${name}（$target 是既有實體目錄，不動它；要改用本 repo 版本請自行備份移除後重跑）" >&2
      continue
    fi

    ln -sfn "$src" "$target"
    echo "linked  $name -> $src ($DEST)"
  done
done
