"""Organisation taxonomy, project catalogue and rule-based classifiers.

Rules come first and every result carries a confidence score; anything below
REVIEW_THRESHOLD is routed to the human review queue instead of being resolved
silently. An LLM fallback would plug in at `classify_project` (see TODO).
"""
from __future__ import annotations

import re

REVIEW_THRESHOLD = 0.8

PURPOSE_SUBS = [
    "Departmental teaching & research",
    "Departmental scholarships",
    "University-wide scholarships",
    "University-wide teaching units",
    "Administrative units",
    "Student clubs",
    "Research centers",
    "College of Sustainability & Green Energy",
]
GROUP_KEYS = ("annual_campaign", "university_fund", "designated")
DONOR_CLASSES = ["alumni", "friends", "company", "organisation", "staff_student"]
METHOD_KEYS = ["credit_card", "bank_transfer", "atm", "cash", "taiwan_pay", "postal_giro", "convenience_store", "check", "in_kind"]

# (department, college, aliases used for fuzzy matching in free text)
DEPARTMENTS = [
    ("Civil Engineering", "Engineering", ["civil", "土木工程學系", "土木工程", "土木系", "土木"]),
    ("Mechanical Engineering", "Engineering", ["mechanical", "機械工程學系", "機械工程", "機械系", "機械"]),
    ("Chemical & Materials Engineering", "Engineering", ["chemical", "materials", "化學工程與材料工程學系", "化學工程", "化工系", "化工"]),
    ("Business Administration", "Management", ["business admin", "企業管理學系", "企業管理", "企管系", "企管"]),
    ("Finance", "Management", ["finance", "財務金融學系", "財務金融", "財金系", "財金"]),
    ("Information Management", "Management", ["information management", "資訊管理學系", "資訊管理", "資管系", "資管"]),
    ("Computer Science", "EECS", ["computer science", "資訊工程學系", "資訊工程", "資訊系", "資工系", "資工"]),
    ("Electrical Engineering", "EECS", ["electrical", "電機工程學系", "電機工程", "電機系", "電機"]),
    ("Communication Engineering", "EECS", ["communication eng", "通訊工程學系", "通訊工程", "通訊系"]),
    ("Physics", "Science", ["physics", "物理學系", "物理系", "物理"]),
    ("Mathematics", "Science", ["mathematics", "math", "數學系", "數學"]),
    ("Chemistry", "Science", ["chemistry", "化學學系", "化學系"]),
    ("Statistics", "Science", ["statistics", "統計研究所", "統計系", "統計"]),
    ("Chinese Literature", "Liberal Arts", ["chinese lit", "中國文學系", "中文系"]),
    ("English", "Liberal Arts", ["english", "英美語文學系", "英文系"]),
    ("History", "Liberal Arts", ["history", "歷史學研究所", "歷史系"]),
    ("Philosophy", "Liberal Arts", ["philosophy", "哲學研究所", "哲學系"]),
    ("Earth Sciences", "Earth Sciences", ["earth sci", "地球科學學系", "地科系"]),
    ("Atmospheric Sciences", "Earth Sciences", ["atmospheric", "大氣科學學系", "大氣系"]),
    ("Space Science", "Earth Sciences", ["space science", "太空科學與工程學系", "太空系"]),
    ("Biomedical Engineering", "Life Sciences & Biomedical", ["biomedical", "生物醫學工程研究所", "生醫系"]),
    ("Life Sciences", "Life Sciences & Biomedical", ["life sci", "生命科學系", "生科系"]),
    ("Hakka Studies", "Hakka College", ["hakka", "客家語文暨社會科學學系", "客家系"]),
]
SUSTAINABILITY_COLLEGE = "Sustainability & Green Energy"
COLLEGES = sorted({c for _, c, _ in DEPARTMENTS} | {SUSTAINABILITY_COLLEGE})
DEPT_TO_COLLEGE = {d: c for d, c, _ in DEPARTMENTS}


def _p(name, group, sub, unit=None, college=None, first=2023, weight=1.0):
    return {"name": name, "purpose_group": group, "purpose_sub": sub, "unit": unit,
            "college": college, "first_year": first, "weight": weight}


