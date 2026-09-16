# 草船借箭 · 自動重驗 + 互動審片台 計劃

目標：下次再生一本書，不再由人逐章逐格看。生成 → 程式檢查 → 裁判 → 不合格自動重生（最多三次）→ 只有被標紅的才給人看；人看的地方是一個網頁，在 Claude Code web 裡就能開，按一個鈕就把該素材丟回 queue 重生。

校準數據與外部查證在 `grok-learned.md` §16；這份只講怎麼做。

---

## 0. 先講可行性（查證過的事實）

| 問題 | 答案 | 依據 |
|---|---|---|
| 網頁從哪裡開？ | Claude Code 的 **Artifact**：發佈到 claude.ai、預設私有、session 裡給連結就能開，手機也能看 | Artifact tool |
| 網頁能載 GitHub Pages 上的圖／片嗎？ | **不能。** Artifact 的 CSP 只放行幾個 CDN 的 script；圖片、影片、fetch 一律擋。素材要**隨網頁一起發佈**成 supporting files（同源就能用） | Artifact 頁面規約 |
| 素材放得下嗎？ | 一版 64 MB、單檔 15 MB、最多 255 個檔。對照圖 ~60 KB、720p 片 ~0.5–0.8 MB；9 章 × 4 種片 × 3 次 ≈ 108 支片 ≈ 60 MB —— **剛好，所以每輪只帶當前候選，舊的丟掉** | 同上 |
| 影片在網頁裡能播嗎？ | 使用者的真瀏覽器有 H.264，能播；容器裡的 Chromium 不能，所以我驗 DOM 不驗播放 | 已踩過 |
| 按鈕怎麼碰到容器？ | 網頁**碰不到**容器（沒有 inbound）。反過來：網頁用 `artifact` capability 把 queue 寫回自己（重新發佈一版），這個 session **watch** 著該 artifact，republish 會喚醒 session；session 讀回 `queue.json`、跑重生、再發佈新版 | artifact-capabilities 規約、`watch_url` |
| session 睡了怎麼辦？ | 容器閒置會被回收，但 republish 喚醒 / `send_later` 排程都能把它拉起來；grok 登入曾經撐過一次容器重啟 | 已踩過 |
| 誰按都算？ | artifact 預設私有；`artifact.publish` 以按的人的身分寫。若之後分享出去，read-only 的人會收到 `not_writer`，按鈕要隱藏 | 規約 |
| 裁判用誰？ | 三者互補，見 §2.2。沒有模型吃得下 mp4，一律先抽格拼對照圖。grok CLI 的 `read_file` 不用另外的 key；Claude 讀 jpg/png/PDF 但**不讀 mp4**；兩者都是**計數可靠、下結論不可靠** | §16、§2.2 |
| 還要不要 xAI API key？ | 可選。REST 的 `grok-imagine-video-1.5` 有 `last_frame`，翻頁片／升起片兩端都能釘住，`rise` 不用倒放，「末格是否空白／是否本章」兩類檢查直接消失 | docs.x.ai |

結論：**做得到**，而且不需要任何新服務。唯一沒實測的是「網頁按鈕 → session 被喚醒」這一段，Phase 0 就是拿一個只有一個按鈕的頁面去驗它。

---

## 1. 迴圈

```
for unit in units:                      # cover, c1 … c8
  for kind in [spread, turn, collapse→rise, ambient]:
    for attempt in 1..3:
      gen(unit, kind, attempt)          # 現有 stage：image_edit / image_to_video
      sheet  = contact_sheet(fps=2)     # 12–20 格，ffmpeg
      m      = metrics(...)             # 純程式（§2.1）
      if not m.ok: record(fail=m); continue
      j      = judge(sheet, kind)       # VLM 只回 JSON 計數與幀號（§2.2）
      ok     = compare(m, j, story)     # 判斷寫在 code（§2.3）
      record(attempt, ok, evidence=(sheet, m, j))
      if ok: adopt(attempt); break
    if not ok: flag(unit, kind)         # 三次都不過 → 網頁標紅、附三次證據
publish_console()                       # §3
```

