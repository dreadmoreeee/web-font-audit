"""Markdown and JSON output."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from . import __version__
from .analyze import PageReport, kb

MAX_FACE_ROWS = 40


def _name(url: str) -> str:
    if url.startswith("data:"):
        return "(inline data: URL)"
    parts = urlsplit(url)
    name = parts.path.rsplit("/", 1)[-1] or parts.path
    if len(name) > 48:
        name = name[:22] + "..." + name[-22:]
    return name


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _count(findings, severity):
    return sum(1 for f in findings if f.severity == severity)


def to_json(reports: list[PageReport], brotli: str = "", budget_failed: bool = False) -> str:
    doc = {
        "tool": "web-font-audit",
        "version": __version__,
        "brotli": brotli,
        "budget_failed": budget_failed,
        "pages": [r.to_dict() for r in reports],
    }
    return json.dumps(doc, indent=2)


def to_markdown(reports: list[PageReport]) -> str:
    lines = ["# Web font audit", ""]
    if len(reports) > 1:
        lines += ["| Page | Font files | Transferred | Families | Errors | Warnings | Info |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for r in reports:
            if r.error:
                lines.append(f"| {r.url} | - | - | - | load failed | | |")
                continue
            lines.append(
                f"| {r.url} | {len(r.network_fonts)} | {kb(r.total_transfer)} | "
                f"{len(r.used_families())} | {_count(r.findings, 'error')} | "
                f"{_count(r.findings, 'warning')} | {_count(r.findings, 'info')} |")
        lines.append("")
    for r in reports:
        lines += page_markdown(r)
    return "\n".join(lines).rstrip() + "\n"


def page_markdown(r: PageReport) -> list[str]:
    lines = [f"## {r.url}", ""]
    if r.error:
        return lines + [f"Could not load the page: {r.error}", ""]
    third = sum(1 for f in r.fonts if f.party == "third-party")
    first = sum(1 for f in r.fonts if f.party == "first-party")
    inline = len(r.fonts) - len(r.network_fonts)
    head = (f"HTTP {r.status}, viewport {r.viewport[0]}x{r.viewport[1]}. "
            f"{len(r.network_fonts)} font file(s), {kb(r.total_transfer)} transferred "
            f"({kb(r.total_decoded)} decoded); {len(r.used_families())} family(ies), "
            f"{len(r.used_variants())} weight/style variant(s) used; "
            f"{first} first-party, {third} third-party")
    if inline:
        head += f", {inline} inline data: font(s)"
    if r.final_url and r.final_url.rstrip("/") != r.url.rstrip("/"):
        lines += [f"Final URL: {r.final_url}", ""]
    lines += [head + ".", ""]

    if r.fonts:
        lines += ["| Font file | Family | Variant | Format | Transfer | Party | font-display | Preload | Chars used (above fold) |",
                  "|---|---|---|---|---:|---|---|---|---:|"]
        for f in r.fonts:
            variants = ", ".join(sorted({f"{x.weight_text()} {x.style}" for x in f.faces})) or "-"
            lines.append(
                f"| {_cell(_name(f.url))} | {_cell(', '.join(f.families) or '-')} | {variants} | "
                f"{f.format} | {kb(f.transfer_bytes)} | {f.party} | "
                f"{_cell(', '.join(f.font_display) or '-')} | {'yes' if f.preloaded else 'no'} | "
                f"{len(f.used_chars)} ({len(f.above_chars)}) |")
        lines.append("")

    subs = [f for f in r.fonts if f.subset]
    if subs:
        if r.subset_flavor == "woff2":
            how = "fontTools subsets built in memory, measured as WOFF2."
        else:
            how = ("fontTools subsets built in memory and measured as WOFF, because the brotli "
                   "package is not installed and WOFF2 cannot be written. For files served in "
                   "another format, sizes are scaled by subset/original WOFF size (marked ~).")
        lines += [f"Subsetting: {how}", "",
                  "| Font file | Served | Code points in font | Latin subset | Page-only subset |",
                  "|---|---:|---:|---:|---:|"]
        for f in subs:
            s = f.subset
            mark = "~" if s["estimated"] else ""
            lines.append(
                f"| {_cell(_name(f.url))} | {kb(f.decoded_bytes)} | {f.cmap_size} | "
                f"{mark}{kb(s['latin_subset_estimate'])} ({s['latin_subset_codepoints']} cp) | "
                f"{mark}{kb(s['page_subset_estimate'])} ({s['page_subset_codepoints']} cp) |")
        lines.append("")

    parse_errors = [f for f in r.fonts if f.parse_error]
    for f in parse_errors:
        lines.append(f"Note: {_name(f.url)} could not be analysed: {f.parse_error}")
    if parse_errors:
        lines.append("")

    if r.findings:
        lines += ["Findings:", ""]
        for f in r.findings:
            lines.append(f"- **{f.severity.upper()}** `{f.code}` {f.message}")
            lines.append(f"  Fix: {f.fix}")
        lines.append("")
    else:
        lines += ["No findings.", ""]

    if r.faces:
        used = sum(1 for v in r.face_used.values() if v)
        lines += [f"@font-face rules: {len(r.faces)} ({used} used on this page)", "",
                  "| Family | Weight | Style | font-display | unicode-range | local() | Used |",
                  "|---|---|---|---|---|---|---|"]
        for face in r.faces[:MAX_FACE_ROWS]:
            ur = face.unicode_range_text or "-"
            if len(ur) > 40:
                ur = ur[:37] + "..."
            lines.append(
                f"| {_cell(face.family)} | {face.weight_text()} | {face.style} | "
                f"{face.display if face.display_declared else '(not set)'} | {_cell(ur)} | "
                f"{_cell(', '.join(face.local_names) or '-')} | "
                f"{'yes' if r.face_used.get(face.order) else 'no'} |")
        if len(r.faces) > MAX_FACE_ROWS:
            lines.append(f"| ... {len(r.faces) - MAX_FACE_ROWS} more (see JSON) | | | | | | |")
        lines.append("")

    if r.preloads:
        lines += ["Font preloads: " + ", ".join(
            f"{_name(p['href'])}{'' if p['crossorigin'] else ' (no crossorigin)'}" for p in r.preloads), ""]
    for note in r.notes:
        lines += [f"Note: {note}", ""]
    if r.budget_failures:
        lines += ["Budget exceeded:", ""] + [f"- {b}" for b in r.budget_failures] + [""]
    return lines
