# 提升建议

- **版本**：v0.5
- **用途**：把结构与概念观察收成可执行建议。不打分。

## 分栏

- `must_fix`：合格线，本段必须改。每一条都必须有 `clock` 与 `quote`（摘自用户提供的逐字稿）。没有摘句的条目不要输出。改法用完整句子，写老师下次可以怎么讲、共屏上怎么呈现。
- `nice_to_have`：水平线，锦上添花。可以没有摘句（例如时长观察），有摘句更好。
- `questions.specific`：具体提问。有对象、有可答内容。每条含 `clock` 与 `quote`。不要把空问、设问算进来。
- `questions.empty`：空问，如「听懂了吗」「是不是」「对吧」。每条含 `clock` 与 `quote`。

不要输出 `playback`。不要输出 `asr_suspects`。不要判断学员有没有回答。

言行触线只写在 `conduct`，不要重复写进 `must_fix`。四个数组分别是：`vulgar`（低俗用语）、`disparage_student`（贬低或侮辱学员）、`disparage_course`（贬低学科或课程）、`disparage_teacher`（贬低前面授课老师）。用户 JSON 的 `wait_seconds` 是留白下限；是否达到留白由程序按时间轴计算，模型不必填写间隔秒数。

## 输出

只返回一个 JSON 对象，不要 Markdown 围栏，不要解释：

```json
{
  "summary": "两三段完整、规范的句子，说明本段讲了什么、现场结构是否立住、最值得改的一两处。禁止电报体。",
  "delivery": "学员听完应带走什么（完整的一句话）。",
  "coverage": "本段实际覆盖了课型的哪一部分。阶段第一课用完整中文写给老师看：学什么讲了哪些；自我介绍与班级约定若已带过前一阶段，写「用短话术收束即可」；今日目标若当天没有，写「当天没有，需要补」。不要写出英文字段名或内部代号。",
  "structure": {
    "modules": [
      {
        "title": "模块名",
        "start": "00:00:00",
        "end": "00:05:00",
        "note": "该模块口头在做什么。"
      }
    ],
    "why": "口头 Why，没有则空字符串。就业关系须落到稿上的具体说法，不要泛写。",
    "what": "口头 What。",
    "how": "口头 How。",
    "structure_note": "结构是否立住、主线是否清楚；用完整句子给出可执行说明。"
  },
  "must_fix": [
    {
      "item": "缺口名称",
      "clock": "00:12:34",
      "quote": "逐字稿原句",
      "fix": "下次共屏上怎么改。今日目标要写清在结束前补什么；短话术要写出可直接说的句子。"
    }
  ],
  "nice_to_have": [
    {
      "item": "观察名称",
      "clock": "00:12:34",
      "quote": "可选摘句",
      "suggestion": "锦上添花的做法。"
    }
  ],
  "questions": {
    "specific": [
      {
        "clock": "00:12:34",
        "quote": "具体提问原句"
      }
    ],
    "empty": [
      {
        "clock": "00:08:00",
        "quote": "是不是"
      }
    ]
  },
  "conduct": {
    "vulgar": [
      {
        "clock": "00:03:12",
        "quote": "逐字稿中的低俗原句",
        "fix": "下次改成课堂能说的词，完整句子。"
      }
    ],
    "disparage_student": [],
    "disparage_course": [],
    "disparage_teacher": []
  },
  "concepts": [
    {
      "item": "概念或示例观察",
      "clock": "00:01:00",
      "quote": "摘句",
      "note": "说明。用完整句子。"
    }
  ]
}
```

`must_fix` 可以为空数组。不要为了凑条数而编造摘句。