原則：
- **fail 不刪**。三次候選全留，人可以在網頁上挑一支「其實可以」的採用。
- **程式指標先跑**，過了才問 VLM（一次 1–4 分鐘，跟生成同量級，不要浪費）。
- **每踩一個坑加一題**，題目住在 story JSON 的 `checks` 裡，像 regression test。

## 2. `verify` 階段（`scripts/arrows_pipeline.py` 新增）

### 2.1 純程式指標（零誤判、免費）

| 指標 | 用在 | 判準 |
|---|---|---|
| 存在、大小、ffprobe 解析度／時長 | 全部 | 1280×720、6 或 10 s（已有） |
| 每格對空白母版 `ref_spread_blank.jpg` 的平均像素距離 | turn | 最後 1 s 的距離 < 閾值（結尾必須空白） |
| 每格對本章跨頁的距離 | collapse（倒放前） | 首格距離 ≈ 0（首格就是跨頁）；末格對空白母版距離小 |
| 逐格動作能量 | turn / rise / ambient | 最後 1 s 趨近 0（不可以還在動）；ambient 全程能量要小（書不能動） |
| 色溫／平均色 vs 母版 | spread | 偏離超過閾值標黃（c8 曾整張偏暖） |
| 書體遮罩區域的差異 | spread | 跨頁裡書封、桌面區域對母版的差異要小（書不能被動到） |

閾值先用現有素材（已知好壞）跑一次定，寫進 story JSON 的 `verify.thresholds`。

### 2.2 誰來看：三種驗法的分工（實測，不是三選一）

**沒有任何模型能直接吃 mp4。** Claude 的 Read 工具讀 mp4 回「cannot read binary files」（實測），Claude API 也沒有原生 video input；grok 的 `read_file` 同樣只吃圖。所以 **ffmpeg 抽格拼對照圖不是繞路，是唯一的路**，這一步無論裁判換成誰都省不掉。

| 驗法 | 能看什麼 | c5 多一個人 | c8 翻頁「空白頁從人物前升起」 |
|---|---|---|---|
| **純 Python**（numpy + ffmpeg 逐格動作能量） | 連續量：動作能量、對母版距離、色溫、解析度時長 | 測不到（不是它能表達的東西） | **抓不到** —— 壞的與修正版都只有一個動作峰 |
| **grok CLI 裁判**，通用問法（「翻幾次？」） | 語意 | 數出 3 人（對），但自己的 `duplicate_costume` 欄位答 false（錯） | **抓不到**，6 格、12 格都答「翻一次，pass」 |
| **grok CLI 裁判**，針對性問法（「有沒有一格是空白頁在仍可見的人物前面？」） | 語意 | — | **抓到**，指出第 5–6 格 fail；但對修正版也答 fail → **誤判**（或該版仍有輕微同症） |
| **Claude 自己看圖**（Read tool 直接渲染 jpg/png/PDF） | 語意，不同模型的第二意見 | 讀了兩張跨頁 | 讀了 12 格對照圖，但**與 grok 同批跑，沒有先獨立記下判斷**，等於沒測到 |

結論：
1. **三者互補。** 程式指標負責連續量（結尾沒停住、解析度掉了、色溫飄了），VLM 負責語意，兩邊都不可少。
2. **通用問法沒有用。** 只有針對已知失敗模式寫的問題抓得到時間軸上的缺陷 —— 這就是 `checks` 要像 regression test 一條一條加的原因。
3. **誤判是真的。** 修正版被判 fail。所以 fail 只能重生 + 標紅，永遠不能自動刪。
4. **Claude 當裁判這條還沒乾淨測過**，Phase 1 要補一次盲測：同一批對照圖，我先獨立寫下判斷，再跟 grok 與程式指標對答案。
5. 容器裡**沒有 Anthropic API key**（`ANTHROPIC_API_KEY` 未設、`ant` CLI 未安裝）。要把 Claude 當裁判做進 pipeline（不佔 session、可平行）需要一把 key；否則只能由 session 裡的我看，但那就是在對話裡看，無法無人值守。

