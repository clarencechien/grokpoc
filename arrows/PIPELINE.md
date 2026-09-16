# 草船借箭 · 立體繪本 pipeline 交接手冊

給下一個接手的人（或 agent）。照這份做，不用重走我們踩過的坑。

## 一句話

`story/red-cliff-arrows.json` 是唯一真相；`scripts/arrows_pipeline.py` 照它分階段生素材並自我檢查；`scripts/arrows_compose.py` 把素材串成書。

## 物件定義（別改，除非整本重做）

- 一本**傳閱多代的 A3 橫式老書**：褪色靛藍布面、泛黃起斑的羊皮紙色卡紙、撕裂毛邊缺角，**內頁與書封切齊**。
- **開 90°，像桌曆**：遠頁立起、前頁平放，鉸鏈是橫貫畫面中央的一條線。翻頁 = 前頁由下緣抬起、繞鉸鏈往後翻。
- 人物是 **chibi 紙偶**（頭約三分之一高、大圓眼），表情用幾筆墨線指定。
- 鏡位：正面略俯；燈：左上暖燈、房間冷藍。所有素材都從同一張母版繼承這些。

## 階段與檔案

| 階段 | 產出 | 怎麼來 |
|---|---|---|
| `refs` | `ref_cast.jpg` | image_gen：五個角色排排站的定裝表 |
| | `ref_spread_blank.jpg` **母版** | image_gen：空白的老書、90° |
| | `ref_cover_closed.jpg` | image_edit 自母版：闔上 |
| `sheets` | `cast/<slot>.jpg`、`cast/sheet_<id>.jpg` | ffmpeg 裁切定裝表，每場景只拼該場景的人 |
| `spreads` | `<id>.jpg` | image_edit [母版, 場景小表]：只加紙雕，書不動 |
| `clips` | `<id>_turn.mp4` | image_to_video 首格 = `<id>.jpg`：前頁翻起到空白 |
| | `<id>_collapse.mp4` → `<id>_rise.mp4` | 收折片倒放 = 空白頁上紙雕升起（首尾都被釘住） |
| | `<id>_ambient.mp4` | 一個環境動作（`video.beat`） |
| `compose` | `book.mp4` | ambient → turn → rise → ambient …，xfade 0.8s |
| `check` | `_check/*_sheet.jpg` + 表格 | 存在／尺寸／時長；逐格對照圖給人看 |

## 標準流程

```bash
export PATH="$HOME/.grok/bin:$PATH"     # grok login --device-auth 已完成
python3 scripts/arrows_pipeline.py check                  # 現況
python3 scripts/arrows_pipeline.py refs                   # 生三張參考圖 → 用眼睛看
python3 scripts/arrows_pipeline.py sheets
python3 scripts/arrows_pipeline.py spreads --ids c2       # 一章一章看：數人頭、看表情、看書有沒有被動到
python3 scripts/arrows_pipeline.py clips   --ids c2
python3 scripts/arrows_pipeline.py compose --ids cover,c1,c2
python3 scripts/arrows_pipeline.py check   --ids c2
```

- 每階段跳過已存在的輸出；要重做加 `--force`。
- `--dry-run` 印出所有 prompt，不呼叫任何東西。先跑一次確認組裝正確。
- grok 一次呼叫 1–3 分鐘；長工作用 `setsid nohup … & disown` 放背景，用檔案存在與否判進度，**別等 log**。

## 每章要寫的欄位（story JSON）

```json
{ "id": "c2", "title": "…", "text": "中文內文",
  "prompt": "紙雕內容（英文；把表情寫進去：stern / gentle smile / terrified）",
  "cast_list": ["zhuge", "zhouyu", "lusu"],
  "only": "exactly THREE figures: …; nobody else",
  "sheet": "cast/sheet_c2.jpg",
  "video": { "beat": "一個環境動作，一句" } }
```

## 六條規則（血淚）

