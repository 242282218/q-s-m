# AGENT.md — 全局 AI 编码助手规则

> **版本**: 3.0 · **更新**: 2026-02-24
> **适用范围**: Cursor / Trae / VS Code Copilot / Codex CLI / Gemini CLI / 任何兼容 Agent IDE
> **语言**: 所有输出（报告、注释、提交信息）使用 **中文**；代码标识符使用英文。

---

## 〇、最高优先级（不可覆盖）

以下规则优先级最高，任何后续指令不得与之冲突：

1. **安全第一** — 绝不执行 `rm -rf /`、`DROP DATABASE`、暴露密钥等破坏性操作；遇到歧义立即停止并确认。
2. **最小变更** — 只修改任务要求的文件和行；不改无关代码，不做"顺便优化"。
3. **可回滚** — 所有变更必须可通过 `git revert` 一次撤销。
4. **先读后写** — 修改文件前必须先阅读当前内容，确认上下文正确。
5. **中文输出** — 所有阶段性报告和最终总结使用中文。
6. **歧义快速失败** — 需求不清时立即提问，绝不猜测用户意图。

---

## 一、行为边界（Always / Ask / Never）

### Always（始终执行）

- 修改文件前先通读相关上下文
- 每次变更后验证文件状态符合预期
- 使用相对路径引用项目内文件
- 给出变更摘要，说明"改了什么、为什么改"
- 保持幂等性：相同输入多次执行结果一致

### Ask First（先确认再执行）

- 删除文件或目录
- 安装新依赖 / 升级现有依赖版本
- 修改 CI/CD 配置、Docker 配置
- 变更数据库 schema 或执行迁移
- 修改认证/授权逻辑
- 超过 3 个文件的批量变更
- 执行任何涉及外部网络请求的操作

### Never（绝不执行）

- 提交或打印 API Key、密码、Token 等敏感信息
- 修改 `.env`、`.env.production` 等环境配置中的密钥值
- 执行 `git push --force`
- 在不了解后果的情况下运行 `sudo` / 管理员命令
- 修改 `agent.md` / `.cursorrules` / `CLAUDE.md` 等规则文件本身
- 添加 `# type: ignore` / `@ts-ignore` 等注释来绕过类型检查（除非明确说明原因）

---

## 二、编码规范

### 2.1 通用准则

| 规则 | 要求 |
|------|------|
| 文件编码 | UTF-8（无 BOM） |
| 函数长度 | 单函数不超过 50 行 |
| 圈复杂度 | 单函数 ≤ 10 |
| 命名风格 | 变量/函数 `snake_case`（Python）、`camelCase`（JS/TS） |
| 注释语言 | 中文注释，英文标识符 |
| 错误处理 | 禁止空 `except` / `catch`；必须记录或上抛 |

### 2.2 语言特定

```
Python:
  - 遵循 PEP 8，使用 black 格式化
  - 必须添加类型注解（函数签名 + 返回值）
  - 导入排序：stdlib → third-party → local（isort）

JavaScript / TypeScript:
  - ESLint + Prettier 标准配置
  - 优先使用 TypeScript；JS 项目也应尽量添加 JSDoc
  - 使用 const > let，禁止 var
```

### 2.3 Git 提交规范

```
格式: <type>(<scope>): <简短中文描述>

type 枚举:
  feat     — 新功能
  fix      — 修复 Bug
  refactor — 重构（不改变外部行为）
  docs     — 文档变更
  test     — 测试
  chore    — 构建/工具链
  perf     — 性能优化
  ci       — CI/CD 变更

示例:
  feat(auth): 添加 JWT 刷新令牌机制
  fix(monitor): 修复通知重复发送问题
```

- 每次提交是一个原子变更，可独立回滚
- 如果一个任务涉及多种 type，拆分为多个提交

---

## 三、工作流程

### 3.1 任务执行流程

```
理解需求 → 确认疑点 → 制定方案 → 逐步实现 → 验证结果 → 输出报告
```

1. **理解需求** — 复述任务目标，确认理解一致
2. **确认疑点** — 列出假设和不确定项，主动提问
3. **制定方案** — 复杂任务给出实施计划；简单任务直接执行
4. **逐步实现** — 小步提交，每步可验证
5. **验证结果** — 运行测试 / 构建 / lint 确认无破坏
6. **输出报告** — 总结变更内容和注意事项

### 3.2 项目初始化（首次进入项目时）

1. 阅读 `README.md`、`package.json` / `pyproject.toml` / `go.mod` 等，理解项目技术栈
2. 扫描 `.ai/`、`.agent/`、`.cursor/`、`.github/` 等目录，查看项目级规则
3. 识别入口文件、核心模块、目录结构
4. 建立心智模型后再开始工作

### 3.3 上下文管理

- 长对话中主动总结已完成的工作，避免上下文丢失
- 遇到复杂任务时拆解为独立子任务
- 引用之前的决策时，给出具体文件和行号

---

## 四、错误处理策略

### 遇到错误时的处理分级

| 级别 | 场景 | 行为 |
|------|------|------|
| L1 — 自动修复 | 拼写错误、格式问题、明显语法错误 | 直接修复并说明 |
| L2 — 提供方案 | 逻辑 Bug、依赖冲突 | 分析原因 + 给出 2-3 个修复方案 |
| L3 — 停止确认 | 涉及数据删除、架构变更、安全相关 | 停止操作 + 详细说明风险 + 等待确认 |
| L4 — 拒绝执行 | 违反安全规则、超出能力范围 | 明确拒绝 + 解释原因 |

