# Repo2Skill 使用指南

## 简介

Repo2Skill 是一个 Agent Skill，它教会 Agent 如何将任意 Python 仓库自动转换为符合 Anthropic Agent Skills 协议的标准技能包。它结合确定性脚本与 Agent 推理能力，覆盖从仓库分析、技能提取、模板组装到安全验证的完整生命周期。

### 核心概念

| 概念               | 说明                                                                                            |
| ------------------ | ----------------------------------------------------------------------------------------------- |
| **四元组模型**     | 每个技能被分解为 `Conditions（条件）/ Policy（策略）/ Termination（终止）/ Interface（接口）`   |
| **渐进式披露**     | Level 1 元数据（30–100 tokens）→ Level 2 正文（200–5,000 tokens）→ Level 3 辅助资产（按需加载） |
| **信任等级 L0–L2** | L0 未验证 → L1 静态扫描通过 → L2 语义审查通过                                                   |
| **技能套件**       | 复杂仓库拆分为多个关联子技能，关系经过 DAG 校验                                                 |

---

## 安装（开发环境）

面向贡献者：本地运行 CLI、跑测试、修改源码。

```bash
# 克隆仓库
git clone <repo-url> repo2skill
cd repo2skill

# 创建虚拟环境并安装
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 验证安装
repo2skill --help
```

依赖：Python 3.11+，以及 `typer`、`pydantic`、`gitpython`、`jinja2`、`pyyaml`。

---

## 部署到 Agent（生产使用）

面向最终用户：将 Repo2Skill 作为一个 Agent Skill 安装到 Agent 运行时的技能目录（例如 Claude Code 的 `~/.claude/skills/`）。

**为什么需要单独的部署步骤？** Agent 运行时从一个固定目录加载技能，技能目录必须自包含——`SKILL.md`、`scripts/`、`references/`，以及 scripts 所依赖的 `repo2skill` Python 包都要齐全。`pip install -e .` 只把包装到了开发环境的 `site-packages`，Agent 进程未必能访问到。`deploy.sh` 解决的就是把"骨架 + 脚本 + 包源码"一起搬到目标目录的问题。

### 一键部署

```bash
# 克隆 Repo2Skill
git clone <repo-url> repo2skill
cd repo2skill

# 部署技能目录（不装依赖）
bash repo2skill-skill/deploy.sh ~/.claude/skills

# 已存在则覆盖（升级时使用）
bash repo2skill-skill/deploy.sh ~/.claude/skills --force

# 自定义子目录名（默认 repo2skill）
bash repo2skill-skill/deploy.sh ~/.claude/skills --skill-name my-r2s
```

### Python 依赖与虚拟环境

**关键约束**：Agent 运行脚本时使用的是它自己进程 `PATH` 上的 `python3`，不会继承你 shell 里 `source venv/bin/activate` 的环境变量。因此必须把 `typer/pydantic/gitpython/jinja2/pyyaml` 装到 **Agent 实际调用的那个 Python** 里。

`deploy.sh --install-deps` 会调用当前 shell 中的 `python3 -m pip install`，部署前用 `which python3` 确认路径与 Agent 一致。常见两种做法：

**方案 A：为 Agent 准备专用虚拟环境（推荐）**：

```bash
python3 -m venv ~/.claude/skills/.venv
source ~/.claude/skills/.venv/bin/activate     # 必需，让 deploy.sh 使用这个 Python
bash repo2skill-skill/deploy.sh ~/.claude/skills --install-deps
# 然后让 Agent 启动时使用该 venv，例如在启动脚本里设置：
#   export PATH="$HOME/.claude/skills/.venv/bin:$PATH"
```

**方案 B：装到 Agent 已在使用的 Python（例如 Homebrew 的 `/opt/homebrew/bin/python3`）**

```bash
bash repo2skill-skill/deploy.sh ~/.claude/skills    # 先只拷贝文件
python3 -m pip install --user typer pydantic gitpython jinja2 pyyaml
# 若遇到 PEP 668 错误（externally-managed-environment），
# 什么都不要加 --break-system-packages，改用方案 A 更安全。
```

