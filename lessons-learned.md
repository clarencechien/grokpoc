# Lessons Learned — grokpoc 立體繪本

這份文件記錄「用 Grok 生成素材 + 做立體 scroll 繪本 + 上 GitHub Pages」整個流程中，
真正花了時間才學到的東西。目的是讓**下一個類似專案一開始就成熟**，不必重踩。

依「最容易讓人卡住 / 最容易做錯」排序。

---

## 1. 用 Grok CLI 當生成後端 —— 不需要 `XAI_API_KEY`

**結論先講**：登入後的 `grok` CLI 本身就是一個帶媒體工具的 headless agent，
能直接生圖生片，**不用申請 Imagine API 金鑰**。

- 安裝：`curl -fsSL https://x.ai/cli/install.sh | bash`（binary 在 `~/.grok/bin/grok`）
- 無瀏覽器環境登入：`grok login --device-code`（憑證存 `~/.grok/auth.json`）
- 內建媒體工具：`image_gen`、`image_edit`、`image_to_video`、`reference_to_video`
- headless 呼叫：`grok --always-approve -p "<指示，含存檔絕對路徑>"`

### 我一開始踩的坑
`grok models` 只列出 `grok-4.6 / grok-4.5`（純文字模型），我就**誤判 CLI 只能文字、
一定要走 Imagine API + 金鑰**。錯。
> **教訓：判斷一個 agent 能做什麼，要看它的「工具（tools）」，不是「模型清單」。**
> 直接問它 `grok -p "list your media tools"`，或查官方 changelog，別憑模型清單推論。

### 其他小坑
- **flag 順序**：`-p/--single` 需要值緊接其後。`grok --always-approve -p "..."` 可以，
  `grok -p --always-approve "..."` 會報 `a value is required for '--single'`。
- 生成的檔案權限是 `0600`（本機看沒問題，發布前不影響）。

---

## 2. 生成管線的設計（`scripts/grok_cli_gen.py` 的心得）

- **一個 asset 一次 `grok -p` 呼叫**，比「一次叫它生一堆」可靠得多，且天然可續跑。
- **可續跑 = 檢查輸出檔存在且大小過門檻就 skip**；崩了直接重跑，不用記進度。
- **驗證要看檔案，不要只信 agent 回話**：agent 可能說「已存檔」但檔案是 0 byte 或缺失。
  用 `out.exists() and out.stat().st_size >= MIN_BYTES` 當成功判準。
- **背景跑 + 輪詢檔案**：Python 重導到檔案時 stdout 會被緩衝，log 常常是空的；
  **以「產出檔案數」判斷進度**（`ls book/assets/*.jpg | wc -l`），別等 log。
- **一致性靠 prompt 前綴**：把 `style`（畫風）與 `cast`（角色外觀）字串前綴到每一個 prompt，
  8 章 24 張圖的畫風與角色才會一致。這招非常有效。

---

## 3. 影片：ZDR（零資料保留 / `/privacy`）會間歇性擋掉 `image_to_video`

- 症狀：部分影片成功、部分回 `Video generation was blocked by zero data retention`。
- 成因：**保留設定為 opt-out 時，影片輸出沒有可落地的儲存**，於是被擋。
- **關鍵：有兩個獨立旗標，別搞混**：
  - **帳號 `/privacy`**：`~/.grok/auth.json` 的 `coding_data_retention_opt_out`（TUI `/privacy` 控制）。
  - **團隊/組織 ZDR**：xAI Console 的 admin 設定（`console.x.ai` 團隊設定）。
- **本專案的實測釐清**：團隊 ZDR **本來就是 Disabled**、不是原因；真正造成 `p1` 被擋的是
  **帳號層級 `coding_data_retention_opt_out = True`（Opt out）**。所以「去把團隊 ZDR 設 Disable」
  沒有效果——那本來就關著。要根治得改**帳號 `/privacy` → Opt in**。
