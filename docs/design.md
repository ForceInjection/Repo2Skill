# Repo2Skill 设计文档 v1.0

**需求分析与设计文档。**

**版本**：1.0
**日期**：2026-05-13
**状态**：草案

---

## 目录

- [1. 引言](#1-引言)
- [2. 核心概念与模型](#2-核心概念与模型)
- [3. 产品定位与用户故事](#3-产品定位与用户故事)
- [4. 技能结构与组件](#4-技能结构与组件)
- [5. 执行流程](#5-执行流程)
- [6. 安全与信任框架](#6-安全与信任框架)
- [7. 多维度质量评估](#7-多维度质量评估)
- [8. 生态集成](#8-生态集成)
- [9. 技术选型](#9-技术选型)
- [10. 自举与自我进化](#10-自举与自我进化)
- [11. 开发路线图](#11-开发路线图)
- [12. 附录 A：关键文件示例](#12-附录-a关键文件示例)
- [13. 参考文献](#13-参考文献)

---

## 1. 引言

### 1.1 背景

Agent 的快速发展催生了对可复用、可组合、可验证的"Agent 技能"的需求。Anthropic 的 Agent Skills 协议提供了标准化的技能封装格式（`SKILL.md`），但如何从海量开源仓库中高效、安全地提取出符合该协议的技能，仍是一个未被系统化解决的问题。

### 1.2 项目愿景

**Repo2Skill** 是一个遵循 Agent Skills 协议的技能包，它赋予 Agent 将任意 GitHub 仓库（或本地路径）自动转换为另一个标准 Agent 技能的能力。Repo2Skill 利用 Agent 本身的推理与交互能力，结合确定性脚本，实现从仓库到技能的全生命周期管理：解构、提取、组装、多级安全验证、质量评估，并输出附带评估报告的技能文件夹。

本设计深度参考了论文《Automating Skill Acquisition through Large-Scale Mining of Open-Source Agentic Repositories: A Framework for Multi-Agent Procedural Knowledge Extraction》[1] 中提出的四元组技能模型、渐进式披露架构（Progressive Disclosure）、四级安全验证框架（G1–G4）、双塔检索（Dense Retrieval + Cross-Encoder Reranker）识别方法以及多维度评估体系；并在此基础上借鉴 TheoremExplainAgent [2] 的多智能体协作模式，由**本设计**将其应用于提取流程自身，以确保生成技能具备工业级安全性与生态兼容性。

### 1.3 范围与非目标

**范围内**：

- 公开 Git 仓库（HTTPS 协议）或本地路径的技能提取。
- 主流语言：Python（Phase 1）、JavaScript/TypeScript、Go、Rust（Phase 4）。
- 生成符合 Anthropic Agent Skills 协议的技能文件夹。

**非目标**：

- 不处理二进制仓库或纯数据集仓库。
- 不自动合并上游 PR 或修改原仓库。
- 不替代人工代码审计，G1–G4 旨在辅助而非替代专家判断。

---

## 2. 核心概念与模型

### 2.1 技能的四元组定义

本节基于论文 [1] 中的形式化模型定义技能四元组 `S = (C, π, T, R)`，每个组件在提取过程中的映射如下表所示：

| 组件                | 含义               | 在提取中的映射                           |
| ------------------- | ------------------ | ---------------------------------------- |
| **C** (Conditions)  | 适用条件与触发场景 | 入口点、CLI 命令、函数前置条件、文件模式 |
| **π** (Policy)      | 核心策略与动作序列 | 函数体、脚本逻辑、工作流步骤、依赖声明   |
| **T** (Termination) | 终止标准与成功判定 | 输出格式、返回值、状态码、副作用检测     |
| **R** (Interface)   | 标准化调用接口     | 参数定义、I/O 格式、允许的工具列表       |

提取过程中的核心任务就是将仓库中的可执行单元映射到此模型，并将其编译为符合 Agent Skills 协议的 `SKILL.md` 文件。SSL [5] 的实验（Skill Discovery MRR@50 从 0.649 提至 0.729）表明将文本型技能显式分解为调度–结构–逻辑三层信号可显著提升下游检索与审查效果，这为本设计采用 `(C, π, T, R)` 显式解耦的结构化提取提供了独立证据。

### 2.2 安全验证体系 (G1–G4)

论文 [1] §7 指出，一项针对社区分发技能的系统性调研发现 **26.1%** 的技能存在数据外泄或权限提升等安全漏洞。为此验证流程采用论文的四级门控，逐级递进：

- **G1 静态安全扫描**：自动检测危险模式（`eval`、`exec`、网络调用、文件删除等）及混淆代码。
- **G2 语义安全审查**：LLM 驱动的指令-意图对齐检查、隐藏 prompt 注入检测、元数据一致性验证。
- **G3 行为沙箱验证**：在隔离容器中运行技能，进行网络隔离、文件系统限制、资源监控以及预配置依赖环境。
- **G4 权限清单校验**：对照技能声明的 `allowed-tools` 与实际行为进行比对，确保无越权。

每个级别的结果汇入最终验证报告，并决定技能的 Trust Level（见 [§6.1 Trust Level 计算](#61-trust-level-计算)）。SSL [5] 在 Risk Assessment 上的 macro-F1 提升（0.409 → 0.509）不限于文本表征，而源于结构化目标的明确提出，为 **本设计** 将 `skill.yaml` frontmatter 与 `SKILL.md` 正文解耦的做法以及 G1–G4 针对结构化字段设计专项规则提供直接理论依据。

### 2.3 分层角色架构 (Script + Agent 混合)

论文 [1] §3 将提取流程定义为三阶段流水线：**仓库结构化分析 → 基于密集检索的语义技能识别 → SKILL.md 标准化翻译**。**本设计**在此流水线基础上，借鉴 TheoremExplainAgent [2] 的多智能体模式，将三个阶段重组为可协作的角色实体。注意：**Structurer 为确定性脚本角色，不涉及 LLM 推理**；真正的智能体角色为 Extractor 与 Reviewer。Extractor 在识别候选技能时遵循论文 §3.2 所述的双塔检索 + Cross-Encoder 重排二阶段方法，按 **Recurrence / Verification / Non-obviousness / Generalizability** 四项准则筛选。

| 角色           | 职责                                             | 执行主体                  |
| -------------- | ------------------------------------------------ | ------------------------- |
| **Structurer** | 仓库克隆、AST 解析、依赖图构建、元数据提取       | 确定性脚本 `structure.py` |
| **Extractor**  | 技能边界识别、四元组标注、候选技能生成与描述     | Agent（利用推理能力）     |
| **Reviewer**   | 语义保真审查、幻觉检测、G1–G2 安全扫描、质量评级 | Agent + 脚本混合          |

三个角色在 Agent 的协调下依次执行，通过清晰的输入/输出 JSON 进行交接。

### 2.4 渐进式披露架构

论文 [1] §2.2（Table 1）要求 `SKILL.md` 实现**渐进式披露（Progressive Disclosure）**，以最小化上下文消耗。生成的技能必须遵循该三级组织方式：

| 层级    | 内容                                                  | 加载时机       | Token 预算 |
| ------- | ----------------------------------------------------- | -------------- | ---------- |
| Level 1 | YAML frontmatter：`name`、`description`、`version` 等 | 启动预加载     | 30–100     |
| Level 2 | 过程性指令：工作流、最佳实践、分步逻辑                | 激活时注入     | 200–5,000  |
| Level 3 | 辅助资产：脚本、参考文档、模板、schema                | 按需由脚本读取 | 不设上限   |

`assemble.py` 在组装时将技能摘要分别映射到 frontmatter（Level 1）、`SKILL.md` 正文（Level 2）、`scripts/` + `references/` + `templates/` 目录（Level 3）。该「鸟瞰 → 主题分支 → 原文」的逐层导航策略与 Corpus2Skill [4] 「距离背景下由 Agent 主动导航层级摘要树」的设计一致，因此技能套件运行时同样对 Agent 暴露「技能列表 → 子技能 → Level 2/3 资产」的导航结构。

### 2.5 技能套件 (Skill Suite)

实际仓库往往包含多个职责相对独立但联系紧密的模块（例如 `data-pipeline` 仓库同时具备数据清洗、特征工程、训练与部署四条子功能线）。将这样的仓库强行压缩为单一 `SKILL.md` 会造成：

- Level 2 指令超出 Token 预算（>5,000），违反渐进式披露原则。
- `description` 字段语义臃肿，导致 Agent 触发时的误匹配率升高。
- `allowed-tools` 并集爆炸，安全边界变模糊。

因此**本设计**允许将一个仓库映射为**一组相关联的技能（Skill Suite）**，同时通过 SkillNet 本体（详见 [§8.3](#83-skillnet-本体标注)）显式声明技能间关系。该策略与 SkillFoundry [3] 的「领域知识树 → 高价值分支挖掘 → 可执行技能包」管道同源，区别在于本设计以单一仓库为领域范围，SkillFoundry 以多异构科学资源（论文/API/脚本/notebook）为范围。

**套件触发准则**（Extractor 在步骤 2 应用）：

| 触发条件                                                       | 动作                       |
| -------------------------------------------------------------- | -------------------------- |
| 候选技能数 > 1 且目标联合 Level 2 Token > 4,000                | 转为套件模式               |
| 仓库 `pyproject.toml` / `package.json` 声明多入口点            | 每个入口点作为独立技能候选 |
| 依赖图中存在两个或以上互不引用的中心模块                       | 模块级切分                 |
| 候选技能 `allowed-tools` 差异显著（并集 > 2 倍任一者自身大小） | 按安全边界切分             |
| 单一技能可覆盖所有语义                                         | 保持单技能模式             |

**套件内部的技能关系**（写入各 `skill.yaml` 的 `ontology.relations`）：

| 关系类型               | 语义                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| `depends-on`           | 调用时必须先加载目标技能（如 `deploy-skill` 需 `build-skill` 的产物） |
| `composes`             | 当前技能是套件的组成部分，指向套件聚合技能名                          |
| `bundled-with`         | 同套件中的对等技能，建议一起安装                                      |
| `requires-output-from` | 产出消费关系，Agent 可据此自动串联调用                                |

套件类输出的目录布局见 [§4 技能结构与组件](#4-技能结构与组件)，执行流程增量见 [§5.4 套件模式执行调整](#54-套件模式执行调整)。

---

## 3. 产品定位与用户故事

### 3.1 产品形态

Repo2Skill 本身是一个 **Agent Skill**，提供标准 `SKILL.md` 及配套脚本。依据 Anthropic Agent Skills 协议，Agent 加载该技能后，当用户描述类似"将此仓库转换为技能"的意图时，Agent 将根据 `SKILL.md` 中的 `description` 字段自动激活 Repo2Skill 并要求用户提供仓库 URL。此外，提供轻量 CLI 包装器（`repo2skill <github-url>`），允许在非对话环境中调用（用于批量处理或 CI/CD）。

### 3.2 用户故事

| 角色           | 典型场景                                                   | 期望结果                                                                                      |
| -------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Agent 使用者   | 对 Agent 说："将这个 GitHub 仓库变成可用的 Skill"          | Agent 加载 Repo2Skill，自动分析仓库，展示识别出的候选技能，用户选择后生成附带验证报告的技能包 |
| 开源维护者     | 为自己的工具仓库生成标准 Skill，准备公开发布到技能注册中心 | 生成经过 G1–G4 全部验证的技能，附带 Trust Level 标记，可直接分发                              |
| 平台构建者     | 批量处理数百个仓库，构建公共技能库                         | 提供 `--non-interactive` 模式，自动采用默认选项，输出技能包并附带评估分数                     |
| 技能生态管理员 | 监控仓库更新，自动触发技能升级                             | 与 `skill-mem` 集成，当上游仓库发布新版本时自动重新提取、对比差异、提出修改建议               |

---

## 4. 技能结构与组件

Repo2Skill 自身的技能包文件树如下。所有运行时产物（如 `verification/` 目录与生成的 `skill.yaml`）写入用户指定的输出路径，不污染 Repo2Skill 自身目录：

```text
repo2skill-skill/
├── SKILL.md                     # 技能入口，完整流程描述
├── scripts/
│   ├── requirements.txt         # Python 依赖清单
│   ├── structure.py             # Structurer：仓库分析，输出 analysis.json（四元组格式）
│   ├── assemble.py              # 将确认后的技能摘要编译为标准 SKILL.md 及文件夹
│   ├── audit_g1.py              # G1 静态安全扫描
│   ├── audit_g2.py              # G2 语义审查辅助（生成检查提示，实际审查由 Agent 执行）
│   ├── audit_g3.py              # G3 沙箱验证（Docker 隔离执行）
│   └── audit_g4.py              # G4 权限清单校验
├── templates/
│   ├── skill.md.j2              # SKILL.md 模板（含 Security 章节）
│   ├── skill.yaml.j2            # skill.yaml 清单模板
│   └── verify_script.py.j2      # G3 验证任务脚本模板
└── examples/
    └── sample_repo/             # 自测用简单仓库（可选）
```

生成技能的目录中会追加：

```text
<output-skill>/
├── SKILL.md
├── skill.yaml
├── scripts/ ...
├── references/                  # Level 3 参考文档（渐进式披露）
├── templates/                   # Level 3 代码/配置模板
└── verification/
    ├── g1_report.json
    ├── g2_report.json
    ├── g3_report.json
    ├── g4_report.json
    └── report.json              # 多维度质量评估汇总
```

**套件模式输出布局**（触发条件见 [§2.5](#25-技能套件-skill-suite)）：将单个仓库映射为具备统一元数据的技能群，每个子技能为独立技能包，由顶层 `suite.yaml` 声明套件信息与关系谱：

```text
<output-suite>/
├── suite.yaml                   # 套件元数据：id、成员列表、关系图、共享 trust-level
├── README.md                    # 套件总览，面向人类使用者
├── data-cleaning/               # 子技能 1
│   ├── SKILL.md
│   ├── skill.yaml               # 内含 ontology.relations 指向其他子技能
│   ├── scripts/ ...
│   └── verification/
├── feature-engineering/         # 子技能 2
│   └── ...
├── training/                    # 子技能 3
│   └── ...
├── deployment/                  # 子技能 4
│   └── ...
└── verification/
    └── suite_report.json        # 聚合所有子技能的评分与关系完整性校验
```

`suite.yaml` 结构示例：

```yaml
suite-id: data-pipeline-suite
version: 1.0.0
source: https://github.com/<owner>/data-pipeline
skills:
  - id: data-cleaning
    path: ./data-cleaning
  - id: feature-engineering
    path: ./feature-engineering
  - id: training
    path: ./training
  - id: deployment
    path: ./deployment
relations:
  - from: feature-engineering
    to: data-cleaning
    type: requires-output-from
  - from: training
    to: feature-engineering
    type: requires-output-from
  - from: deployment
    to: training
    type: depends-on
trust-level: L3 # 套件共享的信任等级，取成员中的最低值
```

各组件输入/输出定义：

| 组件           | 输入                                    | 输出                                              | 触发条件           |
| -------------- | --------------------------------------- | ------------------------------------------------- | ------------------ |
| `structure.py` | GitHub URL 或本地路径                   | `analysis.json`（包含四元组标注、依赖图）         | 流程第一步         |
| `assemble.py`  | 用户确认的技能摘要 JSON + 输出路径      | 标准技能文件夹（`SKILL.md`、`skill.yaml`、脚本）  | 用户确认候选后     |
| `audit_g1.py`  | 生成的技能文件夹路径                    | `g1_report.json`（风险项列表、分数）              | 组装完成后自动调用 |
| `audit_g2.py`  | `analysis.json` + 技能文件夹            | 生成语义审查提示（供 Agent 使用）                 | G1 通过后调用      |
| `audit_g3.py`  | 技能文件夹 + 测试用例描述（Agent 生成） | `g3_report.json`（执行日志、成功/失败、资源用量） | 用户授权后调用     |
| `audit_g4.py`  | 技能文件夹 + G3 执行轨迹                | `g4_report.json`（权限比对结果）                  | G3 通过后调用      |

---

## 5. 执行流程

以下为 Agent 加载 Repo2Skill 后的标准交互流程（以处理 `https://github.com/<owner>/<repo>` 为例）。

### 5.1 交互式流程

```text
步骤 1: 解构 (Structurer)
  ▶ Agent 执行: python scripts/structure.py https://github.com/<owner>/<repo>
  ▶ 输出: analysis.json（包含函数/类列表、四元组预标注、依赖图、README 摘要等）

步骤 2: 技能发现 (Extractor + 用户交互)
  ▶ Agent 解析 analysis.json，利用推理能力识别出 1–5 个候选技能单元
  ▶ Agent 向用户展示候选清单：
    1. code_formatter (入口: my_tool.cli:format)
    2. config_generator (入口: my_tool.config:generate)
    ...
  ▶ 用户回复选择（如"1,3"）或自定义描述

步骤 3: 组装 (Assemble)
  ▶ Agent 将选定的技能整理为确认后的 JSON
  ▶ 执行: python scripts/assemble.py --skill-json confirmed.json --out ./my-tool-skill
  ▶ 输出: 技能文件夹，包含 SKILL.md、skill.yaml、依赖脚本等

步骤 4: G1 静态安全扫描
  ▶ 执行: python scripts/audit_g1.py ./my-tool-skill
  ▶ 输出: g1_report.json
  ▶ 若发现高危项，Agent 立即警告用户

步骤 5: G2 语义审查 (Agent 自主执行)
  ▶ 执行: python scripts/audit_g2.py（生成审查提示）
  ▶ Agent 对比原始源码与生成的技能描述，评估完整性、幻觉风险、prompt 注入
  ▶ 给出数值评级（映射规则见下文），并附解释

步骤 6: G3 沙箱验证 (需用户批准)
  ▶ Agent 先询问："需要进行沙箱验证吗？这将在 Docker 中执行生成的技能。"
  ▶ 用户同意后，Agent 根据技能功能生成一个验收测试场景（如："对 test.py 执行格式化，检查输出是否为有效 Python"）
  ▶ 执行: python scripts/audit_g3.py --skill ./my-tool-skill --test "..."
  ▶ 输出: g3_report.json（包含执行日志、资源用量、是否通过）

步骤 7: G4 权限清单校验
  ▶ 执行: python scripts/audit_g4.py --skill ./my-tool-skill --g3-log g3_report.json
  ▶ 输出: g4_report.json，确认技能未超出声明的 allowed-tools

步骤 8: 汇总与完成
  ▶ Agent 呈现最终报告，包含：
    - 生成的技能位置
    - Trust Level（基于 G1–G4 全部通过的最高等级）
    - 各维度评分
    - 建议操作（如"可安全用于生产"、"需人工审核某步骤"）
```

**G2 分数映射**：步骤 5 的语义审查输出既有类别标签也有数值分数，映射规则为：`完整 → [0.9, 1.0]`、`部分 → [0.5, 0.9)`、`存疑 → [0.0, 0.5)`。该数值写入 `skill.yaml` 的 `g2-score` 字段（kebab-case，与 [§8.1](#81-技能注册中心就绪) 一致）。

### 5.2 非交互模式

使用 `--non-interactive` 时：

- 步骤 2：自动选择所有置信度 ≥ 0.8 的候选技能。
- 步骤 6：使用预定义通用测试脚本或通过 `--skip-g3` 跳过。
- 步骤 8：最终报告写入 `verification/report.json`，不阻塞等待用户确认。

### 5.3 异常处理与回退

| 异常场景                | 默认行为                                                   |
| ----------------------- | ---------------------------------------------------------- |
| `structure.py` 克隆失败 | 终止流程，输出错误原因（网络、认证、仓库不存在）           |
| 未识别出任何候选技能    | 提示用户提供人工描述，或退出                               |
| G1 发现高危项           | 阻断流程；用户显式 `--force-continue` 后降级为 L1 信任等级 |
| G3 执行超时或非零退出   | 标记 `g3_passed: false`，生成的技能降级为 L2               |
| G4 发现越权操作         | 写入 `g4_report.json`，自动从 `allowed-tools` 中移除越权项 |

### 5.4 套件模式执行调整

当步骤 2 触发套件准则（见 [§2.5](#25-技能套件-skill-suite)）时，后续步骤按以下方式调整：

- **步骤 2+（关系标注）**：Extractor 对每对子技能评估五种关系（`depends-on` / `composes` / `bundled-with` / `requires-output-from` / `none`），输出关系图供 `suite.yaml` 使用。
- **步骤 3**：`assemble.py --suite` 一次性生成套件根目录与所有子技能，同时校验关系图无环（DAG）。如存在环，触发模块重划分提示。
- **步骤 4–7**：逐个子技能独立执行 G1–G4，报告写入各自 `verification/`。Reviewer 附加执行跨技能的**集成测试**（依据关系图中 `requires-output-from` 链路，构造端到端流水线样例）。
- **步骤 8**：生成 `verification/suite_report.json`，包含：每个子技能的多维度得分、关系完整性校验结果、套件级的 Trust Level（成员最低值）。Agent 向用户统一呈现套件摘要与可视化关系图。

---

## 6. 安全与信任框架

### 6.1 Trust Level 计算

论文 [1] §7 提出 "skills evolve through trust tiers" 的抽象概念但未给出具体等级定义。**本设计**将 G1–G4 验证结果（详见 [§2.2 安全验证体系](#22-安全验证体系-g1g4)）映射为用户可消费层面的 L0–L4 五级标签：

| Trust Level     | 验证通过要求         | 使用建议                                     |
| --------------- | -------------------- | -------------------------------------------- |
| **L0 未验证**   | 仅完成组装           | 仅供人工审查，不可自动执行                   |
| **L1 静态通过** | G1 无高危项          | 可在受限环境（无网络、只读文件系统）手动试用 |
| **L2 语义一致** | G1 + G2 评估为"完整" | 可在监控下由 Agent 调用                      |
| **L3 沙箱验证** | G1 + G2 + G3 通过    | 标准生产可用                                 |
| **L4 权限校验** | 全部 G1–G4 通过      | 最高信任，适用于自动化流水线                 |

每个生成的技能在 `SKILL.md` 和 `skill.yaml` 中明确标注当前 Trust Level。

### 6.2 安全边界

> [!IMPORTANT]
> 以下边界用于约束 Repo2Skill 自身以及它所生成/测试的技能。下文明确区分"Repo2Skill 自身"与"被测技能"两个主体。

- **写入范围**：Repo2Skill 自身的所有写入操作限定在用户指定的输出目录。
- **仓库拉取**：`structure.py` 克隆仓库时不保留凭证，仅克隆公开仓库（需认证时提示用户手动提供）。
- **沙箱执行**：`audit_g3.py` 启动 Docker 容器以执行 _被测技能_（非 Repo2Skill 自身），容器配置：
  - 网络隔离（`--network none`）
  - 只读挂载技能文件夹（`:ro`）
  - CPU/内存限制（`--cpus=1 --memory=256m`）
  - 超时 120 秒
  - 执行后自动销毁容器
- **网络与环境**：Repo2Skill 自身的脚本（`structure.py`、`assemble.py`、`audit_*.py`）永不主动发起网络请求或读取用户环境变量，唯一的网络操作是 `git clone`；所有 LLM 推理由 Agent 运行时承担。

---

## 7. 多维度质量评估

依据论文 [1] 第 6 节，生成的技能附带多维度评分，记录在 `verification/report.json`：

| 维度           | 指标                                                                                                       | 数据源 / 计算方式                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **安全性**     | 漏洞发生率 = 存在注入或文件滥用风险的技能占比                                                              | G1 报告（对照论文 [1] Table 3 `Vulnerability Rate`）    |
| **功能完整性** | 参数文档覆盖率 = 已描述参数数 / 源码签名参数数                                                             | 对比 `analysis.json` 中函数签名                         |
| **可执行性**   | 任务成功率 = G3 通过用例数 / 总用例数                                                                      | G3 执行通过率                                           |
| **可维护性**   | 公共函数签名变更兼容率（Schema Drift）                                                                     | 对比上游仓库 metadata，计算 `(未变更签名数 / 总签名数)` |
| **教学有效性** | TeachQuiz 分数（仅对教育类技能适用）；其他技能以 `调用有效性 = Agent 首次调用成功数 / 总调用次数` 作为替代 | 教育类：论文 [1] §4.2.3 TeachQuiz 协议；通用类：G3 日志 |

汇总分数可用于技能库中的排序、过滤和自动更新优先级。

---

## 8. 生态集成

### 8.1 技能注册中心就绪

生成的 `skill.yaml` 包含注册中心所需字段。字段命名采用 Anthropic Agent Skills 约定的 `kebab-case`：

```yaml
name: my-tool-skill
version: 1.0.0
source: https://github.com/<owner>/my-tool
trust-level: L3
allowed-tools: [Read, Write, Bash(black)]
dependencies:
  - python>=3.11
  - black>=24.0
security:
  g1-passed: true
  g2-score: 0.95
  g3-passed: true
  g4-passed: true
ontology:
  relations:
    - type: depends-on
      target: python-runtime
```

可直接推送到 [JFrog Artifactory](https://jfrog.com/artifactory/)、AWS Agent Registry、[agentskills.so](https://agentskills.so)（示例平台）等兼容目录。

### 8.2 技能演化与升级

- 与 `skill-mem` 集成，记录提取来源和版本。
- 当源仓库发布新版本时，触发重新提取，对比差异，生成升级建议（遵循论文 [1] §8.1 Evolution Agents 从对话日志与执行轨迹中持续提炼技能的思路）。此外借鉴 SkillFoundry [3] 的闭环验证策略：对技能库持续执行 **扩展 / 修复 / 合并 / 剪枝** 四类操作，避免内部冲突与冷门技能堆积。
- 群体智慧：多个用户对同一仓库的提取结果可聚合，优化技能描述和默认参数。

### 8.3 SkillNet 本体标注

在 `skill.yaml` 中提供轻量级关系声明，支持构建技能知识图谱：

```yaml
ontology:
  relations:
    - type: "requires-output-from"
      target: "file-reader-skill"
    - type: "composes"
      target: "code-quality-tools-suite"
    - type: "bundled-with"
      target: "lint-skill"
    - type: "depends-on"
      target: "python-runtime"
```

当技能属于某套件时，`composes` 指向套件聚合技能名，`bundled-with` 列出同套件成员；套件根目录的 `suite.yaml` 汇总全部关系并提供 DAG 校验。

---

## 9. 技术选型

所有脚本依赖最小化，优先使用 Python 标准库：

| 功能        | 选型                    | 说明                                                                                     |
| ----------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| Git 操作    | `gitpython`             | 稳定、API 清晰                                                                           |
| AST 解析    | `tree-sitter` + 语法包  | 支持 Python/JS/TS/Go/Rust                                                                |
| 结构化摘要  | `tree-sitter` 自实现    | 相比论文 [1] §3.1 推荐的 `repo2AI`，本设计选用 `tree-sitter` 以获得更强的多语言 AST 支持 |
| 密集检索    | `sentence-transformers` | 实现论文 [1] §3.2 的双塔 + Cross-Encoder 二阶段检索                                      |
| 模板引擎    | `jinja2`                | 用于 `SKILL.md` 生成                                                                     |
| Docker 交互 | `docker`                | G3 沙箱必需                                                                              |
| 静态扫描    | 自定义正则 + AST 规则   | 无需外部工具                                                                             |
| CLI 包装器  | `typer`                 | 轻量、良好的帮助信息                                                                     |

所有依赖由 `scripts/requirements.txt` 列出，Agent 可按需安装。

---

## 10. 自举与自我进化

Repo2Skill 的设计自指其本身：

1. 使用 Repo2Skill 处理自己的仓库：

   ```bash
   repo2skill https://github.com/<owner>/repo2skill
   ```

2. 将生成的技能包与当前版本对比，自动识别结构优化（如新增了审计脚本）。
3. 在 `skill-mem` 的跟踪下，持续记录自我演化的历史，并在社区贡献中不断吸纳更优秀的提取实践。

这是 Agent Skills 生态自进化范式的具体体现。

---

## 11. 开发路线图

| 阶段        | 目标                                                                       | 关键产出                             |
| ----------- | -------------------------------------------------------------------------- | ------------------------------------ |
| **Phase 1** | 核心骨架：`structure.py`（四元组输出）、`assemble.py`、`SKILL.md` 流程定义 | 可手动完成一个 Python 仓库的技能化   |
| **Phase 2** | G1/G2 验证实现、用户交互完善                                               | 生成技能附带安全与语义报告           |
| **Phase 3** | G3/G4 沙箱及权限验证、非交互模式                                           | 可信的自动验证，支持批量处理         |
| **Phase 4** | 多语言扩展（JS/TS、Go、Rust）、SkillNet 标注                               | 覆盖主流 Agent 工具语言              |
| **Phase 5** | 自举测试、文档、注册中心集成示例                                           | Repo2Skill v1.0 GA，具备生态连接能力 |

---

## 12. 附录 A：关键文件示例

### 12.1 `analysis.json` 四元组输出片段（`structure.py` 产出）

JSON 中使用 ASCII 键名 `conditions` / `policy` / `termination` / `interface` 以保证下游工具兼容性，表格与正文中仍使用 `C / π / T / R` 的理论符号：

```json
{
  "repo": "psf/black",
  "skills": [
    {
      "id": "sk1",
      "name": "Python Code Formatter",
      "conditions": {
        "trigger": "User requests formatting of Python files",
        "preconditions": ["Python files exist", "black installed"],
        "file_patterns": ["*.py"]
      },
      "policy": {
        "type": "script",
        "entry": "black.main",
        "steps": ["Read file", "Call format_str()", "Write back"],
        "dependencies": ["black>=24.0"]
      },
      "termination": {
        "success": "Return code 0, file content changed or already formatted",
        "output_schema": { "status": "formatted | already_good" }
      },
      "interface": {
        "params": { "file_path": "str", "line_length": "int?" },
        "allowed-tools": ["Read", "Write", "Bash(black)"]
      }
    }
  ]
}
```

### 12.2 技能 `SKILL.md` 模板核心章节（Jinja2）

模板 frontmatter 参考论文 [1] §3.3.1 的字段集合（`name`、`description`、`version`、`dependencies`），并追加 Anthropic Agent Skills 约定的 `allowed-tools` 字段与本设计新增的 `trust-level` 字段。**注**：论文 §3.3.1 同时建议写入独立的 `trigger` 字段，但 Anthropic 现行规范 [1, ref 16] 将触发职责合并至 `description`，因此本模板省略 `trigger`。以下模板使用 `{% raw %}` 块保护，避免在 Markdown 渲染中被误消解：

```jinja
{% raw %}
---
name: {{ skill_name }}
description: {{ description }}
version: {{ version }}
dependencies: {{ dependencies }}
allowed-tools: {{ allowed_tools }}
trust-level: {{ trust_level }}
---

## Conditions

{{ conditions }}

## Policy

{{ policy }}

## Termination

{{ termination }}

## Security

- **Trust Level**: {{ trust_level }}
- **Allowed Tools**: {{ allowed_tools }}
- **Network Access**: Denied
- **Filesystem Scope**: `$(workspace)/*`
- **Verification Report**: `verification/report.json`
{% endraw %}
```

---

## 13. 参考文献

[1] S. Bi, M. Wu, H. Hao, K. Li, W. Liu, S. Song, H. Zhao, and A. Zhou, "Automating skill acquisition through large-scale mining of open-source agentic repositories: A framework for multi-agent procedural knowledge extraction," arXiv preprint arXiv:2603.11808v2, Mar. 2026. [Online]. Available: <https://arxiv.org/abs/2603.11808>

[2] TIGER AI Lab, "TheoremExplainAgent: Towards multimodal explanations for LLM theorem understanding," arXiv preprint arXiv:2502.19400, 2025. [Online]. Available: <https://arxiv.org/abs/2502.19400>

[3] S. Shen, W. Cheng, M. Ma, A. Turcan, M. J. Zhang, and J. Ma, "SkillFoundry: Building self-evolving agent skill libraries from heterogeneous scientific resources," arXiv preprint arXiv:2604.03964, Apr. 2026. [Online]. Available: <https://arxiv.org/abs/2604.03964>

[4] Y. Sun, P. Wei, and L. B. Hsieh, "Don't retrieve, navigate: Distilling enterprise knowledge into navigable agent skills for QA and RAG (Corpus2Skill)," arXiv preprint arXiv:2604.14572, Apr. 2026. [Online]. Available: <https://arxiv.org/abs/2604.14572>

[5] Q. Liang, H. Wang, Z. Liang, and Y. Liu, "From skill text to skill structure: The scheduling-structural-logical representation for agent skills," arXiv preprint arXiv:2604.24026, Apr. 2026. [Online]. Available: <https://arxiv.org/abs/2604.24026>
