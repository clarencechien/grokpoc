# 三隻小豬 · 立體繪本（Grok Imagine 生成實驗）

用 xAI 的 Grok Imagine API 生成插畫與影片，組成一本可翻頁、有景深的 CSS 3D 立體繪本。
這個 repo 同時是一份「Claude Code 遠端環境能不能驅動 Grok」的實測記錄。

## 實驗結論

| 項目 | 結果 |
|---|---|
| 從本環境連到 `api.x.ai` | **可以**。curl 與 Python `urllib` 都能穿過 egress proxy 完成 TLS 交握 |
| 未帶金鑰的 API 回應 | `400 invalid-argument – Incorrect API key provided`，代表請求確實抵達 xAI |
| 帶金鑰實際生圖／生片 | **尚未執行**，本環境沒有 `XAI_API_KEY` |
| 用瀏覽器登入 grok.com（web login） | **不可行**，原因見下 |
| 繪本前端本身 | **完成並已驗證**，Chromium 實際渲染無 console error |

### 為什麼 web login 這條路走不通

1. **Chromium 不信任 egress proxy 的 CA。** 本環境所有對外 HTTPS 都經過會重新終結 TLS 的
   代理。Playwright 內建的 Chromium 不讀 `/root/.pki/nssdb`，因此連 `https://example.com`
   都會 `ERR_CERT_AUTHORITY_INVALID` — 這不是 grok 特有的問題。
   唯一的針對性修法（用 `--ignore-certificate-errors-spki-list` 只信任該張 CA）
   被沙箱判定為 containment escape 而擋下，未繞過。
2. **就算瀏覽器能跑**，登入 grok.com 需要把 X／Google 帳密放進這個隨時會被回收的容器，
   還要過 2FA 與 Cloudflare 驗證（`accounts.x.ai`、`console.x.ai` 對 curl 直接回 403），
   而且用自動化操作消費端網頁介面違反 xAI 的服務條款。

> 註：`accounts.x.ai` / `console.x.ai` 的 403 來自 Cloudflare，不是 egress 政策 —
> proxy 的 `CONNECT` 隧道本身回 `200 Connection Established`。

**建議走官方 API**：到 <https://console.x.ai> 取得金鑰，以環境變數注入這個 session
（Claude Code 的 environment 設定），不要貼在對話裡。

## 使用方式

```bash
export XAI_API_KEY=xai-...

python3 scripts/grok_gen.py --check       # 只驗證金鑰與模型可用性
python3 scripts/grok_gen.py --dry-run     # 印出所有預計送出的請求，不連線
python3 scripts/grok_gen.py --pages p1    # 先試一頁，確認畫風再全跑
python3 scripts/grok_gen.py               # 全部 24 張圖 + 8 段影片（可中斷續跑）
python3 scripts/build_book.py             # 把素材接進繪本
open book/index.html
```

`grok_gen.py` 只用標準函式庫，不需 `pip install`。已存在的素材預設跳過，
所以中途失敗直接重跑即可；要重新生成某頁加 `--force`。

## 結構

```
story/three-little-pigs.json   故事唯一來源：中文內文 + 每層的英文 prompt + 版面座標
scripts/grok_gen.py            呼叫 Grok Imagine：生圖 → 以該圖為首格生影片
scripts/build_book.py          把故事與素材清單內嵌進 template，產出 book/index.html
book/template.html             繪本本體（CSS 3D 立體書機構）
book/index.html                建置產物，可直接用 file:// 開啟
book/assets/                   生成的 .jpg / .mp4 與 manifest.json
```

## 立體書是怎麼做的

每頁是一個 diorama，分三層：

- `bg` — 鋪滿整個跨頁的背景板
- `mid` — 主體，站起來的紙卡（`translateZ(80px)`）
- `fg` — 前景道具，站得更前面（`translateZ(170px)`）

翻頁時紙卡從 `rotateX(-86deg)`（平貼在頁面上）彈起到 `rotateX(0)`，並依序延遲，
重現實體立體書「攤開就跳起來」的動作。滑鼠移動會傾斜整個 diorama 產生視差，
空白鍵把該頁的背景板換成 Grok 生成的影片。

素材還沒生成時會顯示紙雕風格的 SVG 佔位圖，所以繪本在沒有金鑰的狀態下也能翻。

## 生成策略

- `story.style` 與 `story.cast` 會自動前綴到每一個 prompt，讓八頁的畫風與角色外觀一致
  （草帽＋芥黃圍巾的大哥、丹寧吊帶褲的二哥、紅圍巾＋小鏟子的小弟、炭灰外套的野狼）。
- 影片用 image-to-video：先產出該頁的背景板，再把它以 base64 data URI 當作首格送進
  `/v1/videos/generations`，所以動畫和靜態插畫是同一個構圖。
- 影片是非同步的，腳本會拿 `request_id` 輪詢 `/v1/videos/{id}` 直到 `done`。
