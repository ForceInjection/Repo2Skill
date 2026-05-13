# 自举测试：Repo2Skill 处理自身 — 差距分析

**日期**：2026-05-14
**方法**：运行 Repo2Skill 全流程处理自身仓库，对比生成输出与手写 `repo2skill-skill/SKILL.md`

---

## 执行摘要

**自举通过**：Structurer 成功解析 22 个模块（111 个函数），Extractor 识别 5 个候选，Assembler 组装为套件，G1 扫描通过。

**质量差距**：生成的技能是**单函数级别**的描述，手写版是**多函数工作流级别**的 Agent 指令。这是结构性的粒度差异，不是 bug。

---

## 输入

| 指标 | 数值 |
|------|------|
| Python 文件 | 22 |
| 函数提取 | 111 |
| 模块数 | 22 |
| 候选技能 | 16 → 5（规则评分 Top 5） |
| 选中组装 | 3（sk8 extract_skills, sk11 detect_suite_mode, sk16 create_sample_repo） |

---

## 对比：手写 vs 生成

### 手写 `repo2skill-skill/SKILL.md`

| 特征 | 数值 |
|------|------|
| 覆盖范围 | **完整工作流**：11 个步骤，从 structure 到 trust level |
| 步骤类型 | **操作指令**："Run scripts/structure.py", "Read analysis.json", "Present candidates" |
| 上下文 | Extractor 4 项准则 + 评分公式；G2 三维度 + 阈值；Suite 4 条件；Trust L0–L2 表 |
| 粒度 | **工作流级别**：一个 SKILL.md 覆盖整个 pipeline |
| 命名 | "Repo2Skill"（产品名） |
| Token 数 | L1 ~69, L2 ~2400 |

### 生成的最佳技能 `sk8 (extract_skills)`

| 特征 | 数值 |
|------|------|
| 覆盖范围 | **单函数**：`extract_skills()` |
| 步骤类型 | **函数引用**："Use extract_skills_with_scores()", "Use _score_recurrence()" |
| 上下文 | 无筛选准则、无评分公式、无工作流说明 |
| 粒度 | **函数级别**：一个 SKILL.md = 一个 Python 函数 |
| 命名 | "Src Repo2Skill Extractor - extract_skills"（模块路径 + 函数名） |
| Token 数 | L1 ~38, L2 ~240 |

---

## 差距分类

### G1 — 粒度（结构性）

**问题**：Structurer 以模块为单位生成候选。每个模块的第一个函数成为"主函数"，其余函数作为 steps 追加。导致一个 SKILL.md 描述一个 Python 模块，而非一个 Agent 工作流。

**手写版**：一个 SKILL.md 是一个**跨模块的工作流**。

**影响**：生成的技能无法直接替代手写版。Agent 加载后只能调用单个函数，无法理解完整流程。

**缓解方向**（Phase 2/3）：
- Structurer 增加跨模块工作流检测（如识别 CLI 入口 → 追踪调用链）
- Extractor 增加候选合并逻辑（将相关模块合并为一个 workflow 类型技能）
- 或：接受套件模式为默认，多个单函数技能通过 `requires-output-from` 串联

### G2 — 步骤质量（语义性）

**问题**：Steps 是函数引用列表（"Use module.func()"），不是操作指令。

**手写版**："Run `scripts/structure.py <source> <output_dir>` to clone/analyze the repo"

**影响**：Agent 无法根据 steps 执行操作，因为没有描述这些函数做什么、输入输出是什么。

**缓解方向**：Steps 使用函数的 docstring 而非 `"Use func()"` 格式。

### G3 — 上下文缺失

**问题**：生成的技能不包含：
- Extractor 的 4 项筛选准则
- G2 的 3 维度审查标准
- Suite 模式的 4 条触发条件
- Trust Level 计算表
- 候选展示格式

**手写版**：这些都在 Level 2 body 中，作为 Agent 执行任务时的参考。

**影响**：生成的技能只能告诉 Agent 有哪些函数，不能告诉 Agent **如何判断**。

**缓解方向**：这些是 Agent 在 Extractor/Reviewer 角色中产生的知识，难以从代码中自动提取。可能需要 Agent 在提取时主动写入。

### G4 — 命名

**问题**：`_derive_skill_name()` 生成 `"Src Repo2Skill Extractor - extract_skills"`。

**手写版**：`"Repo2Skill"`。

**影响**：名称过长且包含实现细节（模块路径）。Agent 触发匹配可能不准确。

**缓解方向**：命名使用 `readme_summary` 的 repo 名称 + 功能类别（如 "Repo2Skill - Extraction"）。

### G5 — 依赖精度

**问题**：`__future__` 被列为依赖（因为源码中有 `from __future__ import annotations`）。

**影响**：Agent 可能尝试 `pip install __future__`（不存在此包）。

**缓解方向**：过滤 stdlib 和 `__future__` 等非 pip 依赖。

### G6 — 缺模块

**问题**：Structurer 漏掉了 `repo2skill-skill/` 目录中的文件（因为它们在项目根目录外）。手写版 SKILL.md 描述的完整工作流包含 `scripts/structure.py`、`scripts/assemble.py` 等，这些未被解析。

**影响**：生成的技能不包含 runner 脚本。

**缓解方向**：Structurer 应支持多根目录扫描，或 Agent 手动指定额外路径。

---

## 量化

| 维度 | 手写版 | 生成版（最佳） | 差距 |
|------|--------|---------------|------|
| 覆盖函数数 | 全流程（~8 个脚本） | 1 个函数 | 8x |
| 步骤是否可执行 | 是（操作指令） | 否（函数引用） | — |
| 上下文丰富度 | 高（准则、公式、阈值） | 低（仅模板结构） | — |
| L2 Token 数 | ~2400 | ~240 | 10x |
| skill.yaml 元数据 | 完整（dependencies, allowed-tools, security） | 完整 | — |
| Trust Level | L1 | L0（组装在 G1 前） | 1 级 |

---

## 结论

Repo2Skill 成功处理了自身仓库：Structurer 正确解析了 AST，Extractor 识别了相关函数，Assembler 生成了合规的技能包，G1 通过了安全扫描。但生成的技能是**单函数描述**，而期望的是**多函数工作流指令**。这是当前架构的固有限制，不是 bug。

下一步（Phase 2 深度完善 / Phase 3）应优先解决 G1（粒度）和 G2（步骤质量），才能让自举输出达到手写版的质量水平。