1. **先看再生**。母版錯，整本都錯。每張參考圖、每張跨頁都要用眼睛核對再往下。
2. **一次只改一件事**。先生攤開的書，再放紙雕；先生跨頁，再翻頁。同時要三件事，模型不是糊成一團就是丟掉一件。
3. **參考圖裡只放該場景的人**。文字白名單擋不住整表複製；表上沒有的人它就無從搬。
4. **形容詞不夠，要畫面座標和排除條件**。「上緣裝訂」會被畫成左翻書；要寫「縫線橫貫畫面頂緣、左右不得有書脊」。
5. **grok 只釘首格**。翻頁從跨頁生（動作在訓練資料裡，它會翻）；揭露用收折片倒放，首尾都是我們的圖。720p 要顯式指定，預設 480p。
6. **別用會匹配到自己 shell 的 pattern 去 pkill**。會把自己的指令一起殺掉，改動沒寫進去。

## 上線與驗證（別省）

- **素材換版一定要換 URL**。每次重生寫回的都是同一組檔名（`c3.jpg`、`c5_turn.mp4`…），瀏覽器就拿舊快取，畫面會變成幾章新幾章舊。`scripts/build_arrows.py` 已把每個素材蓋上內容指紋（`c3.jpg?v=<sha1前10碼>`），換了 bytes URL 就一定換；根目錄 `index.html` 的兩張書封縮圖也要跟著蓋。
- **驗證看 content-length，不要只看 HTTP 200**。GitHub Pages 的舊檔一樣回 200。逐檔比對線上 `Content-Length` 與本機 `stat -c%s`，全部相符才算上線完成。
- **重新壓縮前先刪掉 `*.orig.*`**。`stage_publish` 會保留 `<name>.orig.*` 原檔；殘留的舊備份會被再壓一次蓋回新素材。

## 下次的 `verify` 階段（設計已校準，尚未實作）

`check` 現在只做存在／尺寸／時長並吐對照圖給人看。校準過的下一步（細節與實測表在 `grok-learned.md` §16）：

1. 純程式指標先跑：ffprobe、每格對空白母版的距離（翻頁片末段要收斂到 0）、動作能量（最後 1 秒趨近 0）、色溫統計。
2. 過了才叫裁判：`grok --always-approve -p '… read_file <對照圖> … answer ONLY with one JSON object {…}'`，**只讓它回計數與幀號**，比對寫在 code（`figures_total == len(cast_list)` 等）。它數人頭準，叫它下結論會錯。
3. 針對已知缺陷各寫一題（空白頁是否在可見人物前升起、背景是否畫了人、同裝扮是否兩個）；通用問法抓不到時間軸上的語意錯。
4. fail → 重生，最多三次，全部保留並附證據；三次都不過才標給人。裁判會誤判，不能自動刪。
5. 若改打 xAI REST（`grok-imagine-video-1.5` 有 `last_frame`），翻頁片與升起片兩端都能釘住，`rise` 不用再倒放，「末格是否空白／是否本章」兩類檢查直接消失。

## 已知未解 / 可再調

- 掀頁靜圖（矩形硬卡繞鉸鏈翻到一半）grok image_edit 三次都畫不出來；不需要它，別再試。
- 翻頁時頁背是空白，實體書兩面都有內容；影響不大。
- 有時稻草兵數量、道具位置會偏離；靠 `only` 的計數語言與單一修改（如 `fix_fan`）補。
- 若改用能釘末格的模型（OpenRouter 上的 Veo 3.1 Lite / Seedance），`clips` 階段可把 turn 的末格釘成下一章跨頁，省掉 rise；`scripts/or_gen.py` 有現成呼叫。

## 相關檔案

- `scripts/arrows_gen.py` — grok CLI 的低階包裝（image_gen / edit / multi-edit / video，720p 固定）
- `scripts/clip_frames.py` — 抽格對照圖（需系統 ffmpeg；Playwright 那份讀不了 mp4）
- `scripts/or_gen.py` — OpenRouter 路線（Nano Banana 2 + Veo 3.1 Lite 首末格）
- `grok-learned.md`、`lessons-learned.md` — 工具與流程的完整筆記
