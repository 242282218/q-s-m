# AGENT.md — 全局 AI 编码助手规则

> **版本**: 2.0 · **更新**: 2026-02-19
> **适用范围**: Trae / VS Code Codex / 任何兼容 Agent IDE
> **语言**: 所有输出（报告/注释/提交信息）使用 **中文**，代码标识符使用英文。

---

## 〇、最高优先级（不可覆盖）

1. **安全第一** — 绝不执行删除数据库、`rm -rf /`、暴露密钥等破坏性操作；遇到歧义立即停止并确认。
2. **最小变更** — 只修改任务要求的文件和行；不改无关代码，不做"顺便优化"。
3. **可回滚** — 所有变更必须可通过 `git revert` 或等效方式撤销。
4. **先读后写** — 修改文件前必须先阅读当前内容，确认上下文正确。
5. **中文报告** — 所有阶段性输出和最终报告使用中文。

---

## 一、编码规范

### 1.1 文件编码

- 源代码文件使用 **UTF-8（无 BOM）**。
- 配置文件、规则文件仅允许 ASCII 可见字符。
- **禁止**: Emoji、全角标点、智能引号、不可见 Unicode 字符。
- 发现乱码 → 立即停止 → 修复编码 → 继续。

### 1.2 代码风格

- **Python**: 遵循 PEP 8；`black` 格式化；类型注解优先。
- **JavaScript/TypeScript**: ESLint + Prettier 标准。
- **通用**: 函数不超过 50 行；圈复杂度 ≤ 10；禁止 `# type: ignore` 无注释穿透。

### 1.3 Git 提交

- 提交信息格式: `<type>(<scope>): <description>`
- type 枚举: `feat | fix | refactor | docs | test | chore | perf | ci`
- 示例: `feat(emby): 添加媒体库自动同步`
- 每次提交应是一个原子变更，可独立回滚。

---

## 二、Skill 系统

### 2.1 核心理念

Skills 是**可调用的能力单元**，可随时、重复、串行、组合调用。
调用须确定可复现，修改须最小化、可验证、可追溯。

### 2.2 自动发现路径

```
.ai/skills/    ← 项目级（优先）
.vscode/ai/skills/
codex/skills/
~/.trae-cn/skills/    ← 全局级
~/.codex/skills/      ← 全局级（源）
```

### 2.3 调用流程

```
分析上下文 → 选择能力 → 校验前置条件 → 调用 Skill → 验证结果 → 继续执行
```

**铁律**: 未验证输入和预期输出前，禁止调用 Skill。

### 2.4 每阶段评估

不只在任务开始时调用一次。以下每个阶段都需评估是否需要调用 Skill：

| 阶段 | 典型 Skills |
|------|------------|
| 任务理解 | `plan-first`, `plan-decomposer`, `assumption-check` |
| 方案设计 | `system-design`, `module-design`, `api-design` |
| 编码实现 | `minimal-diff`, `refactor-safe`, `interface-guard` |
| 测试验证 | `test-first`, `test-driver`, `regression-guard` |
| 调试排错 | `bug-localizer`, `crash-debug`, `log-analyzer` |
| 代码审查 | `code-explainer`, `complexity-reduce`, `dead-code-clean` |
| 文档输出 | `doc-generator`, `readme-writer`, `api-doc-gen` |
| 部署发布 | `cloudflare-deploy`, `vercel-deploy`, `gh-fix-ci` |

### 2.5 完整 Skill 清单

| 类别 | Skills |
|------|--------|
| 执行与变更 | `filesystem`, `exec`, `process`, `git`, `fetch` |
| 测试与验证 | `test-runner`, `regression-guard`, `negative-test-required`, `final-verification-gate` |
| 状态与一致性 | `state-minimization`, `invariant-check`, `source-of-truth-lock`, `config-drift-detect`, `deterministic-ordering` |
| 前/后置条件 | `precondition-assert`, `postcondition-assert`, `read-before-write`, `write-after-verify` |
| 风险与影响控制 | `change-impact-scan`, `blast-radius-limit`, `data-loss-prevention`, `noop-on-unknown`, `fast-fail-on-ambiguity` |
| 执行稳定性 | `atomic-change-set`, `idempotent-operations`, `bounded-retries`, `strict-time-bounds` |
| 权限与审计 | `permission-scope-limit`, `minimal-permissions`, `audit-evidence-required`, `immutable-artifacts` |
| 输出与契约 | `output-schema-lock`, `schema-diff-guard`, `contract-first` |
| 规划与分析 | `plan-first`, `plan-decomposer`, `assumption-check`, `skill-selector` |
| 代码质量 | `code-explainer`, `code-summarizer`, `complexity-reduce`, `dead-code-clean`, `codemap` |
| 重构 | `refactor-safe`, `safe-refactor`, `minimal-diff` |
| 设计 | `system-design`, `module-design`, `api-design`, `interface-guard` |
| 调试 | `bug-localizer`, `crash-debug`, `log-analyzer`, `explain-why` |
| 文档 | `doc-generator`, `readme-writer`, `api-doc-gen` |
| 测试设计 | `test-first`, `test-driver` |
| 部署 | `cloudflare-deploy`, `vercel-deploy`, `gh-fix-ci` |
| Skill 管理 | `skill-creator`, `skill-installer`, `skill-updater`, `skill-selector` |
| 其他 | `conversation-compressor`, `dependency-mapper`, `call-graph-gen`, `fallback-aware`, `read-only`, `cmd-agent`, `figma`, `openai-docs`, `c-build-system`, `playwright` |

