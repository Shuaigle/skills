# Skills

9 個 agent skills。取自 [mattpocock/skills](https://github.com/mattpocock/skills)，融入 [shadcn/improve](https://github.com/shadcn/improve) 的計畫紀律：grill 系列四合一，spec/ticket 落地為本地檔案（`.scratch/`），要求自足、可跑的驗證準則、STOP 條件與 drift check。

每個 skill 附 `SKILL.md`（Agent Skills 標準）與 `agents/openai.yaml`（Codex metadata），Claude Code 與 Codex 裝完即用。

## 安裝

Claude Code / Codex / 其他相容 harness：

```bash
npx skills@latest add Shuaigle/skills
```

Claude Code plugin（自動更新）：

```
/plugin marketplace add Shuaigle/skills
/plugin install shuaigle@shuaigle
```

開發模式（symlink 進 `~/.claude/skills` 與 `~/.agents/skills`，`git pull` 即更新）：

```bash
git clone https://github.com/Shuaigle/skills.git
cd skills && ./scripts/link-skills.sh
```

呼叫語法：plugin 裝法要帶 namespace（`/shuaigle:grill`）；skills.sh 或 symlink 裝法用裸名（`/grill`）；Codex 用 `$grill`，或由 description 自動觸發。

依賴說明：`implement` 收尾與 `diagnosing-bugs` 的交棒會用環境裡既有的 code-review／audit skill，沒有就以自我審查、文字報告代替。spec 與 tickets 都是本地檔案，無外部服務依賴。

## Skills

| Skill | 觸發 | 用途 |
|---|---|---|
| [grill](./skills/grill/SKILL.md) | model | 連環拷問把計畫問到定案；`grill docs` 同時維護 CONTEXT.md 與 ADR |
| [to-spec](./skills/to-spec/SKILL.md) | user | 把目前對話收斂成自足的 spec，寫入 `.scratch/<feature>/spec.md` |
| [to-tickets](./skills/to-tickets/SKILL.md) | user | 拆成 tracer-bullet ticket 檔：自足、可跑的驗證準則、STOP 條件、blocking 關係 |
| [implement](./skills/implement/SKILL.md) | user | 照 spec/tickets 實作：drift check、`tdd`、跑指令驗收、review、commit |
| [to-docs](./skills/to-docs/SKILL.md) | user | 實作 commit 後沉澱：夠格的決策進 CONTEXT.md／ADR，脫鉤的記錄提議刪除，文檔獨立 commit |
| [tdd](./skills/tdd/SKILL.md) | model | 紅綠循環；seam 先議定，只測外部行為 |
| [diagnosing-bugs](./skills/diagnosing-bugs/SKILL.md) | model | 先建 tight feedback loop 再查因的除錯紀律 |
| [codebase-design](./skills/codebase-design/SKILL.md) | model | Deep module 詞彙與原則：小介面、大實作、清楚的 seam |
| [handoff](./skills/handoff/SKILL.md) | user | 把對話壓縮成交接文檔給下一個 agent |

觸發欄：user = 打名字才會動；model = agent 自行判斷時機，也可手動。

典型流程：`grill docs` 對齊 → `to-spec` 出規格 → `to-tickets` 拆票 → `implement` 實作（內部走 `tdd`）→ `to-docs` 沉澱 → 卡住用 `diagnosing-bugs`。

`.scratch/` 的 spec 與 ticket 是施工架，用完即丟；只有 `CONTEXT.md`、`docs/adr/` 與測試會留下。`to-docs` 決定哪些留、哪些刪，也可以單獨叫起來修剪已經跟程式碼脫鉤的舊記錄。

## 出處與授權

skills 源自 [mattpocock/skills](https://github.com/mattpocock/skills)（MIT，[全文](./LICENSES/mattpocock-skills-LICENSE.txt)），結構手法參考 [shadcn/improve](https://github.com/shadcn/improve)（MIT，[全文](./LICENSES/shadcn-improve-LICENSE.md)）。本 repo 的改動以 [MIT](./LICENSE) 釋出。
