# Repo2Skill 后续计划

**日期**：2026-05-14
**当前状态**：Phase 1 完成，Phase 2 基本完成（7/8），Suite Mode 提前交付

---

## 阶段一：Phase 2 收尾（小改动，预计 1-2 小时）

### 1.1 P4-T8：套件级 Trust Level

`assemble_suite()` 在 `suite.yaml` 中硬编码 `trust-level: L1`。应改为接受调用方传入的 trust_level 参数。

- **改动**：`assemble_suite()` 新增 `trust_level` 参数（默认 "L1"），CLI 的 `_assemble_as_suite()` 传入计算好的值
- **测试**：`TestAssembleSuite` 增加 trust_level 传入验证

### 1.2 SKILL.md 模板空白行过多

生成的 SKILL.md 中 `dependencies:` 和 `allowed-tools:` 块前后有大量空白行。原因是 Jinja2 的 `{% if %}` / `{% for %}` 标签保留了换行。

- **改动**：在 `skill.md.j2` 和 `skill.yaml.j2` 中使用 `{%-` 和 `-%}` 去除多余空白
- **验证**：对比修复前后生成的 SKILL.md

### 1.3 `—` 替换后的双连字符问题

`_derive_skill_name` 的 ` — ` → ` - ` 修复后，名称中的 ` - ` 经 `replace(" ", "-")` 变成 `--`，如 `policy-benchmark----find-skills`。建议去掉 skill 名称中的函数名部分（只用模块名），或在生成目录名时使用更干净的 sanitize 逻辑。

- **改动**：`assemble_skill()` 中 `skill_name.replace(" ", "-").replace("_", "-")` 改为 `re.sub(r"[^a-z0-9]+", "-", skill_name.lower()).strip("-")`

---

## 阶段二：自举测试 ✅ 已完成

详见 [bootstrap-gap-analysis.md](./bootstrap-gap-analysis.md)。6 个差距已识别：

| Gap | 描述 | 严重度 | 解决方 |
|-----|------|--------|--------|
| G1 | 粒度：函数级 vs 工作流级 | 结构性 | **Agent** (Extractor 合并) |
| G2 | 步骤质量："Use func()" vs 操作指令 | 语义性 | Agent + 脚本 |
| G3 | 上下文缺失：无准则/公式/阈值 | 语义性 | **Agent** (Extractor 补充) |
| G4 | 命名：模块路径在产品名中 | 表面 | Python 脚本 |
| G5 | 依赖精度：`__future__` 被列为依赖 | 表面 | Python 脚本 |
| G6 | 缺 `repo2skill-skill/` 中的脚本文件 | 表面 | Python 脚本 |

**核心发现**：G1 和 G3 不是 Python 脚本能解决的问题——它们是 Extractor Agent 的工作。当前 Agent 只对 structurer 的函数列表做评分精炼，但要生成工作流级技能，Agent 需要主动合并相关函数、推断上下文、编写步骤。

---

## 阶段三：Extractor Agent 增强（预计 4-6 小时）

**目标**：增强 SKILL.md 中的 Extractor 指令，让 Agent 在提取阶段产出工作流级技能，而非函数级描述。

**不改 Python 脚本的架构**（Structurer 继续产出函数级 analysis.json），改变的是 **Agent 如何使用这些数据**。

### 3.1 SKILL.md Extractor 指令增强 — 解决 G1/G3

在 SKILL.md 的 Extractor 章节增加以下指引：

#### 工作流合并 (G1)

```
当多个候选技能共享同一调用链时（如 A 调用 B，B 调用 C），
将它们合并为一个 workflow 类型的技能：
- 以入口函数（如 CLI main）为 primary
- 将其余函数作为 policy.steps 的子步骤
- 使用 dependency_graph 的边来识别调用链

合并阈值：
- 同一模块内的函数 → 默认合并
- 跨模块但同一顶级包（如 repo2skill.*）→ 评估是否属于同一功能线
- 测试辅助函数 → 不合并到核心技能
```

#### 上下文补充 (G3)

```
从以下来源为每个候选补充上下文：
1. readme_summary：提取 repo 级别的描述
2. dependency_graph：识别该模块在系统中的位置（入口/中间/叶节点）
3. pyproject.toml [project.scripts]：识别 CLI 入口点
4. 函数 docstring：提取 Args/Returns/Raises 作为自然语言步骤

将补充的上下文写入：
- conditions.trigger：从 README 描述 + 函数用途组合
- policy.steps：用 docstring 内容替换 "Use func()" 格式
- description：readme_summary 的第一段 + 函数的核心功能
```

#### 候选评分的调整

```
在应用 4 项准则时，对以下情况加分：
- 属于 CLI 入口的函数（pyproject.toml [project.scripts]）→ 通用性 +0.2
- 依赖图中入度 > 3 的函数（被多处调用）→ 非显然度 +0.2
- 有完整 docstring（Args + Returns + Raises）→ 验证度 +0.2

对以下情况减分：
- __init__ 方法 → 泛化度 -0.2（构造函数不可复用）
- 测试函数（模块路径含 test/）→ 重复度 -0.3（测试模式常见）
- 私有函数（_ 前缀）→ 泛化度 -0.2
```

### 3.2 Python 侧小修 — 解决 G4/G5/G6

| Gap | 改动 | 位置 |
|-----|------|------|
| G4 命名 | `_derive_skill_name()` 使用 `readme_summary` 的 repo 名替换模块路径前缀 | `structure.py` |
| G5 依赖 | `_prefill_policy()` 过滤 `__future__`、stdlib 等非 pip 包 | `structure.py` |
| G6 文件范围 | 支持 `--include-dirs` 参数扫描额外目录 | `structure.py` / CLI |

### 3.3 验收标准

用 Repo2Skill 再次处理自身，验证：

| 检查项 | 目标 |
|--------|------|
| 核心模块被合并为 workflow 技能 | `structure.py` + `extract.py` + `assemble.py` → 1 个 "Skill Extraction Pipeline" 技能 |
| steps 使用自然语言 | "Use module.func()" → "运用 AST 解析仓库，输出带四元组标注的 analysis.json" |
| 技能名称不含模块路径 | "Src Repo2Skill Extractor - extract_skills" → "Skill Extraction Pipeline" |
| `__future__` 不出现在依赖中 | 依赖列表不含 stdlib 包 |
| G1 通过 | 自举输出无高危项 |

---

## 阶段四：Phase 3 规划（设计阶段，不编码）

（同前）G3 沙箱、G4 权限审计、批量处理的设计文档。

---

## 不做（Phase 4/5 范围）

（同前）多语言、密集检索、注册中心、skill-mem、升级流程。

---

## 优先级总结

```
阶段一 ✅  收尾修复（已完成）
阶段二 ✅  自举测试 + 差距分析（已完成）
阶段三 ✅   Extractor Agent 增强（已完成）
阶段四 ⬜   Phase 3 设计文档
```
