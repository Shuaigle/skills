#!/usr/bin/env bash
set -euo pipefail

# 將 skills/*/ symlink 進本機 harness 的 skill 目錄：
#   - ~/.claude/skills  — Claude Code
#   - ~/.agents/skills  — Codex 等 Agent Skills 相容 harness
# `git pull` 後重跑即同步。行為：
#   - 只認 skills/*/SKILL.md（不撈更深層的巢狀檔案）
#   - 先清掉「指向本 repo 但 skill 已刪除/改名」的 stale symlink
#   - 指向其他來源的同名 symlink：跳過並警告，不覆蓋
#   - 同名實體目錄：備份成 <名稱>.bak.<時間戳> 再連結

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DESTS=("$HOME/.claude/skills" "$HOME/.agents/skills")

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
      echo "error: 無法解析 symlink $DEST，先手動處理再重跑。" >&2
      exit 1
    fi
    case "$resolved" in
      "$REPO"|"$REPO"/*)
        echo "error: $DEST 指向本 repo（$resolved），先移除（rm \"$DEST\"）再重跑。" >&2
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
          echo "skip    $name（$target 指向其他來源，不覆蓋；要換成本 repo 版本請先手動移除）" >&2
          continue
          ;;
      esac
    elif [ -e "$target" ]; then
      backup="$target.bak.$(date +%Y%m%d%H%M%S)"
      mv "$target" "$backup"
      echo "backup  $target -> $backup"
    fi

    ln -sfn "$src" "$target"
    echo "linked  $name -> $src ($DEST)"
  done
done