def build_catalogue() -> list[dict]:
    """The cross-year project catalogue (WP2). Built from annual reports in real use."""
    out = []
    for dept, college, _ in DEPARTMENTS:
        out.append(_p(f"{dept}: Teaching & Research Fund", "designated", PURPOSE_SUBS[0], dept, college, 2023, 1.0))
        out.append(_p(f"{dept}: Scholarship", "designated", PURPOSE_SUBS[1], dept, college, 2023, 0.8))
    out.append(_p("Civil Engineering: Low-carbon Infrastructure Fund", "designated", PURPOSE_SUBS[0],
                  "Civil Engineering", "Engineering", 2025, 3.0))
    for n, w in [("Excellence Scholarship Fund", 1.4), ("Founders Memorial Scholarship", 0.8),
                 ("Need-based Scholarship Program", 1.2), ("Alumni Association Scholarship", 0.7)]:
        out.append(_p(n, "designated", PURPOSE_SUBS[2], None, None, 2023, w))
    out.append(_p("General Education Center: Course Development", "designated", PURPOSE_SUBS[3], None, None, 2023, 0.4))
    out.append(_p("Physical Education Office: Teams and Facilities", "designated", PURPOSE_SUBS[3], None, None, 2023, 0.7))
    for n, w, f in [("Library: Reading Room Renewal", 0.8, 2023), ("Library: Rare Books Preservation", 0.4, 2023),
                    ("Student Affairs: Student Aid Fund", 1.0, 2023), ("R&D Office: Chair Professor Fund", 0.4, 2023),
                    ("Secretariat: Anniversary Events", 0.6, 2023), ("University History Museum", 0.3, 2024),
                    ("Campus: New Teaching & Research Building", 0.5, 2023),
                    ("Athletics: Intercollegiate Games", 0.5, 2025)]:
        out.append(_p(n, "designated", PURPOSE_SUBS[4], None, None, f, w))
    for n, w in [("Student Club: Community Service Trip", 0.6), ("Student Club: Robotics Club", 0.5),
                 ("Student Club: Choir", 0.3), ("Student Club: Rural Education", 0.5), ("Student Club: Debate Team", 0.3)]:
        out.append(_p(n, "designated", PURPOSE_SUBS[5], None, None, 2023, w))
    for n, w in [("Polar Research Center", 0.5), ("Space Science & Technology Center", 0.5),
                 ("Opera Archive & Museum Center", 0.6), ("Climate Observatory Center", 0.3)]:
        out.append(_p(n, "designated", PURPOSE_SUBS[6], None, None, 2023, w))
    out.append(_p("Sustainability & Green Energy: Research Fund", "designated", PURPOSE_SUBS[7],
                  "Sustainability & Green Energy", SUSTAINABILITY_COLLEGE, 2023, 0.5))
    for n, w in [("University Fund: General", 2.0), ("University Fund: Anniversary Campaign", 1.0),
                 ("University Fund: Talent Recruitment", 0.6)]:
        out.append(_p(n, "university_fund", None, None, None, 2023, w))
    for n, w, f in [("Campaign: Study with Peace of Mind", 3.0, 2023), ("Campaign: Tree Adoption", 2.0, 2023),
                    ("Campaign: Resilience Student Aid", 1.2, 2023), ("Campaign: Opera Research Outreach", 0.8, 2023),
                    ("Campaign: Mechanical Global Mobility", 0.9, 2023), ("Campaign: Library Roof Restoration", 0.5, 2024),
                    ("Campaign: Food Safety Initiative", 1.5, 2025), ("Campaign: Night Angels Social Engagement", 0.6, 2025),
                    ("Campaign: Games Torch", 0.7, 2025)]:
        out.append(_p(n, "annual_campaign", None, None, None, f, w))
    return out


CATALOGUE = build_catalogue()
def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _pkey(s: str | None) -> str:
    """Catalogue lookup key: tolerant to case, spacing, ' - ' vs ': ' and a trailing full stop."""
    return _norm(s).replace(" - ", ": ").rstrip(".")


_CATALOGUE_BY_KEY = {_pkey(p["name"]): p for p in CATALOGUE}


def find_department(text: str | None) -> tuple[str, str] | None:
    """The department named in free text. The longest alias wins, so 資訊工程 is not read as 資訊管理."""
    t = _norm(text)
    if not t:
        return None
    best, best_len = None, 0
    for dept, college, aliases in DEPARTMENTS:
        for alias in (dept.lower(), *aliases):
            if alias and alias in t and len(alias) > best_len:
                best, best_len = (dept, college), len(alias)
    return best