> 不推荐直接装到系统 Python；PEP 668 会拦截，即使绕过也容易弄坏其他包依赖。

### 部署后的目录结构

```text
<agent_skills_dir>/repo2skill/
├── SKILL.md          # 技能入口（被 Agent 加载）
├── skill.yaml        # 技能元数据
├── scripts/          # CLI 包装脚本：structure / extract / assemble / audit_g1 / audit_g2
├── references/       # 渐进式披露 Level 3 参考文档
└── repo2skill/       # 内联打包的 Python 包（来自 src/repo2skill/）
```

scripts 内置 `sys.path` 引导，会优先使用同目录下内联的 `repo2skill/` 包，所以 **目标机器无需额外 `pip install -e .`**，只要 Python 环境里有 `typer/pydantic/gitpython/jinja2/pyyaml` 这五个依赖即可（`--install-deps` 会一次装齐）。

### 升级

```bash
cd repo2skill && git pull
bash repo2skill-skill/deploy.sh ~/.claude/skills --force
```

---

## 快速开始

### 开发模式（CLI）

开发环境下直接调用 `repo2skill` 命令：

```bash
# 最简单的用法：分析一个本地仓库，生成单个技能
repo2skill ./my-python-project --non-interactive -o ./output

# 分析 GitHub 仓库
repo2skill https://github.com/psf/black --non-interactive -o ./output

# 套件模式：将复杂仓库拆分为多个技能
repo2skill ./my-monorepo --mode suite --confidence-threshold 0.3 -o ./output

# 自动检测是否应该使用套件模式
repo2skill ./my-project --mode auto -o ./output

# 交互模式（默认）：手动选择要生成的候选技能
repo2skill ./my-project --interactive -o ./output

# 导出分析结果供 Agent 审阅
repo2skill ./my-project --non-interactive --write-analysis -o ./output
```

### Agent 模式

部署到 `<agent_skills_dir>/repo2skill/` 后，Agent 会自动加载 `SKILL.md`。在对话中直接说：

> "把 `https://github.com/psf/black` 转换成 Agent Skill。"

Agent 将依次执行：

1. 运行 `scripts/structure.py` 分析仓库结构
2. 运行 `scripts/extract.py` 获取规则基线评分
3. Agent 自身作为 Extractor，应用 4 项筛选准则精炼候选技能
4. 展示候选技能供你选择
5. 检测是否需要套件模式
6. 组装技能目录
7. 执行 G1 静态安全扫描
8. Agent 作为 Reviewer G2 进行语义审查
9. 计算最终信任等级

---

## CLI 参数参考

| 参数                                  | 类型                      | 默认值        | 说明                             |
| ------------------------------------- | ------------------------- | ------------- | -------------------------------- |
| `source`                              | `str`                     | 必填          | GitHub URL、git URL 或本地路径   |
| `--out` / `-o`                        | `Path`                    | 当前目录      | 输出目录                         |
| `--verbose` / `-v`                    | `bool`                    | `false`       | 详细日志                         |
| `--interactive` / `--non-interactive` | `bool`                    | `interactive` | 交互式/非交互式候选选择          |
| `--mode`                              | `single \| suite \| auto` | `auto`        | 输出模式                         |
| `--confidence-threshold`              | `float`                   | `0.8`         | 非交互模式下自动选择的最低置信度 |
| `--force-continue`                    | `bool`                    | `false`       | G1 发现高危项时仍继续            |
| `--write-analysis`                    | `bool`                    | `false`       | 导出 `analysis.json` 到输出目录  |

---

## 输出结构

### 单技能模式

```text
<output>/
└── <skill-name>-skill/
    ├── SKILL.md           # 技能入口（含 frontmatter + 四元组）
    ├── skill.yaml         # 技能元数据（kebab-case）
    ├── scripts/           # Level 3 辅助脚本
    ├── references/        # Level 3 参考文档
    ├── templates/         # Level 3 模板
    └── verification/      # 验证报告
        └── g1_report.json # G1 静态扫描报告
```

