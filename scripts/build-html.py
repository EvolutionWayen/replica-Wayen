#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把整套体系合成一份自包含的 HTML 手册。

特性
  - 不引用任何外部资源（无 CDN、无外链字体、无外部图片）
  - 左侧固定目录（章节 + 二级标题，点击跳转）
  - 苹果风排版：中性灰阶 + 单一蓝色强调、充足留白、细边框
  - 代码块、表格、任务列表、引用块都有样式
  - 缺文件不报错，跳过并在页内标注

用法
  python3 scripts/build-html.py                     # 输出到体系根/体系总览.html
  python3 scripts/build-html.py --out /tmp/x.html
  python3 scripts/build-html.py --only 00,stages     # 只渲染匹配的章节
  python3 scripts/build-html.py --list               # 只列章节，不渲染
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:  # pragma: no cover
    sys.exit("需要 markdown 库：pip3 install markdown")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "体系总览.html"

# (相对路径 or 目录, 导航标题, 所属分区)
# 目录以 / 结尾表示展开其中所有 .md（按文件名排序）
CHAPTERS = [
    ("README.md", "上手：这是什么、怎么用", "入口"),
    ("00-体系总纲.md", "体系总纲（12 阶段 / 12 门 / 红线）", "入口"),
    ("产品官审查手册.md", "产品官审查手册（你怎么开会）", "入口"),
    ("中途接入.md", "中途接入：已有产品怎么收敛", "入口"),

    ("stages/", "阶段卡", "阶段"),
    ("templates/blueprint/SCHEMAS.md", "数据契约（机器格式定义）", "产出格式"),
    ("templates/blueprint/", "蓝图模板（S1–S3）", "产出格式"),
    ("templates/engineering/", "工程模板（S0–S11）", "产出格式"),

    ("gates/README.md", "门禁引擎说明", "门禁与工具"),
    ("tools/README.md", "工具说明", "门禁与工具"),
    ("scripts/README.md", "脚本说明", "门禁与工具"),

    ("skills/replica-os/SKILL.md", "技能 · 主编排", "技能"),
    ("skills/replica-blueprint/SKILL.md", "技能 · 行为蓝图", "技能"),
    ("skills/replica-local-source/SKILL.md", "技能 · 本地源码分析", "技能"),

    ("case-todo/README.md", "实证案例（案例层，非规范）", "案例与溯源"),
]

SKIP_DIR_FILES = {"SCHEMAS.md"}  # 已在上面单独列出，目录展开时跳过


def md_to_html(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "toc", "nl2br"],
        output_format="html5",
    )


def slugify(text: str, seen: dict) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-").lower() or "sec"
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def collect(chapters_filter: list[str] | None):
    """展开章节清单 -> [(rel_path, nav_title, group)]"""
    out = []
    for rel, title, group in CHAPTERS:
        if rel.endswith("/"):
            d = ROOT / rel
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.md")):
                if f.name in SKIP_DIR_FILES:
                    continue
                stem = f.stem
                # 去掉 .template 后缀，让标题更干净
                label = stem.replace(".template", "")
                out.append((str(f.relative_to(ROOT)), f"{label}", group))
        else:
            if (ROOT / rel).is_file():
                out.append((rel, title, group))
    if chapters_filter:
        keep = []
        for item in out:
            if any(k in item[0] for k in chapters_filter):
                keep.append(item)
        out = keep
    return out


