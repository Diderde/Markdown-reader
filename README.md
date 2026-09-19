# Markdown Reader

简体中文 | [English](README_EN.md)

[![CI](https://github.com/Diderde/Markdown-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/Diderde/Markdown-reader/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Mobile%20Web-lightgrey)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![License](https://img.shields.io/badge/license-GPL--2.0--or--later-informational)

双栏编辑、实时渲染的 Markdown 阅读器，**桌面端与移动端自适应**。本项目仅在 Windows 11 与桌面端测试过。

## 运行

```powershell
cd markdown-reader
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python main.py        # 桌面窗口
```

**一键启动（推荐）**：双击 `run.bat`——自动检测环境；依赖缺失时会在命令行询问，同意后自动创建 `.venv` 并安装（get-pip.py 仅从 PyPA 官方地址下载，且经主机白名单 + 受限地址校验）。`--yes` 可跳过询问，`--narrow` 强制移动端布局。

- **桌面**：直接 `python main.py`（或 `flet run`）；
- **Web**：`flet run --web`，浏览器访问（手机浏览器即移动端布局）；
- **移动端**：`flet run --android` / `--ios`（需 Flet CLI），或打包后安装。

## 功能

- 宽屏（≥900px）双栏「源码 | 预览」；窄屏自动切为「源码 / 预览」标签页
- 输入自适应防抖（120ms ~ 2s），解析与控件构建在后台线程执行
- 手写 CommonMark 简化解析器：标题（ATX/Setext）、段落、围栏与缩进代码块、引用、
  列表（含任务列表）、GFM 表格（对齐 + `\|` 转义）、分隔线、链接引用定义
- 行内语法：**加粗**、*斜体*、~~删除线~~、==高亮==（内置扩展）、行内代码、
  行内链接/图片/自动链接/邮箱、引用式与快捷链接、反斜杠转义、硬/软换行
- 六种语言轻量语法高亮：Python / JavaScript / JSON / HTML / CSS / Bash
- 打开 .md 文件（UTF-8 / GB18030 自动识别）、示例文档、清空、源码区显隐
- 状态栏：文件名、字符数、解析耗时、块/节点数、错误计数
- 防卡死：所有前向扫描有界、递归深度上限、行内解析迭代预算；渲染失败保留上次结果并显示错误横幅

## 项目结构

```
markdown-reader/
├── main.py              # Flet 应用外壳（布局/防抖/文件导入/状态栏）
├── md_core/
│   ├── inline.py        # 行内解析（flanking、三的倍数规则、扩展注册）
│   ├── blocks.py        # 块级词法（单遍行扫描、有界递归）
│   ├── highlight.py     # 轻量语法高亮 tokenizer
│   ├── extensions.py    # 行内扩展注册表（==高亮== 内置）
│   ├── render.py        # 节点树 → Flet 控件
│   ├── pipeline.py      # 清洗/预扫描/统计/编码识别
│   ├── nodes.py         # 文档节点定义
│   └── sample.py        # 示例文档与内置 PNG 占位图
└── tests/               # 解析核心单元测试（36 例，不依赖 Flet）
```


## 许可

本项目以 [GPL-2.0-or-later](LICENSE) 许可开源：修改后再分发的版本须同样以 GPL-2.0-or-later 开源并保留版权声明。
