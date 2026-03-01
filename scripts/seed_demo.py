from datetime import date

from app.db import SessionLocal, Base, engine
from app.models import CaseRecord


DEMO_CASES = [
    {
        "source": "demo",
        "source_case_id": "demo-1",
        "case_caption": "Doe v. Noem",
        "court": "W.D. Pa.",
        "district_court": "W.D. Pa.",
        "judge_name": "Judge Alpha",
        "decision_date": date(2026, 2, 15),
        "opinion_url": "https://example.local/demo-1",
        "opinion_text": """
        Petitioner seeks habeas relief and a bond hearing. The Court concludes petitioner is detained pursuant to § 1226(a),
        not § 1225(b)(2)(A), and is eligible for a bond hearing. The petition is granted in part.
        The Court relies on ordinary meaning, statutory scheme, and Jennings v. Rodriguez.
        Petitioner has an asylum application pending and is already within the United States.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-2",
        "case_caption": "Roe v. Noem",
        "court": "S.D. Tex.",
        "district_court": "S.D. Tex.",
        "judge_name": "Judge Beta",
        "decision_date": date(2026, 2, 10),
        "opinion_url": "https://example.local/demo-2",
        "opinion_text": """
        This habeas petition is denied. The Court holds detention is governed by § 1225 and petitioner is not eligible for a bond hearing.
        The Court notes mandatory detention for arriving aliens near the border and discusses statutory purpose and precedent.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-3",
        "case_caption": "Smith v. Noem",
        "court": "E.D.N.Y.",
        "district_court": "E.D.N.Y.",
        "judge_name": "Judge Alpha",
        "decision_date": date(2026, 2, 20),
        "opinion_url": "https://example.local/demo-3",
        "opinion_text": """
        The habeas petition is granted. The Court finds petitioner detained pursuant to § 1226(a).
        Petitioner is entitled to a bond hearing. The Court discusses textual analysis, historical practice,
        and the statutory scheme. Petitioner entered without inspection years ago and was later detained in the interior.
        """,
    },
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        inserted = 0
        for item in DEMO_CASES:
            exists = db.query(CaseRecord).filter_by(source=item["source"], source_case_id=item["source_case_id"]).one_or_none()
            if exists:
                continue
            db.add(CaseRecord(**item))
            inserted += 1

        db.commit()
        print(f"Inserted {inserted} demo cases.")
    finally:
        db.close()


if __name__ == "__main__":
    main()