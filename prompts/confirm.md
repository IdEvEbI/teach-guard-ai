# 确认草稿

- **版本**：v0.1
- **用途**：根据原始逐字稿与画面词表，列出需要维护者确认的条目。不是评课，不打分。

只返回一个 JSON 对象。不要改逐字稿原文。

## 专名

对照 `transcript` 与 `screen`。若稿上的词像听写错误，且画面上有更可能的专名，列入 `terms`。没有把握就不要编。

每条包含：`clock`（稿上时间）、`heard`（稿上原词）、`screen`（画面用词，没有则空字符串）、`snapshot`（如 `snapshot/00600.jpg`）。

## 开场三项（仅 `stage_first`）

若稿上没有自我介绍、班级约定或今日目标，把对应键放入 `opening_needed`：`self_intro` / `class_norms` / `today_goal`。不要猜测「下一段视频才有」。其他课型让 `opening_needed` 为空数组。

## 输出

```json
{
  "terms": [
    {
      "clock": "00:10:10",
      "heard": "CRT决策数",
      "screen": "CART决策树",
      "snapshot": "snapshot/00600.jpg"
    }
  ],
  "opening_needed": ["self_intro", "class_norms", "today_goal"]
}
```