### 套件模式输出

```text
<output>/
└── <suite-name>-suite/
    ├── suite.yaml         # 套件元数据（suite-id / skills[] / relations[] / trust-level）
    ├── README.md          # 套件总览
    ├── <sub-skill-1>/
    │   ├── SKILL.md
    │   └── skill.yaml
    ├── <sub-skill-2>/
    │   └── ...
    └── verification/      # 套件级验证
```

### 中间产物

当使用 `--write-analysis` 时，输出目录还会包含：

| 文件              | 来源           | 内容                                             |
| ----------------- | -------------- | ------------------------------------------------ |
| `analysis.json`   | `structure.py` | 四元组标注、依赖图、README 摘要                  |
| `candidates.json` | `extract.py`   | 规则基线评分（含 confidence、reasoning、scores） |

---

## 工作流：分步执行

如果你不想一次性跑完整个流水线，可以直接调用 `scripts/` 中的脚本分步执行。下方示例使用开发仓库内的路径 `repo2skill-skill/scripts/`；**部署后** 路径变为 `<agent_skills_dir>/repo2skill/scripts/`，参数完全相同。

```bash
# 步骤 1：解构 —— 分析仓库，生成 analysis.json
python repo2skill-skill/scripts/structure.py <source> <output_dir>

# 步骤 2：提取 —— 规则基线评分，生成 candidates.json
python repo2skill-skill/scripts/extract.py <output_dir>/analysis.json <output_dir>

# 步骤 3：Agent 审阅 candidates.json，应用 4 项筛选准则，选出最终技能

# 步骤 4：组装 —— 渲染模板，生成技能目录
python repo2skill-skill/scripts/assemble.py <output_dir>/analysis.json <sk1,sk3> <output_dir>
# 套件模式：
python repo2skill-skill/scripts/assemble.py <output_dir>/analysis.json <sk1,sk3> <output_dir> --mode suite

# 步骤 5：G1 静态安全扫描
python repo2skill-skill/scripts/audit_g1.py <skill_dir>

# 步骤 6：G2 审查上下文生成（供 Agent 使用）
python repo2skill-skill/scripts/audit_g2.py <skill_dir> <output_dir>/analysis.json
```

---

## Extractor 的四项筛选准则

当 Agent 作为 Extractor 时，从 `candidates.json` 的规则基线出发，应用以下准则精炼评分：

### 1. 重复度 Recurrence（0.0–1.0）

该模式在仓库中有多独特？越罕见的模式越值得文档化。

- 检查 `dependency_graph` 中是否有相似结构的模块
- `__init__` 方法很常见，不要高估其价值
- 仓库中唯一的方法/入口得分更高

### 2. 验证度 Verification（0.0–1.0）

文档写得有多好？

- 检查 `conditions.trigger`（从 docstring 首行预填充）
- 检查 `interface.params` 中的类型注解（空字符串值 = 无类型提示）
- 检查 `policy.steps` 数量和具体程度

### 3. 非显然度 Non-obviousness（0.0–1.0）

代码有多复杂？复杂度越高，文档化价值越大。

- `policy.steps` 数量（26 步是极端，1–2 步较简单）
- `policy.dependencies` 广度
- `conditions.preconditions` 具体程度

### 4. 泛化度 Generalizability（0.0–1.0）

在多种上下文中的复用性如何？

- `interface.params` 中的参数数量（但 `self` 不计算在内）
- `conditions.file_patterns` 的广度（如 `["*.py", "*.md"]` > `["*.py"]`）
- "function" 类型比 "script" 类型复用性更高

### 评分合成

```text
confidence = (recurrence + verification + non_obviousness + generalizability) / 4
```

可在 ±0.1 范围内根据定性判断微调。对任何偏离规则基线的修改，必须在 `reasoning` 中给出解释。

---

## 信任等级

