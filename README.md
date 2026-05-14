# Repo2Skill

> 将任意 Git 仓库自动转化为经过验证的 Agent 技能。

**Repo2Skill** 是一个遵循 Agent Skills 协议的技能包，它教会 Agent 如何解构任意 Git 仓库并输出一个符合标准的 Agent 技能（或在仓库较为复杂时，输出一个 **技能套件**）。它结合确定性脚本与 Agent 推理能力，覆盖全生命周期：分析、提取、组装、安全验证（G1/G2）、质量评分。

**状态**：v0.2.0 · Phase 1+2 完成 · 65 测试通过

---

## 为什么需要 Repo2Skill

Anthropic 的 Agent Skills 协议标准化了技能封装方式（`SKILL.md` + frontmatter + 渐进式披露），但如何从开源长尾中系统地提取技能仍然是一个高人工成本、高风险的过程。Repo2Skill 自动化整条流水线。

核心特性：

| 特性                        | 含义                                                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **四元组模型**              | 每个技能被分解为 `(Conditions, Policy, Termination, Interface)` —— 显式、机器可检查、利于审计                        |
| **渐进式披露**              | Level 1 frontmatter（30–100 tokens）/ Level 2 正文（200–5,000）/ Level 3 辅助资产（无上限）                          |
| **G1 安全扫描**             | 17 条正则/AST 规则，三级（high/medium/low），高危阻断 + `--force-continue` 覆盖                                      |
| **G2 语义审查**             | Agent 执行三维度评估（幻觉、注入、元数据一致性），数值评分写入 `skill.yaml`                                          |
| **Agent 增强（Enrich）**    | Agent 在组装后实质性重写 SKILL.md：将 "Use func()" 替换为自然语言步骤，功能性命名，上下文补充                        |
| **技能套件（Skill Suite）** | 复杂仓库映射为一组相关技能，关系经过 DAG 校验（`depends-on` / `composes` / `bundled-with` / `requires-output-from`） |
| **注册中心就绪**            | 输出使用 kebab-case 字段的 `skill.yaml`，兼容 JFrog Artifactory、AWS Agent Registry 等目录                           |

---

## 工作原理

```text
[源码仓库]
    │
    ▼
structure.py ───► analysis.json ───► Agent (Extractor)
    (AST解析,          (165个函数,       (5步筛选: Filter →
     依赖图构建,        依赖图,          Merge → Score → Enrich)
     机械式四元组)      README摘要)            │
                                               ▼
                                       assemble.py ───► SKILL.md (模板)
                                               │
                                               ▼
                                       Agent (Enrich) ───► SKILL.md (重写)
                                               │
                                               ▼
                                       audit_g1.py ───► G1 报告
                                               │
                                               ▼
                                       Agent (Reviewer G2) ───► G2 评分
                                               │
                                               ▼
                                       Trust Level (L0–L2)
```

**角色分工**（Python = 机械，Agent = 判断）：

| 角色            | 执行主体   | 职责                                                                                                   |
| --------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| **Structurer**  | 确定性脚本 | AST 解析、依赖图构建、四元组预标注（docstring → trigger，签名 → params）。**不过滤、不推断、不判断。** |
| **Extractor**   | Agent      | 5 步筛选（Filter 去噪 → Merge 合并 → Score 评分 → Present 展示 → Enrich 重写）                         |
| **Assembler**   | 确定性脚本 | Jinja2 模板渲染 → 技能目录（模板基线，Agent 后续重写）                                                 |
| **Reviewer G1** | 确定性脚本 | 正则/AST 静态扫描 → `g1_report.json`                                                                   |
| **Reviewer G2** | Agent      | 3 维度语义审查 → 评分写入 `skill.yaml`                                                                 |

---

## 快速开始

```bash
# 安装
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# CLI 模式
repo2skill ./my-python-project --non-interactive -o ./output
repo2skill ./my-monorepo --mode suite -o ./output

# 运行测试
.venv/bin/python -m pytest tests/ -v
```

Agent 模式：加载 `repo2skill-skill/SKILL.md`，然后说 "把这个仓库转换成 Agent Skill"。

---

## 仓库结构

```text
Repo2Skill/
├── repo2skill-skill/          # 可分发的 Agent Skill 清单
│   ├── SKILL.md               # 完整工作流（12 步）+ Extractor 5-step + Enrich Guide
│   ├── skill.yaml             # Repo2Skill 自身元数据
│   └── scripts/               # 薄 CLI 包装器 → 导入 src/repo2skill/
├── src/repo2skill/            # Python package（所有确定性逻辑）
│   ├── models.py              # Pydantic 模型（Skill 四元组、G1/G2 报告、Suite）
│   ├── structure.py           # Structurer：AST 解析 + 依赖图 + 四元组预标注
│   ├── extractor.py           # 规则基线评分（Agent 的提示，非决策）
│   ├── assemble.py            # Jinja2 渲染 → 技能目录
│   ├── suite.py               # Suite 检测（4 准则）+ DAG 校验 + 套件组装
│   ├── reviewer/g1.py         # G1 静态扫描（17 条规则）
│   └── cli.py                 # typer CLI
├── templates/                 # Jinja2 模板（skill.md.j2, skill.yaml.j2, suite.yaml.j2）
├── tests/                     # 65 测试（8 smoke + 57 phase2）
├── docs/
│   ├── design.md              # 完整设计文档 v1.0
│   ├── task.md                # 5 阶段 × 42 任务（含状态追踪）
│   └── usage-guide.md         # 中文使用指南
├── pyproject.toml
└── README.md
```

---

## 阶段概览

| 阶段 | 名称          | 退出条件                                             | 状态      |
| ---- | ------------- | ---------------------------------------------------- | --------- |
| 1    | 核心流水线    | Python 仓库 → `SKILL.md`，端到端跑通                 | ✅        |
| 2    | G1 + G2       | 静态扫描 + 语义审查；Trust Level L0–L2；Agent Enrich | ✅        |
| 3    | G3 + G4       | Docker 沙箱 + 权限比对；完整的 L0–L4                 | ⬜ 规划中 |
| 4    | 多语言 + 套件 | JS/TS、Go、Rust；套件已提前实现                      | 🔶        |
| 5    | 自举 + 生态   | Repo2Skill 自我生成；注册中心对接                    | ⬜        |

---

## 文档

- **[docs/design.md](docs/design.md)** — 设计文档 v1.0（13 章）
- **[docs/task.md](docs/task.md)** — 5 阶段 × 42 任务（含当前状态与实现偏离记录）
- **[docs/usage-guide.md](docs/usage-guide.md)** — 中文使用指南

---

## 许可证

参见 [LICENSE](LICENSE)。
