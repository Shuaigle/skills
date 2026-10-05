# Skills

12 個 agent skills。取自 [mattpocock/skills](https://github.com/mattpocock/skills)，融入 [shadcn/improve](https://github.com/shadcn/improve) 的計畫紀律：grill 系列四合一，spec/ticket 落地為本地檔案（`.scratch/`），要求自足、可跑的驗證準則、STOP 條件與 drift check（先確認計畫仍符合程式碼）。

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
| [grill](./skills/grill/SKILL.md) | model | 追蹤決策前提與未決事項，優先用選項 UI 一次問一題；`grill docs` 同時維護詞彙與決策記錄（預設 CONTEXT.md 與 docs/adr/） |
| [prototype-logic](./skills/prototype-logic/SKILL.md) | model | 用可操作的單檔 HTML 驗證一個邏輯或狀態模型問題，支援自由操作、重設與情境演練 |
| [to-spec](./skills/to-spec/SKILL.md) | user | 把目前對話收斂成自足的 spec，寫入 `.scratch/<feature>/spec.md` |
| [to-tickets](./skills/to-tickets/SKILL.md) | user | 把 spec 純轉譯成 tracer-bullet tickets（可工作的縱切）：自足、可跑的驗證準則、STOP 條件、blocking 關係 |
| [implement](./skills/implement/SKILL.md) | user | 照 spec/tickets 實作：drift check、`tdd`、跑指令驗收、需求與規範雙軸審查、授權後 commit |
| [to-docs](./skills/to-docs/SKILL.md) | user | 實作 commit 後沉澱：詞彙與夠格的決策寫進 repo 既有文檔，逐項提議處理脫鉤記錄，文檔獨立 commit |
| [retro](./skills/retro/SKILL.md) | user | 從 session 的實際摩擦提出 agent 環境改善；機械錯誤優先變成自動檢查，判斷問題才補規範 |
| [tdd](./skills/tdd/SKILL.md) | model | 紅綠循環；seam（模組介面所在、測試穿過的位置）先議定，只測外部行為 |
| [diagnosing-bugs](./skills/diagnosing-bugs/SKILL.md) | model | 先建 tight feedback loop（可快速重現的明確紅綠訊號），再查原因 |
| [codebase-design](./skills/codebase-design/SKILL.md) | model | Deep module 詞彙與原則：小介面隱藏大量行為，並選定清楚的 seam |
| [handoff](./skills/handoff/SKILL.md) | user | 把對話壓縮成交接文檔給下一個 agent |
| [writing-great-skills](./skills/writing-great-skills/SKILL.md) | user | 寫與改 skill 的參考：invocation 取捨、資訊層級、環境真相、剪枝、leading words、失效模式 |

觸發欄：user = 打名字才會動；model = agent 自行判斷時機，也可手動。

典型流程：`grill docs` 對齊 → `to-spec` 出規格 → `to-tickets` 拆票 → `implement` 實作（內部走 `tdd`）→ `to-docs` 沉澱 → 卡住用 `diagnosing-bugs`。

討論中需要可執行證據時，用 `prototype-logic` 驗證一個問題，再回到 grill 或 spec。原型是暫存施工架，模擬通過不代表 production 已驗證。工作中反覆卡住或出錯後，可用 `retro` 回顧環境；它只提建議，不直接套用。

`.scratch/` 的 spec 與 ticket 是施工架，用完即丟；長期留下的是詞彙記錄、決策記錄與測試。前兩者預設落在 `CONTEXT.md` 與 `docs/adr/`，repo 已有自己的文檔系統就寫進既有位置，不另開一套。測試由 `tdd` 產出、測試套件把關；`to-docs` 只管前兩者，逐項提議哪些留、哪些改、哪些刪，也可以單獨叫起來修剪已經跟程式碼脫鉤的舊記錄。

## 出處與授權

skills 源自 [mattpocock/skills](https://github.com/mattpocock/skills)（MIT，[全文](./LICENSES/mattpocock-skills-LICENSE.txt)），結構手法參考 [shadcn/improve](https://github.com/shadcn/improve)（MIT，[全文](./LICENSES/shadcn-improve-LICENSE.md)）。本 repo 的改動以 [MIT](./LICENSE) 釋出。
