"""
Extract CNSVS Scales section data (GAD-7, NPQ, PHQ-9, PSQI, PCL-5) from PDF text.
Returns structured rows for the dashboard (score + optional severity/response).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Dashboard scales (user-requested set)
SCALE_TESTS: Dict[str, Dict[str, str]] = {
    "GAD-7": {
        "name": "Generalized Anxiety Disorder 7-item (GAD-7) Scale",
        "pattern": r"Generalized Anxiety Disorder 7-item.*GAD-7.*Scale",
        "total_pattern": r"GAD-7\s+Anxiety\s+Severity\s+(\d+)",
        "total_label": "GAD-7 Anxiety Severity (Total)",
    },
    "PHQ-9": {
        "name": "Patient Health Questionnaire (PHQ-9)",
        "pattern": r"Patient Health Questionnaire.*PHQ-9",
        "total_pattern": r"PHQ-9\s+Score\s+(\d+)",
        "total_label": "PHQ-9 Score (Total)",
    },
    "NPQ-45": {
        "name": "NeuroPsych Questionnaire (NPQ) SF-45",
        "pattern": r"NeuroPsych Questionnaire.*NPQ.*SF-45",
    },
    "PSQI": {
        "name": "Pittsburgh Sleep Quality Index (PSQI) SF-10",
        "pattern": r"Pittsburgh Sleep Quality Index.*PSQI.*SF-10",
    },
    "PCL-5": {
        "name": "The PTSD Checklist (PCL-5) SF-20",
        "pattern": r"The PTSD Checklist.*PCL-5.*SF-20",
    },
}

NPQ_DOMAIN_NAMES = [
    "Attention", "Impulsive", "Memory", "Anxiety", "Panic", "Depression",
    "Mood Stability", "Aggression", "Fatigue", "Sleep", "Suicide", "Pain",
]

ITEM_LINE_RE = re.compile(
    r"^(\d+)\s+(.+?)\s+(\d+)\s*[-–]\s*(.+)$",
    re.UNICODE,
)
# "• Feeling nervous, anxious or on edge: 3 - Nearly every day"
# "• Difficulty concentrating: 3 - A severe problem"
COLON_BULLET_ITEM_RE = re.compile(
    r"^[•\*\-]?\s*(.+?):\s*(\d+)\s*[-–]\s*(.+)$",
    re.UNICODE,
)
NPQ_SECTION_RE = re.compile(r"^(.+?)\s+Questions\s*$", re.IGNORECASE)
PCL5_CLUSTER_RE = re.compile(
    r"^([A-Z][^\(]+?)\s*\(Items\s+\d+\s*[-–]\s*\d+\)\s+(\d+)\s*$",
    re.UNICODE,
)
PSQI_DOMAIN_PAIR_RE = re.compile(
    r"^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s*$",
)
PSQI_SINGLE_RE = re.compile(r"^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s*$")


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _row(
    metric: str,
    score: Any,
    *,
    severity: str = "",
    response: str = "",
    row_type: str = "item",
    sort_index: Optional[int] = None,
    npq_domain: str = "",
) -> Optional[Dict[str, Any]]:
    s = _num(score)
    if s is None:
        return None
    metric = re.sub(r"\s+", " ", str(metric or "")).strip()
    if not metric:
        return None
    out: Dict[str, Any] = {
        "metric": metric,
        "score": s,
        "standard_score": s,
        "percentile": None,
        "severity": (severity or "").strip(),
        "response": (response or "").strip(),
        "row_type": row_type,
        "flagged": False,
    }
    if sort_index is not None:
        out["sort_index"] = sort_index
    domain = (npq_domain or "").strip()
    if domain:
        out["npq_domain"] = domain
    return out


def _norm_metric_key(metric: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (metric or "").lower())


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        key = _norm_metric_key(r.get("metric", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _parse_numbered_items(
    section: str,
    *,
    label_prefix: bool = True,
    sort_base: int = 0,
    npq_domain: str = "",
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = ITEM_LINE_RE.match(stripped)
        if not m:
            continue
        num, text, score, response = m.group(1), m.group(2).strip(), m.group(3), m.group(4).strip()
        if label_prefix and num == "10" and re.search(r"how difficult have the problems", text, re.I):
            continue
        metric = f"Item {num}: {text}" if label_prefix else text
        try:
            sort_index = sort_base + int(num)
        except ValueError:
            sort_index = sort_base + len(rows) + 1
        entry = _row(
            metric,
            score,
            response=response,
            row_type="item",
            sort_index=sort_index,
            npq_domain=npq_domain,
        )
        if entry:
            rows.append(entry)
    return rows


def _parse_colon_bullet_items(section: str, *, section_prefix: str = "") -> List[Dict[str, Any]]:
    """Parse lines like '• Question text: 3 - Nearly every day'."""
    rows: List[Dict[str, Any]] = []
    prefix = f"{section_prefix} · " if section_prefix else ""
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = COLON_BULLET_ITEM_RE.match(stripped)
        if not m:
            continue
        text, score, response = m.group(1).strip(), m.group(2), m.group(3).strip()
        if not text:
            continue
        entry = _row(f"{prefix}{text}", score, response=response, row_type="item")
        if entry:
            rows.append(entry)
    return rows


def _parse_gad_phq_items(section: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.extend(_parse_numbered_items(section, label_prefix=True))
    rows.extend(_parse_colon_bullet_items(section))
    return _dedupe_rows(rows)


def _parse_total(
    section: str,
    pattern: str,
    label: str,
    *,
    sort_index: Optional[int] = 9999,
) -> Optional[Dict[str, Any]]:
    m = re.search(pattern, section, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    return _row(label, m.group(1), row_type="total", sort_index=sort_index)


PHQ_ITEM10_METRIC = (
    "Item 10: How difficult have the problems you reported made it for you to do your work, "
    "take care of things at home, or get along with other people?"
)
PHQ_ITEM10_RE = re.compile(
    r"10\.?\s*How difficult have the problems[\s\S]*?(\d+)\s*[-–]\s*(.+?)(?=\s*Developed\b|\Z)",
    re.IGNORECASE,
)


def _parse_phq_item10(section: str) -> Optional[Dict[str, Any]]:
    m = PHQ_ITEM10_RE.search(section)
    if not m:
        return None
    response = re.sub(r"\s+", " ", m.group(2).strip())
    return _row(
        PHQ_ITEM10_METRIC,
        m.group(1),
        response=response,
        row_type="item",
        sort_index=10,
    )


def _parse_npq_domains(section: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    block = section
    if "Domain Score" in section:
        idx = section.find("Domain Score")
        block = section[idx:]
        q_idx = block.find("Attention Questions")
        if q_idx > 0:
            block = block[:q_idx]
    text = re.sub(r"\s+", " ", block)
    try:
        from cnsvs.limbic_service import parse_domain_scores

        for d in parse_domain_scores(text):
            entry = _row(
                d.get("domain", ""),
                d.get("score", ""),
                severity=d.get("severity", ""),
                row_type="domain",
            )
            if entry:
                rows.append(entry)
    except ImportError:
        pass
    if rows:
        return rows
    severity_levels = [
        "Moderately Severe", "Not a problem", "Severe", "Moderate", "Mild", "Minimal", "None",
    ]
    for domain in NPQ_DOMAIN_NAMES:
        pattern = rf"\b{re.escape(domain)}\s+(\d+)\s+"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        score = match.group(1)
        after = text[match.end() :].strip()
        severity = ""
        for sev in severity_levels:
            if after.lower().startswith(sev.lower()):
                severity = sev
                break
        entry = _row(
            domain,
            score,
            severity=severity,
            row_type="domain",
            sort_index=NPQ_DOMAIN_NAMES.index(domain) + 1,
        )
        if entry:
            rows.append(entry)
    return rows


def _parse_npq_question_items(section: str) -> List[Dict[str, Any]]:
    """Parse NPQ sub-scales under '* Questions' headers (bullet/colon or numbered items)."""
    rows: List[Dict[str, Any]] = []
    current_section = ""
    item_in_section = 0
    q_start = section.find("Attention Questions")
    block = section[q_start:] if q_start >= 0 else section
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        sm = NPQ_SECTION_RE.match(stripped)
        if sm:
            current_section = sm.group(1).strip()
            item_in_section = 0
            continue
        if "Domain Score" in stripped and "Severity" in stripped:
            continue
        prefix = f"{current_section} · " if current_section else ""
        domain_idx = (
            NPQ_DOMAIN_NAMES.index(current_section) + 1
            if current_section in NPQ_DOMAIN_NAMES
            else 99
        )
        m = COLON_BULLET_ITEM_RE.match(stripped)
        if m:
            text, score, response = m.group(1).strip(), m.group(2), m.group(3).strip()
            item_in_section += 1
            entry = _row(
                f"{prefix}{text}",
                score,
                response=response,
                row_type="item",
                sort_index=domain_idx * 100 + item_in_section,
                npq_domain=current_section,
            )
            if entry:
                rows.append(entry)
            continue
        plain = re.sub(r"^[•\*\-]\s*", "", stripped)
        m2 = ITEM_LINE_RE.match(plain)
        if m2:
            text, score, response = m2.group(2).strip(), m2.group(3), m2.group(4).strip()
            item_in_section += 1
            entry = _row(
                f"{prefix}{text}",
                score,
                response=response,
                row_type="item",
                sort_index=domain_idx * 100 + item_in_section,
                npq_domain=current_section,
            )
            if entry:
                rows.append(entry)
    return rows


def _parse_npq_full(section: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.extend(_parse_npq_domains(section))
    rows.extend(_parse_npq_question_items(section))
    return _dedupe_rows(rows)


def _parse_psqi_domains(section: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    in_table = False
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "Domain" in stripped and "Score" in stripped:
            in_table = True
            continue
        if not in_table:
            continue
        if stripped[0].isdigit() and len(stripped.split()[0]) <= 2:
            break
        m_pair = PSQI_DOMAIN_PAIR_RE.match(stripped)
        if m_pair:
            for domain, score in ((m_pair.group(1).strip(), m_pair.group(2)), (m_pair.group(3).strip(), m_pair.group(4))):
                entry = _row(domain, score, row_type="domain")
                if entry:
                    rows.append(entry)
            continue
        m_single = PSQI_SINGLE_RE.match(stripped)
        if m_single:
            domain, score = m_single.group(1).strip(), m_single.group(2)
            if "psqi total" in domain.lower() or domain.lower() == "total score":
                entry = _row("PSQI Total Score", score, row_type="total")
            else:
                entry = _row(domain, score, row_type="domain")
            if entry:
                rows.append(entry)
    return rows


def _parse_pcl5_clusters(section: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = PCL5_CLUSTER_RE.match(stripped)
        if not m:
            continue
        domain = m.group(1).strip()
        score = m.group(2)
        row_type = "total" if "total score" in domain.lower() else "domain"
        entry = _row(domain, score, row_type=row_type)
        if entry:
            rows.append(entry)
    return rows


def _scale_section_ranges(full_text: str) -> Dict[str, str]:
    """Map canonical scale name -> section text using ordered header positions."""
    hits: List[Tuple[int, str, str]] = []
    for scale_id, cfg in SCALE_TESTS.items():
        m = re.search(cfg["pattern"], full_text, re.IGNORECASE)
        if m:
            hits.append((m.start(), scale_id, cfg["name"]))
    hits.sort(key=lambda x: x[0])
    sections: Dict[str, str] = {}
    for i, (start, _sid, name) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(full_text)
        sections[name] = full_text[start:end]
    return sections


def parse_scale(scale_id: str, section: str) -> List[Dict[str, Any]]:
    cfg = SCALE_TESTS[scale_id]
    rows: List[Dict[str, Any]] = []

    if scale_id in ("GAD-7", "PHQ-9"):
        rows.extend(_parse_gad_phq_items(section))
        if scale_id == "PHQ-9":
            item10 = _parse_phq_item10(section)
            if item10:
                rows.append(item10)
        total = _parse_total(
            section,
            cfg["total_pattern"],
            cfg["total_label"],
            sort_index=11 if scale_id == "PHQ-9" else 8,
        )
        if total:
            rows.append(total)
    elif scale_id == "NPQ-45":
        rows.extend(_parse_npq_full(section))
    elif scale_id == "PSQI":
        rows.extend(_parse_psqi_domains(section))
    elif scale_id == "PCL-5":
        rows.extend(_parse_pcl5_clusters(section))
        rows.extend(_parse_numbered_items(section))

    return rows


def parse_scales_from_text(full_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """Return {canonical_scale_name: [rows]} for scales found in the PDF."""
    scales: Dict[str, List[Dict[str, Any]]] = {}
    if not full_text or not full_text.strip():
        return scales

    id_by_name = {cfg["name"]: sid for sid, cfg in SCALE_TESTS.items()}
    for name, section in _scale_section_ranges(full_text).items():
        scale_id = id_by_name.get(name)
        if not scale_id:
            continue
        rows = parse_scale(scale_id, section)
        if rows:
            rows.sort(key=lambda r: (r.get("sort_index") is None, r.get("sort_index") or 0))
            scales[name] = rows
    return scales


def parse_scales_from_pdf(pdf_path: str) -> Dict[str, List[Dict[str, Any]]]:
    from main import extract_text_from_pdf

    return parse_scales_from_text(extract_text_from_pdf(pdf_path))
