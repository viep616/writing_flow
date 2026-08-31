"""archive · 时间戳留档与后缀合成（纯代码）

后缀合成顺序固定（人工按后缀即知质检结论）：
  _契约争议 → _评审未达标 → _致命一击未过 → _数值存疑 → _未通过门 → _交接不完整
留档不阻断：md 必出；PDF 仅在 WRITING_FLOW_PDF=1 时尝试（工具缺失自动跳过）。
"""

import os
import shutil
from pathlib import Path


def compose_suffix(snap: dict) -> str:
    parts = []
    if snap.get("contract_status") == "contested":
        parts.append("_契约争议")
    review = snap.get("review", {})
    if review and not review.get("passed", True):
        parts.append("_评审未达标")
    if snap.get("kill", {}).get("verdict") in {"FAIL", "WARN"}:
        parts.append("_致命一击未过")
    audit = snap.get("audit", {})
    if audit and (audit.get("findings", 0) > 0 or audit.get("parse_error")):
        parts.append("_数值存疑")
    if snap.get("overall") == "no":
        parts.append("_未通过门")
    if "交接不完整" in snap.get("human_flags", []):
        parts.append("_交接不完整")
    return "".join(parts)


def run(out_dir: Path, snap: dict, draft_path: Path, md2pdf_module=None) -> str:
    out_dir, draft_path = Path(out_dir), Path(draft_path)
    stamp = snap.get("stamp", "")
    suffix = compose_suffix(snap)

    fixed = out_dir / "论文_成稿.md"
    archived = out_dir / f"论文_成稿_{stamp}{suffix}.md"
    shutil.copyfile(draft_path, fixed)
    shutil.copyfile(draft_path, archived)

    if md2pdf_module is not None and os.getenv("WRITING_FLOW_PDF", "") == "1":
        try:
            md2pdf_module.md_to_pdf(str(fixed), str(fixed.with_suffix(".pdf")))
            shutil.copyfile(fixed.with_suffix(".pdf"), archived.with_suffix(".pdf"))
            print("[留档] PDF 已生成")
        except Exception as exc:  # PDF 工具链缺失不阻断
            print(f"[留档] PDF 跳过：{exc}")

    print(f"[留档] {archived.name}（后缀='{suffix or '全绿'}'）")
    return str(archived)
