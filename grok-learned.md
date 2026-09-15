# Grok CLI（Grok Build）實戰筆記

把 **登入 → 生圖 → 生影片** 這條路完整走通後的操作手冊。
重點：**登入後的 CLI 本身就能生圖生片，不需要 `XAI_API_KEY`。**

官方文件：<https://docs.x.ai/build/overview>

---

## 1. Grok Build 是什麼

一個**編碼代理 CLI**（性質接近 Claude Code），可互動 TUI、可 headless、可走 ACP。
它的價值不只在寫程式 —— 它內建 `image_gen` / `image_edit` / `image_to_video` /
`reference_to_video` 四個媒體工具，所以**它同時是一個可用指令驅動的生圖生片後端**。

> ⚠️ **最容易誤判的一點**：`grok models` 只會列出 `grok-4.6` / `grok-4.5` 兩個純文字模型。
> 不要因此斷定「CLI 只能處理文字」。
> **要看它有什麼「工具」，不是看「模型清單」。**
> 確認方式：`grok -p "List the names of every tool you have available."`

---

## 2. 安裝

```bash
curl -fsSL https://x.ai/cli/install.sh | bash
```

- 裝到 `~/.grok/bin/grok`（另建 `agent` 同名連結），並 symlink 到 `~/.local/bin/`
- **不需要 sudo**，不動系統目錄
- 會把 `~/.grok/bin` 寫進 `~/.bashrc` 的 PATH
- Windows：`irm https://x.ai/cli/install.ps1 | iex`

指定版本：`curl -fsSL https://x.ai/cli/install.sh | bash -s 1.0.30`

當下 session 立即可用：

```bash
export PATH="$HOME/.grok/bin:$PATH"
grok --version      # grok 1.0.30 (04b7ffed98c6)
```

---

## 3. 登入 —— 遠端／無瀏覽器環境用 device-code

```bash
grok login --device-auth      # 別名：--device-code
```

輸出：

```
To sign in, open this URL in your browser:
  https://accounts.x.ai/oauth2/device?user_code=XXXX-XXXX
Confirm this code in your browser:
  XXXX-XXXX
Waiting for authorization...
```

**在你自己的電腦**開那個網址、核對代碼、按同意。CLI 輪詢到授權後印出：

```
✓ Signed in as you@example.com
```

### 為什麼這是遠端環境的正解

- **帳密全程不進容器**。登入在你本機的瀏覽器完成，容器只收到 token。
- 不需要在容器裡跑瀏覽器，因此**完全避開無頭瀏覽器的 CA / Cloudflare 問題**。
- 憑證寫在 `~/.grok/auth.json`（權限 `600`）。容器被回收就沒了，重跑 login 即可。

其他方式：

| 方式 | 指令 / 變數 | 適用 |
|---|---|---|
| device-code | `grok login --device-auth` | **遠端、headless（推薦）** |
| 瀏覽器 | `grok login --oauth` | 本機有 GUI 瀏覽器 |
| API 金鑰 | `export XAI_API_KEY=xai-...` | CI／不想互動登入 |
| 部署金鑰 | `GROK_DEPLOYMENT_KEY=<key>` | 企業佈署，安裝時即帶入 |

登出：`grok logout`

### 驗證登入成功

```bash
grok models
# You are logged in with grok.com.
# Default model: grok-4.6
# Available models:
#   * grok-4.6 (default)
#   - grok-4.5
```

---

## 4. Headless 呼叫

```bash
grok --always-approve -p "你的指示"
```

- `-p` / `--single`：單次 prompt，不進 TUI
- `--always-approve`：自動核准工具執行。**批次腳本一定要加**，否則會卡在權限確認
- `--output-format streaming-json`：要解析輸出時用
- `--cwd <dir>`：指定工作目錄

### ⚠️ flag 順序陷阱

```bash
grok --always-approve -p "..."      # ✅ 可以
grok -p --always-approve "..."      # ❌ a value is required for '--single'
```

`-p` 後面必須**緊接**它的值。

---

## 5. 生圖

沒有 `grok image` 這種子指令 —— 用自然語言叫它呼叫工具，**並明確要求存檔路徑**：

```bash
grok --always-approve -p 'Use your image_gen tool to generate exactly one image
with this prompt, then save the generated image file to book/assets/p1_bg.jpg
(create the directory if needed). Do not modify the prompt.
Report the final absolute file path and its size in bytes.

PROMPT: <你的完整英文 prompt>'
```

實測：一張 1280×720 左右的圖約 300 KB，單次呼叫約 1–2 分鐘。

**要點**

