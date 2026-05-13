# Repo2Skill v1.0 任务分解

**配套设计文档**：[design.md](./design.md)
**版本**：1.0
**日期**：2026-05-13
**状态**：草案

本文档将 [design.md](./design.md) §11 开发路线图中的五个阶段展开为可追踪、可验收的具体任务。每条任务包含：

- **ID**：`P<phase>-T<task>` 形式的唯一标识。
- **标题**：简明描述。
- **设计锚点**：对应 `design.md` 的章节。
- **依赖**：前置任务 ID（无则留空）。
- **交付物**：可提交、可验证的文件或功能。
- **验收标准**：可测量的完成判据。

---

## 目录

- [Repo2Skill v1.0 任务分解](#repo2skill-v10-任务分解)
  - [目录](#目录)
  - [Phase 1 核心骨架](#phase-1-核心骨架)
  - [Phase 2 G1/G2 验证与交互完善](#phase-2-g1g2-验证与交互完善)
  - [Phase 3 G3/G4 沙箱与非交互模式](#phase-3-g3g4-沙箱与非交互模式)
  - [Phase 4 多语言扩展与技能套件](#phase-4-多语言扩展与技能套件)
  - [Phase 5 自举、文档与生态对接](#phase-5-自举文档与生态对接)
  - [里程碑与交付节奏](#里程碑与交付节奏)
  - [风险与缓解](#风险与缓解)

---

## Phase 1 核心骨架

**目标**：跑通从 Python 仓库到可读 `SKILL.md` 的端到端主干，不含安全验证。

| ID    | 标题                       | 设计锚点                                                                                                     | 依赖         | 交付物                                                                                                          | 验收标准                                                                                                                                                          |
| ----- | -------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------ | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1-T1 | 项目脚手架初始化           | [§4](./design.md#4-技能结构与组件)                                                                           | —            | `repo2skill-skill/` 目录骨架、`scripts/requirements.txt`、`pyproject.toml`、`pre-commit` 配置                   | `pip install -e .` 成功，`pytest -q` 返回占位测试通过                                                                                                             |
| P1-T2 | 四元组数据模型             | [§2.1](./design.md#21-技能的四元组定义)                                                                      | P1-T1        | `models.py`：`Skill`、`Conditions`、`Policy`、`Termination`、`Interface` 五个 Pydantic 模型                     | 模型序列化输出的 JSON 键名符合 [§12.1](./design.md#121-analysisjson-四元组输出片段structurepy-产出) 中的示例                                                      |
| P1-T3 | Structurer：仓库克隆与 AST | [§2.3](./design.md#23-分层角色架构-script--agent-混合)、[§9](./design.md#9-技术选型)                         | P1-T2        | `scripts/structure.py`：`gitpython` 克隆、`tree-sitter` 解析、依赖图构建                                        | 对 `psf/black` 生成 `analysis.json`，包含 ≥ 3 个函数签名与完整依赖边                                                                                              |
| P1-T4 | Structurer：四元组预标注   | [§2.1](./design.md#21-技能的四元组定义)                                                                      | P1-T3        | Structurer 预填充 C/π/T/R 字段（基于签名、docstring 与依赖图）                                                  | 生成的 `analysis.json` 覆盖入口点的 `entry`、`dependencies`、`params` 字段                                                                                        |
| P1-T5 | Extractor 原型（规则版）   | [§2.3](./design.md#23-分层角色架构-script--agent-混合)                                                       | P1-T4        | `prompts/extractor.md` + 1–5 候选技能生成逻辑                                                                   | 对样例仓库输出 1–5 条候选，覆盖 Recurrence/Verification/Non-obviousness/Generalizability 四准则                                                                   |
| P1-T6 | Assemble：Jinja2 模板      | [§12.2](./design.md#122-技能-skillmd-模板核心章节jinja2)                                                     | P1-T2        | `templates/skill.md.j2`、`templates/skill.yaml.j2`                                                              | 渲染结果包含 `name/description/version/dependencies/allowed-tools/trust-level` 全部字段；`{% raw %}` 块完整                                                       |
| P1-T7 | Assemble：`assemble.py`    | [§4](./design.md#4-技能结构与组件)、[§5.1](./design.md#51-交互式流程)、[§2.4](./design.md#24-渐进式披露架构) | P1-T5、P1-T6 | `scripts/assemble.py`：渲染 + 目录组装（`SKILL.md` / `skill.yaml` / `scripts/` / `references/` / `templates/`） | 对样例仓库生成的 `<output-skill>/` 通过 `markdownlint` 与 `yamllint` 基本检查；Level 1 frontmatter 30–100 tokens、Level 2 正文 200–5,000 tokens（符合渐进式披露） |
| P1-T8 | CLI 入口                   | [§3.1](./design.md#31-产品形态)                                                                              | P1-T7        | `typer` CLI：`repo2skill <github-url>` 端到端                                                                   | 从 URL 到 `<output-skill>/` 单命令完成；`--help` 输出准确                                                                                                         |
| P1-T9 | Phase 1 冒烟测试           | [§10](./design.md#10-自举与自我进化)                                                                         | P1-T8        | `tests/smoke/test_phase1.py`：Python 样例仓库端到端                                                             | GitHub Actions 上 `pytest tests/smoke` 绿灯                                                                                                                       |

---

## Phase 2 G1/G2 验证与交互完善

**目标**：引入静态与语义两级安全验证，完善 Agent ↔ 用户交互。

| ID    | 标题                               | 设计锚点                                                                                      | 依赖         | 交付物                                                                                | 验收标准                                                                                                                                          |
| ----- | ---------------------------------- | --------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| P2-T1 | G1 规则库设计                      | [§2.2](./design.md#22-安全验证体系-g1g4)                                                      | P1-T9        | `rules/g1_patterns.yaml`：危险 API 正则 + AST 规则                                    | 覆盖 `eval` / `exec` / `os.system` / `socket` / `shutil.rmtree` 等 ≥ 15 条规则                                                                    |
| P2-T2 | `audit_g1.py`                      | [§2.2](./design.md#22-安全验证体系-g1g4)、[§7](./design.md#7-多维度质量评估)                  | P2-T1        | `scripts/audit_g1.py` + `g1_report.json` schema                                       | 已知含 `eval` 样例被识别；无报警样例通过；报告含 `vulnerability-rate` 字段                                                                        |
| P2-T3 | Extractor 升级为 Agent-in-the-loop | [§2.3](./design.md#23-分层角色架构-script--agent-混合)                                        | P1-T5        | Agent 协议（输入/输出 JSON schema）+ prompts                                          | 对同一仓库，Agent 版 Recall ≥ 规则版 × 1.3                                                                                                        |
| P2-T4 | G2 审查提示生成                    | [§2.2](./design.md#22-安全验证体系-g1g4)                                                      | P2-T2        | `scripts/audit_g2.py`：聚合源码 + SKILL.md diff 生成审查提示                          | 生成的提示长度 ≤ 8k tokens，且包含幻觉检测、prompt 注入、元数据一致性三类检查点                                                                   |
| P2-T5 | G2 分数映射                        | [§5.1](./design.md#51-交互式流程)（G2 分数映射说明）、[§8.1](./design.md#81-技能注册中心就绪) | P2-T4        | `g2_score` 计算器：类别 → 区间数值；写入 `skill.yaml` 使用 kebab-case `g2-score` 字段 | 输出 ∈ `[0.0, 1.0]` 且符合 `完整 → [0.9, 1.0]` / `部分 → [0.5, 0.9)` / `存疑 → [0.0, 0.5)` 规则；`skill.yaml` 中字段名为 `g2-score`（kebab-case） |
| P2-T6 | 交互式候选展示                     | [§3.2](./design.md#32-用户故事)、[§5.1](./design.md#51-交互式流程)                            | P1-T5        | Agent 端脚本模板：候选清单 + 多选输入解析                                             | 支持 `1,3` / `all` / `none` / `描述文本` 四种输入，并给出错误提示                                                                                 |
| P2-T7 | 异常回退机制                       | [§5.3](./design.md#53-异常处理与回退)                                                         | P2-T2        | 回退逻辑：克隆失败 / 无候选 / G1 高危 / G3 超时 / G4 越权                             | 每种异常均有单元测试覆盖，输出退出码与日志                                                                                                        |
| P2-T8 | Trust Level L0–L2 计算器           | [§6.1](./design.md#61-trust-level-计算)                                                       | P2-T2、P2-T5 | `trust_level.py`：根据 G1/G2 结果输出 L0/L1/L2                                        | 覆盖率测试 ≥ 90%，边界情况（G1 通过但 G2 存疑）结果为 L1                                                                                          |

---

## Phase 3 G3/G4 沙箱与非交互模式

**目标**：打通完整的 G1–G4 四级验证，并支持批处理。

| ID    | 标题                     | 设计锚点                                                                  | 依赖  | 交付物                                                                              | 验收标准                                                                           |
| ----- | ------------------------ | ------------------------------------------------------------------------- | ----- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| P3-T1 | Docker 基础镜像          | [§6.2](./design.md#62-安全边界)                                           | P2-T8 | `docker/runner.Dockerfile`：Python 3.11 slim + `tree-sitter` + 常用格式化/lint 工具 | 镜像 < 400 MB；`docker run --rm` 启动 < 2s                                         |
| P3-T2 | `audit_g3.py`            | [§2.2](./design.md#22-安全验证体系-g1g4)、[§6.2](./design.md#62-安全边界) | P3-T1 | 沙箱执行器：`--network none`、只读挂载、CPU/内存限制、120s 超时                     | 对 `black` 格式化样例返回 `g3_passed: true`；对触发超时样例返回 `g3_passed: false` |
| P3-T3 | G3 测试用例生成器        | [§5.1](./design.md#51-交互式流程) 步骤 6                                  | P2-T3 | Agent prompts：基于技能描述生成验收测试 + 期望断言                                  | 3 个样例技能各生成 ≥ 1 个可执行测试用例                                            |
| P3-T4 | `audit_g4.py`            | [§2.2](./design.md#22-安全验证体系-g1g4)                                  | P3-T2 | G3 执行轨迹解析 + `allowed-tools` 差异分析                                          | 识别 `write` 越权、`网络调用` 越权两类案例；输出 `g4_report.json` 列出越权项       |
| P3-T5 | Trust Level L3/L4 计算   | [§6.1](./design.md#61-trust-level-计算)                                   | P3-T4 | 扩展 `trust_level.py`                                                               | G1+G2+G3 通过 → L3；四项全部通过 → L4；单元测试覆盖 ≥ 95%                          |
| P3-T6 | 多维度评估汇总           | [§7](./design.md#7-多维度质量评估)                                        | P3-T4 | `scripts/aggregate_report.py` → `verification/report.json`                          | 五个维度指标齐全；安全维度与 G1 报告 `Vulnerability Rate` 数值一致                 |
| P3-T7 | `--non-interactive` 模式 | [§5.2](./design.md#52-非交互模式)                                         | P3-T6 | CLI 标志：`--non-interactive`、`--confidence-threshold`、`--skip-g3`                | 批量处理 10 个仓库的脚本一次性完成；失败项记入 `batch_summary.json`，不阻塞后续    |
| P3-T8 | 端到端回归测试           | [§10](./design.md#10-自举与自我进化)                                      | P3-T7 | `tests/e2e/fixtures/` 内含 3 个代表性仓库                                           | CI 上完整 G1–G4 流程耗时 < 8 分钟；生成技能全部达到 L3 或以上                      |

---

## Phase 4 多语言扩展与技能套件

**目标**：覆盖 JS/TS、Go、Rust；支持将复杂仓库映射为相关联的技能套件。

| ID    | 标题                       | 设计锚点                                                                             | 依赖  | 交付物                                                                    | 验收标准                                                                                                                          |
| ----- | -------------------------- | ------------------------------------------------------------------------------------ | ----- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| P4-T1 | `tree-sitter` 语法包集成   | [§9](./design.md#9-技术选型)                                                         | P3-T8 | JS/TS、Go、Rust 四语言语法包载入与 AST 抽象                               | 对每语言样例仓库生成函数级签名与依赖边                                                                                            |
| P4-T2 | 多语言 G1 规则扩展         | [§2.2](./design.md#22-安全验证体系-g1g4)                                             | P4-T1 | `rules/g1_patterns.{js,go,rs}.yaml`                                       | 每语言 ≥ 8 条危险 API 规则；false positive 率 < 10%                                                                               |
| P4-T3 | 套件触发准则实现           | [§2.5](./design.md#25-技能套件-skill-suite)                                          | P4-T1 | `suite_detector.py`：候选数/Token 估算/入口点/依赖图/权限差异五准则       | 对 `data-pipeline` 级仓库触发套件；简单工具仓库保持单技能                                                                         |
| P4-T4 | `suite.yaml` schema + 渲染 | [§4](./design.md#4-技能结构与组件)                                                   | P4-T3 | `templates/suite.yaml.j2` + 校验器                                        | 生成的 `suite.yaml` 含 `suite-id/version/source/skills/relations/trust-level` 全部字段                                            |
| P4-T5 | 关系标注与 DAG 校验        | [§2.5](./design.md#25-技能套件-skill-suite)、[§5.4](./design.md#54-套件模式执行调整) | P4-T4 | 两两关系评估 prompt + 图构建器 + 环检测                                   | 对已知含环案例触发模块重划分提示；无环案例通过                                                                                    |
| P4-T6 | `assemble.py --suite`      | [§5.4](./design.md#54-套件模式执行调整)                                              | P4-T5 | 扩展 `assemble.py`：一次性生成 `<output-suite>/` 与所有子技能             | 子技能目录数 = 识别出的技能数；顶层 `README.md` 自动生成                                                                          |
| P4-T7 | 跨技能集成测试             | [§5.4](./design.md#54-套件模式执行调整)                                              | P4-T6 | 端到端流水线生成器：按 `requires-output-from` 链路串联                    | 对 `data-pipeline` 套件生成 ≥ 1 条覆盖全部成员的流水线测试                                                                        |
| P4-T8 | 套件级 Trust Level         | [§6.1](./design.md#61-trust-level-计算)、[§2.5](./design.md#25-技能套件-skill-suite) | P4-T7 | 取成员最低值 + 关系完整性补偿                                             | 当任一成员 < L2 时套件 ≤ L2；关系图不完整时套件降一级                                                                             |
| P4-T9 | SkillNet 本体写入          | [§8.3](./design.md#83-skillnet-本体标注)                                             | P4-T6 | `skill.yaml.ontology.relations` 与 `skill.yaml.dependencies` 字段自动填充 | 四种关系类型（`depends-on`/`composes`/`bundled-with`/`requires-output-from`）均可生成；`dependencies` 按 §12.2 结构写入运行时依赖 |

---

## Phase 5 自举、文档与生态对接

**目标**：Repo2Skill v1.0 GA，具备分发、升级、演化能力。

| ID    | 标题                  | 设计锚点                                               | 依赖          | 交付物                                                               | 验收标准                                                                |
| ----- | --------------------- | ------------------------------------------------------ | ------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| P5-T1 | 自举测试              | [§10](./design.md#10-自举与自我进化)                   | P4-T9         | 对 Repo2Skill 自身仓库执行 `repo2skill` 的脚本与报告                 | 生成的自描述技能通过 G1–G4，Trust Level ≥ L3                            |
| P5-T2 | 用户文档              | —                                                      | P5-T1         | `docs/README.md`、`docs/quickstart.md`、`docs/faq.md`                | 新用户可在 15 分钟内完成第一个技能生成                                  |
| P5-T3 | 开发者文档            | [§2.3](./design.md#23-分层角色架构-script--agent-混合) | P5-T1         | `docs/architecture.md`、`docs/contributing.md`                       | 包含组件交互图与贡献流程                                                |
| P5-T4 | 注册中心对接示例      | [§8.1](./design.md#81-技能注册中心就绪)                | P5-T1         | JFrog Artifactory / AWS Agent Registry / agentskills.so 三个示例脚本 | 每个示例附带 README 与 CI 触发命令；至少一个示例在 staging 环境推送成功 |
| P5-T5 | `skill-mem` 集成      | [§8.2](./design.md#82-技能演化与升级)                  | P5-T1         | `integration/skill_mem_adapter.py`                                   | 生成技能时写入 `skill-mem` 记录，包含来源、版本、提取时间戳             |
| P5-T6 | 技能升级流程          | [§8.2](./design.md#82-技能演化与升级)                  | P5-T5         | `scripts/upgrade.py`：diff + 升级建议生成                            | 对新旧版本 `psf/black` 输出结构化升级建议 JSON                          |
| P5-T7 | Evolution Agents 钩子 | [§8.2](./design.md#82-技能演化与升级)                  | P5-T6         | 日志采集钩子：记录用户对生成技能的修改与反馈                         | 对 10 次用户交互产生 ≥ 1 条建议优化                                     |
| P5-T8 | GA 发布与版本冻结     | [§11](./design.md#11-开发路线图)                       | P5-T2 – P5-T7 | `CHANGELOG.md` v1.0.0、签名 tag、GitHub Release                      | PyPI 包可 `pip install repo2skill==1.0.0`；Release 页含校验和           |

---

## 里程碑与交付节奏

| 里程碑 | 对应 Phase | 关键产出         | 退出标准                                     |
| ------ | ---------- | ---------------- | -------------------------------------------- |
| M1     | Phase 1    | 可用主干         | Python 仓库端到端成功；冒烟测试绿灯          |
| M2     | Phase 2    | 安全报告 Alpha   | G1/G2 报告可读；Trust Level ≤ L2             |
| M3     | Phase 3    | 沙箱可信 Beta    | 批处理 10 仓库无阻塞失败；平均 L3            |
| M4     | Phase 4    | 多语言 + 套件 RC | 四语言覆盖；`data-pipeline` 级仓库正确套件化 |
| M5     | Phase 5    | v1.0 GA          | 自举通过；注册中心示例可推送；文档完备       |

---

## 风险与缓解

| 风险                               | 影响                    | 缓解策略                                                              |
| ---------------------------------- | ----------------------- | --------------------------------------------------------------------- |
| `tree-sitter` 多语言语法包兼容性差 | Phase 1 与 Phase 4 延期 | 预置语法版本锁，CI 对每语言最小样例定期回归                           |
| Docker 在 CI 环境受限              | Phase 3 延期            | 提供 `--skip-g3` 降级通道；本地开发者机器为 G3 主要运行环境           |
| Agent 生成 prompt 漂移             | G2/Extractor 质量不稳   | 版本化 prompts，提供 `prompts/CHANGELOG.md`；关键 prompt 纳入评估基准 |
| 套件关系图爆炸                     | Phase 4 性能            | 对 > 8 个子技能的仓库退回到模块级分片策略                             |
| 注册中心 API 变更                  | Phase 5 延期            | 将对接逻辑抽象为适配器接口；CI 每周对三个目标注册中心做健康检查       |
