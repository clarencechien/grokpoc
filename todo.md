# TODO — 草船借箭（story 2）

_最後更新：2026-09-15。接手前先讀 `arrows/PIPELINE.md`，網頁部分讀 `arrows/WEB-PLAN.md`。_

## 現況

- ✅ 風格定案：老書破頁 + Q 版紙偶，90° 桌曆式開合，由下往上翻。
- ✅ 參考圖（定裝表、空白母版、闔上封面）與封面、c1 跨頁完成並核對。
- ✅ 轉場機制驗證：翻頁片（grok 首格）+ 收折片倒放（升起）+ 環境片，ffmpeg xfade 串接；demo_book.mp4。
- ✅ 整條線收成 `scripts/arrows_pipeline.py`（refs/sheets/spreads/clips/compose/check），可續跑、可 dry-run。

## 待辦

- [ ] c2–c8：`python3 scripts/arrows_pipeline.py all --ids cX`，一章一章用眼睛核對（人數、表情、書不變）。
- [ ] 各章 prompt 補表情與道具描述（現有 c2–c8 prompt 是舊版措辭，先跑一章看再調）。
- [ ] 網頁：照 `arrows/WEB-PLAN.md`（template + build 腳本 + 首頁選單 + 發布壓縮 + 驗證）。
- [ ] `lessons-learned.md` 補本輪結論（grok-learned.md §11–15 已寫）。

## 已知小瑕疵（可後補）

- 收折片裡桌子、燈籠沒跟人物一起倒下（倒放時比人先出現）。
- 翻頁時頁背空白；船在翻頁中有輕微滑動。
- 封面稻草兵五個（要求四個）、立於前頁而非船上。