- 而且它是**軟性/間歇**阻擋：本次 9 段影片最後全數生成（`p1` 重試一次就過），
  不是一段都生不出來的硬阻擋——**先重試，通常就過**。
- 診斷法：直接讀 `~/.grok/auth.json` 看 `coding_data_retention_opt_out` 布林值，最準；
  別只憑錯誤訊息裡的 "ZDR" 字樣就假設是團隊層級。
- 解法（由輕到重）：
  1. **重試**（最有效，本次 `p1.mp4` 第一次失敗、重試就過）——所以管線要能單章重生。
  2. **關閉 `/privacy`（ZDR）**。它是 **TUI 的 slash 指令、寫入「帳號層級」選擇，不是 `config.toml` 的鍵**：
     - 執行 `grok` 進 TUI → 輸入 **`/privacy`**（或 `/settings`）→ 在
       「**Coding data, retention, and training**」選 **Opt in**（允許保留）。
       **Opt out** 就是 ZDR 狀態、會擋影片。
     - 改完**開新 session** 才生效；此選擇**持久、跨 session、帳號範圍**。
     - 若該列鎖成 `ZDR` / `· Admin Managed`：需團隊管理員到
       <https://console.x.ai/team/default/settings/team> → **Zero Data Retention** → **Disable**。
     - 註：`config.toml` 只有 `privacy.privacy_banner_acked`（橫幅已讀時間），**不控制 ZDR**。
  3. 想維持 ZDR 又要生影片：設 `tools.zdr_video_output_s3`（`~/.grok/managed_config.toml`）。
- 生「圖」不受影響，只有「影片」會中。
- **前端要能容忍缺片**：素材不存在時 fallback 成靜態圖，缺一兩段影片不該讓繪本壞掉。

---

## 4. 立體 scroll 前端的設計要點

- **固定舞台 + 隱形捲軸**：`.deck` 用 `position:fixed`，另有一個高度 = `(N+2)*SEG_VH*100vh`
  的 `#track` 提供捲動距離；`scroll` 事件用 rAF throttle 後重算 3D。這比「每章一個 sticky」單純。
- **每章一個連續參數 `t = pos - i`**（`<0` 未到、`0` 置中、`>0` 翻走），所有動畫都由 `t` 推導，
  易懂又好調。
- **字幕淡入淡出視窗要 < 1 章寬**，且與鄰章在 `cop=0` 相接，否則過場時兩章字幕會同時出現、疊成糊。
  本次用 `min(smooth(-0.5,-0.28,t), 1-smooth(0.28,0.5,t))`。
- **隱藏元素用 `display:none`，不要只靠 `opacity:0`/`visibility:hidden`**：
  帶 `backdrop-filter` / `will-change` 的面板，光設 opacity 有時不會真的從合成樹移除。
- **固定舞台裡的圖用 eager 載入**（不要 `loading="lazy"`）：卡片一直在 viewport 內，
  lazy 沒好處，反而會在首次繪製出現空白卡。
- **版面別讓字幕蓋住主體**：把書用 `place-items:start` + 高度上限（如 `min(88vw,86vh,960px)`）
  約束在上半部，底部留給字幕帶。
- 尊重 `prefers-reduced-motion`：關掉旋轉/視差，改用淡入。

---

## 5. 用 headless Chrome 驗證的陷阱（**這段最花時間**）

想用 `google-chrome --headless=new ... --screenshot` 驗證 scroll 效果時，會遇到：

- **`window.scrollTo()` 在 headless 截圖裡不生效**：截到的永遠是 scroll=0（封面）。
- 為了硬捲，覆寫 `Object.defineProperty(window,'scrollY',{get:()=>F})` 再手動叫 `scrub()`——
  但這會產生 **「拼裝影格」（Frankenstein frame）**：部分元素套用了新 scrub 狀態、部分還停在舊影格，
  於是出現「圖是第 5 章、字幕卻是第 4 章」這種**假象**。這不是頁面真實行為。
