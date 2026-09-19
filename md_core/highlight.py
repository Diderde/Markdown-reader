# SPDX-License-Identifier: GPL-2.0-or-later
"""轻量语法高亮 tokenizer：移植自 JS 版，粘性正则 → Python 的 match(src, pos)。"""

from __future__ import annotations

import re

TOKEN_RULES: dict[str, list[tuple[str, re.Pattern]]] = {
    "js": [
        ("com", re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")),
        ("str", re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`")),
        ("num", re.compile(r"\b\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?\b")),
        ("kw", re.compile(
            r"\b(?:const|let|var|function|return|if|else|for|while|do|class|new|import|export|from|async|await"
            r"|try|catch|finally|throw|typeof|instanceof|in|of|null|undefined|true|false|this|extends|static"
            r"|get|set|default|switch|case|break|continue|void|delete|yield|super|interface|type|enum"
            r"|implements|private|protected|public|readonly|abstract)\b")),
    ],
    "json": [
        ("str", re.compile(r"\"(?:[^\"\\]|\\.)*\"")),
        ("num", re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?")),
        ("kw", re.compile(r"\b(?:true|false|null)\b")),
    ],
    "css": [
        ("com", re.compile(r"/\*[\s\S]*?\*/")),
        ("str", re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")),
        ("num", re.compile(r"-?\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|vmin|vmax|s|ms|fr|deg)?")),
        ("prop", re.compile(r"[a-zA-Z-]+(?=\s*:)")),
        ("kw", re.compile(
            r"#[0-9a-fA-F]{3,8}\b|\b(?:solid|dashed|none|block|flex|grid|absolute|relative|fixed|bold"
            r"|italic|center|left|right|top|bottom|auto|inherit|important)\b")),
    ],
    "html": [
        ("com", re.compile(r"<!--[\s\S]*?-->")),
        ("str", re.compile(r"\"[^\"]*\"|'[^']*'")),
        ("tag", re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^<>]*?)?/?>")),
    ],
    "bash": [
        ("com", re.compile(r"#[^\n]*")),
        ("str", re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")),
        ("num", re.compile(r"\b\d+\b")),
        ("kw", re.compile(
            r"\b(?:if|then|else|elif|fi|for|while|do|done|case|esac|function|export|local|echo|cd|rm|cp|mv"
            r"|mkdir|touch|sudo|apt|apt-get|npm|yarn|pnpm|git|curl|wget|chmod|chown|grep|sed|awk|cat|ls|pwd"
            r"|source|exit|return)\b")),
    ],
    "python": [
        ("com", re.compile(r"#[^\n]*")),
        ("str", re.compile(
            r"(?:r|u|f|rf|fr)?(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'[^'\n]*'|\"[^\"\n]*\")")),
        ("num", re.compile(r"\b\d[\d_]*(?:\.\d+)?\b")),
        ("kw", re.compile(
            r"\b(?:def|class|return|if|elif|else|for|while|import|from|as|with|try|except|finally|raise"
            r"|lambda|pass|yield|None|True|False|and|or|not|in|is|async|await|global|nonlocal|del|assert"
            r"|break|continue|self)\b")),
    ],
}

LANG_ALIAS = {
    "js": "js", "javascript": "js", "ts": "js", "typescript": "js",
    "json": "json", "html": "html", "xml": "html", "svg": "html",
    "css": "css", "bash": "bash", "sh": "bash", "shell": "bash", "zsh": "bash",
    "python": "python", "py": "python",
    "text": "", "plain": "", "txt": "",
}


def resolve_lang(lang: str) -> str:
    """语言别名 → 规则键；未知语言返回空串（不高亮）。"""
    return LANG_ALIAS.get((lang or "").strip().lower(), "")


def tokenize_code(code: str, lang: str) -> list[tuple[str, str]]:
    """逐 token 切分，返回 [(cls, text)]；未匹配字符按普通文本输出。"""
    rules = TOKEN_RULES.get(lang)
    if not rules:
        return [("", code)]
    out: list[tuple[str, str]] = []
    i = 0
    n = len(code)
    while i < n:
        for cls, pattern in rules:
            m = pattern.match(code, i)
            if m:
                out.append((cls, m.group(0)))
                i = m.end()
                break
        else:
            out.append(("", code[i]))
            i += 1
    return out
