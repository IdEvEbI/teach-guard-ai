# 确认草稿

- **版本**：v0.4
- **用途**：根据原始逐字稿，列出阶段第一课开场三项是否当天就没有。不是评课，不打分。本步**只读逐字稿**，不读画面词表，不做稿 vs 画面专名对照。

只返回一个 JSON 对象。不要改逐字稿原文。`terms` 必须是空数组。

## 开场三项（仅 `stage_first`）

若稿上没有自我介绍、班级约定或今日目标，把对应键放入 `opening_needed`：`self_intro` / `class_norms` / `today_goal`。不要猜测「下一段视频才有」。其他课型让 `opening_needed` 为空数组。

## 输出

```json
{
  "terms": [],
  "opening_needed": ["self_intro", "class_norms", "today_goal"]
}
```
