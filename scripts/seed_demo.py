from datetime import date

from app.db import SessionLocal, Base, engine
from app.models import CaseRecord


DEMO_CASES = [
    {
        "source": "demo",
        "source_case_id": "demo-001",
        "case_caption": "Doe v. Noem",
        "court": "W.D. Pa.",
        "district_court": "W.D. Pa.",
        "judge_name": "Judge Alpha",
        "judge_role": "district",
        "decision_date": date(2026, 1, 8),
        "opinion_url": "https://example.local/demo-001",
        "opinion_text": """
        Petitioner, through counsel, seeks habeas relief and a bond hearing after prolonged immigration detention.
        The Court concludes petitioner is detained pursuant to § 1226(a), not § 1225(b)(2)(A),
        and is eligible for a bond hearing. The petition is granted in part.
        The Court relies on ordinary meaning, dictionary usage, statutory scheme, Jennings v. Rodriguez,
        historical practice, and consistent practice. Petitioner has an asylum application pending
        and is once inside the United States after living in the interior for years.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-002",
        "case_caption": "Smith v. Noem",
        "court": "E.D.N.Y.",
        "district_court": "E.D.N.Y.",
        "judge_name": "Judge Alpha",
        "judge_role": "district",
        "decision_date": date(2026, 1, 15),
        "opinion_url": "https://example.local/demo-002",
        "opinion_text": """
        Petitioner filed this habeas petition pro se. The habeas petition is granted.
        The Court finds petitioner detained pursuant to § 1226(a)
        and entitled to a bond hearing. The Court discusses ordinary meaning, statutory scheme,
        historical practice, longstanding practice, and Jennings v. Rodriguez.
        Petitioner entered without inspection years ago and was later detained in the interior,
        once inside the United States, while pursuing asylum relief.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-003",
        "case_caption": "Garcia v. Noem",
        "court": "D.N.J.",
        "district_court": "D.N.J.",
        "judge_name": "Judge Alpha",
        "judge_role": "district",
        "decision_date": date(2026, 1, 28),
        "opinion_url": "https://example.local/demo-003",
        "opinion_text": """
        Counsel for petitioner seeks habeas relief. The petition for writ of habeas corpus is granted.
        The Court concludes detention is governed by § 1226(a).
        Petitioner is eligible for a bond hearing and habeas relief is granted.
        The Court relies on ordinary meaning, dictionary analysis, statutory scheme, historical practice,
        consistent practice, and Jennings. The petitioner has an asylum application pending and is already
        within the country after years in the interior.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-004",
        "case_caption": "Lopez v. Noem",
        "court": "D. Md.",
        "district_court": "D. Md.",
        "judge_name": "Judge Alpha",
        "judge_role": "district",
        "decision_date": date(2026, 2, 6),
        "opinion_url": "https://example.local/demo-004",
        "opinion_text": """
        Petitioner appears pro se and seeks habeas relief. The habeas petition is granted in part and denied in part.
        The Court holds petitioner is detained under § 1226(a) and must receive a bond hearing,
        although other requested relief is denied.
        The Court's textual analysis relies on ordinary meaning, superfluous, statutory scheme,
        historical practice, and Jennings v. Rodriguez. Petitioner is once inside the United States,
        has lived in the interior, and seeks asylum.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-005",
        "case_caption": "Roe v. Noem",
        "court": "S.D. Tex.",
        "district_court": "S.D. Tex.",
        "judge_name": "Judge Beta",
        "judge_role": "district",
        "decision_date": date(2026, 1, 10),
        "opinion_url": "https://example.local/demo-005",
        "opinion_text": """
        Petitioner, through counsel, seeks habeas relief. This habeas petition is denied.
        The Court holds detention is governed by § 1225(b)(2)(A)
        and petitioner is not eligible for a bond hearing.
        The Court notes mandatory detention for an arriving alien near the border and at the border,
        discusses statutory purpose, deter, applicants for admission, and Jennings v. Rodriguez.
        Petitioner presented at a port of entry near the southern border.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-006",
        "case_caption": "Ahmed v. Noem",
        "court": "S.D. Tex.",
        "district_court": "S.D. Tex.",
        "judge_name": "Judge Beta",
        "judge_role": "district",
        "decision_date": date(2026, 1, 21),
        "opinion_url": "https://example.local/demo-006",
        "opinion_text": """
        Petitioner filed this habeas petition pro se. The habeas petition is denied.
        The Court concludes petitioner is detained pursuant to § 1225(b)(2)(A)
        and is not eligible for a bond hearing because mandatory detention applies.
        The Court emphasizes arriving alien status, applicants for admission, statutory purpose,
        deterrent concerns, and the statutory scheme. Petitioner was apprehended near the border
        after arriving in the United States through a port of entry at the southern border.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-007",
        "case_caption": "Khan v. Noem",
        "court": "W.D. Tex.",
        "district_court": "W.D. Tex.",
        "judge_name": "Judge Beta",
        "judge_role": "district",
        "decision_date": date(2026, 2, 2),
        "opinion_url": "https://example.local/demo-007",
        "opinion_text": """
        Petitioner, through counsel, seeks habeas relief. Petition for writ of habeas corpus is denied.
        The Court holds detention is governed by § 1225
        and petitioner is ineligible for a bond hearing.
        The Court relies on applicants for admission, arriving alien, statutory purpose, absurdity concerns,
        equal footing, and Congress's purpose to deter unlawful entry. The petitioner was stopped
        near the border after arriving in the United States and processed at a port of entry.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-008",
        "case_caption": "Diaz v. Noem",
        "court": "S.D. Cal.",
        "district_court": "S.D. Cal.",
        "judge_name": "Judge Beta",
        "judge_role": "district",
        "decision_date": date(2026, 2, 14),
        "opinion_url": "https://example.local/demo-008",
        "opinion_text": """
        Petitioner appears pro se. The Court denies the habeas petition.
        Detention is governed by § 1225(b)(2)(A),
        and no bond hearing is available because mandatory detention applies.
        The Court discusses arriving alien status, applicants for admission, statutory scheme,
        Congress's purpose, deter, and precedent including Jennings.
        Petitioner was encountered at the border near the southern border and processed at a port of entry.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-009",
        "case_caption": "Singh v. Noem",
        "court": "D. Mass.",
        "district_court": "D. Mass.",
        "judge_name": "Judge Gamma",
        "judge_role": "district",
        "decision_date": date(2026, 1, 12),
        "opinion_url": "https://example.local/demo-009",
        "opinion_text": """
        Petitioner, through counsel, seeks habeas relief. The habeas petition is granted.
        The Court finds petitioner detained pursuant to § 1226(a)
        and entitled for a bond hearing. Due to prolonged detention, habeas relief is granted.
        The Court relies on ordinary meaning, statutory scheme, historical practice,
        longstanding practice, and Jennings v. Rodriguez. Petitioner has an asylum claim
        and was arrested in the interior once inside the United States.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-010",
        "case_caption": "Patel v. Noem",
        "court": "N.D. Ga.",
        "district_court": "N.D. Ga.",
        "judge_name": "Judge Gamma",
        "judge_role": "district",
        "decision_date": date(2026, 1, 26),
        "opinion_url": "https://example.local/demo-010",
        "opinion_text": """
        Petitioner filed this habeas petition pro se. The habeas petition is denied.
        The Court concludes detention is governed by § 1225
        and petitioner is not eligible for a bond hearing.
        The Court discusses arriving alien status, statutory purpose, deterrent concerns,
        applicants for admission, and Jennings. The petitioner was processed at a port of entry
        near the border after arriving in the United States.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-011",
        "case_caption": "Mendoza v. Noem",
        "court": "D. Conn.",
        "district_court": "D. Conn.",
        "judge_name": "Judge Gamma",
        "judge_role": "district",
        "decision_date": date(2026, 2, 9),
        "opinion_url": "https://example.local/demo-011",
        "opinion_text": """
        Counsel for petitioner argues detention is governed by § 1226(a). The petition is granted in part and denied in part.
        The Court holds petitioner is detained under § 1226(a) and shall receive a bond hearing.
        The Court relies on ordinary meaning, superfluous, statutory scheme, historical practice,
        and Jennings v. Rodriguez. Petitioner has lived in the interior for years and is once inside
        the United States while seeking asylum.
        """,
    },
    {
        "source": "demo",
        "source_case_id": "demo-012",
        "case_caption": "Ruiz v. Noem",
        "court": "M.D. Fla.",
        "district_court": "M.D. Fla.",
        "judge_name": "Judge Gamma",
        "judge_role": "district",
        "decision_date": date(2026, 2, 18),
        "opinion_url": "https://example.local/demo-012",
        "opinion_text": """
        Petitioner appears pro se. The Court denies the habeas petition.
        The Court concludes petitioner remains detained
        pursuant to § 1225(b)(2)(A) and no bond hearing is available.
        The Court discusses arriving alien status, applicants for admission, statutory purpose,
        Congress's purpose, and deterrent concerns. Petitioner was encountered at the border
        and near the border after arriving in the United States through a port of entry.
        """,
    },
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing_demo_cases = db.query(CaseRecord).filter(CaseRecord.source == "demo").all()
        deleted = len(existing_demo_cases)
        for case in existing_demo_cases:
            db.delete(case)
        db.flush()

        for item in DEMO_CASES:
            db.add(CaseRecord(**item))

        db.commit()
        print(
            f"Replaced demo dataset. Deleted {deleted} old demo cases and inserted {len(DEMO_CASES)} new demo cases."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()