# 《草船借箭》· 紙雕動態繪本 — 計劃

第二本故事。**刻意走與第一本不同的路線**：不是 CSS 3D pop-up，而是
**image-to-video 為主、翻頁動作烘焙進影片、網頁只負責向下捲動切換影片**。

> 狀態：**計劃 + prompt 已就緒，尚未生成**（依指示先停在這）。
> 要開始生成時見下方「執行步驟」。

---

## 定案的方向（已與需求方確認）

- **視覺框**：全幅電影感 —— 每章紙雕場景鋪滿畫面，章與章之間以紙頁掀起／滑入當轉場。
- **章數**：8 章（完整版）。
- **畫面比例**：16:9（`--aspect 16:9`）。
- **美術**：紙雕 diorama × 中國水墨氛圍，夜霧、燈籠暖光對冷藍、棉紙霧氣、電影級光影。

## 與第一本的差異

| | 三隻小豬（book/） | 草船借箭（arrows/） |
|---|---|---|
| 立體來源 | CSS 3D（bg/mid/fg 分層 + `rotateX`） | **烘焙進影片**（image_to_video） |
| 每章素材 | 3 張分層圖 + 1 段背景影片 | **1 張靜圖 + 1 段影片** |
| 翻頁 | CSS 頁面沿頂邊 `rotateX` | **影片裡的紙頁掀起／滑入**（story 的 `turn` 前綴） |
| 網頁職責 | 驅動整個 3D、視差、pop-up | **只做垂直捲動 + 播放當前影片** |

## 素材與 prompt（已寫好）

- `story/red-cliff-arrows.json` —— 唯一來源：
  - `style`（紙雕電影風）與 `cast`（諸葛亮/周瑜/魯肅/曹操/草船）前綴到每個 prompt，鎖一致性。
  - `turn`：**翻頁動作的共用前綴**，會加在每段影片的動態 prompt 前（「一張紙頁從上方掀下、
    落定後場景彈出景深」）。
  - 8 章：周瑜刁難 → 三日軍令狀 → 借船紮草人 → 按兵不動 → 大霧漫江 → 擂鼓吶喊 →
    萬箭齊發 → 滿載而歸；每章有 `prompt`（靜圖構圖）與 `video.prompt`（動態）+ `duration`。
  - `cover`：主視覺 + 封面動態。
- `scripts/arrows_gen.py` —— image-to-video 生成器（用已登入的 grok 代理，無需金鑰）：
  每個單位 `image_gen` 生靜圖 → `image_to_video` 生片；可續跑、以檔案大小判成功、
  維護 `arrows/assets/manifest.json`。已 `--dry-run` 驗證 prompt 串接正確。

## 待建（尚未做）

- `arrows/template.html` + `scripts/build_arrows.py` —— **極簡全幅捲動影片播放器**：
  - 每章一個 `100vh` scroll-snap 區塊，內含 full-bleed `<video>`（`object-fit:cover`、
    muted、playsInline）。
  - 進入視窗才播放並從頭開始（`currentTime=0`），離開就暫停（省資源）；捲動向下 = 下一段影片。
  - 字幕（章名 + 內文）以底部漸層浮層淡入，不擋主體。
  - chrome 極簡：章節進度點、書名；尊重 `prefers-reduced-motion`（不自動播、給控制列）。
  - 素材未生成時顯示靜圖或佔位；缺片可 fallback 靜圖。
- 首頁整合：root `index.html` 從「直接轉址 book/」改成**兩本書的選單**（三隻小豬 / 草船借箭），
  草船借箭部署在 `/arrows/`。

## 執行步驟（要生成時再跑）

```bash
python3 scripts/arrows_gen.py --check           # 確認代理有 image_gen / image_to_video
python3 scripts/arrows_gen.py --dry-run         # 檢視所有預計送出的 prompt
python3 scripts/arrows_gen.py --ids cover,c1    # 先試封面+第一章，確認畫風再全跑
python3 scripts/arrows_gen.py --stills          # 先生 9 張靜圖（cover + 8 章）
python3 scripts/arrows_gen.py --videos          # 再 image-to-video 成 9 段影片
python3 scripts/build_arrows.py                 # 組進播放器
```

> ZDR 已在此帳號關閉（`coding_data_retention_opt_out = False`），影片應可穩定生成；
> 若仍有零星失敗，單章 `--ids cX --videos --force` 重試。細節見 [lessons-learned.md]。

## 風險 / 待驗證

- **翻頁能不能真的長在影片裡**：`image_to_video` 是動畫「既有靜圖」，要它「掀紙頁露出場景」
  可能只做出紙面掃過的效果而非真正翻頁。→ 先用 `cover,c1` 各生一段驗證；
  若不理想，退而求其次：影片只做場景動態，翻頁改由網頁做輕量紙頁滑入轉場。
- 全幅影片檔案較大（每段數 MB）→ 8+1 段合計可能 20–40MB，注意 repo/Pages 體積。