### 2.2.1 裁判呼叫（VLM 只回 JSON）

呼叫：`grok --always-approve -p "Look at <sheet> with read_file … answer ONLY with one JSON object {…}"`，解析最後一個 `{…}`。

每種素材一組題，全部是**計數與幀號**，不要問 pass/fail：

- **spread**：`figures_total`、`figures_by_costume`、`people_painted_into_backdrop`、`boats`、`straw_soldier_bundles`、`book_or_table_changed`
- **turn**（12 格）：`frames_blank_page_in_front_of_visible_figures`、`frames_page_mid_air`、`final_frame_empty`、`camera_moved`、`hinge_stays_horizontal`
- **collapse / rise**：`first_frame_matches_scene`、`final_frame_empty`、`figures_left_standing_in_final`
- **ambient**：`things_that_move`（列表）、`book_moved`、`figures_changed_shape`

已知缺陷各一題，寫在 story JSON：
```json
"checks": {
  "turn": ["second_page_in_front", "ends_empty", "single_flip"],
  "spread": ["cast_count", "no_painted_people", "no_duplicate_costume", "book_untouched"]
}
```

### 2.3 比對（code）

```python
ok = (j.figures_total == len(unit.cast_list)
      and not j.people_painted_into_backdrop
      and j.boats == unit.expect.boats
      and not j.frames_blank_page_in_front_of_visible_figures
      and j.final_frame_empty and m.tail_distance_to_blank < T)
```
每條規則有名字，fail 時把**規則名 + 裁判原話 + 幀號**寫進 `state.json`，網頁直接顯示。

### 2.4 檔案佈局

```
arrows/_cand/<unit>/<kind>/<attempt>.{jpg|mp4}     候選（不進 git，只進 artifact）
arrows/_cand/<unit>/<kind>/<attempt>.sheet.jpg     對照圖
arrows/_cand/<unit>/<kind>/<attempt>.json          {metrics, judge, rules:[{name, ok, why}]}
arrows/_cand/state.json                            全書總表（網頁讀這個）
arrows/assets/<unit>_<kind>.*                      採用後才複製過來（現有流程不變）
```

`state.json` 一筆：
```json
{"unit":"c8","kind":"turn","adopted":2,
 "attempts":[{"n":1,"ok":false,"failed":["second_page_in_front"],"frames":[5,6]},
             {"n":2,"ok":true}],
 "flag":false}
```

## 3. 審片台（Artifact）

### 3.1 長什麼樣

- 一個 9 × 4 的格子：列 = cover…c8，欄 = 跨頁／翻頁／升起／環境。每格一個色點：綠（採用）、紅（三次都不過）、黃（程式指標過、裁判有疑）、灰（還沒生）、藍（queue 中）。
- 點格子展開：候選 1–3 的對照圖並排、下方是影片（真瀏覽器可播）、右側是規則清單，紅的那條寫裁判原話與幀號。
- 每個候選有兩個鈕：**採用**、**重來**。重來可以勾一個已知缺陷（＝下次 prompt 加強那一條）或打一句話（＝新的一題，寫回 story JSON 的 `checks`）。
- 上方一條 queue：誰在排、誰在跑、跑完的。
- 頁面自帶當前版本的 `state.json`（inline）；素材是 supporting files：`sheets/…jpg`、`clips/…mp4`。

### 3.2 資料流

```
pipeline 跑完一輪
  → build_console.py 產 console.html + files（sheets、clips、state.json）
  → Artifact publish（同 URL 更新）
使用者按「重來 c8/turn，勾 second_page_in_front」
  → 頁面把 queue 寫進自己：artifact.publish(html 含新 queue)   ← 喚醒 session
session 醒來
  → Artifact read 該頁 → 讀出 queue
  → pipeline verify --ids c8 --kinds turn --force --hint second_page_in_front
  → 重新 build_console + publish
```