- `backdrop-filter` / `will-change` 的圖層在 headless 會**快取陳舊像素**，JS 改了樣式也不重畫。
- 把測試 HTML 丟到 `/tmp/` 會讓 `assets/...` 相對路徑失效（破圖）——要放回 `book/` 同目錄。

**可靠的做法：**
- **要驗「邏輯/DOM 狀態」→ 加 debug overlay，用 `getComputedStyle` 直接讀 DOM**
  （例如列出哪些 `.cap` 的 `display !== 'none'`）。**DOM readout 是權威，像素不是。**
- **要驗「版面/CSS」→ 直接截 scroll=0（封面）**，這個 headless 畫得可靠。
- 捲動狀態的「好不好看」，最終還是得在**真瀏覽器**手動滾一次確認；別用 headless 像素下結論。

---

## 6. GitHub Pages 部署

- Pages 資料夾只能選 **repo root 或 `/docs`**；內容在 `book/` 的話：
  - 從 root 服務，網址是 `.../<repo>/book/`；
  - 加一個 **root `index.html` meta-refresh 轉址**到 `./book/`，讓 `.../<repo>/` 也能進。
- **加 `.nojekyll`**（root）：跳過 Jekyll，檔名有底線或特殊字元也不會被吃掉。
- 用 API 開站：
  `gh api -X POST repos/<owner>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'`
- 查建置：`gh api repos/<owner>/<repo>/pages/builds/latest --jq '.status'`（等 `built`）。
- **第一次建置偶爾 `errored`（"Page build failed"）是暫時性**：
  `gh api -X POST repos/<owner>/<repo>/pages/builds` 重觸發通常就過。
- **別無腦 `git add -A`**：本次不小心把使用者的 `debug/image.png` 也 commit 進公開站，
  事後還要 `git rm --cached` + 加 `.gitignore`。**staging 前先 `git status` 看一眼。**
- 驗證上線：`curl -sI` 抓 root / 頁面 / 一張圖 / 一段影片，確認都 200；
  用 `?cb=$RANDOM` 破 CDN 快取確認是新版。

---

## 7. 內容品質 vs 結構正確（容易被忽略）

- 立體繪本的「背景層」應該是**純風景**；主體/道具才放在會立起的紙卡上。
- 但影像模型**常自作主張把角色也畫進背景**（即使 prompt 沒要求），
  造成「會動的背景」和「靜態紙卡」角色重複、看起來像出錯。
- **對策**：背景 prompt 明確寫 `empty landscape, no characters, no <主角>`；
  分層設計時就把「誰該出現在哪一層」講清楚。
- 教訓：**結構對（動畫在最底層是設計正確）不等於內容對**；審查時兩者都要看。

---

## 8. 一般工作習慣（這次驗證有效）

- **改寫前先備份**：`template.html` → `template.pageflip.bak.html`，隨時能對照/回退。
- **先用 `--check` / `--dry-run` 確認阻擋點與請求內容**，再真的花錢/花時間跑。
- **過時的既有結論要重新驗證**：README 當時記錄「需要金鑰」，但工具已進化到不需要——
  別把舊文件當定論。

---

## 給下一個專案的快速 checklist

1. `grok login --device-code`，用 `grok -p "list your media tools"` 確認能生什麼。
2. 生成腳本：一 asset 一呼叫、skip-existing、以檔案大小為成功判準、可單項重生。
3. prompt 一律前綴 `style` + `cast`，背景層明寫 `no characters`。
4. 影片預期會有 ZDR 間歇失敗 → 內建重試；前端對缺片做靜態 fallback。
5. 前端：固定舞台 + track 高度；動畫由 `t` 推導；字幕視窗 < 1 章、隱藏用 `display:none`；圖 eager。
6. 驗證：CSS/版面截 scroll=0；捲動狀態用 DOM debug overlay 讀，不信 headless 像素；最後真瀏覽器手動滾一次。
7. Pages：root 轉址 + `.nojekyll`；`git status` 後再 commit；建置 errored 就重觸發；`curl -sI` 破快取驗上線。