- **一個 asset 一次呼叫**。比「一次叫它生一批」可靠得多，而且天然可續跑。
- **明講存檔絕對／相對路徑**，否則它會丟在暫存目錄。
- **叫它不要改 prompt**（`Do not modify the prompt`），不然它會自作主張潤飾。
- 產出檔案權限是 `0600`。

---

## 6. 生影片

```bash
grok --always-approve -p 'Use your image_to_video tool with the source image
arrows/assets/c1.jpg and this motion prompt to generate a 6-second video,
then save it to arrows/assets/c1.mp4. Report the file path and size in bytes.

PROMPT: <動態描述>'
```

### ⚠️ 最重要的限制（吃過虧）

**`image_to_video` 只是把「既有那張靜圖」動起來，它不會無中生有。**

所以**影片裡會有什麼，取決於來源靜圖裡已經有什麼**。

實例：想要「翻頁效果在影片裡」，卻餵給它一張滿版的場景圖 —— 畫面裡根本沒有書、
沒有紙頁、沒有裝訂邊，於是模型只能掃出一點紙面質感，成品「不太像翻頁」。
**光加強影片 prompt 沒用，要改的是靜圖 prompt**：讓第 0 格就是一本實體立體書、
看得見頁緣與書溝、最好那一頁已經掀到一半，模型才有東西可以續動。

> 口訣：**要動什麼，先讓它出現在靜圖裡。**

另一個工具 `reference_to_video` 給的自由度較高（以參考圖生片而非逐格續動），
需要新內容時值得一併試。

---

## 7. ZDR（零資料保留）會擋掉影片

- 症狀：`Video generation was blocked by zero data retention`，且**時好時壞**
- 成因：保留設定為 opt-out 時，影片輸出沒有可落地的儲存位置
- **兩個獨立旗標，別搞混**：
  - **帳號層級**：`~/.grok/auth.json` 的 `coding_data_retention_opt_out` ← 多數情況是這個
  - **團隊層級**：`console.x.ai` 團隊設定的 Zero Data Retention
- 解法，由輕到重：
  1. **先重試** —— 它是軟性間歇阻擋，重試通常就過。管線要能單項重生。
  2. 進 TUI 跑 `grok` → 輸入 `/privacy` → 「Coding data, retention, and training」選 **Opt in**。
     改完**開新 session** 才生效，設定是帳號範圍、跨 session 持久。
  3. 若該列鎖成 `ZDR` / `Admin Managed`，要團隊管理員到 console 關掉。
  4. 想維持 ZDR 又要生片：設 `tools.zdr_video_output_s3`（`~/.grok/managed_config.toml`）。
- **生圖不受影響，只有影片會中。**
- `config.toml` 的 `privacy.privacy_banner_acked` 只是橫幅已讀時間，**不控制 ZDR**。

---

## 8. 批次生成管線的設計原則

1. **一 asset 一呼叫**，迴圈跑。
2. **skip-existing 續跑**：輸出檔存在且大小超過門檻就跳過。崩了直接重跑，不用記進度。
3. **以檔案判成功，不要信 agent 回話**。它可能說「已存檔」但檔案是 0 byte 或根本不在。
   判準用 `out.exists() and out.stat().st_size >= MIN_BYTES`。
4. **背景跑 + 輪詢檔案數判進度**。Python 重導到檔案時 stdout 會被緩衝，log 常常是空的，
   改看 `ls assets/*.jpg | wc -l`。
5. **一致性靠 prompt 前綴**：把 `style`（畫風）與 `cast`（角色外觀）字串前綴到每一個 prompt。
   這招非常有效 —— 8 章 24 張圖畫風與角色都能鎖住。
6. **分層設計要講清楚誰在哪層**：背景層 prompt 要明寫 `empty landscape, no characters`，
   否則模型會自作主張把主角也畫進背景，跟前景紙卡重複。

---

## 9. 這個容器環境的補充

- **CLI 不需要任何 TLS 修補就能用** —— 它自己處理憑證，直接穿過 egress proxy。
- 但**無頭 Chromium 預設連不上任何 HTTPS**（`ERR_CERT_AUTHORITY_INVALID`），
  因為 `/root/.pki/nssdb` 是空的。要用 Playwright 驗證網頁時得先補：

  ```bash
  apt-get update -qq && apt-get install -y libnss3-tools
  certutil -A -d sql:/root/.pki/nssdb -n ccr -t "C,," -i /root/.ccr/agent-proxy-ca.crt
  ```

  這是把環境本來就提供的 CA 正式匯入瀏覽器信任庫，**不是關閉憑證驗證**。
