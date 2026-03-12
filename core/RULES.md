# RULES.md

## 编码读取规则

- PowerShell 读取文本文件时，优先使用 `Get-Content -Encoding utf8`。
- 需要在终端展示中文内容前，先设置 UTF-8 输出环境，例如：
  - `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
  - `$OutputEncoding = [System.Text.Encoding]::UTF8`
- 如果文件内容仍显示乱码，必须切换读取方式后再继续，例如使用 Python UTF-8 读取验证。
- 禁止基于乱码输出推断源码、配置或文档本身有问题。

## 审计规则

- 审计中文项目时，先确认读取编码，再做结构、逻辑、依赖和风险判断。
- 引用中文文件内容前，先确认原文已被正确解码。
