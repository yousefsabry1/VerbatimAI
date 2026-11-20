"""
Integration tests for Evidence-Grounded Speech Understanding (Mode 2),
Egyptian Arabic negation handling, responsibility extraction, and actionable brief exports.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.understanding.instruction_extractor import (
    extract_instructions_from_segments,
    format_brief_as_markdown,
)
from app.core.database import (
    save_understanding_brief,
    get_understanding_brief,
    delete_understanding_brief,
)

client = TestClient(app)


def test_understanding_negation_and_removal_extraction():
    segments = [
        {
            "id": 1,
            "start": 0.0,
            "end": 15.0,
            "text": "احنا عايزين اللوجو بتاع الـ CIS دا حط اللوجو بتاع Egypt Section نفسه مش بتاع الشابتر الاساسي",
        },
        {
            "id": 2,
            "start": 15.0,
            "end": 30.0,
            "text": "طبعا صورة الجامعة دي احنا محتاجين نشيلها يعني هما ملهمش علاقة بصورة الجامعة باي حاجة",
        },
        {
            "id": 3,
            "start": 30.0,
            "end": 45.0,
            "text": "انت هنا قايل instructors مش عارف ايه ان cis هتبعت حد فلأ انت هنا محتاج توضح ان هي الناس بتوع الجامعة تمام",
        },
        {
            "id": 4,
            "start": 45.0,
            "end": 60.0,
            "text": "الـ capital والـ small والحاجات دي بس محتاجة تتراجع في الجزئية اللي تحت دي كلها",
        },
        {
            "id": 5,
            "start": 60.0,
            "end": 75.0,
            "text": "ADMINTATING TOUR ماشي مش مشكلة",
        },
    ]

    brief = extract_instructions_from_segments("test_job_understand_1", segments)

    assert brief["job_id"] == "test_job_understand_1"
    cats = brief["categories"]

    # 1. Verify removal extraction
    removals = cats["content_to_remove"]
    assert len(removals) >= 1
    assert any("صورة" in item["title"] for item in removals)
    assert removals[0]["provenance"] == "explicitly_spoken"
    assert removals[0]["evidence"]["segment_id"] == 2
    assert removals[0]["evidence"]["time_formatted"] == "00:15 - 00:30"

    # 2. Verify negative instructions
    negations = cats["negative_instructions"]
    assert len(negations) >= 1
    assert any("مش" in item["description"] or "الشابتر" in item["title"] for item in negations)

    # 3. Verify responsibility assignment
    responsibilities = cats["responsibilities"]
    assert len(responsibilities) >= 1
    assert any("الجامعة" in item["title"] or "جامعه" in item["title"] for item in responsibilities)

    # 4. Verify wording corrections
    wording = cats["wording_corrections"]
    assert len(wording) >= 1
    assert any("capital" in item["title"].lower() for item in wording)

    # 5. Verify reversal detection on mid-sentence self-correction
    # Segment 3 has "مش عارف ايه فلأ انت هنا محتاج"
    rev_items = [item for item in cats["responsibilities"] if item.get("reversal_detected")]
    assert len(rev_items) >= 1
    assert rev_items[0]["reversal_details"] is not None


def test_understanding_database_crud():
    job_id = "test_crud_understand_999"
    test_data = {
        "job_id": job_id,
        "title": "موجز اختباري",
        "topic_overview": "نظرة عامة اختبارية للمشروع",
        "categories": {
            "required_changes": [
                {
                    "id": "chg_1",
                    "title": "تعديل الشعار",
                    "description": "استخدام شعار Egypt Section",
                    "provenance": "explicitly_spoken",
                    "evidence": {
                        "segment_id": 1,
                        "start": 0.0,
                        "end": 10.0,
                        "time_formatted": "00:00 - 00:10",
                        "quote": "حط اللوجو بتاع Egypt Section",
                    },
                }
            ]
        },
    }

    # Save
    res_id = save_understanding_brief(job_id, test_data["title"], test_data["topic_overview"], test_data)
    assert res_id == job_id

    # Retrieve
    retrieved = get_understanding_brief(job_id)
    assert retrieved is not None
    assert retrieved["title"] == "موجز اختباري"
    assert len(retrieved["brief"]["categories"]["required_changes"]) == 1

    # Cleanup
    deleted = delete_understanding_brief(job_id)
    assert deleted is True
    assert get_understanding_brief(job_id) is None


def test_understanding_api_endpoints():
    # Use real job in DB
    job_id = "818483f608"

    # Generate
    gen_res = client.post(f"/api/understanding/{job_id}/generate", json={"prefer_human_corrected": True})
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["status"] == "success"
    assert "brief" in gen_data
    assert "categories" in gen_data["brief"]

    # Get
    get_res = client.get(f"/api/understanding/{job_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["status"] == "success"
    assert get_data["title"] == gen_data["brief"]["title"]

    # Export Markdown
    md_res = client.get(f"/api/understanding/{job_id}/export/markdown")
    assert md_res.status_code == 200
    assert md_res.headers["content-disposition"].startswith("attachment")
    assert "Actionable" in md_res.text or "موجز" in md_res.text or "التوجيهات" in md_res.text

    # Export JSON
    json_res = client.get(f"/api/understanding/{job_id}/export/json")
    assert json_res.status_code == 200
    assert json_res.json()["job_id"] == job_id


def test_markdown_formatter_grounding():
    test_brief = {
        "title": "موجز قرارات تجريبي",
        "topic_overview": "ملخص عام للتسجيل",
        "categories": {
            "required_changes": [
                {
                    "title": "تعديل الشعار",
                    "description": "استخدام الشعار الرسمي",
                    "provenance": "explicitly_spoken",
                    "reversal_detected": True,
                    "evidence": {
                        "time_formatted": "01:10 - 01:25",
                        "quote": "حط اللوجو بتاع Egypt Section",
                    },
                }
            ],
            "content_to_remove": [
                {
                    "title": "حذف صورة الجامعة",
                    "description": "إزالة الصورة لعدم الصلة",
                    "provenance": "explicitly_spoken",
                    "reversal_detected": False,
                    "evidence": {
                        "time_formatted": "01:30 - 01:45",
                        "quote": "صورة الجامعة دي نشيلها",
                    },
                }
            ],
        },
    }

    md = format_brief_as_markdown(test_brief)
    assert "# موجز قرارات تجريبي" in md
    assert "[01:10 - 01:25]" in md
    assert "[01:30 - 01:45]" in md
    assert "حط اللوجو بتاع Egypt Section" in md
    assert "صورة الجامعة دي نشيلها" in md
    assert "Speaker Revised Phrasing" in md
