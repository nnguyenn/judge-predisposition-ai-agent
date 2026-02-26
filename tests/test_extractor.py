from app.services.extractor import extract_case


def test_extract_basic_holding():
    text = """
    The Court concludes petitioner is detained pursuant to § 1226(a), not § 1225(b)(2)(A),
    and is eligible for a bond hearing. The habeas petition is granted.
    The Court's reasoning includes textual analysis, ordinary meaning, and statutory scheme.
    Jennings v. Rodriguez is discussed.
    """
    out = extract_case(text)
    assert out.holdings["applicable_provision"] == "1226"
    assert out.holdings["bond_status"] == "eligible"
    assert out.holdings["habeas_relief"] == "granted"
    assert out.reasoning_basis["textual_analysis"]["present"] is True
    assert out.reasoning_basis["structure_context"]["present"] is True