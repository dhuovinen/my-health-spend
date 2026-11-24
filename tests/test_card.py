"""The insurance card reader (ING-11, ADR-059) on synthetic cards: text in, fields with confidences out."""

from mhs.ingest.card import CHECK_BELOW, IDENTIFIER_FIELDS, read_card
from tests import cards


def people(r):
    return {p.name: p for p in r.people}


def test_example_card_front_and_back_tc1():
    r = read_card(cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    assert r.looks_like_card and r.kind == "medical" and r.has_back
    assert r.value("insurer") == "Example Health"
    assert r.value("plan_name") == "Choice Plus PPO"
    assert r.value("plan_type") == "PPO"
    assert r.value("group_number") == "0123456"
    assert r.value("member_number") == "XJK123456789"
    assert r.value("effective_date") == "2026-01-01"
    assert {k: f.value for k, f in r.copays.items()} == {
        "primary_care": 3000, "specialist": 6000, "urgent_care": 7500, "emergency": 35000}
    assert (r.value("rx_bin"), r.value("rx_pcn"), r.value("rx_group")) == ("610014", "MEDADV", "RX1234")
    assert r.value("payer_id") == "12345"
    by = people(r)
    assert set(by) == {"Pat Sample", "Jordan Sample", "Alex Sample"}
    assert by["Pat Sample"].subscriber and by["Pat Sample"].member_number.value == "XJK123456789"
    assert not by["Jordan Sample"].subscriber
    contacts = {c.label: c for c in r.contacts}
    assert contacts["Member services"].phone == "800-555-0100"
    assert contacts["Provider services"].phone == "800-555-0111"
    assert contacts["Pharmacy help"].phone == "800-555-0122"
    assert contacts["Nurse line"].phone == "800-555-0133"
    assert contacts["Claims address"].address == "Example Health, PO Box 1234, Springfield, IL 62701"
    assert contacts["Website"].url == "www.examplehealth.example"


def test_every_field_found_by_label_is_confident():
    r = read_card(cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    assert all(not f.check for k, f in r.fields.items() if k in ("group_number", "member_number", "effective_date"))
    assert r.fields["insurer"].confidence < 0.7 or r.fields["insurer"].value == "Example Health"


def test_unknown_insurer_is_a_position_guess_marked_check():
    r = read_card(cards.EXAMPLE_FRONT)
    assert r.fields["insurer"].confidence < 0.9  # not in the known list


def test_known_insurer_name_is_confident_and_canonical():
    r = read_card(cards.CIGNA_FRONT, cards.CIGNA_BACK)
    assert r.fields["insurer"].value == "Cigna" and r.fields["insurer"].confidence >= 0.9


def test_per_person_rows_hdhp_limits_and_address_below_label():
    r = read_card(cards.CIGNA_FRONT, cards.CIGNA_BACK)
    by = people(r)
    assert by["River Tester"].member_number.value == "U99887766-01"
    assert by["Morgan Tester"].member_number.value == "U99887766-02"
    assert r.value("group_number") == "3344556"
    assert r.value("plan_type") == "HDHP" and r.value("hsa_eligible_plan") is True
    assert r.value("effective_date") == "2026-01-01"
    limits = {(l["type"], l["level"]): l["amount"] for l in r.limits}
    assert limits == {("deductible", "individual"): 320000, ("deductible", "family"): 640000,
                      ("out_of_pocket_max", "individual"): 500000}
    assert r.value("coinsurance_pct") == 20
    assert r.copays["primary_care"].value == 0 and r.copays["specialist"].value == 4000
    assert r.value("rx_bin") == "003858" and r.value("rx_group") == "RXCIG1"
    contacts = {c.label: c for c in r.contacts}
    assert contacts["Member services"].phone == "800-555-0144"  # the label is on the line above the number
    assert contacts["Prior authorization"].phone == "800-555-0155"
    assert contacts["Claims address"].address == "Cigna Claims, PO Box 99000, Dallas, TX 75201"
    assert contacts["Appeals address"].address.endswith("Dallas, TX 75202")
    assert r.value("payer_id") == "62308"


def test_front_only_has_no_contacts_from_the_back_tc6():
    r = read_card(cards.EXAMPLE_FRONT)
    assert r.looks_like_card and not r.has_back
    assert not [c for c in r.contacts if c.label in ("Claims address", "Member services")]
    assert r.value("member_number") == "XJK123456789"


def test_dental_card_is_dental_tc12():
    r = read_card(cards.DENTAL_FRONT, cards.DENTAL_BACK)
    assert r.kind == "dental" and r.looks_like_card and not r.refusal
    assert r.value("coverage_kind") == "dental"
    assert r.value("group_number") == "778899" and r.value("member_number") == "DNT555123456"


def test_vision_card_is_refused_tc12():
    r = read_card(cards.VISION_FRONT, cards.VISION_BACK)
    assert r.kind == "vision" and not r.fields and "vision plan" in r.refusal


def test_a_non_card_is_not_read_tc8():
    r = read_card(cards.NOT_A_CARD)
    assert not r.looks_like_card and "doesn't look like an insurance card" in r.refusal
    assert read_card("").looks_like_card is False


def test_poor_ocr_marks_fields_check():
    good = read_card(cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    poor = read_card(cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK, ocr_confidence=0.6)
    assert not good.fields["group_number"].check and poor.fields["group_number"].confidence < CHECK_BELOW
    assert poor.copays["specialist"].check


def test_stranger_listed_as_a_dependent_is_read_as_a_name():
    assert "Casey Stranger" in people(read_card(cards.STRANGER_FRONT))


def test_ocr_noise_in_the_bin_is_repaired_and_short_ids_are_refused():
    r = read_card("Example Health\nMember ID: AB12\nGroup: 12\nRxBIN 6l00I4\nEff. Date: 01/01/2026 PPO")
    assert r.value("rx_bin") == "610014"  # l and I read as 1
    assert r.value("member_number") is None and r.value("group_number") is None


def test_identifier_fields_are_named_for_the_vault():
    assert set(IDENTIFIER_FIELDS) == {"group_number", "member_number", "rx_group"}


def test_scrubbed_card_keeps_the_insurers_public_contacts_and_tokenizes_the_rest_tc5():
    import re

    from mhs.ingest.scrub import Scrubber, scrub_card

    def tokenize(kind: str, value: str) -> str:
        return "tok_" + re.sub(r"[^a-z2-7]", "a", f"{kind}{value}".lower())[:26].ljust(26, "a")

    front, back, out = scrub_card(Scrubber(tokenize, ["Pat Sample", "Jordan Sample", "Alex Sample"]),
                                  cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    for private in ("XJK123456789", "0123456", "PAT SAMPLE", "JORDAN", "ALEX", "RX1234"):
        assert private not in front + back, private
    for public in ("1-800-555-0100", "800-555-0133", "PO Box 1234, Springfield, IL 62701", "Payer ID: 12345",
                   "www.examplehealth.example", "Example Health"):
        assert public in front + back, public
    assert out.tokens


def test_a_member_phone_number_on_a_card_is_still_scrubbed():
    import re

    from mhs.ingest.scrub import Scrubber, scrub_card

    front, _, _ = scrub_card(Scrubber(lambda k, v: "tok_" + "a" * 26, []),
                             cards.EXAMPLE_FRONT + "Member phone: 555-867-5309\n", "")
    assert "555-867-5309" not in front


def test_layout_rules_accuracy_on_the_synthetic_set_tc13():
    """Per-field accuracy of the rules on the synthetic cards, so a change that makes a field worse shows here."""
    truth = [
        (cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK, {"group_number": "0123456", "member_number": "XJK123456789",
                                                   "plan_type": "PPO", "effective_date": "2026-01-01",
                                                   "rx_bin": "610014", "payer_id": "12345"}),
        (cards.CIGNA_FRONT, cards.CIGNA_BACK, {"group_number": "3344556", "plan_type": "HDHP",
                                               "effective_date": "2026-01-01", "rx_bin": "003858",
                                               "payer_id": "62308", "insurer": "Cigna"}),
        (cards.DENTAL_FRONT, cards.DENTAL_BACK, {"group_number": "778899", "member_number": "DNT555123456",
                                                 "effective_date": "2026-01-01", "payer_id": "44556"}),
    ]
    total = right = 0
    for front, back, expected in truth:
        r = read_card(front, back)
        for key, value in expected.items():
            total += 1
            right += r.value(key) == value
    assert right == total, f"{right} of {total}"


def test_a_synthetic_card_photo_is_read_end_to_end():
    """Image -> Tesseract -> rules. Skips where Tesseract isn't installed (the compose tests runner has it)."""
    import shutil

    import pytest

    if not shutil.which("tesseract"):
        pytest.skip("tesseract isn't installed here")
    from mhs.ingest.ocr import TesseractOcr

    front, back = cards.card_images(cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    ocr = TesseractOcr()
    f, b = ocr.read(front, "image/png"), ocr.read(back, "image/png")
    r = read_card(f.text, b.text, min(f.confidence, b.confidence))
    assert r.value("group_number") == "0123456" and r.value("member_number") == "XJK123456789"