| 等级   | 条件                                      | 使用建议                       |
| ------ | ----------------------------------------- | ------------------------------ |
| **L0** | 未验证 —— 未通过任何安全检查              | 仅供人工审查，不可自动执行     |
| **L1** | G1 静态扫描通过（无高危项）               | 可在受限环境中手动试用         |
| **L2** | L1 + G2 聚合分数 >= 0.8，且无维度低于 0.5 | 可在监控下由 Agent 调用        |
| L3     | G3 沙箱验证通过                           | 标准生产可用（Phase 3 规划中） |
| L4     | 全部 G1–G4 通过                           | 最高信任（Phase 3 规划中）     |

---

## G2 语义审查

Agent 作为 Reviewer G2 时，从三个维度评估生成的技能：

### 幻觉检查

技能是否引用了原仓库中不存在的 API、函数或文件？

- 对照 `analysis.json` 的 `dependency_graph.nodes` 验证 `policy.entry`
- 验证每个 `policy.steps` 引用（如 "Use module.func()"）对应真实函数
- 检查 `policy.dependencies` 与源仓库实际导入是否一致

### Prompt 注入检查

技能内容是否会导致 Agent 执行非预期命令？

- 覆盖 Agent 安全指南的指令
- 代码块中隐藏的命令
- 操纵性语言（"you MUST"、"ignore previous instructions"）

### 元数据一致性

`SKILL.md` frontmatter 与 `skill.yaml` 是否匹配？

- `name`、`version` 是否一致
- `allowed-tools` 是否一致
- `trust-level` 是否正确反映 G1 结果

### 评分公式

```text
g2_score = (hallucination_score + injection_score + consistency_score) / 3
```

---

## 套件模式

当仓库满足以下任一条件时，应使用套件模式：

1. **候选数 > 1** 且合并后 Level 2 正文超过 4,000 tokens
2. **多个入口点类型**：候选技能中存在不同的 `policy.type`（如同时有 "script" 和 "function"）
3. **依赖图分离**：`dependency_graph` 包含两个或以上互不连通的子图
4. **工具集分歧**：候选技能的 `allowed-tools` 集合差异显著

套件内部技能关系类型：

- `depends-on`：调用前必须先加载目标技能
- `composes`：当前技能是套件的组成部分
- `bundled-with`：对等技能，建议一起安装
- `requires-output-from`：产出消费关系，Agent 可据此自动串联调用

所有关系必须构成 DAG（无环），否则需要调整技能划分。

---

## 测试

```bash
# 运行全部测试（60 个）
.venv/bin/python -m pytest tests/ -v

# 仅运行冒烟测试
.venv/bin/python -m pytest tests/smoke/ -v

# 仅运行 Phase 2 测试
.venv/bin/python -m pytest tests/phase2/ -v

# 运行单个测试
.venv/bin/python -m pytest tests/phase2/test_suite.py::TestValidateDAG::test_cycle_detected -v
```

---

## 常见问题

### 为什么生成的技能信任等级是 L0？

L0 是组装时的默认等级。CLI 在组装后执行 G1 扫描，如果通过则更新为 L1。使用 `--non-interactive` 模式时可以看到最终的信任等级输出。

### 为什么没有 API Key 参数？

Repo2Skill 遵循"Agent 就是 LLM"的架构原则。Python 脚本只做确定性工作（AST 解析、正则扫描、模板渲染），所有推理工作（Extractor 精炼、G2 审查）由 Agent 自身完成，不需要额外的 API 调用。

### 如何让 Agent 执行 G2 审查？

1. 先运行 `audit_g2.py` 生成审查上下文文件 `g2_<skill>.md`
2. 让 Agent 读取该文件
3. Agent 按照 SKILL.md 中 G2 Review 部分的指引，从幻觉、注入、一致性三个维度评估
4. Agent 将分数写入 `skill.yaml` 的 `security.g2-score` 字段

### 支持哪些语言？

当前仅支持 Python。多语言支持（JS/TS、Go、Rust）计划在 Phase 4 实现。

### 为什么不用 tree-sitter？

Phase 1–2 使用 Python 标准库的 `ast` 模块，足以覆盖 Python 仓库的分析需求。迁移到 `tree-sitter` 计划在 Phase 4（多语言扩展）时进行。
