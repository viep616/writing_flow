r"""Markdown 论文 → PDF 转换器（pandoc + xelatex 胶水层）。

职责：
1. insert_figures：把 make_charts 生成的插图以固定位置插入论文终稿
   （锚点=「结果与讨论」节标题后的第一个表格之后；无表格则紧跟标题），
   图与图注均由程序确定性生成，不经过 LLM，杜绝幻觉插图；
2. preprocess：Unicode 上下标字符转 LaTeX 数学模式（SOF₂→SOF$_{2}$、
   10⁻³→10$^{-3}$），规避 SimHei/Latin Modern 缺字形问题；
3. md_to_pdf：调用 pandoc + xelatex 编译 PDF（中文 xeCJK + SimHei）。

外部依赖（均装在 D 盘）：
    D:\pandoc\pandoc-3.6.4\pandoc.exe
    D:\MiKTeX\miktex\bin\x64\xelatex.exe

用法（项目根目录）：
    python tools/md2pdf.py 论文.md [输出.pdf]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PANDOC = Path(r"D:\pandoc\pandoc-3.6.4\pandoc.exe")
XELATEX = Path(r"D:\MiKTeX\miktex\bin\x64\xelatex.exe")

# 由 run.py 注入的真实用户目录（APPDATA/LOCALAPPDATA/USERPROFILE）。
# run.py 为 crewai 把这些变量重定向到项目 .appdata/ 后，MiKTeX 会找不到
# 用户级配置/格式缓存而回退写 C:\ProgramData（沙箱禁止）；调 pandoc 的
# 子进程须恢复真实值。独立运行本脚本时为空 dict，行为不变。
REAL_USER_ENV: dict[str, str] = {}

SUB_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUP_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
ANCHOR_RE = re.compile(r"^#{1,6}\s*\d*[.、]?\s*(结果.{0,2}讨论|位点选择性|吸附行为).*$", re.M)


def preprocess(text: str) -> str:
    """PDF 预处理三连（确定性，零 LLM）：
    ① 修订说明块清洗：写手常把「<!-- 修订说明 -->」放开头且注释未包住 wN 列表 →
       整块剪下移至文末并转为完整 HTML 注释（PDF 不渲染，md 留档不受影响）；
    ② LaTeX 公式定界规范化：\\(x\\) → $x$、\\[x\\] → $$x$$（pandoc 只认美元定界）；
    ③ Unicode 上下标序列 → LaTeX 数学模式（连续序列合并成一个组）。"""
    text = _strip_revision_notes(text)
    text = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1) + "$", text, flags=re.S)
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: "$$" + m.group(1) + "$$", text, flags=re.S)
    text = re.sub(r"[₀₁₂₃₄₅₆₇₈₉]+",
                  lambda m: "$_{" + m.group().translate(SUB_MAP) + "}$", text)
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+",
                  lambda m: "$^{" + m.group().translate(SUP_MAP) + "}$", text)
    return text


def _strip_revision_notes(text: str) -> str:
    """头部修订说明块（注释行 + wN 明文列表，止于首个 ---/标题行）→ 移文末完整注释。"""
    lines = text.splitlines()
    if not lines or "修订说明" not in lines[0]:
        return text
    end = 1
    while end < len(lines):
        s = lines[end].strip()
        if s.startswith("#") or s == "---":
            break
        end += 1
    if end < len(lines) and lines[end].strip() == "---":  # 跳过紧邻的分隔线
        end += 1
    block = "\n".join(lines[:end]).strip()
    rest = "\n".join(lines[end:]).lstrip()
    # 承载容器用 fenced div + CSS display:none：pandoc 对含列表的多行 HTML 注释
    # 会拆进正文渲染（实测 w1 列表出现在 PDF 第 14 页），fenced div 不受影响
    return (
        rest.rstrip("\n")
        + "\n\n::: {.revision-notes}\n" + block + "\n:::\n"
    )


_FIG_MARKER_RE = re.compile(r"<!--\s*FIG:\s*([A-Za-z0-9_\-]+)\s*-->")
_FIG_REF_RE = re.compile(r"图\s*(\d+)\s*[:：]")


def insert_figures(md_path: Path, figures: list[tuple[str, str]]) -> bool:
    """把图表插入论文 md——优先按正文锚点（图文结合），无锚点回退到节首/文末。

    锚点约定：正文中讨论某图的段落后写 `<!-- FIG:<文件名不含扩展名> -->`，
    此处替换为 `![](figures/<文件>)` + 斜体图注（图注由 qe_charts 程序生成，不经过 LLM）。
    幂等：文中已含 figures/ 引用则跳过。
    """
    if not figures or not md_path.is_file():
        return False
    text = md_path.read_text(encoding="utf-8")
    if "figures/" in text or "figures\\" in text:
        print("[插图] 论文已包含图表引用，跳过")
        return False
    by_stem = {Path(fn).stem: (fn, cap) for fn, cap in figures}
    placed: set[str] = set()

    def _replace(m: re.Match) -> str:
        stem = m.group(1)
        if stem not in by_stem:
            return m.group(0)  # 无对应图：保留原标记（fail-safe，不吞掉正文）
        fn, cap = by_stem[stem]
        placed.add(stem)
        return f"\n\n![](figures/{fn})\n\n*{cap}*\n"

    text = _FIG_MARKER_RE.sub(_replace, text)
    if placed:
        print(f"[插图] 已按正文锚点插入 {len(placed)}/{len(figures)} 张图（图文结合）")

    pending = [(fn, cap) for stem, (fn, cap) in by_stem.items() if stem not in placed]
    if pending:
        # 第二层：按正文"图 N"引用就近锚定（先引后述）——跳过 HTML 注释内的误匹配
        lines = text.splitlines(keepends=True)
        in_comment = False
        ref_pos: dict[int, int] = {}  # 图号 → 行索引（首次正文引用）
        for i, line in enumerate(lines):
            starts = "<!--" in line
            ends = "-->" in line
            if starts:
                in_comment = True
            if not in_comment:
                m = _FIG_REF_RE.search(line)
                if m:
                    ref_pos.setdefault(int(m.group(1)), i)
            if ends:
                in_comment = False
        anchored: list[tuple[int, tuple[str, str]]] = []
        for n, (fn, cap) in enumerate(pending, start=1):
            # 图号 = 传入顺序（qe_charts 固定 图1..图4）；若正文有显式编号也可用
            pos = ref_pos.get(n)
            if pos is not None:
                anchored.append((pos, (fn, cap)))
        if anchored:
            for pos, (fn, cap) in sorted(anchored, reverse=True):
                block = f"\n\n![](figures/{fn})\n\n*{cap}*\n"
                lines.insert(pos + 1, block)
            text = "".join(lines)
            print(f"[插图] 已按正文「图 N」引用就近插入 {len(anchored)}/{len(pending)} 张图（图文结合·引用锚定）")
            pending = [(fn, cap) for n, (fn, cap) in enumerate(pending, start=1)
                       if ref_pos.get(n) is None]
    if pending:
        block = "\n\n" + "\n\n".join(f"![](figures/{fn})\n\n*{cap}*" for fn, cap in pending) + "\n"
        text = text.rstrip("\n") + "\n" + block
        print(f"[插图] 无正文引用图 {len(pending)} 张已追加至文末")
    md_path.write_text(text, encoding="utf-8")
    return True


_PRINT_CSS = """
@page { size: A4; margin: 2.2cm 2cm; }
body { font-family: "SimSun", "Noto Sans CJK SC", "Microsoft YaHei", serif; font-size: 11pt; line-height: 1.65; color: #111; }
h1 { font-family: "SimHei", sans-serif; font-size: 17pt; text-align: center; margin: 0 0 1.2em; }
h2 { font-family: "SimHei", sans-serif; font-size: 13.5pt; border-left: 4px solid #1a5276; padding-left: .5em; margin-top: 1.4em; }
h3 { font-family: "SimHei", sans-serif; font-size: 12pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 1em 0; table-layout: fixed; word-break: break-all; }
th, td { border: 0.6pt solid #666; padding: 2.5pt 4pt; text-align: left; vertical-align: top; }
th { background: #eef3f7; font-family: "SimHei", sans-serif; }
code { font-family: Consolas, monospace; font-size: 9pt; background: #f4f4f4; padding: 0 2px; }
blockquote { border-left: 3px solid #999; margin-left: 0; padding-left: 1em; color: #444; }
img { max-width: 100%; }
.revision-notes { display: none; }
"""

BROWSER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def _find_browser() -> Path | None:
    return next((p for p in BROWSER_CANDIDATES if p.is_file()), None)


def _pdf_via_browser(tmp_md: Path, pdf_path: Path) -> bool:
    """pandoc → 自包含 HTML（MathML 公式 + 内嵌 CSS/图）→ Edge/Chrome 无头打印。
    优点：宽表 word-break 不重叠、公式离线渲染、不受 xelatex DLL 沙箱限制。
    坑（实测）：Edge 无头对中文长文件名的 file:/// URL 与 --print-to-pdf 路径
    组合渲染异常（产出残缺 PDF）——中间文件全程 ASCII 名（系统临时目录），成功后拷回。"""
    import shutil
    import tempfile

    browser = _find_browser()
    if browser is None:
        print("[PDF] 未找到 Edge/Chrome，浏览器打印后端不可用")
        return False
    with tempfile.TemporaryDirectory(prefix="md2pdf_") as td:
        tdir = Path(td)
        t_md = tdir / "paper.md"
        t_md.write_text(tmp_md.read_text(encoding="utf-8"), encoding="utf-8")
        # 相对路径资源（figures/ 配图）必须随迁，否则 Edge 加载失败只剩 12px 占位框（实测）
        src_figures = tmp_md.parent / "figures"
        if src_figures.is_dir():
            shutil.copytree(src_figures, tdir / "figures")
        t_css = tdir / "print.css"
        t_css.write_text(_PRINT_CSS, encoding="utf-8")
        t_html = tdir / "paper.html"
        r = subprocess.run(
            [str(PANDOC), t_md.name, "-s", "--mathml", "--embed-resources",
             "--css", t_css.name, "-o", t_html.name, "--metadata", "title=",
             "--resource-path", str(tmp_md.parent)],
            cwd=tdir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode != 0 or not t_html.is_file():
            print(f"[PDF] pandoc→HTML 失败（exit {r.returncode}）：{''.join(r.stderr.splitlines()[:5])}")
            return False
        t_pdf = tdir / "paper.pdf"
        pr = subprocess.run(
            [str(browser), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={t_pdf}", t_html.as_uri()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if not t_pdf.is_file() or t_pdf.stat().st_size < 1024:
            print(f"[PDF] 浏览器打印未产出，stderr：{''.join((pr.stderr or '').splitlines()[:5])}")
            return False
        shutil.copyfile(t_pdf, pdf_path)
    print(f"[PDF] 已生成 {pdf_path.name}（{pdf_path.stat().st_size // 1024} KB，浏览器打印后端）")
    return True


def md_to_pdf(md_path: Path, pdf_path: Path | None = None) -> bool:
    """论文 md → PDF。返回是否成功（失败不抛异常，由调用方决定留档策略）。
    引擎选择（WRITING_FLOW_PDF_ENGINE，默认 auto）：auto=先 xelatex，失败自动回退浏览器打印；
    xelatex / browser 强制指定。"""
    md_path = Path(md_path)
    if not md_path.is_file():
        print(f"[PDF] 输入不存在：{md_path}")
        return False
    engine = os.getenv("WRITING_FLOW_PDF_ENGINE", "auto").lower()
    pdf_path = Path(pdf_path) if pdf_path else md_path.with_suffix(".pdf")
    browser_ok = engine in ("auto", "browser")
    if engine == "browser" or not (PANDOC.is_file() and XELATEX.is_file()):
        if not browser_ok:
            print(f"[PDF] 缺少 pandoc 或 xelatex，跳过 PDF 转换\n      {PANDOC}\n      {XELATEX}")
            return False
    tmp_md = md_path.with_name(md_path.stem + ".tmp_pdf.md")
    tmp_md.write_text(preprocess(md_path.read_text(encoding="utf-8")), encoding="utf-8")
    try:
        if engine in ("auto", "xelatex") and PANDOC.is_file() and XELATEX.is_file():
            if _pdf_via_xelatex(tmp_md, pdf_path):
                return True
            if engine == "xelatex":
                return False
            print("[PDF] xelatex 后端失败，回退浏览器打印后端")
        if browser_ok and PANDOC.is_file():
            return _pdf_via_browser(tmp_md, pdf_path)
        return False
    finally:
        tmp_md.unlink(missing_ok=True)


def _pdf_via_xelatex(tmp_md: Path, pdf_path: Path) -> bool:
    cmd = [
        str(PANDOC), tmp_md.name, "-o", pdf_path.name,
        f"--pdf-engine={XELATEX}",
        "-V", "CJKmainfont=SimHei",
        "-V", "geometry:margin=2.5cm",
        "-V", "fontsize=11pt",
        "-V", r"header-includes=\usepackage{array}\setlength{\tabcolsep}{2.5pt}\renewcommand{\arraystretch}{1.08}",
        "--resource-path", ".",
    ]
    env = dict(os.environ)
    env.update(REAL_USER_ENV)  # 恢复真实用户目录，MiKTeX 依赖其定位配置
    try:
        r = subprocess.run(cmd, cwd=tmp_md.parent, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        print("[PDF] xelatex 编译超时（>600s）")
        return False
    if r.returncode != 0 or not pdf_path.is_file():
        print(f"[PDF] xelatex 转换失败（exit {r.returncode}），stderr 摘要：")
        print("\n".join(r.stderr.splitlines()[:10]))
        return False
    print(f"[PDF] 已生成 {pdf_path.name}（{pdf_path.stat().st_size // 1024} KB，xelatex 后端）")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    md = Path(sys.argv[1])
    pdf = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    return 0 if md_to_pdf(md, pdf) else 1


if __name__ == "__main__":
    sys.exit(main())