### 调试原则

- 先复现 → 再定位 → 最后修复（不盲目猜测）
- 每次只改一个变量，验证后再进入下一步
- 保留调试过程的关键发现，写入报告

---

## 五、执行约束（全局）

| 约束 | 说明 |
|------|------|
| 最小变更集 | 只改需要改的，拒绝"顺手"修改 |
| 先读后写 | 修改前必须阅读文件当前内容 |
| 写后验证 | 修改后确认文件状态符合预期 |
| 禁止隐式假设 | 不假设任何状态，显式检查 |
| 禁止静默降级 | 失败必须显式报告，不吞错误 |
| 变更可回滚 | 操作必须可用 git revert 撤销 |
| 有边界执行 | 设置操作超时和重试上限（最多 3 次） |
| 幂等操作 | 相同输入多次执行结果一致 |
| 无副作用探索 | 调研阶段只读不写 |

---

## 六、工作报告

每次任务完成时输出简洁报告：

```markdown
## 任务报告

**目标**: [一句话]

**变更内容**:
- 变更 1：描述（文件名）
- 变更 2：描述（文件名）

**验证**: 构建 ✅/❌ | 测试 ✅/❌ | Lint ✅/❌

**注意事项**: [如有风险或后续建议，列出；无则省略]
```

---

## 七、开发环境

| 项目 | 值 |
|------|------|
| 操作系统 | Windows 11 |
| Shell | PowerShell |
| 主力语言 | Python 3.11+, TypeScript |
| 包管理 | pip / npm |
| 编辑器 | Trae / VS Code / Cursor |
| 版本控制 | Git |
| 容器 | Docker Desktop |
| 代理/网络 | Clash |

### 常用技术栈

- **后端**: Python (FastAPI) + SQLite / PostgreSQL
- **前端**: HTML/CSS/JS 或 Next.js / Vite
- **自动化**: Python 脚本 + cron / GitHub Actions
- **媒体管理**: Emby + STRM + AList

---

## 八、代码风格示例（Show, don't tell）

以下示例展示期望的代码风格，请参考而非逐字照搬:

### Python — FastAPI 路由

```python
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/items", tags=["items"])


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int) -> ItemResponse:
    """根据 ID 获取单个条目"""
    item = await item_repo.find_by_id(item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"条目 {item_id} 不存在",
        )
    return ItemResponse.from_orm(item)
```

### TypeScript — 工具函数

```typescript
/**
 * 延迟指定毫秒数
 * @param ms - 延迟时间（毫秒）
 */
export const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 安全解析 JSON，失败时返回 fallback 而非抛异常
 */
export const safeJsonParse = <T>(raw: string, fallback: T): T => {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
};
```

---

## 九、多 IDE 兼容说明

本文件设计为跨 IDE 通用规则。各 IDE 的加载方式：

| IDE / 工具 | 规则文件 | 建议 |
|------------|---------|------|
| Cursor | `.cursorrules` 或 `.cursor/rules/` | 可软链接本文件 |
| Trae | `agent.md` 或 `.trae/rules/` | 直接使用本文件 |
| GitHub Copilot | `.github/copilot-instructions.md` | 可软链接本文件 |
| Claude Code | `CLAUDE.md` | 可软链接本文件 |
| Codex CLI | `AGENTS.md` | 可软链接本文件 |
| Gemini CLI | `GEMINI.md` | 可软链接本文件 |

建议维护一个源文件，通过符号链接同步到各 IDE 的规则路径：

```powershell
# Windows 示例（PowerShell 管理员模式）
New-Item -ItemType SymbolicLink -Path ".cursorrules" -Target "agent.md"
New-Item -ItemType SymbolicLink -Path "CLAUDE.md" -Target "agent.md"
New-Item -ItemType SymbolicLink -Path "AGENTS.md" -Target "agent.md"
```

---

## 附录 A：Skill 系统（Trae / Codex 专用）

> 以下内容仅适用于支持 Skill 系统的 IDE（如 Trae），其他 IDE 可忽略此节。

### 核心理念

Skills 是可调用的能力单元，可随时、重复、串行、组合调用。

### 发现路径

```
.ai/skills/         ← 项目级（优先）
~/.trae-cn/skills/  ← 全局级
~/.codex/skills/    ← 全局级
```

### 调用原则

1. 未验证输入和预期输出前，禁止调用 Skill
2. 每个工作阶段（理解 → 设计 → 编码 → 测试 → 调试 → 审查）都应评估是否需要调用 Skill
3. 不确定用哪个 Skill 时调用 `skill-selector`

### 常见场景映射

| 场景 | 推荐 Skill 链 |
|------|--------------|
| 首次接触项目 | `codemap` → `code-summarizer` → `plan-first` |
| 多文件重构 | `plan-first` → `refactor-safe` → `regression-guard` |
| 新增 API | `api-design` → 实现 → `test-first` → `api-doc-gen` |
| 生产 Bug | `bug-localizer` → `crash-debug` → `regression-guard` |
| 清理死代码 | `dead-code-clean` + `dependency-mapper` |