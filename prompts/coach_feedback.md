# 提升建议

- **版本**：v0.6.1
- **用途**：把结构与概念观察收成可执行建议。不打分。

## 分栏

- `must_fix`：合格线，本段必须改。每一条都必须有 `clock`、`quote` 与 `force`（`design` / `communication` / `expression`）。没有摘句的条目不要输出。改法用完整句子。
- `nice_to_have`：水平线，参考调整。可以没有摘句（例如时长观察），有摘句更好。不要猜测共屏有没有翻页；画面主体是否长时间未推进由程序写入水平线。
- `questions.rhetorical`：设问。老师自问自答、用来带方向。开场里「你觉得……」紧接着自己讲下去，写这里，不要写进 `specific`。
- `questions.specific`：具体提问。有对象、有可答内容，并且老师停下来等学员。不要把空问、设问算进来。
- `questions.empty`：空问，只计无法具体作答的句子，如「听懂了吗」「能跟上吧」「有没有问题」。不要把口头禅「是吧」「是不是」算进来。

不要输出 `playback`。不要输出 `asr_suspects`。不要判断学员有没有回答。

设问不要因为间隔 0 秒写成沟通力必须改。空问只有高频敷衍检测时才写入沟通力合格线。

言行触线只写在 `conduct`，不要重复写进 `must_fix`。四个数组分别是：`vulgar`、`disparage_student`、`disparage_course`、`disparage_teacher`。用户 JSON 的 `wait_seconds` 是留白下限；是否达到留白由程序按时间轴计算。

## 输出

只返回一个 JSON 对象，不要 Markdown 围栏，不要解释：

```json
{
  "summary": "两三段完整、规范的句子。点明最值得改的是设计、沟通还是表达。禁止电报体。",
  "delivery": "学员听完应带走什么（完整的一句话）。",
  "coverage": "本段实际覆盖了课型的哪一部分。阶段第一课用完整中文写给老师看。不要写出内部代号。",
  "structure": {
    "modules": [
      {
        "title": "模块名",
        "start": "00:00:00",
        "end": "00:05:00",
        "note": "该模块口头在做什么。"
      }
    ],
    "why": "口头 Why，没有则空字符串。就业关系须落到稿上的具体说法。",
    "what": "口头 What。",
    "how": "口头 How。",
    "structure_note": "结构是否立住、主线是否清楚；用完整句子。",
    "learn_what": [
      {
        "layer": "chain",
        "status": "partial",
        "note": "培养链与就业关系讲到了哪一步。",
        "clock": "00:04:15",
        "quote": "可选摘句"
      },
      {
        "layer": "outcome",
        "status": "missing",
        "note": "阶段末成果是否让学员看见。",
        "clock": "",
        "quote": ""
      },
      {
        "layer": "days",
        "status": "covered",
        "note": "各天预期讲了哪些。",
        "clock": "",
        "quote": ""
      }
    ]
  },
  "must_fix": [
    {
      "item": "缺口名称",
      "force": "design",
      "clock": "00:12:34",
      "quote": "逐字稿原句",
      "fix": "下次共屏上怎么改。今日目标要写清今天学什么、解决什么问题。"
    }
  ],
  "nice_to_have": [
    {
      "item": "观察名称",
      "clock": "00:12:34",
      "quote": "可选摘句",
      "suggestion": "参考调整的做法。"
    }
  ],
  "questions": {
    "rhetorical": [
      {
        "clock": "00:15:56",
        "quote": "你觉得这三大类算法的评估规则一样吗"
      }
    ],
    "specific": [
      {
        "clock": "00:12:34",
        "quote": "具体提问原句"
      }
    ],
    "empty": [
      {
        "clock": "00:25:33",
        "quote": "能跟上我思路吧"
      }
    ]
  },
  "conduct": {
    "vulgar": [],
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

`must_fix` 可以为空数组。不要为了凑条数而编造摘句。`learn_what` 仅 `stage_first` 需要三层；其他课型输出空数组。