def build(chapters, out_path: Path) -> tuple[int, int]:
    seen_slugs: dict[str, int] = {}
    sections = []   # (anchor, nav_html, body_html, group)
    total_words = 0
    last_group = {"value": None}

    for rel, title, group in chapters:
        path = ROOT / rel
        raw = path.read_text(encoding="utf-8")
        raw = strip_frontmatter(raw)
        body = md_to_html(raw)

        # 给 h2/h3 加锚点，并收集侧栏二级目录
        subs = []

        def _anchor(m):
            tag, attrs, inner = m.group(1), m.group(2), m.group(3)
            plain = re.sub(r"<[^>]+>", "", inner)
            sid = slugify(f"{rel}-{plain}", seen_slugs)
            if tag == "h2":
                subs.append((sid, plain))
            return f'<{tag} id="{sid}"{attrs}>{inner}</{tag}>'

        body = re.sub(r"<(h2|h3)([^>]*)>(.*?)</\1>", _anchor, body, flags=re.S)

        sec_anchor = slugify(rel, seen_slugs)
        nav_subs = "".join(
            f'<a class="nav-sub" href="#{sid}">{html.escape(t)}</a>' for sid, t in subs
        )
        # 只在分组变化时输出分组标题，避免同一分组重复出现
        nonlocal_last = last_group["value"]
        group_html = ""
        if group != nonlocal_last:
            group_html = f'<div class="nav-group">{html.escape(group)}</div>'
            last_group["value"] = group
        nav = (
            group_html
            + f'<a class="nav-item" href="#{sec_anchor}">{html.escape(title)}</a>'
            + (f'<div class="nav-subs">{nav_subs}</div>' if nav_subs else "")
        )
        sections.append((sec_anchor, nav, body, group, rel))
        total_words += len(raw)

    toc_html = "\n".join(s[1] for s in sections)
    body_html = "\n".join(
        f'<section id="{a}"><div class="file-tag">{html.escape(rel)}</div>{b}</section>'
        for a, _, b, _, rel in sections
    )

    doc = TEMPLATE.format(
        toc=toc_html,
        body=body_html,
        css=CSS,
        js=JS,
        n_chapters=len(sections),
        n_words=total_words,
    )
    out_path.write_text(doc, encoding="utf-8")
    return len(sections), total_words


CSS = """
:root{
  --ink:#1d1d1f; --ink-2:#3a3a3c; --ink-3:#6e6e73; --ink-4:#86868b;
  --line:#e6e6ea; --line-2:#f0f0f2;
  --bg:#ffffff; --bg-2:#fafafc; --bg-3:#f5f5f7;
  --blue:#0071e3; --blue-soft:#eaf3fd;
  --ok:#1a7f37; --warn:#9a6700; --bad:#b42318;
  --radius:10px;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",
         "Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); font-size:15.5px; line-height:1.75;
  letter-spacing:.005em; -webkit-font-smoothing:antialiased;
}
.layout{display:flex; align-items:flex-start}

/* ---------- 侧栏 ---------- */
.side{
  width:288px; flex:0 0 288px; position:sticky; top:0; height:100vh;
  overflow-y:auto; background:var(--bg-2); border-right:1px solid var(--line);
  padding:28px 18px 80px; font-size:13.5px;
}
.side h1{
  font-size:15px; font-weight:600; letter-spacing:.01em; margin:0 0 4px 6px;
}
.side .meta{color:var(--ink-4); font-size:12px; margin:0 0 22px 6px; line-height:1.6}
.nav-group{
  color:var(--ink-4); font-size:11px; font-weight:600; letter-spacing:.08em;
  text-transform:uppercase; margin:20px 6px 6px;
}
.nav-item{
  display:block; padding:5px 8px; border-radius:6px; color:var(--ink-2);
  text-decoration:none; line-height:1.5;
}
.nav-item:hover{background:var(--bg-3); color:var(--ink)}
.nav-subs{margin:2px 0 2px 8px; border-left:1px solid var(--line); padding-left:6px}
.nav-sub{
  display:block; padding:3px 8px; border-radius:5px; color:var(--ink-4);
  text-decoration:none; font-size:12.5px; line-height:1.45;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.nav-sub:hover{background:var(--bg-3); color:var(--ink-2)}

/* ---------- 正文 ---------- */
.main{flex:1 1 auto; min-width:0; padding:56px 56px 140px; max-width:980px; margin:0 auto}
section{padding-bottom:44px; border-bottom:1px solid var(--line-2); margin-bottom:44px}
section:last-child{border-bottom:0}
.file-tag{
  font-family:var(--mono); font-size:11.5px; color:var(--ink-4);
  margin-bottom:10px; letter-spacing:.02em;
}
h1{font-size:29px; line-height:1.3; font-weight:650; letter-spacing:-.015em; margin:.2em 0 .7em}
h2{
  font-size:20px; font-weight:600; letter-spacing:-.008em;
  margin:2.1em 0 .7em; padding-top:.2em; scroll-margin-top:24px;
}
h3{font-size:16.5px; font-weight:600; margin:1.7em 0 .5em; scroll-margin-top:24px}
h4{font-size:15px; font-weight:600; margin:1.4em 0 .4em; color:var(--ink-2)}
p{margin:.75em 0}
ul,ol{margin:.75em 0; padding-left:1.5em}
li{margin:.32em 0}
li>ul,li>ol{margin:.2em 0}
a{color:var(--blue); text-decoration:none}
a:hover{text-decoration:underline}
strong{font-weight:600}
hr{border:0; border-top:1px solid var(--line); margin:2.4em 0}

blockquote{
  margin:1.1em 0; padding:.7em 1.1em; border-left:3px solid var(--blue);
  background:var(--blue-soft); border-radius:0 var(--radius) var(--radius) 0;
  color:var(--ink-2);
}
blockquote p:first-child{margin-top:0}
blockquote p:last-child{margin-bottom:0}

code{
  font-family:var(--mono); font-size:.88em; background:var(--bg-3);
  padding:.14em .38em; border-radius:4px; color:#b0234a;
}
pre{
  background:var(--bg-3); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 16px; overflow-x:auto; line-height:1.6; margin:1.1em 0;
  font-size:13px;
}
pre code{background:none; padding:0; color:var(--ink); font-size:13px}

table{
  border-collapse:collapse; width:100%; margin:1.1em 0; font-size:14px;
  display:block; overflow-x:auto; white-space:nowrap;
}
th,td{border:1px solid var(--line); padding:8px 11px; text-align:left; vertical-align:top}
th{background:var(--bg-2); font-weight:600; color:var(--ink-2); white-space:nowrap}
tr:nth-child(even) td{background:#fcfcfd}

.task-list-item{list-style:none; margin-left:-1.2em}
.task-list-item input{margin-right:.5em; vertical-align:-2px}

/* ---------- 顶部进度条 ---------- */
#progress{
  position:fixed; top:0; left:0; height:2px; background:var(--blue);
  width:0; z-index:50; transition:width .1s linear;
}
/* ---------- 回到顶部 ---------- */
#totop{
  position:fixed; right:26px; bottom:26px; width:38px; height:38px;
  border-radius:50%; border:1px solid var(--line); background:#fff;
  color:var(--ink-3); cursor:pointer; font-size:15px; line-height:1;
  box-shadow:0 2px 10px rgba(0,0,0,.06); opacity:0; pointer-events:none;
  transition:opacity .2s;
}
#totop.show{opacity:1; pointer-events:auto}

@media (max-width:980px){
  .side{display:none}
  .main{padding:28px 20px 100px}
  h1{font-size:24px}
  h2{font-size:18px}
}
@media print{
  .side,#totop,#progress{display:none}
  .main{padding:0; max-width:none}
  section{border-bottom:0; page-break-inside:avoid}
  pre,table{page-break-inside:avoid}
  a{color:var(--ink)}
}
"""

