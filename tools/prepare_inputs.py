"""prepare_inputs · 输入判道与素材标准化（纯代码，零 LLM）

判道优先级：data/upstream_handoff/（上游交接） > 独立素材（叙事/数据表） > data/ 下已有初稿。
产物形态分流：叙事/数据表 → standalone（全新成稿）；已成初稿 → refine（精修升级）。
输出 SOURCES_MANIFEST.json：每份素材的路径与 SHA256 指纹，是后续所有审计的基准输入。
"""

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import qe_extract  # main.py 已将 tools/ 挂入 sys.path
except ImportError:  # 包内相对导入兜底
    from . import qe_extract  # type: ignore[no-redef]

MANIFEST_NAME = "SOURCES_MANIFEST.json"


def _sha16(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _find_raw_calc_root(base: Path) -> Path | None:
    """定位原始计算归档根：base 本身或其一级子目录中含 adsorption_*/ 下 .pwo 的目录。
    匹配 QE 归档命名规范（见 qe_extract._SYS_RE）；未命中返回 None。"""
    if not base.is_dir():
        return None
    for cand in [base, *sorted(p for p in base.iterdir() if p.is_dir())]:
        if any(cand.glob("adsorption_*/**/*.pwo")):
            return cand
    return None


def _is_handoff_name(name: str) -> bool:
    return name.startswith("HANDOFF")


def _form_of(name: str) -> str:
    low = name.lower()
    if "narrative" in low or "叙事" in name:
        return "narrative"
    if "vasp" in low or "数据" in name:
        return "data"
    return "draft"


def _latest(files: list) -> Path:
    return max(files, key=lambda p: p.stat().st_mtime)


def _source_id_from_handoff(handoff_md: Path) -> str:
    try:
        text = handoff_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"state\.?id[:：]?\s*`?([A-Za-z0-9\-_]+)", text)
    return m.group(1) if m else ""


def topic_anchor_from_handoff(handoff_md: Path) -> str:
    """解析 HANDOFF 的「课题锚定」行（上游指定写作段锚定课题；空则由素材自行提炼）。"""
    try:
        text = handoff_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"课题锚定[:：]\s*(.+)", text)
    return m.group(1).strip() if m else ""


def run(data_dir: Path, output_dir: Path) -> dict:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    files: list = []  # [{role, path, sha256}]
    mode, source_ref, handoff_present = "standalone", "", False
    raw_calc_root_ref = ""
    from_upstream = False  # 素材是否来自上游交接区（"交接不完整"标记仅对上游来源的 refine 有意义）

    upstream = data_dir / "upstream_handoff"
    upstream_artifacts = (
        [p for p in upstream.glob("*.md") if not _is_handoff_name(p.name)] if upstream.is_dir() else []
    )

    raw_calc_root = _find_raw_calc_root(upstream)
    if raw_calc_root is not None:
        # 原始计算归档（QE pwo）：自动触发确定性提取 → 白名单表；README 归档说明不再误判为初稿
        from_upstream = True
        mode = "standalone"
        handoff_md = upstream / "HANDOFF.md"
        handoff_present = handoff_md.is_file()
        source_ref = _source_id_from_handoff(handoff_md) if handoff_present else raw_calc_root.name
        table = qe_extract.write_whitelist_table(
            qe_extract.extract(raw_calc_root),
            output_dir / "QE_数据表.md",
            output_dir / "QE_数据表.json",
        )
        files.append({"role": "data", "path": str(table), "sha256": _sha16(table)})
        for aux_name, role in (("README.md", "readme"), ("convergence_results.csv", "aux")):
            aux = next((c for c in (raw_calc_root / aux_name, raw_calc_root.parent / aux_name) if c.is_file()), None)
            if aux is not None:  # 归档根内部或其同级均可（两种交付摆放兼容）
                files.append({"role": role, "path": str(aux), "sha256": _sha16(aux)})
        # 原始输出目录只留档溯源（manifest 顶层字段），不入素材清单——
        # M3-④ 实测：目录条目会诱导规划师读 94×4.5MB pwo，上下文撑爆后臆造体系名
        raw_calc_root_ref = str(raw_calc_root)
        print(f"[判道] 原始计算归档：{raw_calc_root.name}（qe_extract 已生成白名单表，HANDOFF {'有' if handoff_present else '缺失'}）")
    elif upstream_artifacts:
        from_upstream = True
        artifact = _latest(upstream_artifacts)
        form = _form_of(artifact.name)
        mode = "refine" if form == "draft" else "standalone"
        handoff_md = upstream / "HANDOFF.md"
        handoff_present = handoff_md.is_file()
        source_ref = _source_id_from_handoff(handoff_md) if handoff_present else artifact.name
        files.append({"role": form, "path": str(artifact), "sha256": _sha16(artifact)})
        print(f"[判道] 上游交接：{artifact.name}（形态 {form}，HANDOFF {'有' if handoff_present else '缺失'}）")
    else:
        narrative = data_dir / "NARRATIVE_REPORT.md"
        data_table = data_dir / "vasp_results.md"
        if narrative.is_file() or data_table.is_file():
            mode, source_ref = "standalone", (narrative if narrative.is_file() else data_table).name
            if narrative.is_file():
                files.append({"role": "narrative", "path": str(narrative), "sha256": _sha16(narrative)})
            if data_table.is_file():
                files.append({"role": "data", "path": str(data_table), "sha256": _sha16(data_table)})
            print(f"[判道] 独立素材：{[f['path'] for f in files]}")
        else:
            drafts = [
                p
                for p in data_dir.glob("*.md")
                if p.name not in {"NARRATIVE_REPORT.md", "vasp_results.md", "README.md"}
            ]
            if drafts:
                draft = _latest(drafts)
                mode, source_ref = "refine", draft.name
                files.append({"role": "draft", "path": str(draft), "sha256": _sha16(draft)})
                print(f"[判道] 已有初稿：{draft.name} → 精修模式")
            else:
                searched = [str(upstream), str(narrative), str(data_table), f"{data_dir}/*.md"]
                print(f"[报错] 未找到任何有效输入。检索过的位置：{searched}", file=sys.stderr)
                sys.exit(2)

    manifest = {
        "mode": mode,
        "source_ref": source_ref,
        "handoff_present": handoff_present,
        "from_upstream": from_upstream,
        "topic_anchor": topic_anchor_from_handoff(data_dir / "upstream_handoff" / "HANDOFF.md"),
        "raw_calc_root": raw_calc_root_ref,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def current_data_file(output_dir: Path):
    """返回素材清单中的数据表（白名单源）路径；无则 None。"""
    manifest_path = Path(output_dir) / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for f in manifest.get("files", []):
        if f.get("role") == "data" and Path(f["path"]).is_file():
            return Path(f["path"])
    return None