- `~/.grok/auth.json` 受沙箱保護，讀取會被擋（Credential Materialization）。
  不需要也不應該去解析它；用 `grok models` 確認登入狀態即可。

---

## 快速 checklist

```bash
# 1. 裝
curl -fsSL https://x.ai/cli/install.sh | bash
export PATH="$HOME/.grok/bin:$PATH"

# 2. 登入（在自己電腦開網址授權）
grok login --device-auth

# 3. 確認
grok models
grok -p "List the names of every tool you have available."

# 4. 生一張試水溫，確認畫風再全跑
grok --always-approve -p 'Use image_gen ... save to out.jpg ... PROMPT: ...'
```

---

## 10. ⚠️ 官方 `imagine` skill —— 早該先讀的那份

Grok CLI 自帶一套 skill，就在 `~/.grok/bundled/skills/`。其中兩份直接規範生圖生片：

- **`imagine/SKILL.md`** —— 生圖、修圖、生影片的完整規範（**必讀**）
- **`game-character-consistency/SKILL.md`** —— 同一角色跨多張圖的 edit-chain protocol

還有 `game-asset-core`、`game-tilesets`、`game-ui-icons`、`game-animation-frames`
是疊在 imagine 之上的遊戲美術特化版。

> **教訓：接一個新 agent CLI 當生成後端時，第一件事是翻它的 `bundled/skills/`。**
> 我們靠試誤重新發現的規則，有一半這份文件裡本來就寫了。

### 這份 skill 講了什麼（逐條對照我們踩過的坑）

| 官方規定 | 我們原本的做法 | 後果 |
|---|---|---|
| 影片 prompt **1–2 句**、現在式、**一個**鏡頭運動 | ~1500 字元，style + cast 整段貼上 | 模型抓不到重點，翻頁草率 |
| 一個 shot **一個主體、一個簡單動作**；多動作「models handle it poorly」 | 翻頁＋紙雕彈起＋分層依序＋環境動態 = 4+ 動作 | 翻頁被壓成 0.5 秒，動作互搶 |
| 複雜來源圖動畫時**會變形**；要嘛換簡單的底圖，要嘛**只動鏡頭** | 立體書紙雕極精細（紙層／帳篷／人物／燈籠／書頁） | 風格漂移：披風、燈籠形制、鏡位全變 |
| duration **只有 6s 或 10s**，其餘四捨五入 | 用了 5 / 6 / 7 / 8 | 5/7/8 根本無效 |
| 反覆出現的角色要先生一張 canonical reference，之後一律 `image_edit` 衍生，**never a fresh `image_gen`** | 8 章各自 fresh `image_gen` | 章與章之間角色必然漂移 |
| `image_edit` 時**必須保留 style words**，否則「drift toward photorealism」 | 未特別保留 | 人物一度變成寫實真人臉 |
| 鏡頭連續性：用 ffmpeg 抽上一段**最後一格**當下一段來源 | 沒做 | 章之間不連戲 |
| 多格拼貼（storyboard／contact sheet）要**用程式組**，不要叫模型畫 | — | 模型畫不準格線與標籤 |
| 串接用 `ffmpeg -f concat -c copy`，**不要重新編碼** | — | 避免畫質損失 |

### 其他要點

- **沒有 seed 參數。** 全篇未提供，一致性只能靠 reference + edit-chain 手工製造
  （原文：「Grok Build has no persistent character or style memory, so consistency
  is manufactured on every call」）。
- **沒有 text-to-video。** 影片一定從圖開始，預設 `image_to_video`。
- `image_gen` 的 `aspect_ratio` 只吃 `1:1 / 16:9 / 9:16 / 4:3 / 3:4 / auto`。
  影片比例**在來源圖上決定**，不要事後裁切。
- `image_gen` / `image_edit` **都沒有 `n` / `count`**，要多版本就多呼叫幾次。
- 需要精確文字、數字、圖表、格線的東西**不要用影像模型**，用 HTML/CSS 生再截圖。
- 被 moderation 擋下時**不要改寫 prompt 規避**，直接告知使用者換方向。

### 正確的 pipeline 形狀（skill 建議的）

1. 先生 **canonical references**：場景 master、角色 reference，一次定裝。
2. 每個 shot 的來源圖用 **`image_edit` 從 reference 衍生**（保留 style words），不要重生。
3. **一個 shot 一個動作**，6 秒為主，寧可多切幾個 shot。
4. `image_to_video` 動畫每個 shot；下一 shot 用上一段最後一格當來源以接戲。
5. 最後 `ffmpeg -f concat -c copy` 串起來。