- 每輪只帶**當前候選**（≤ 3 支／格），舊候選留在容器的 `_cand/` 不上傳，控制在 64 MB 內。
- queue 項目帶 id 與狀態（queued → running → done），session 醒來先把 running 寫回去再跑，避免重複執行。
- 頁面要處理 `conflict`（session 剛好也在發佈）：不重試，等 reload。
- 若 `artifact.publish` 的 files form 不可用，退回整頁 html form（把 queue 嵌在 HTML 裡）。

### 3.3 網頁碰不到的事（要老實寫在頁上）

- 按了鈕不會立刻開始：要等 session 醒、跑 3–8 分鐘（生成 + 裁判）。頁上顯示「排隊中／執行中／預計幾分鐘」。
- 網頁看不到容器的即時 log；進度靠 session 每完成一支就 republish 一次。
- 容器被回收後 `_cand/` 會不見；採用了的素材要 commit。

## 4. 分階段

| Phase | 做什麼 | 產出 | 驗收 |
|---|---|---|---|
| **0 · 喚醒實驗** | 一個只有一顆鈕的 artifact，按下去把 `queue` 寫回自己 | 一個連結 | 使用者按一下，session 收到 republish 通知並讀到 queue 內容 |
| 1 · verify 階段 | `metrics()`、`judge()`、`compare()`、`_cand/` 佈局、`state.json`；用現有 v0/v1/v2 素材當測資把閾值定好；**補跑一次 Claude 看圖的盲測**（先獨立記判斷再對答案，§2.2 結論 4） | `arrows_pipeline.py verify` | 已知的 c5 多人、c8 第二頁都被標紅；正確素材不被誤殺（或誤殺率記下來）；盲測結果寫進 §2.2 表 |
| 2 · 審片台（唯讀） | `build_console.py`：格子、候選、規則、影片 | artifact | 九章看得到、標紅對得上 state.json |
| 3 · queue | 採用／重來鈕、queue 狀態、session 端的讀 queue → 跑 → republish | 同上 | 按重來 → 10 分鐘內新候選出現在頁上 |
| 4 · （選）API 路線 | `scripts/xai_video.py` 直接打 `/v1/videos/generations` 帶 `last_frame` | 新的 clips 階段 | rise 不再倒放；turn 末格 = 母版 |

## Phase 0 結果（2026-09-16 實測）

| 段 | 結果 |
|---|---|
| 網頁按鈕 → `artifact.publish` 把 queue 寫回頁面 | **通**，兩次都寫進去（01:40、01:42），內容完整（unit / kind / hint / 時間） |
| session 讀回 queue（`Artifact read`）→ 改狀態寫回頁面 | **通** |
| republish → 自動喚醒 session | **沒通**，兩次都沒有。第一次時訂閱還在註冊；第二次發佈回報「已註冊」仍沒醒，是使用者傳訊息才叫醒 session 去讀的 |

所以 Phase 3 的 queue 接手改成**排程輪詢**：審片期間 session 用 `send_later` 每 5–10 分鐘讀一次頁面（沒新 queue 就靜默重排、有就跑），按完等幾分鐘會被接手；頁面上寫清楚「排隊中，最久 N 分鐘內開始」。未測的第三條路：在 artifact 上留言送給 Claude 是文件上寫明的喚醒事件，若日後要即時，可以把「重來」改成引導使用者留言，或再測一次 republish 喚醒是否只在特定狀態下才發。

## 5. 要你決定的

1. 裁判用 grok（同一家模型評自己，不用 key）還是 Claude（不同模型的第二意見）？建議：**程式指標 + grok 計數**當第一線，Claude 只看被標紅的。要讓 Claude 無人值守地當裁判需要一把 Anthropic API key（容器裡目前沒有）；否則只能由 session 裡的我看，那就無法離開對話自動跑。
2. 要不要申請 xAI API key 走 `last_frame`？這會把抽卡面砍掉一半，但要付費；先用 CLI 把 Phase 1–3 做完再決定也行。
3. Phase 0 現在就做：連結給你，你按一下，我看 session 有沒有醒。
