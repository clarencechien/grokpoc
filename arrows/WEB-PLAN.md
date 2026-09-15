# 草船借箭 · 組裝成 GitHub Pages 網頁的計劃

目標：把 `arrows/assets/` 的素材組成一本在瀏覽器裡翻的立體繪本，和三隻小豬並列在同一個站。**不用再生任何新素材**，全部用 pipeline 的產出。

## 站的結構

```
/index.html            兩本書的選單（取代現在的「直接轉址 book/」）
/book/                 三隻小豬（現有，不動）
/arrows/index.html     草船借箭（本計劃）
/arrows/assets/        cover.jpg, c1.jpg …, *_turn.mp4, *_rise.mp4, *_ambient.mp4
/.nojekyll             已有
```

Pages 從 `main` 的 root 服務；`.nojekyll` 已在。

## 播放模型：三段片 + 章節內文

每一章是一個「狀態」，狀態內循環播放，切換時播轉場：

```
[ 章 N ambient 循環 ]  ──(下一頁)──▶  N_turn → N+1_rise → [ 章 N+1 ambient 循環 ]
                                          ▲空白的那一刻疊上「第 N+1 章 · 標題」
```

- **ambient 循環**：`<video loop muted playsinline>`，該章內文以字幕帶淡入在下方。
- **翻頁**：使用者捲動／點擊／按鍵觸發，依序播 `N_turn.mp4` → `N+1_rise.mp4`（`ended` 事件接續），最後切到 `N+1_ambient` 循環。
- **章節標題頁**：`rise` 片開頭那一秒是空白老書 —— 用 HTML 把「第 N 章 · 標題」疊在頁面位置上淡入淡出，**不生成文字影像**（模型畫不準字）。這就是「第幾章的空白頁翻出紙雕」。
- **缺片 fallback**：缺 turn → 直接淡入；缺 rise → 淡入 `{id}.jpg`；缺 ambient → 定格 `{id}.jpg`。跟 `arrows_compose.py` 同一套規則。
- 封面：起手是 `ref_cover_closed.jpg` 定格 + 書名，第一次互動播「封面翻開」（可用 cover_turn 或直接淡入 cover ambient）。

不用一支 `book.mp4` 的原因：無法停在章內循環、字幕無法對齊、也不能互動。`book.mp4` 留給分享／預覽用。

## 建置

- `arrows/template.html`：播放器（單檔，無外部依賴；CSS 變數控色；`prefers-reduced-motion` 時不自動播轉場、給控制列）。
- `scripts/build_arrows.py`：讀 `story/red-cliff-arrows.json` + 掃 `arrows/assets/` 產出 manifest（哪章有哪些片），內嵌進 template → `arrows/index.html`。沿用 `build_book.py` 的作法（自足、`file://` 可開）。
- 素材壓縮：目前 720p 每片 2–3 MB，9 章 × 3 ≈ 70 MB。發布前統一重編碼 `-crf 26 -preset slow -movflags +faststart`，目標每片 <1 MB、整站 <30 MB；海報圖用 `{id}.jpg` 縮到 1280 寬、品質 80。
- 手機：直式時 16:9 影片置中、上下留給字幕；`playsinline` + `muted` 才能自動播。

## 首頁選單

`/index.html` 改成兩張卡片（三隻小豬 / 草船借箭），各用封面圖 + 一句話，點進去分別到 `/book/` 與 `/arrows/`。

## 驗證（照 lessons-learned §5）

1. `build_arrows.py` 後在本機 `python3 -m http.server` 開，真瀏覽器手動翻一輪。
2. Headless Chromium 只驗 **DOM 狀態**（當前章、正在播哪支影片、字幕是否 `display:none`），不看像素。
3. 推 `main` 後 `curl -sI` 抓根、`/arrows/`、一張圖、一支片，確認 200；`?cb=$RANDOM` 破快取。
4. 手機實機開一次（自動播放與直式版面）。

## 步驟

- [ ] 跑完 c2–c8 的 `spreads` 與 `clips`（`arrows_pipeline.py all --ids c2` … 一章一章看）
- [ ] 重編碼素材到發布尺寸（加到 pipeline 的 `publish` 階段）
- [ ] `arrows/template.html` + `scripts/build_arrows.py`
- [ ] 章節標題疊字、字幕、鍵盤／捲動／點擊三種觸發
- [ ] 首頁兩本書選單
- [ ] 本機驗 → 推 main → Pages 建置 → curl 驗上線 → 手機驗
- [ ] `todo.md`、`README.md` 更新

## 風險

- 三段片之間的接點：turn 的結尾與 rise 的開頭都是「空白老書」，但兩支片各自生成，亮度／紙張細節會有微差；用 0.5–0.8 秒淡入蓋過即可，`arrows_compose.py` 已驗證可接受。
- 自動播放政策：必須 muted；第一次互動後才允許有聲（本書無聲，無影響）。
- 素材總量：先壓縮再推；GitHub 單檔 <100 MB、repo 建議 <1 GB，目前遠低於此。
