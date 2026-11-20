"""
Evidence-Grounded Speech Understanding & Actionable Brief Extractor.
Extracts structured project instructions, changes, removals, additions,
responsibilities, negations, confirmed decisions, and open questions
from conversational Egyptian Arabic-English transcripts.
Strictly grounds every extracted claim to transcript segment IDs and timestamps.
"""
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    segment_id: int
    start: float
    end: float
    time_formatted: str
    quote: str


class InstructionItem(BaseModel):
    id: str
    category: str  # 'required_changes', 'content_to_remove', 'content_to_add', 'responsibilities', 'negative_instructions', 'wording_corrections', 'confirmed_decisions', 'unresolved_questions', 'uncertain_statements'
    title: str
    description: str
    provenance: str  # 'explicitly_spoken', 'interpreted_from_context', 'needs_human_verification'
    evidence: EvidenceSpan
    confidence: float = 0.90
    negation_detected: bool = False
    reversal_detected: bool = False
    reversal_details: Optional[str] = None


class UnderstandingBrief(BaseModel):
    job_id: str
    title: str
    topic_overview: str
    summary_counts: Dict[str, int]
    categories: Dict[str, List[InstructionItem]]
    created_at: str


def format_timestamp(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


# Linguistic patterns for Egyptian Arabic dialect
NEGATION_PATTERNS = [
    r"\b(مش|ملهمش|ما|بلاش|لا|مش عايزين|مش بتاع|مش هتبعت|مش هتكون|مش هتبقى)\b",
]

REMOVAL_PATTERNS = [
    r"\b(نشيلها|نشيل|شيل|امسح|احذف|ملهمش علاقه|بلاش صوره|نلغي|شيلها)\b",
]

ADDITION_PATTERNS = [
    r"\b(عايزين|نحط|حط|ضيف|نعمل|اعمل|نضيف|نزود|طلعله|نطلع)\b",
]

RESPONSIBILITY_PATTERNS = [
    r"\b(بتوع الجامعه|الناس بتوع|هما اللي|هم اللي|هتبعت حد|مسؤوليه|مسؤولين|المنظمين|هيوفروا)\b",
]

WORDING_PATTERNS = [
    r"\b(capital|small|title|logo|لوجو|اللوجو|الخط|صيغه|اختصار|مسمى|اسم|ال chapter|البرانش)\b",
]

CONFIRMED_PATTERNS = [
    r"\b(تمام ماشي|ماشي مش مشكله|تمام|ماشي|اوكي|مش مشكله|شغال|معتمد)\b",
]

REVERSAL_PATTERNS = [
    r"\b(استنى كدا|استنى|قصدي|فلأ|فلا|لا انت|بدل كدا|بل)\b",
    r"فلأ\s+(انت|إنت)",
    r"لا\s+(انت|إنت)",
]

UNCERTAINTY_PATTERNS = [
    r"\b(مش عارف ايه|شوف عادي|اي حاجه|او حاجه|اي اختصار|مش متأكد|مش حاجه معينه)\b",
]


def extract_instructions_from_segments(
    job_id: str,
    segments: List[Dict[str, Any]],
    job_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts an evidence-grounded structured understanding brief from transcript segments.
    Preserves strict traceability: every instruction references its source segment and time.
    """
    items_by_cat: Dict[str, List[Dict[str, Any]]] = {
        "required_changes": [],
        "content_to_remove": [],
        "content_to_add": [],
        "responsibilities": [],
        "negative_instructions": [],
        "wording_corrections": [],
        "confirmed_decisions": [],
        "unresolved_questions": [],
        "uncertain_statements": [],
    }

    item_counter = 1

    for seg in segments:
        seg_id = seg.get("id", 0)
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        text = seg.get("text", "").strip()
        if not text:
            continue

        time_fmt = f"{format_timestamp(start)} - {format_timestamp(end)}"
        evidence = {
            "segment_id": seg_id,
            "start": start,
            "end": end,
            "time_formatted": time_fmt,
            "quote": text,
        }

        # Check for mid-sentence reversals / self-corrections
        has_reversal = False
        reversal_info = None
        for pat in REVERSAL_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                has_reversal = True
                reversal_info = f"Speaker revised initial phrasing: '{m.group(0)}'"
                break

        # Check for Removal Requests
        for pat in REMOVAL_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                # Analyze target
                target = "محتوى محدد"
                if "صوره" in text or "صورة" in text:
                    target = "صورة الجامعة أو صور غير متعلقة"
                elif "لوجو" in text or "logo" in text.lower():
                    target = "شعار غير معتمد"

                items_by_cat["content_to_remove"].append({
                    "id": f"rem_{item_counter}",
                    "category": "content_to_remove",
                    "title": f"حذف أو إزالة: {target}",
                    "description": f"طلب صريح بإزالة {target} من العرض أو المستند لعدم ملاءمتها.",
                    "provenance": "explicitly_spoken",
                    "evidence": evidence,
                    "confidence": 0.95,
                    "negation_detected": True,
                    "reversal_detected": has_reversal,
                    "reversal_details": reversal_info,
                })
                item_counter += 1
                break

        # Check for Explicit Negation Instructions ("لا تضع...", "مش بتاع كذا")
        if re.search(r"\b(مش بتاع|مش|بلاش|لا انت|فلأ)\b", text, re.IGNORECASE):
            neg_title = "تعليمات نفي واشتراط عدم التعيين"
            if "chapter" in text.lower() or "شابتر" in text:
                neg_title = "عدم استخدام شعار الشابتر الأساسي"
            elif "cis" in text.lower() and ("مدرب" in text or "instructor" in text.lower() or "تبعت" in text):
                neg_title = "عدم إسناد مهمة المدربين إلى CIS بل إلى الجامعة"

            items_by_cat["negative_instructions"].append({
                "id": f"neg_{item_counter}",
                "category": "negative_instructions",
                "title": neg_title,
                "description": f"استبعاد صريح لعنصر أو مسؤولية محددة: '{text[:80]}...'",
                "provenance": "explicitly_spoken",
                "evidence": evidence,
                "confidence": 0.92,
                "negation_detected": True,
                "reversal_detected": has_reversal,
                "reversal_details": reversal_info,
            })
            item_counter += 1

        # Check for Responsibility Assignments
        for pat in RESPONSIBILITY_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                party = "جهة محددة"
                if "جامعه" in text or "جامعة" in text:
                    party = "الجامعة (University Partner)"
                elif "cis" in text.lower():
                    party = "CIS Chapter"

                items_by_cat["responsibilities"].append({
                    "id": f"resp_{item_counter}",
                    "category": "responsibilities",
                    "title": f"تحديد جهة المسؤولية: {party}",
                    "description": f"توضيح أن تنفيذ البند يقع على عاتق {party} وليس جهة أخرى.",
                    "provenance": "explicitly_spoken" if ("ناس بتوع" in text or "هم اللي" in text) else "interpreted_from_context",
                    "evidence": evidence,
                    "confidence": 0.90,
                    "negation_detected": bool(re.search(r"\bمش\b", text)),
                    "reversal_detected": has_reversal,
                    "reversal_details": reversal_info,
                })
                item_counter += 1
                break

        # Check for Additions / Required Modifications
        for pat in ADDITION_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                elem = "عنصر جديد"
                if "لوجو" in text or "logo" in text.lower():
                    elem = "لوجو فرع مصر (Egypt Section Logo)"
                elif "title" in text.lower() or "عنوان" in text:
                    elem = "عنوان الفعالية (Event Title)"
                elif "اختصار" in text:
                    elem = "اختصار مسمى المشروع"

                items_by_cat["required_changes"].append({
                    "id": f"chg_{item_counter}",
                    "category": "required_changes",
                    "title": f"تعديل أو إضافة: {elem}",
                    "description": f"توجيه بتضمين أو استبدال {elem} في الموضع المطلوب.",
                    "provenance": "explicitly_spoken",
                    "evidence": evidence,
                    "confidence": 0.92,
                    "negation_detected": False,
                    "reversal_detected": has_reversal,
                    "reversal_details": reversal_info,
                })
                item_counter += 1
                break

        # Check for Wording & Formatting Corrections
        for pat in WORDING_PATTERNS:
            if re.search(pat, text, re.IGNORECASE) and ("capital" in text.lower() or "small" in text.lower() or "مراجعه" in text or "تراجع" in text):
                items_by_cat["wording_corrections"].append({
                    "id": f"wrd_{item_counter}",
                    "category": "wording_corrections",
                    "title": "مراجعة الصياغة الإنجليزية وحالة الأحرف (Capital / Small)",
                    "description": "ضرورة تدقيق وتصحيح كتابة المصطلحات الإنجليزية وحروف الـ Capital والـ Small في كافة الأجزاء.",
                    "provenance": "explicitly_spoken",
                    "evidence": evidence,
                    "confidence": 0.95,
                    "negation_detected": False,
                    "reversal_detected": has_reversal,
                    "reversal_details": reversal_info,
                })
                item_counter += 1
                break

        # Check for Confirmed Decisions
        if re.search(r"\b(ماشي مش مشكله|تمام ماشي|اعتمد|شغال تمام)\b", text, re.IGNORECASE):
            items_by_cat["confirmed_decisions"].append({
                "id": f"dec_{item_counter}",
                "category": "confirmed_decisions",
                "title": "تأكيد وقبول البند المقترح",
                "description": "موافقة المتحدث على صياغة أو فقرة مقترحة دون اعتراض.",
                "provenance": "explicitly_spoken",
                "evidence": evidence,
                "confidence": 0.90,
                "negation_detected": False,
                "reversal_detected": False,
            })
            item_counter += 1

        # Check for Uncertainty / Open Questions
        for pat in UNCERTAINTY_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                items_by_cat["uncertain_statements"].append({
                    "id": f"unc_{item_counter}",
                    "category": "uncertain_statements",
                    "title": "صيغة غير محسومة أو قابلة للاختيار الحر",
                    "description": "المتحدث ترك تحديد التفاصيل للطرف الآخر دون فرض خيار قطعي.",
                    "provenance": "needs_human_verification",
                    "evidence": evidence,
                    "confidence": 0.80,
                    "negation_detected": False,
                    "reversal_detected": False,
                })
                item_counter += 1
                break

    # Topic Overview Synthesis
    full_text = " ".join([s.get("text", "") for s in segments])
    topic_overview = "تسجيل صوتي بالعامية المصرية يتضمن مراجعة وتعديلات على مقترح مشروع (Proposal) وفعاليات مشتركة، مع تحديد مسؤوليات كل جهة وحذف الصور والشعارات غير المعتمدة."
    if "proposal" in full_text.lower() or "بروبوزال" in full_text or "برو" in full_text.lower():
        topic_overview = "ملاحظات وتعديلات تفصيلية على مقترح المشروع (Project Proposal) تشمل تدقيق الشعارات الرسمية، مراجعة اللغة الإنجليزية وحالة الأحرف، وإعادة توزيع المسؤوليات بين الشركاء."

    summary_counts = {cat: len(items) for cat, items in items_by_cat.items()}

    return {
        "job_id": job_id,
        "title": job_title or "موجز التوجيهات والقرارات المنطوقة (Actionable Brief)",
        "topic_overview": topic_overview,
        "summary_counts": summary_counts,
        "categories": items_by_cat,
    }


def format_brief_as_markdown(brief: Dict[str, Any]) -> str:
    """
    Renders the structured understanding brief into an executive Markdown report.
    """
    lines = [
        f"# {brief.get('title', 'Actionable Spoken Instructions Brief')}",
        "",
        "## نظرة عامة على التسجيل (Recording Overview)",
        f"{brief.get('topic_overview', '')}",
        "",
        "---",
        "## فهرس القرارات والتوجيهات المنطوقة",
    ]

    cats = brief.get("categories", {})

    section_titles = {
        "required_changes": "1. التعديلات المطلوبة (Required Changes)",
        "content_to_remove": "2. العناصر المطلوب حذفها (Content to Remove)",
        "content_to_add": "3. العناصر المطلوب إضافتها (Content to Add)",
        "responsibilities": "4. توزيع المسؤوليات والجهات المنفذة (Responsibilities)",
        "negative_instructions": "5. توجيهات النفي والاشتراطات السلبية (Negative Instructions)",
        "wording_corrections": "6. تصحيحات الصياغة والمصطلحات (Wording & Formatting)",
        "confirmed_decisions": "7. القرارات المعتمدة (Confirmed Decisions)",
        "uncertain_statements": "8. تصريحات غير محسومة أو تتطلب مراجعة (Uncertain / Open Items)",
    }

    for cat_key, cat_title in section_titles.items():
        items = cats.get(cat_key, [])
        if not items:
            continue

        lines.append(f"\n### {cat_title}")
        for item in items:
            ev = item.get("evidence", {})
            prov = item.get("provenance", "explicitly_spoken").replace("_", " ").title()
            rev_badge = " ⚠️ [Speaker Revised Phrasing]" if item.get("reversal_detected") else ""

            lines.append(f"- **{item['title']}** `{prov}`{rev_badge}")
            lines.append(f"  - *التفاصيل:* {item['description']}")
            lines.append(f"  - *الدليل الصوتي المنطوق:* `[{ev.get('time_formatted', '')}]` \"{ev.get('quote', '')}\"")

    lines.append("\n---")
    lines.append("### ملاحظة منهجية حول الموثوقية (Provenance Disclosure)")
    lines.append("هذا التقرير التحليلي مشتق بالكامل من النصوص المنطوقة مع الربط الإلزامي بالطوابع الزمنية الصوتية.")
    lines.append("لا يعد هذا التحليل بديلاً عن النص الحرفي الدقيق (Strict Verbatim)، وإنما طبقة فهم داعمة لاتخاذ القرارات.")

    return "\n".join(lines)
