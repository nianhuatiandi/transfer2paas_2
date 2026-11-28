"""Export the experimental BWF lexicon as UTF-8 text; no API calls."""
import json
from pathlib import Path


def main():
    package = Path(__file__).resolve().parents[2]
    path = package / "lexicons" / "badminton_bwf_v01.json"
    vocab = json.loads(path.read_text(encoding="utf-8"))
    lines = [
        "羽毛球 BWF 依据词表 v0.1",
        "整理日期：2026-11-25",
        "机器可读版本：badminton_bwf_v01.json",
        "英文术语来自 BWF 教材；中文为项目工作译名，判别/时间/计数规则为项目草案。",
        "状态：" + vocab["status"],
        "",
    ]
    sections = [
        ("movement_terms", "一、移动技术（教材第 51 页总表，共 8 类）"),
        ("stroke_terms", "二、击球技术（模块 7，共 20 项）"),
        ("movement_roles", "三、移动周期阶段（不是并列技术动作）"),
        ("stroke_subphases", "四、击球子阶段（不与整个击球重复计数）"),
        ("training_terms", "五、训练与喂球术语（区分投送动作和训练组织形式）"),
        ("project_extensions", "六、项目补充标签（不冒充官方词表）"),
        ("key_moments", "七、项目时间关键点（不增加动作数）"),
    ]
    for key, title in sections:
        lines.extend([title, "-" * 48])
        for term in vocab[key]:
            source = (
                f"书内 p.{term['printed_page']} / PDF 第 {term['pdf_page']} 页"
                if "printed_page" in term else "项目自定义，无官方独立词条"
            )
            lines.append(f"{term['label']} | {term['zh']} | {term.get('official_en', '')} | {source}")
            for field in ("project_cues", "project_boundary", "project_uncertainty", "translation_note", "note"):
                if term.get(field):
                    lines.append("  " + term[field])
        lines.append("")
    lines.extend(["八、项目标注规则（不是 BWF 官方标注标准）", "-" * 48])
    for key, value in vocab["annotation_policy"].items():
        lines.append(key + ": " + (" / ".join(value) if isinstance(value, list) else value))
    lines.extend(["", "九、来源与限制", "-" * 48])
    lines.extend(vocab["source_caveats"])
    lines.extend(["", vocab["source"]["download_url"]])
    path.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Exported UTF-8 lexicon:", path.with_suffix(".txt"))


if __name__ == "__main__":
    main()
