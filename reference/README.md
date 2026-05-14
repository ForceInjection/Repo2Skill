# 参考文献综述

本目录包含四篇与 Agent Skills 自动化获取、表示和检索相关的学术论文。这些论文构成了 Repo2Skill 项目的理论基础和前沿参考。

---

## 目录

- [参考文献综述](#参考文献综述)
  - [目录](#目录)
  - [论文概览与关系](#论文概览与关系)
  - [1. Automating Skill Acquisition (Bi et al., 2026)](#1-automating-skill-acquisition-bi-et-al-2026)
    - [1.1 核心贡献](#11-核心贡献)
    - [1.2 技能表示](#12-技能表示)
    - [1.3 提取流水线](#13-提取流水线)
    - [1.4 安全验证 (G1–G4)](#14-安全验证-g1g4)
    - [1.5 关键发现](#15-关键发现)
  - [2. Corpus2Skill (Sun et al., 2026)](#2-corpus2skill-sun-et-al-2026)
    - [2.1 核心贡献](#21-核心贡献)
    - [2.2 离线编译流水线](#22-离线编译流水线)
    - [2.3 导航机制](#23-导航机制)
    - [2.4 关键结果](#24-关键结果)
  - [3. SkillFoundry (Shen et al., 2026)](#3-skillfoundry-shen-et-al-2026)
    - [3.1 核心贡献](#31-核心贡献)
    - [五阶段流水线](#五阶段流水线)
    - [3.2 关键结果](#32-关键结果)
    - [3.3 技能包结构](#33-技能包结构)
  - [4. SSL Representation (Liang et al., 2026)](#4-ssl-representation-liang-et-al-2026)
    - [4.1 核心贡献](#41-核心贡献)
    - [SSL 三层模型](#ssl-三层模型)
      - [Scheduling Layer（调度层）](#scheduling-layer调度层)
      - [4.2 Structural Layer（结构层）](#42-structural-layer结构层)
      - [4.3 Logical Layer（逻辑层）](#43-logical-layer逻辑层)
    - [4.4 LLM 规范化器](#44-llm-规范化器)
    - [4.5 关键结果](#45-关键结果)
  - [5. Repo2Skill 设计思考](#5-repo2skill-设计思考)
    - [5.1 与 Automating Skill Acquisition 的对齐与分叉](#51-与-automating-skill-acquisition-的对齐与分叉)
    - [5.2 Corpus2Skill：边界的确认](#52-corpus2skill边界的确认)
    - [5.3 SkillFoundry：闭环验证与领域的取舍](#53-skillfoundry闭环验证与领域的取舍)
    - [5.4 SSL：结构化表示的价值与成本](#54-ssl结构化表示的价值与成本)
    - [5.5 设计演进路线](#55-设计演进路线)

---

## 论文概览与关系

| 论文                         | arXiv ID   | 核心贡献                                         | 与 Repo2Skill 的关系                                  |
| ---------------------------- | ---------- | ------------------------------------------------ | ----------------------------------------------------- |
| Automating Skill Acquisition | 2603.11808 | 从 GitHub 仓库自动提取 Agent Skills 的完整流水线 | **直接对应** — 四元组模型、G1–G4 安全验证、渐进式披露 |
| Corpus2Skill                 | 2604.14572 | 将文档语料库编译为可导航的技能树以替代检索       | **补充** — 文档知识 → 技能层次化，与代码技能互补      |
| SkillFoundry                 | 2604.03964 | 从异构科学资源构建自演化技能库的框架             | **扩展** — 覆盖科学计算领域、闭环验证                 |
| SSL Representation           | 2604.24026 | 技能文本的结构化表示（调度-结构-逻辑三层模型）   | **增强** — 提升技能检索和风险审计的表示能力           |

这四篇论文从不同维度回答同一个问题：**如何系统性地将非结构化的知识资源（代码仓库、文档、科学工作流）转化为 Agent 可执行的技能**。前三篇论文（Automating Skill Acquisition、SkillFoundry、Corpus2Skill）覆盖了三种不同的知识源——代码仓库、科学资源和文档语料库，而 SSL Representation 则为这些技能的统一结构化表示提供了语言。

---

## 1. Automating Skill Acquisition (Bi et al., 2026)

**标题**: Automating Skill Acquisition through Large-Scale Mining of Open-Source Agentic Repositories: A Framework for Multi-Agent Procedural Knowledge Extraction

**arXiv**: [2603.11808v2](https://arxiv.org/abs/2603.11808)

**作者**: Shuzhen Bi, Mengsong Wu, Hao Hao, Keqian Li, Wentao Liu, Siyu Song, Hongbo Zhao, Aimin Zhou (华东师范大学、上海创新研究院、中国科学技术大学)

---

### 1.1 核心贡献

提出从开源 GitHub 仓库中系统性地挖掘 Agent 技能的框架。聚焦于从 **TheoremExplainAgent** 和 **Code2Video**（均基于 Manim 动画引擎）中提取可视化和教育类技能。

### 1.2 技能表示

技能 S 被定义为一个**四元组**：**S = (𝒞, π, 𝒯, ℛ)**：

- **𝒞** (Conditions): 适用条件与触发场景
- **π** (Policy): 核心程序性知识——动作与推理步骤序列
- **𝒯** (Termination): 成功完成的逻辑条件
- **ℛ** (Interface): 标准化的可调用边界（输入参数、输出格式、组合协议）

采用 Anthropic 的 SKILL.md 规范，实现**渐进式披露（Progressive Disclosure）**三级架构：

| 层级    | 内容                                | Token 预算 |
| ------- | ----------------------------------- | ---------- |
| Level 1 | YAML 元数据（名称、描述、触发条件） | 30–100     |
| Level 2 | 工作流、最佳实践、步骤逻辑          | 200–5,000  |
| Level 3 | 脚本、参考文档、模板                | 无上限     |

### 1.3 提取流水线

1. **仓库结构分析**: 使用 repo2AI 生成目录层次和文件内容的 Markdown 表示
2. **语义技能识别**: **两阶段排序**——Dense Retrieval（bi-encoder 余弦相似度初筛）+ Cross-Encoder（联合编码精细评分），依据四个标准过滤：Recurrence、Verification、Non-obviousness、Generalizability
3. **翻译为 SKILL.md**: 生成 YAML 元数据 → 撰写 LLM 可消费的指令 → 打包辅助资产

### 1.4 安全验证 (G1–G4)

- **G1**: 静态分析——扫描危险 API（`eval`、`exec`、`socket`、`subprocess`）
- **G2**: 语义分类——LLM 检查指令-目的对齐、提示注入、元数据一致性
- **G3**: 行为沙箱——隔离容器中执行脚本（网络隔离、文件系统限制）
- **G4**: 权限校验——验证 `allowed-tools` 与实际资源访问的偏差

社区技能调查发现 **26.1%** 的产物存在漏洞。

### 1.5 关键发现

- o3-mini agent 在 TheoremExplainBench 上达到 **0.77** 总分
- Agent 生成的教育内容实现 **40%** 的知识传递效率提升
- SkillNet 本体结构：执行步骤减少 30%，平均任务奖励提升 40%

---

## 2. Corpus2Skill (Sun et al., 2026)

**标题**: Don't Retrieve, Navigate: Distilling Enterprise Knowledge into Navigable Agent Skills for QA and RAG

**arXiv**: [2604.14572v2](https://arxiv.org/abs/2604.14572)

**作者**: Yiqun Sun, Pengfei Wei, Lawrence B. Hsieh

---

### 2.1 核心贡献

提出 **Corpus2Skill**：将文档语料库离线编译为可导航的技能层次树，Agent 在推理时通过**导航树结构**而非密集检索来定位证据。

### 2.2 离线编译流水线

1. **文档嵌入**: Sentence-BERT 将文档编码为稠密向量
2. **迭代层次聚类**: K-Means（分支比 p，默认 10）递归聚类 → LLM 为每个簇生成摘要 → 重新嵌入 → 继续下一层
3. **标注**: LLM 生成 2–5 字的文件系统安全标签
4. **技能树构建**: 每个簇成为目录（`SKILL.md` 用于非叶节点，`INDEX.md` 用于叶节点），完整文档存储在外部 `documents.json` 中

### 2.3 导航机制

Agent 获得两个工具：

- `code_execution` — 浏览 SKILL.md/INDEX.md
- `get_document(doc_id)` — 检索完整文档

典型查询在 **2–3 轮** 内完成。层次深度为 `O(log_p N)`。对于 100,000 份文档，仅需 5 层。

### 2.4 关键结果

| 数据集             | 方法            | Token F1  | Factuality |
| ------------------ | --------------- | --------- | ---------- |
| WixQA (6,221 docs) | Corpus2Skill    | **0.468** | **0.739**  |
|                    | Dense Retrieval | 0.363     | 0.536      |
|                    | RAPTOR          | 0.389     | 0.675      |
|                    | Agentic RAG     | 0.381     | 0.719      |
| 10 数据集宏平均    | Corpus2Skill    | **0.350** | 0.565      |

- 编译成本: **6.5 分钟**，**$5–10** LLM 调用费用（WixQA 规模）
- 更换 Haiku 4.5 成本降低 29%，保留 91% F1
- 适用范围\*\*: 单一领域、原子文档的语料库（0.5k–3k 字符）；不适合开放式长文档

---

## 3. SkillFoundry (Shen et al., 2026)

**标题**: SKILLFOUNDRY: Building Self-Evolving Agent Skill Libraries from Heterogeneous Scientific Resources

**arXiv**: [2604.03964v1](https://arxiv.org/abs/2604.03964)

**作者**: Shuaike Shen, Wenduo Cheng, Mingqian Ma, Alistair Turcan, Martin Jinye Zhang, Jian Ma

---

### 3.1 核心贡献

提出 **SkillFoundry**：从异构科学资源（仓库、API、脚本、Notebook、文档、数据库、论文）中自动构建自演化技能库的框架。

### 五阶段流水线

1. **领域知识树构建**: 将目标领域组织为层次树（内部节点 = 子领域，叶节点 = 技能目标），优先处理资源丰富但技能覆盖薄弱的子树
2. **资源挖掘**: 从高价值分支提取权威资源（官方文档、维护中的仓库、论文等）
3. **操作合同提取**: 为每项技能提取任务范围、输入/输出、环境假设、执行步骤、出处链接和测试
4. **技能包编译**: 组装为包含人类可读规范、机器可读元数据、出处记录、可执行脚本和示例资产的完整包
5. **闭环验证**: 五级验证——执行测试 → 系统测试 → 合成数据测试 → 效用基准测试 → 新颖性审查；失败技能进入修复循环

### 3.2 关键结果

- **286 技能**，覆盖 **27 个领域、254 个子领域**，从 **394 个资源**中挖掘
- **71.1%** 的技能与现有库（SkillHub、SkillSMP）不重复
- MoSciBench (6 数据集): Repo-Acc 从 61.19% 提升至 **66.73%** (+5.54%)
- 细胞类型注释（空间转录组学）: 准确率从 68.5% 提升至 **82.9%**
- scDRS 工作流: 定性评分最高达 **7/7**，RMSE 从 0.11 降至 **0.02**

### 3.3 技能包结构

每项技能包含六个层次：人类可读规范、机器可读元数据、出处记录、可执行脚本、示例资产、仓库级测试。

---

## 4. SSL Representation (Liang et al., 2026)

**标题**: From Skill Text to Skill Structure: The Scheduling-Structural-Logical Representation for Agent Skills

**arXiv**: [2604.24026v4](https://arxiv.org/abs/2604.24026)

**作者**: Qiliang Liang, Hansi Wang, Zhong Liang, Yang Liu

---

### 4.1 核心贡献

提出 **SSL（Scheduling-Structural-Logical）表示法**——对 SKILL.md 等文本化技能文档的结构化解构。将技能文本从单一叙事形式分解为三个相互关联但类型不同的表示层。

### SSL 三层模型

**形式定义**: G_d = (r_sch, G_str, G_log, R_cont, R_entry)

#### Scheduling Layer（调度层）

技能级别的调用接口：

- `skill_id`、`skill_name`、`skill_goal` — 身份与目标
- `intent_signature`、`tags` — 路由信号
- `top_pattern` — 执行模式分类
- `expected_inputs`、`expected_outputs` — I/O 契约
- `dependencies` — 所需权限与能力
- `control_flow_features` — 粗略控制流特征（分支、循环、工具调用、敏感资源访问）

理论来源: Schank 的 Memory Organization Packets（MOPs）

#### 4.2 Structural Layer（结构层）

场景级别的执行阶段：

- 节点 = **场景**（Scene），边 = 阶段级转换
- 封闭的场景类型词汇：`PREPARE` | `ACQUIRE` | `REASON` | `ACT` | `VERIFY` | `RECOVER` | `FINALIZE`
- 每个场景包含：目标、数据契约、进入条件、退出条件、下一步规则、包含的逻辑步骤

理论来源: Schank & Abelson 的 Script Theory

#### 4.3 Logical Layer（逻辑层）

原子操作与资源使用：

- 节点 = **逻辑步骤**（源文本支持的最小操作单元）
- 封闭的动作类型词汇：`READ` | `SELECT` | `COMPARE` | `VALIDATE` | `INFER` | `WRITE` | `UPDATE_STATE` | `CALL_TOOL` | `REQUEST` | `TRANSFER` | `NOTIFY` | `TERMINATE`
- 封闭的资源范围词汇：`MEMORY` | `LOCAL_FS` | `CODEBASE` | `PROCESS` | `USER_DATA` | `CREDENTIALS` | `NETWORK` | `OTHER`
- 每个步骤记录：动作类型、执行者、对象、工具、输入参数、输出绑定、前置条件、效果、资源范围、下一步规则

理论来源: Schank 的 Conceptual Dependency

### 4.4 LLM 规范化器

使用 DeepSeek-V3.2，四步流程：

1. 提取 Scheduling 记录
2. 分解为场景
3. 扩展为逻辑步骤
4. 验证生成的图

**忠实度审计**: 人类审计 100 项技能中，**83%** 的 SSL 被判定为得到源文本支撑。

### 4.5 关键结果

| 任务     | 指标      | 基线 (Full SKILL.md) | SSL       | 提升   |
| -------- | --------- | -------------------- | --------- | ------ |
| 技能发现 | MRR@50    | 0.645                | **0.729** | +0.084 |
| 技能发现 | Recall@10 | 0.821                | **0.905** | +0.084 |
| 风险评估 | Macro F1  | 0.409                | **0.509** | +0.100 |
| 风险评估 | Macro Acc | 0.765                | **0.801** | +0.036 |

最大收益在 Data Exfiltration (F1 0.699)、Credential Access (F1 0.780) 维度。

---

## 5. Repo2Skill 设计思考

这四篇论文不是同等重要的参考——它们从不同的产品边界出发，在方法论和设计选择上有实质差异。本节站在 Repo2Skill 的设计立场，审视与每篇论文的对齐、分叉和刻意不采纳。

---

### 5.1 与 Automating Skill Acquisition 的对齐与分叉

**这是我们最直接的论文基准。** 两者共享设计语言：四元组模型 (C/π/T/R)、渐进式披露三级架构、G1–G4 安全验证框架、提取-翻译流水线。但关键差异反映了两者的设计哲学分歧：

**已对齐且实现的部分**：

- 四元组模型 → `models.py` 完整实现
- 渐进式披露 → `SKILL.md.j2` 模板遵循 Level 1–3 Token 预算
- G1 安全扫描 → `reviewer/g1.py`（22 条规则，含硬编码路径和嵌入式密钥检测）
- G2 语义审查 → Agent 驱动（`references/g2-review.md`）
- Suite/SkillNet 本体 → `suite.py`（detect + infer + validate + overlap detection）

**Repo2Skill 的分叉设计**：

- **分类 vs 生成**：论文的 Extractor 用两阶段排序（Dense Retrieval + Cross-Encoder）对候选技能分类并过滤；Repo2Skill 的 Extractor 采用规则化 6 维评分作为基线，将筛选和生成工作留给 Agent（Enrich 步骤）。这是一个刻意的架构选择——"Python 做机械，Agent 做判断"。两阶段排序标记为 Phase 3，但前提是它不会削弱 Agent 在 Enrich 阶段的自主性。
- **Enrich 步骤**：论文的 Assembler 直接将提取结果写入模板，产出即为终稿。Repo2Skill 在组装后增加了一个 Agent Enrich 步骤——Agent 读取模板填充的 SKILL.md 并实质性地重写它（Steps 从 "Use func()" 变为自然语言，名称从模块路径变为功能性命名）。这是 Repo2Skill 最有价值的差异化：**模板提供基线，Agent 负责质量**。
- **技能套件**：论文提到 SkillNet 但未详细展开。Repo2Skill 将 Suite Mode 作为一等概念实现——4 条检测准则、4 种关系类型、DAG 校验、套件级 Trust Level。这是对论文框架的实质性扩展。

---

### 5.2 Corpus2Skill：边界的确认

Corpus2Skill 处理的是一个**不同的问题**——从文档语料库构建导航技能树，而非从代码仓库提取可执行技能。它的核心洞见是"不要检索，要导航"，但这依赖于一个前提：**知识可以按主题层次聚类，并且每个文档都是自包含的原子单元**。

**对 Repo2Skill 的启发**：

- Corpus2Skill 的层次导航模式验证了 Suite Mode 的设计方向——在复杂仓库中，多个子技能通过关系链接形成可导航网络，Agent 可以按 `depends-on` 和 `requires-output-from` 边进行遍历，类似于 Corpus2Skill 的树导航
- 它的 `O(log_p N)` 导航复杂度为 Repo2Skill 的技能发现效率提供了理论上界参考

**Repo2Skill 刻意不采纳的方向**：

- Corpus2Skill 假设"文档 → 技能树"的映射是稳定的（添加文档需要重新编译）。Repo2Skill 的技能提取是**按仓库单次运行的**，不维护跨仓库的知识树。如果未来扩展到多仓库技能目录，Corpus2Skill 的重编译策略需要被可用增量更新的方法替代
- Corpus2Skill 的 K-Means 硬分配（每个文档仅一条路径）不适合代码模块——一个 Python 模块可能同时属于多个技能（既是数据层的 part，也是 CLI 层的 part）。Repo2Skill 的 Suite Mode 允许一个模块被多个子技能交叉引用

---

### 5.3 SkillFoundry：闭环验证与领域的取舍

SkillFoundry 是四篇论文中**工程成熟度最高的系统**——286 技能、394 资源、27 领域、100% 验证通过率。它的工业级设计为 Repo2Skill 的未来提供了重要参考，但 Repo2Skill 与之在产品定位上有根本差异。

**已采纳的设计**：

- **新颖性/冗余审查** → `detect_skill_overlap()`：SkillFoundry 将新技能与 SkillHub/SkillSMP 比对，Repo2Skill 将其适配为套件内的 Jaccard 相似度检测。这是对同一设计思想的简化实现
- **G1 扩展**：SkillFoundry 对"操作合同"中环境假设和出处链接的重视，直接推动了 Repo2Skill 在 G1 中增加硬编码路径和嵌入式密钥检测——这些是在代码提取阶段最容易引入的供应链风险

**Repo2Skill 刻意不同的设计选择**：

- **执行验证 vs 静态提取**：SkillFoundry 的核心差异化是闭环执行验证（修复循环、合成数据测试、效用基准）。这需要 Docker 沙箱（G3）和可执行测试环境，对代码 → 技能的场景是合理的。但 Repo2Skill 的技能目标不是"生成一个可以运行并自我修复的脚本"，而是"生成一个 Agent 可以理解的程序性知识文档"。因此 Enrich 步骤替代了执行验证——Agent 的语义审查比 Docker 沙箱更适合验证"这个技能是否正确地教会了 Agent 如何使用代码"
- **领域知识树 vs 仓库聚焦**：SkillFoundry 跨仓库构建领域知识树，启动成本高（需要手动策划分类法）。Repo2Skill 选择以单个仓库为边界——这是有意为之的产品定位：**降低启动成本，让每个仓库的所有者都能独立生成技能**。跨仓库的层次组织是 Phase 5+ 的事，但前提是单仓库提取足够可靠

---

### 5.4 SSL：结构化表示的价值与成本

SSL 是四篇论文中**最具学术深度的工作**——用 Schank & Abelson 的经典认知理论重新框架化技能表示。但它的 LLM 规范化器依赖 DeepSeek-V3.2，且 83% 的忠实度意味着 17% 的 SSL 产出包含推测性内容。

**对 Repo2Skill 的核心挑战**：

SSL 发现"SKILL.md + SSL 的组合视图"在风险评估上优于单独的 Full SKILL.md（F1 0.409 → 0.509）。这意味着：**文本化技能 + 结构化证据 > 纯文本技能 > 纯结构化技能**。这对 Repo2Skill 的影响是双重的：

1. Repo2Skill 生成的是文本化 SKILL.md（通过模板 + Enrich）。如果能在 Level 3 资产中附带一份结构化的 `skill_structure.json`（简化的 SSL），Agent 在风险审查时就有了更精确的操作证据
2. Logical 层的 `resource_scope` 和 `act_type` 词汇可以直接映射到 G4 权限审计——这是 Phase 3 中最明确的增强方向

**Repo2Skill 当前不采纳 SSL 的原因**：

- SSL 完整实现的成本很高（需要额外的 LLM 规范化调用，23 页规格说明，复杂的验证管道）
- 已有的交叉审查证明，文本化 SKILL.md + G1 扫描的组合已经能捕获最关键的漏洞（Data Exfiltration F1 0.699 是 SSL 报告的最高单维度 F1，与 G1 的硬编码路径/嵌入式密钥检测高度重叠）
- 一个更务实的路径是：**在 G2 Review 阶段让 Agent 按简化版 SSL 框架审查 SKILL.md**，而不是让 Python 脚本自动生成 SSL。这符合 Agent-orchestrated 的架构原则
- Phase 5 的自举测试可以作为 SSL 简化的验证场：如果 Agent 能用 Repo2Skill 生成的 SKILL.md 正确地审计 Repo2Skill 自身的风险，那就证明结构化增强的边际收益有限

---

### 5.5 设计演进路线

| 设计主题 | 当前状态                  | 论文参考                            | 后续方向                                                 |
| -------- | ------------------------- | ----------------------------------- | -------------------------------------------------------- |
| 评分机制 | 6 维规则化基线            | Automating Skill Acquisition §3.2   | Phase 3: Dense Retrieval 作为辅助信号，不替代 Agent 判断 |
| 安全验证 | G1 (22 规则) + G2 (Agent) | Automating Skill Acquisition §2.2   | Phase 3: G3/G4 沙箱 + 权限审计                           |
| 技能组织 | Suite Mode (4 准则 + DAG) | SkillFoundry §3 + Corpus2Skill §3.4 | Phase 5: 多仓库技能目录，增量更新                        |
| 表示增强 | 四元组 + 渐进式披露       | SSL Representation §3–4             | Phase 5: 简化版 `skill_structure.json` 作为 Level 3 资产 |
| 冗余检测 | `detect_skill_overlap()`  | SkillFoundry §4 (Novelty Review)    | 扩展为跨库比对                                           |
| 执行验证 | Enrich (Agent 重写)       | SkillFoundry §4 (Closed-Loop)       | Phase 3: G3 沙箱执行 + Agent 诊断                        |

**核心设计原则**（Repo2Skill 在所有上述决策中保持一致）：

1. **Agent 做判断，Python 做机械** — 论文中的任何 LLM 调用，在 Repo2Skill 中都交由 Agent 在对话上下文中完成
2. **单仓库优先** — 降低启动成本。跨仓库组织是建立在稳定单仓库提取之上的功能
3. **文本化技能是主产物** — 结构化证据是辅助（Level 3），而非替代。SKILL.md 的质量是第一指标

---
