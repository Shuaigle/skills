# Skills

14 個 agent skills。取自 [mattpocock/skills](https://github.com/mattpocock/skills)，融入 [shadcn/improve](https://github.com/shadcn/improve) 的計畫紀律：grill 系列四合一，spec/ticket 落地為本地檔案（`.scratch/`），要求自足、可跑的驗證準則、STOP 條件與 drift check（先確認計畫仍符合程式碼）。

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

Codex plugin（含 Jev hooks；從本 repo 安裝）：

```bash
codex plugin marketplace add ./
codex plugin add shuaigle@shuaigle
```

這組指令已確認 Codex CLI `0.162.1` 支援。安裝後在 `/hooks` 檢查定義，由使用者批准 hook trust，再手動啟用 Jev。symlink／skills.sh 只安裝 skill；Codex plugin 的 hooks 見 [Codex 路由](./skills/jev/references/codex-native.md)。

開發模式（symlink，`git pull` 即更新）：

```bash
git clone https://github.com/Shuaigle/skills.git
cd skills && ./scripts/link-skills.sh
```

腳本分別查詢 Claude Code 與 Codex 的 plugin 安裝狀態；已安裝 shuaigle plugin 時，跳過該宿主的 skill 連結，避免重複載入。未安裝時同步 `~/.claude/skills` 或 `~/.agents/skills`；既有連結不會因此自動刪除。

呼叫語法：plugin 裝法要帶 namespace（`/shuaigle:grill`）；skills.sh 或 symlink 裝法用裸名（`/grill`）；Codex 用 `$grill`，或由 description 自動觸發。

依賴說明：`diagnosing-bugs` 的架構交棒會用環境裡既有的 audit skill（如 `improve`），沒有就以文字報告代替。`review` 預設開 fresh-context subagent 審，harness 不支援時自己審，並在報告開頭的來源行註明。spec 與 tickets 都是本地檔案。`jev` 需要 Python 3、網路與環境變數 `JEV_API_KEY`，呼叫 TypeSafe API。Claude Code 原生 subagent 模型路由需要 `2.1.287+`，effort 路由在 `2.1.302` 驗證過，並以 plugin 方式載入本 repo 的 mod；symlink／skills.sh 只安裝 skill，不會載入 mod。開發時可用 `claude --plugin-dir .`。

## Skills

| Skill | 觸發 | 用途 |
|---|---|---|
| [grill](./skills/grill/SKILL.md) | model | 聚焦本次交付、正確性與已知限制的必要決策，優先用選項 UI 一次問一題；`grill docs` 同時維護詞彙與決策記錄（預設 CONTEXT.md 與 docs/adr/） |
| [prototype-logic](./skills/prototype-logic/SKILL.md) | model | 用可操作的單檔 HTML 驗證一個邏輯或狀態模型問題，支援自由操作、重設與情境演練 |
| [to-spec](./skills/to-spec/SKILL.md) | user | 把已確認需求收斂成自足、可驗收的 spec，寫入 `.scratch/<feature>/spec.md` |
| [to-tickets](./skills/to-tickets/SKILL.md) | user | 把 spec 純轉譯成 tracer-bullet tickets（可工作的縱切）：自足、可跑的驗證準則、STOP 條件、blocking 關係；前置重構須有具體阻擋證據 |
| [implement](./skills/implement/SKILL.md) | user | 照 spec/tickets 實作：drift check、`tdd`、跑指令驗收、授權後 commit；不自審，收尾指向 `review` |
| [review](./skills/review/SKILL.md) | user | 在沒寫過這段 code 的 session 三軸審 diff（含未 commit 與 untracked）：Spec、Correctness、Standards 分開報告；作者的設計文件只當待驗證的說法；逐條開檔驗證，外部 review 意見也走同一套 |
| [to-docs](./skills/to-docs/SKILL.md) | user | 實作 commit 後沉澱：詞彙與夠格的決策寫進 repo 既有文檔，逐項提議處理脫鉤記錄，文檔獨立 commit |
| [retro](./skills/retro/SKILL.md) | user | 從 session 的實際摩擦提出 agent 環境改善；機械錯誤優先變成自動檢查，判斷問題才補規範 |
| [tdd](./skills/tdd/SKILL.md) | model | 紅綠循環；seam（模組介面所在、測試穿過的位置）先議定，只測外部行為 |
| [diagnosing-bugs](./skills/diagnosing-bugs/SKILL.md) | model | 先建 tight feedback loop（可快速重現的明確紅綠訊號），再查原因 |
| [codebase-design](./skills/codebase-design/SKILL.md) | model | 從直接方案出發，新增機制須有當前需求或限制的依據；Deep module 詞彙、小介面與 seam 原則 |
| [handoff](./skills/handoff/SKILL.md) | user | 把對話壓縮成交接文檔給下一個 agent |
| [writing-great-skills](./skills/writing-great-skills/SKILL.md) | user | 寫與改 skill 的參考：invocation 取捨、資訊層級、環境真相、剪枝、leading words、失效模式 |
| [jev](./skills/jev/SKILL.md) | user | 使用者啟用後選零到多個 skills 與 subagent 模型／effort 組合，每個獨立子任務只問一次；Claude native 支援在本對話手動排除模型，未知額度仍可路由 |

觸發欄：user = 打名字才會動；model = agent 自行判斷時機，也可手動。

`jev` 只能由使用者明確呼叫或啟用；啟用的決策會在目前對話自動執行。兩個獨立選項：`skill` 可不選或選一到多個可自動呼叫的 skills，`subagent` 在預定派工前一起決定該子任務的模型與 effort。Effort 屬於 `subagent`，不新增開關。`jev on` 與 `jev on all` 都開啟兩項；`jev on subagent` 累加該項，`jev off skill` 只關閉 skill 決策，`jev off` 全關，`jev status` 列出兩項狀態。新對話預設全關。Claude Code plugin 用 `/shuaigle:jev on`，裸 skill 用 `/jev on`，Codex skill 用 `$jev on`；Codex hooks 建議用人類訊息第一行的 `jev on`。主對話沿用原本模型。

每個獨立子任務把啟用的決策合併問一次，後續讀檔與追問重用結果；例如十個相關檔案的讀取與摘要算一個子任務。目標、候選或偏好改變時建立新子任務。subagent 使用自己的摘要與 spawn 工具支援的模型／effort 組合，以一個原子選項一起決定；具體 effort 只列已驗證的組合。Null 表示 effort 由宿主控制，也可用於 Claude 缺 effort 能力清單時明示的 model-only fallback，保留模型與 skill 決策；同一模型不能混列 null 和具體 effort。只傳摘要與去除私人資訊的候選描述。使用者指定的模型、effort、skill，以及手動限定 skill 的政策優先；已指定 effort 卻缺逐模型能力證據時，保留該 effort 與原本子模型，回報限制。開啟 subagent 決策不會額外建立 agent。批次讀檔適合以精簡上下文交給 Jev 選出的子模型，短讀取可直接留在主對話。

Codex hooks 在涵蓋的工具路徑上要求先取得子任務決策，路由前依宿主的逐模型能力清單驗證候選組合，再把已準備的 spawn 改為 Jev 選出的模型與 `reasoning_effort`；null 會清除舊 effort 欄位。快取保留目前對話的旗標、雜湊與最小決策，不保存金鑰、原始任務或 child brief；路由失敗也會重用該次 fallback。resume／compact 保留狀態，新的、fork 或 clear 對話重設全關。hooks 無法辨識所有語意上的任務邊界，特殊工具是否涵蓋取決於宿主，需在實際宿主確認。

Claude 原生 mod 載入後，只有 `subagent` 開啟時由 mod 在預定 spawn 前詢問 Jev，依該次 spawn 的識別重用成功或失敗決策；候選是每個可用模型各配 `low`／`medium`／`high`／`xhigh`／`max`；mod 在 `agent.spawn` 套用模型，再以 `turn.step` 改寫該子 agent 每次 model request 的 effort。宿主遇到模型不支援的 effort 會靜默降級或不送，hook 看不到結果，所以 status 回報推薦與實際子模型、requested effort，actual effort 標為 unverified。主 agent 在 Agent tool 明確傳 effort、設了 `CLAUDE_CODE_EFFORT_LEVEL`，或 spawn 沒有穩定 ID 時，mod 不改寫 effort。

工具 enum、模型選單與組織 allowlist 不代表剩餘 credits；未知額度仍可路由。Claude native 的排除清單只由人輸入 `/jev exclude <models...>`、`/jev include <models...>` 改動，不需 API key，也不改啟用旗標。額度錯誤不會自動排除模型；使用者可在失敗後 exclude、恢復後 include。Include 只解除本地排除，不驗證額度。已知模型家族的 alias 與版本 ID 共用排除範圍，排除其中一個會排除整個家族。

`subagent` 開啟時，Claude native 過濾新子任務候選並在派工前重查準備及快取選擇；resume、fork、workflow 沿用宿主行為，不受這項 guard 保護。關閉時暫停檢查但保留清單，新 session／module 重載／結束時重設。它不會自行換成另一模型或重播失敗工作。排除變更後保留已選 skills 與 brief，以新 routing unit／revision 交 Jev 選更新後的候選，避免重播可能已有副作用的工作。Codex gate 不提供這兩個原生命令或額度檢查。

Claude 內建 Agent 工具在 `2.1.292+` 支援非 fork 的逐次 effort。兩項全開時，agent 對 child unit 一次批次詢問 skill＋模型／effort 選項；有可信矩陣時精確套用 Jev 選出的 `Agent.model`／`Agent.effort`，skills 放入 brief。缺矩陣時仍用已驗證模型的 `effort: null` 選項與 skills 同批詢問，effort 留給宿主預設並明示未路由；不能把工具的 effort enum 直接乘上全部模型。Mod 不再問第二次；API 或回應驗證失敗時整批沿用原設定。這個混合流程依賴 agent 準備，沒有原生 receipt 強制檢查。只開 `skill` 或本地工作由 agent 選 skills 並重用。旗標只存在記憶體，mod 重載或 session 結束即重設。詳見 [Claude 路由](./skills/jev/references/claude-native.md)。

典型流程：`grill docs` 對齊 → `to-spec` 出規格 → `to-tickets` 拆票 → `implement` 實作（內部走 `tdd`）→ 換 session（最好換模型）跑 `review` → `to-docs` 沉澱 → 卡住用 `diagnosing-bugs`。

討論中需要可執行證據時，用 `prototype-logic` 驗證一個問題，再回到 grill 或 spec。原型是暫存施工架，模擬通過不代表 production 已驗證。工作中反覆卡住或出錯後，可用 `retro` 回顧環境；它只提建議，不直接套用。

`.scratch/` 的 spec 與 ticket 是施工架，用完即丟；長期留下的是詞彙記錄、決策記錄與測試。前兩者預設落在 `CONTEXT.md` 與 `docs/adr/`，repo 已有自己的文檔系統就寫進既有位置，不另開一套。測試由 `tdd` 產出、測試套件把關；`to-docs` 只管前兩者，逐項提議哪些留、哪些改、哪些刪，也可以單獨叫起來修剪已經跟程式碼脫鉤的舊記錄。

## 出處與授權

skills 源自 [mattpocock/skills](https://github.com/mattpocock/skills)（MIT，[全文](./LICENSES/mattpocock-skills-LICENSE.txt)），結構手法參考 [shadcn/improve](https://github.com/shadcn/improve)（MIT，[全文](./LICENSES/shadcn-improve-LICENSE.md)）。本 repo 的改動以 [MIT](./LICENSE) 釋出。
