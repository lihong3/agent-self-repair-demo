# Agent Self-Repair Demo

一个可运行的“评测驱动的多 Agent 自修复构建系统”Demo。它把自然语言目标拆解为需求、架构、测试、代码、评测和修复流程，并输出可审计的构建报告。

## 核心能力

- 需求分析 Agent：把自然语言目标转成结构化需求。
- 架构 Agent：生成最小可运行模块设计。
- 测试设计 Agent：生成 `unittest` 测试文件。
- 代码 Agent：生成业务代码。
- 评测 Agent：自动运行测试并保存结果。
- 修复 Agent：根据失败信息进行定向修复。
- Token 预算记录：记录每个 Agent 的输入、输出和粗略 token 消耗。

## 快速运行

```bash
python self_repair_agents.py --clean
```

默认会生成 `.agent_build/` 目录，并在第一轮故意注入一个字段名缺陷，用于演示自动评测和修复闭环。

## 自定义目标

```bash
python self_repair_agents.py --clean --goal "构建一个客户线索管理模块，支持新增线索、更新状态、查询线索"
```

## 不注入初始缺陷

```bash
python self_repair_agents.py --clean --no-seed-bug
```

## 接入 OpenAI SDK

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key"
python self_repair_agents.py --clean --use-openai --model gpt-5.5
```

## 输出文件

运行后会在 `.agent_build/` 下生成：

- `01_requirements.json`
- `02_architecture.json`
- `app.py`
- `test_app.py`
- `latest_eval.txt`
- `repair_round_1.md`
- `report.json`
- `summary.md`

## 项目价值

这个 Demo 展示了一个完整的 Agent 构建闭环：从需求拆解开始，到代码生成、自动评测、错误归因、局部修复和报告输出结束。它适合用于说明 Agent 系统在提高评估通过率、降低调试轮次、控制 token 预算方面的实际价值。

## 04 具体成果描述

我使用 Agent 构建了一个可运行的“评测驱动自修复开发系统”。用户输入自然语言目标后，系统会由多个 Agent 协作完成需求拆解、架构设计、测试生成、代码生成、自动评测和失败修复。默认示例会构建一个客户线索管理模块，并故意注入一次字段名错误，随后由评测 Agent 捕获失败信息，再由修复 Agent 定向修改代码，最终重新运行测试并输出通过结果。

运行 `python self_repair_agents.py --clean` 后，系统会生成 `.agent_build/` 目录，其中包含可执行应用代码、单元测试、评测日志、修复记录和最终报告。这个成果体现了 Agent 在自动化软件构建中的实际效果：把模糊需求转为可验证代码，用测试结果驱动迭代，并留下完整审计记录。