JS = """
(function(){
  var p=document.getElementById('progress');
  var t=document.getElementById('totop');
  function onScroll(){
    var h=document.documentElement;
    var max=h.scrollHeight-h.clientHeight;
    var y=h.scrollTop||document.body.scrollTop;
    p.style.width = max>0 ? (y/max*100)+'%' : '0%';
    t.classList.toggle('show', y>600);
  }
  document.addEventListener('scroll',onScroll,{passive:true});
  t.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'})});
  onScroll();
})();
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>复制重建体系 · 总览</title>
<style>{css}</style>
</head>
<body>
<div id="progress"></div>
<div class="layout">
<nav class="side">
  <h1>复制重建体系</h1>
  <div class="meta">{n_chapters} 篇 · 约 {n_words} 字<br>Replica OS v2.0</div>
  {toc}
</nav>
<main class="main">
{body}
</main>
</div>
<button id="totop" title="回到顶部">↑</button>
<script>{js}</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="把整套体系合成一份自包含 HTML 手册")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", default="", help="逗号分隔的路径关键词，只渲染匹配章节")
    ap.add_argument("--list", action="store_true", help="只列出章节")
    args = ap.parse_args()

    flt = [s.strip() for s in args.only.split(",") if s.strip()] or None
    chapters = collect(flt)
    if not chapters:
        sys.exit("没有找到任何可渲染的章节（--only 过滤过严，或文件未就绪）")

    if args.list:
        for rel, title, group in chapters:
            print(f"{group:8s} {rel:60s} {title}")
        print(f"\n共 {len(chapters)} 篇")
        return

    out = Path(args.out)
    n, words = build(chapters, out)
    size = out.stat().st_size
    print(f"已生成：{out}")
    print(f"  章节 {n} 篇 · 约 {words} 字 · {size/1024:.0f} KB")
    print(f"  外部依赖：0（无 CDN / 无外链字体 / 无外部图片）")


if __name__ == "__main__":
    main()
