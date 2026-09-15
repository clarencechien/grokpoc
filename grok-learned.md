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
