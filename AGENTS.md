# Repo 規範

單層結構：`skills/<name>/`，內含 `SKILL.md`、選配 `references/`、`agents/openai.yaml`（Codex）。

## 同步規則（動到 skill 時逐條檢查）

1. README 的 skills 表、`.claude-plugin/plugin.json` 的 `skills` 陣列，以及 `.claude-plugin/marketplace.json` 的 description 與 keywords，三處同步更新。validate 不檢查 description 內容，漏了不會報錯。
2. 每個 skill 都要有 `agents/openai.yaml`。user-invoked 的 skill：`SKILL.md` 設 `disable-model-invocation: true`，`openai.yaml` 設 `policy.allow_implicit_invocation: false`，兩者同進退。
3. bump `plugin.json` 的 `version`，跑 `claude plugin validate . --strict`。
4. 重跑 `scripts/link-skills.sh`。

## 硬規則

- 個人資訊（本機路徑、私人專案細節、ID、金鑰）不進 repo。個人專屬 skills 放 `~/.claude/skills`，不放這裡。commit 前檢查：`git diff --cached | grep -nE '/Users/|/home/'` 須無結果。
- 文檔零廢話：直述句，砍填充語與空泛形容。

## 出處

skills 取自 mattpocock/skills 改造：grilling／grill-me／grill-with-docs／domain-modeling 併成 grill，to-spec 與 to-tickets 落地為本地檔案（`.scratch/<feature-slug>/`），暫不連動 GitHub issues。shadcn/improve 的計畫紀律融入 to-spec／to-tickets／implement：spec 與 ticket 自足（執行者零對話脈絡）、驗收用可跑的指令、STOP 條件、drift check（戳記 commit）。to-docs 是本 repo 原創，上游無對應：`.scratch/` 的 spec 與 ticket 是拋棄式的，長期文檔只留詞彙記錄與決策記錄（預設 CONTEXT.md 與 docs/adr/，repo 有既有文檔系統就沿用；測試也長期留，但歸 tdd 與測試套件），to-docs 管這兩份文檔的沉澱與修剪，判準取自 improve 的 recon 觀點（ADR 記過的取捨在稽核時算 by-design，不算 finding）。授權見 `LICENSES/`。不追蹤上游；要吸收上游更新時手動 diff（搬入版本：mattpocock/skills@ed37663、shadcn/improve@03369ee）。