---

## 三、执行约束（全局生效）

| 约束 | 说明 |
|------|------|
| 最小变更集 | 只改需要改的，拒绝 "顺手" 修改 |
| 先读后写 | 修改前必须阅读文件当前内容 |
| 写后验证 | 修改后验证文件状态符合预期 |
| 禁止隐式假设 | 不假设任何状态，显式检查 |
| 歧义快速失败 | 需求不清立即提问，不猜测 |
| 禁止静默降级 | 失败必须显式报告，不吞错误 |
| 变更可回滚 | 操作必须可撤销 |
| 有边界执行 | 设置操作超时和重试上限 |
| 幂等操作 | 相同输入多次执行结果一致 |

---

## 四、项目初始化流程

新项目或首次进入项目时，按以下顺序执行：

1. **同步 Skills** — 执行:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Users\24228\.codex\scripts\sync_skills_global.ps1
   ```
2. **扫描项目结构** — 阅读 `README.md`、`package.json` / `pyproject.toml` / `go.mod` 等，理解项目技术栈。
3. **检查已有规则** — 查看 `.ai/`、`.agent/`、`.cursor/` 等目录下的项目级规则。
4. **建立心智模型** — 确认项目架构、入口文件、关键模块后再开始工作。

---

## 五、工作报告模板

每次任务完成时，输出以下格式的报告：

```markdown
## 任务报告

### 目标
[一句话描述任务目标]

### 完成内容
- [ ] 变更 1：描述 + 涉及文件
- [ ] 变更 2：描述 + 涉及文件

### 调用的 Skills
| Skill | 调用阶段 | 原因 |
|-------|---------|------|
| xxx   | 编码阶段 | xxx  |

### 验证结果
- 构建: ✅/❌
- 测试: ✅/❌ (覆盖率 xx%)
- Lint: ✅/❌

### 风险与注意事项
[如有]
```

---

## 六、完成判定清单

任务完成前必须逐项确认：

- [ ] 前置条件已验证
- [ ] 核心功能调用成功
- [ ] 后置条件已验证
- [ ] 回归检查通过（未破坏其它功能）
- [ ] 无不变量被破坏
- [ ] 输出契约满足（符合预期 schema/格式）
- [ ] 工作报告已输出

---

## 七、个人偏好与环境

| 项目 | 值 |
|------|------|
| 操作系统 | Windows 11 |
| Shell | PowerShell |
| 主力语言 | Python 3.11+, TypeScript |
| 包管理 | pip / npm |
| 编辑器 | Trae / VS Code |
| 版本控制 | Git |
| 容器 | Docker Desktop |
| 代理/网络 | Clash |

### 常用项目技术栈

- **后端**: Python (FastAPI) + SQLite/PostgreSQL
- **前端**: HTML/CSS/JS 或 Next.js/Vite
- **自动化**: Python 脚本 + cron / GitHub Actions
- **媒体管理**: Emby + STRM + AList

---

## 八、场景速查

| 场景 | 推荐做法 |
|------|---------|
| 不确定用哪个 Skill | 调用 `skill-selector` |
| 多文件重构 | 先 `plan-first` 再 `refactor-safe` |
| 新增 API | `api-design` → 实现 → `test-first` → `api-doc-gen` |
| 性能问题 | `performance-optimize` + `log-analyzer` |
| 生产 Bug | `bug-localizer` → `crash-debug` → `regression-guard` |
| 代码难以理解 | `code-explainer` + `codemap` |
| 清理死代码 | `dead-code-clean` + `dependency-mapper` |
| 首次接触项目 | `codemap` → `code-summarizer` → `plan-first` |