def classify_project(name: str | None) -> dict:
    """Return purpose_group/purpose_sub/unit/college + confidence.

    TODO(LLM fallback): for confidence < REVIEW_THRESHOLD, ask an LLM for a label
    with a structured-output schema, then keep it in the review queue regardless.
    """
    key = _norm(name)
    canonical = (name or "").strip() or None
    empty = {"purpose_group": None, "purpose_sub": None, "unit": None, "college": None, "confidence": 0.0,
             "canonical": canonical}
    if not key:
        return empty
    known = _CATALOGUE_BY_KEY.get(_pkey(name))
    if known:
        return {"purpose_group": known["purpose_group"], "purpose_sub": known["purpose_sub"],
                "unit": known["unit"], "college": known["college"], "confidence": 1.0, "canonical": known["name"]}

    dept = find_department(key)
    unit, college = (dept if dept else (None, None))

    def out(group, sub, conf, u=unit, c=college):
        return {"purpose_group": group, "purpose_sub": sub, "unit": u, "college": c, "confidence": conf,
                "canonical": canonical}

    if "university fund" in key or "school fund" in key or "anniversary fund" in key:
        return out("university_fund", None, 0.9, None, None)
    if key.startswith("campaign") or "annual campaign" in key:
        return out("annual_campaign", None, 0.85, None, None)
    if "club" in key or "student team" in key:
        return out("designated", PURPOSE_SUBS[5], 0.85, None, None)
    if "sustainab" in key or "green energy" in key or "永續與綠能" in key:
        return out("designated", PURPOSE_SUBS[7], 0.85, SUSTAINABILITY_COLLEGE, SUSTAINABILITY_COLLEGE)
    if "general education" in key or "physical education" in key:
        return out("designated", PURPOSE_SUBS[3], 0.8, None, None)
    if any(w in key for w in ("library", "student affairs", "secretariat", "r&d", "office", "building", "museum")):
        return out("designated", PURPOSE_SUBS[4], 0.8, None, None)
    if "scholarship" in key or "financial aid" in key:
        if dept:
            return out("designated", PURPOSE_SUBS[1], 0.85)
        return out("designated", PURPOSE_SUBS[2], 0.7, None, None)
    if "center" in key or "centre" in key or "observatory" in key:
        return out("designated", PURPOSE_SUBS[6], 0.7, None, None)
    if dept:
        return out("designated", PURPOSE_SUBS[0], 0.8)
    return empty


# ------------------------------------------------------------ normalisers

_METHOD_RULES = [
    ("atm", ("atm",)),
    ("credit_card", ("credit", "card", "visa", "刷卡", "信用卡")),
    ("taiwan_pay", ("taiwan pay", "taiwanpay", "台灣pay")),
    ("bank_transfer", ("wire", "transfer", "bank", "電匯", "匯款")),
    ("postal_giro", ("postal", "giro", "郵政")),
    ("convenience_store", ("convenience", "超商")),
    ("check", ("check", "cheque", "draft", "支票", "匯票")),
    ("cash", ("cash", "現金")),
    ("in_kind", ("in-kind", "in kind", "實物")),
]


def normalise_method(raw) -> str | None:
    t = _norm(str(raw)) if raw is not None and str(raw) != "nan" else ""
    if not t:
        return None
    for label, keys in _METHOD_RULES:
        if any(k in t for k in keys):
            return label
    return None


def normalise_mode(raw) -> str:
    t = _norm(str(raw)) if raw is not None and str(raw) != "nan" else ""
    return "recurring" if any(k in t for k in ("recurring", "monthly", "regular", "定期")) else "one_time"


def normalise_bool(raw) -> bool:
    t = _norm(str(raw)) if raw is not None and str(raw) != "nan" else ""
    return t in {"yes", "y", "true", "1", "是", "anonymous", "anon"}


def normalise_donor_class(raw) -> tuple[str, float]:
    t = _norm(str(raw)) if raw is not None and str(raw) != "nan" else ""
    if not t:
        return "unknown", 0.0
    rules = [
        ("alumni", ("alumni", "alumnus", "alumna", "校友")),
        ("friends", ("friend", "中大之友")),
        ("company", ("compan", "corp", "business", "enterprise", "ltd", "inc", "企業", "公司")),
        ("organisation", ("foundation", "organi", "association", "legal", "society", "法人")),
        ("staff_student", ("faculty", "staff", "student", "教職員")),
    ]
    for label, keys in rules:
        if any(k in t for k in keys):
            return label, 0.95
    return "unknown", 0.2


_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def extract_alumni_attrs(raw) -> tuple[int | None, str | None]:
    t = str(raw) if raw is not None and str(raw) != "nan" else ""
    year = None
    m = _YEAR_RE.search(t)
    if m:
        year = int(m.group(1))
    dept = find_department(t)
    return year, (dept[0] if dept else None)
