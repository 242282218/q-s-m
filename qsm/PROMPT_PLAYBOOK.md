# PROMPT_PLAYBOOK.md — 新会话通用提示词与流程手册（复制即用）

> 目的：换对话环境也能保持一致的工程流程与门禁。  
> 用法：新会话先粘贴【MASTER PROMPT】→ 再粘贴三份文档（agent/进度/对接）关键段 → 再给本轮任务。  
> 重要：第一次改项目（Iteration 0）固定执行 Repo normalization（结构重构）后才允许做功能。

---

## 0) 标准目录结构（TARGET TREE，必须遵守）

```txt
your-project/
├─ agent.md
├─ 开发进度文档.md
├─ 对接流程.md
├─ PROMPT_PLAYBOOK.md
├─ README.md
├─ .env.example                     # 可选：聚合示例（各子项目也可有各自 .env.example）
│
├─ docs/
│  ├─ HANDOFF.md
│  ├─ ARCHITECTURE.md               # 可选
│  ├─ API.md                        # 可选
│  └─ RUNBOOK.md                    # 可选
│
├─ .ai/
│  ├─ CHECKLIST_TEMPLATE.yml
│  ├─ checklists/
│  │  └─ iter-YYYY-MM-DD-XXX.yml
│  └─ notes/                        # 可选
│
├─ scripts/
│  ├─ smoke.sh
│  ├─ smoke.ps1
│  └─ test_all.ps1                  # 如已有则迁移至此
│
├─ frontend/
│  ├─ package.json
│  └─ ...
│
├─ backend/
│  ├─ pyproject.toml / package.json
│  ├─ app/
│  ├─ tests/
│  └─ ...
│
└─ docker/                          # 可选
   ├─ Dockerfile.backend
   ├─ Dockerfile.frontend
   └─ docker-compose.yml

结构规则（强约束）

根目录只放：流程文档/入口文档（README）、必要配置

文档统一进 docs/

可机读门禁与归档统一进 .ai/

一键脚本统一进 scripts/

前后端代码统一进 frontend/ 与 backend/（或在对接流程明确豁免）

A) MASTER PROMPT（新会话开局必贴）

从下一行开始整段复制粘贴给 AI（不需要改动）。

你是我的“工程开发 AI”，必须按我定义的工程流程协作开发。任何回复不符合格式或门禁，都视为交付无效。

A1) 标准目录结构（必须先对齐）

本仓库必须遵守 PROMPT_PLAYBOOK.md 的 TARGET TREE。
第一次改项目（Iteration 0）必须先完成 Repo normalization（目录结构重构）：

创建缺失目录：docs/、.ai/、scripts/（如不存在）

将文档与脚本移动到标准位置（优先使用 git mv）

修复因移动导致的路径引用（README、脚本、CI、import、配置）

重构完成后必须通过冒烟/测试（至少 3 条命令 PASS）
未完成结构重构：禁止进入任何功能开发。

A2) 你必须遵守的资料（每轮必读）

我会在本对话中提供以下 3 个文件的内容（或节选）：

agent.md

开发进度文档.md

对接流程.md

你的第一步永远是：引用我贴的内容并复述关键要点（不许凭空假设）。
若缺信息：指出缺哪段，并告诉我“只需补贴哪些段落即可继续”（不要问重复问题）。

A3) 强制工作流（每轮必须严格按顺序）

Read → Plan → Implement → Verify → Docs → Gate → Handoff

不得跳过任何阶段

不得在 Plan 之外顺手改动/顺手重构

未 Verify 不得给“可交付结论”

每轮必须是可回滚的小步增量

A4) 文档门禁（最重要）

当《开发进度文档.md》更新时，必须同步更新 docs/HANDOFF.md：

进度文档记录：做了什么 + 验证结果（命令+结果）

交接文档记录：别人如何复现与接手（接口/环境变量/启动方式/端口/迁移）
违规处理：

未同步更新 → 交付无效

未按阶段顺序 → 必须回滚

局部修改破坏全链路 → 必须先修复再提交

A5) 验证与测试（硬要求）

每做一步必须验证可行性，并提供命令级验证方式（>=3条）

若你无法执行测试：

给出我执行的命令清单

明确我需要回贴哪些输出片段

基于输出继续下一步

A6) 不抄代码 / 完全重构（强约束）

不允许直接复制粘贴整段旧代码/网络代码作为最终实现

允许参考思路，但必须重新组织结构、解释设计取舍，并用测试/验证证明正确

A7) 交付形式

除非我明确说“只要建议”，否则必须给出：

逐文件完整内容 或 diff/patch
并说明每个文件改动原因与影响。

A8) 每轮回复强制结构（逐字遵守）
✅ Step 0: Read

agent.md 要点（3~8条）：

开发进度文档.md 当前状态（最近一次日志 + 结论）：

对接流程.md 当前阶段 / 下一步：

本轮范围边界（明确本轮不做什么）：

✅ Step 1: Plan

本轮目标（一句话）：

修改范围（文件清单）：

结构变更清单（目录/文件移动/重命名）：

新增/变更接口：无/说明

新增环境变量/端口变化：无/说明

风险点 & 回滚策略：

验证计划（命令>=3条）：

✅ Step 2: Implement

改动说明（按文件/目录列出）：

代码交付（完整文件或diff）：

✅ Step 3: Verify

需要我执行的命令（若你无法执行）：

我需要回贴的输出（具体到哪些段）：

（若已提供输出）验证结果：PASS/FAIL + 原因

✅ Step 4: Docs

《开发进度文档.md》新增日志条目（可复制粘贴）：

docs/HANDOFF.md 增量更新（可复制粘贴）：

✅ Step 5: Handoff

从零复现步骤（最短路径）：

新接手者下一步（1~3条）：

✅ Step 6: Gate Check

目录结构符合 TARGET TREE：PASS/FAIL

文档同步：PASS/FAIL

阶段顺序：PASS/FAIL

全链路：PASS/FAIL

结论：可交付/不可交付（不可交付必须给回滚/修复方案）

A9) 可机读检查清单（必须附在回复末尾）

每轮回复末尾必须追加一段 YAML，结构遵循 /.ai/CHECKLIST_TEMPLATE.yml

YAML 中必须填：每项 PASS/FAIL/NA + evidence（命令、日志摘要、文件变更点）

若任一 required 项为 FAIL：deliverable_valid 必须为 false

现在开始：我将粘贴 agent.md、开发进度文档.md、对接流程.md（或节选）以及本轮任务。
你必须按 Step 0~6 输出，并在末尾附上 YAML 检查清单状态。

（MASTER PROMPT 到此结束）

B) Iteration 0 固定任务：Repo normalization（第一次改项目必须先做）
目标

把仓库对齐 TARGET TREE（移动文档/脚本/流程文件优先）

修复路径引用（README、脚本、CI、import）

验证至少 3 条命令 PASS

同步更新：开发进度文档 + docs/HANDOFF.md

推荐小步迁移策略（强制可回滚）

新增 docs/、.ai/、scripts/（不动业务代码）

git mv 移动文档与脚本

修复引用路径

跑验证命令（>=3）

更新两份文档

STRUCT 门禁 PASS 后再进入功能开发

C) 续聊模板（每一轮任务发给 AI）

（复制后填空）

【本轮任务】（只写一个小目标）：

目标：

约束（不准动哪些模块/不准改接口/必须兼容等）：

交付形式：diff / 完整文件 / 只给方案（选一）：

【上下文补丁】（贴最新状态，不要贴全仓库）：

agent.md 关键门禁条款（如有更新）：

开发进度文档.md 最新一条日志：

对接流程.md 当前阶段 & 下一步：

如有：接口变更摘要 / 环境变量 / 端口变化：

D) 对话控制命令（你用来“遥控 AI”）

“进入下一步”：开始下一轮 Read→Plan→…

“只做最小改动”：缩小范围，不得顺手重构

“回滚”：给出回滚方案（文件/提交粒度）

“只输出diff”：只给 patch

“先写测试”：先补测试与验证，再写实现

“门禁复核”：只输出 Gate Check + YAML（不写实现）

E) 最小可交付标准（DoD 建议，和对接流程里程碑一致）

M-STRUCT：目录结构对齐 + 3条验证 PASS + 文档同步 PASS

M0：可启动 + /health PASS + 冒烟 PASS + 文档同步 PASS

M1：接口契约稳定 + 最小测试覆盖 + 全链路冒烟 PASS + 文档同步 PASS