# TODO — 草船借箭（story 2）進度與待辦

_最後更新：2026-09-15。接手前先讀這份，再看 `arrows/PLAN.md`。_

## 現況（做到哪）

- ✅ 計劃 + prompt 就緒並已 commit：`story/red-cliff-arrows.json`（8 章 + 封面）、
  `scripts/arrows_gen.py`、`arrows/PLAN.md`。
- ✅ **試點已生成**：`cover` 與 `c1` 的靜圖 + 影片（`arrows/assets/` 內
  `cover.jpg/mp4`、`c1.jpg/mp4`）。
- ✅ 靜圖品質很好、畫風/角色一致（諸葛亮素袍羽扇、周瑜玄甲紅綬、草船草人、夜霧燈籠）。

## ⚠️ 關鍵發現（待處理的核心問題）

- **「翻頁動作烘焙進影片」行不通**。使用者實看 `c1.mp4` 回饋：**「不太像翻頁」**。
- 原因如 PLAN 風險欄所料：`image_to_video` 只是把「既有靜圖」動起來，
  做不出真正的紙頁翻動；story 裡的 `turn`（紙頁掀下）前綴只換來輕微紙面掃動。

## 下次第一件事：驗證影片（工具缺）

- 本機**沒有** ffmpeg / ffprobe / mediainfo，Python 也**沒有 pip / imageio / cv2**，
  無法抽格。要驗證動態內容需先解決抽格：
  - 選項 A：裝 ffmpeg（`apt`/`brew`，看本機權限）→ `ffmpeg -i c1.mp4 -vf fps=2 f_%03d.png`。
  - 選項 B：裝 pip 後 `python3 -m pip install imageio imageio-ffmpeg pillow` 再抽格。
  - 選項 C：直接在瀏覽器/播放器看（使用者已看過，結論：不像翻頁）。

## 決策（待拍板）：翻頁改由「網頁」做

PLAN 的退路方案，建議採用：

1. **影片只做場景動態**（霧/水/箭/鼓/燈/扇），拿掉「翻頁」語意。
   - 改 `story/red-cliff-arrows.json` 的 `turn` 前綴：移除「紙頁掀下」那句，
     或改成純進場氛圍（如「場景緩緩甦醒」）。
   - `cover`、`c1` 兩段影片可**重生**（`arrows_gen.py --ids cover,c1 --videos --force`）
     或先留著看場景動態是否堪用。
2. **翻頁改成網頁的輕量轉場**：捲到下一章時，用 CSS 讓一張紙頁從上緣掀起/滑入蓋掉再揭開，
   露出下一段全幅影片（呼應第一本「下往上翻」的語彙，但這裡是網頁層做）。

## 待建（尚未做）

- [ ] `arrows/template.html` + `scripts/build_arrows.py`：全幅 `100vh` scroll-snap 影片播放器
      （進場才 `currentTime=0` 播放、離開暫停；底部漸層字幕；章節進度點；reduced-motion 友善）。
- [ ] 網頁層的紙頁翻場轉場（見上）。
- [ ] 生成其餘 `c2`–`c8` 靜圖 + 影片（`arrows_gen.py --stills` 再 `--videos`）。
- [ ] 首頁改成兩本書選單：root `index.html` 從「轉址 book/」→「三隻小豬 / 草船借箭」選單，
      草船借箭部署在 `/arrows/`。
- [ ] build + headless 驗證 + push + 等 Pages。

## 檔案狀態

- 已 commit（本次）：`todo.md`、`arrows/assets/{cover,c1}.{jpg,mp4}`、`arrows/assets/manifest.json`。
- 若決定重生影片：直接 `--force` 覆蓋即可。

## 備忘

- ZDR 已關（`coding_data_retention_opt_out = False`），影片生成穩定。
- 生成用背景跑 + 輪詢檔案數判進度（log 會被 Python 緩衝，別等 log）。
- 教訓已記：**image_to_video 只能動既有靜圖，無法做真正翻頁/新內容** → 轉場交給網頁。
