"""Scrubbing recall on synthetic text (PRV-04 TC-2/TC-3, ADR-029): a seed set of made-up people whose identifiers
are planted in letters, phone notes, EOB and statement headers, mostly without the household knowing the names.
Every planted identifier must be gone from the scrubbed text, and the amounts, dates, codes and the household's
providers must survive. No database; the people and numbers are invented."""

import itertools

import pytest

from mhs.ingest.extract import extract
from mhs.ingest.scrub import PresidioScrubber, Scrubber
from mhs.vault.store import new_token

PEOPLE = [
    ("Maria", "Gonzalez"), ("Jordan", "Rivera"), ("Robert", "Nakamura"), ("Aisha", "Okafor"), ("Ethan", "Kowalski"),
    ("Priya", "Raman"), ("Lucas", "Fitzgerald"), ("Hannah", "Berg"), ("Samuel", "Osei"), ("Grace", "Thornton"),
]
STREETS = ["Oak Lane", "Maple Avenue", "Birch Road", "Cedar Court", "Willow Drive"]
CITIES = [("Riverton", "OR", "97001"), ("Lakewood", "CO", "80214"), ("Fairview", "TN", "37062"),
          ("Georgetown", "TX", "78626"), ("Salem", "MA", "01970")]
PROVIDERS = ["Lakeside Family Medicine", "Summit Imaging Center"]


def person(i: int) -> dict:
    first, last = PEOPLE[i]
    city, state, zip_code = CITIES[i % len(CITIES)]
    return {
        "first": first, "last": last, "name": f"{first} {last}",
        "phone": f"(555) {310 + i:03d}-{4000 + 37 * i:04d}",
        "email": f"{first.lower()}.{last.lower()}@example.com",
        "ssn": f"{521 + i:03d}-{40 + i:02d}-{6100 + 13 * i:04d}",
        "street": f"{100 + 7 * i} {STREETS[i % len(STREETS)]}",
        "city": city, "zip": f"{state} {zip_code}",
        "member_id": f"XHP{880000 + 1111 * i}",
        "account": f"{700100 + 97 * i}",
        "dob": f"{(i % 12) + 1:02d}/{(i * 3) % 27 + 1:02d}/19{60 + i}",
    }


TEMPLATES = [
    # (text, the person's identifiers that appear in it)
    ("Dear {name},\nThank you for visiting Lakeside Family Medicine on 03/14/2026. Your balance is $45.00.\n"
     "Questions? Call us, or reach you at {phone} or {email}.", ["name", "phone", "email"]),
    ("Phone note 04/02/2026: spoke with {name} about claim C-2026-0042. Mailing address on file is\n"
     "{street}, {city}, {zip}. Patient asked to resend the itemized bill for 99213.", ["name", "street", "city", "zip"]),
    ("Summit Imaging Center\nEXPLANATION OF BENEFITS   THIS IS NOT A BILL\nSubscriber: {last}, {first}\n"
     "Member ID: {member_id}\nDate of birth: {dob}\nAmount billed: $320.00\nPlan paid: $155.00",
     ["last_first", "member_id", "dob"]),
    ("Statement date: 10/01/2026\nGuarantor: {name}\nAccount number: {account}\nSSN: {ssn}\n"
     "09/28/2026 11102 Skin biopsy $320.00 $0.00 $320.00\nAmount due: $320.00", ["name", "account", "ssn"]),
    ("Appeal letter. I, {name}, ask you to review claim C-2026-0077. My husband {spouse} was\n"
     "also seen that day. Send the decision to {email}; my number is {phone}.", ["name", "spouse", "email", "phone"]),
    ("Front desk log 05/06/2026\n{name} came in asking whether 99213 is covered; {spouse} will bring the card.",
     ["name", "spouse"]),
]
SURVIVORS = ["$45.00", "$320.00", "$155.00", "03/14/2026", "10/01/2026", "09/28/2026", "C-2026-0042", "99213",
             "11102", "Skin biopsy", "Lakeside Family Medicine", "Summit Imaging Center", "THIS IS NOT A BILL"]


def documents():
    """(text, planted values) for every person and template."""
    for i, (text, keys) in itertools.product(range(len(PEOPLE)), TEMPLATES):
        p = person(i)
        spouse = person((i + 1) % len(PEOPLE))["name"]
        values = {**p, "spouse": spouse, "last_first": f"{p['last']}, {p['first']}"}
        yield text.format(**values), [values[k] for k in keys]


def recall(scrubber_cls) -> tuple[float, list[str], list[str]]:
    missed, damaged, total = [], [], 0
    for text, planted in documents():
        s = scrubber_cls(lambda kind, value: new_token(), [], keep=PROVIDERS)
        out = s.scrub(text).text
        for value in planted:
            total += 1
            if value in out or any(part in out for part in value.split(", ") if len(part) > 3):
                missed.append(value)
        damaged += [v for v in SURVIVORS if v in text and v not in out]
    return 1 - len(missed) / total, missed, damaged


def test_tc_prv_04_3_presidio_recall_on_the_seed_set():
    """Proposed target: at least 99% of seeded identifiers (TC-PRV-04-3). Nothing else is touched."""
    pytest.importorskip("presidio_analyzer")
    rate, missed, damaged = recall(PresidioScrubber)
    assert rate >= 0.99, f"recall {rate:.1%}; missed {missed}"
    assert damaged == []


def test_presidio_finds_what_the_rules_miss():
    """The rules know only the household's members and labelled fields; strangers' names in letters need Presidio."""
    pytest.importorskip("presidio_analyzer")
    rules_rate, rules_missed, _ = recall(Scrubber)
    presidio_rate, _, _ = recall(PresidioScrubber)
    assert presidio_rate > rules_rate
    assert any(name in rules_missed for name in (person(i)["name"] for i in range(len(PEOPLE))))


def test_one_token_for_a_stranger_however_spelled():
    """PRV-03 for people Presidio finds: "Maria Gonzalez" and "Gonzalez, Maria" are one token."""
    pytest.importorskip("presidio_analyzer")
    tokens: dict = {}
    s = PresidioScrubber(lambda kind, value: tokens.setdefault((kind, value), new_token()), [])
    out = s.scrub("Dear Maria Gonzalez,\nwe wrote to Gonzalez, Maria on 03/14/2026 about $20.00.").text
    assert "Maria" not in out and "Gonzalez" not in out and "03/14/2026" in out and "$20.00" in out
    assert [k for k in tokens if k[0] == "name"] == [("name", "maria gonzalez")]


LETTERHEAD_STATEMENT = """Riverbend Orthopedics
455 River Road, Springfield
Statement date: 09/10/2026
Account number: 880142
Patient: Sample, Jordan
Phone: (555) 014-2290
Date        Code   Description                      Charges   Insurance   Adjustments   Payments   Balance
08/14/2026 99214 Office visit, established patient $260.00 $0.00 $0.00 $0.00 $260.00
Amount due: $260.00
"""


def test_a_bare_letterhead_survives_every_upload():
    """Presidio reads the original text, not text holding random tokens: with the address token right under it,
    the letterhead used to read as a person in about one upload in four, and the visit lost its provider. Thirty
    uploads would all have kept it about once in 13,000 runs."""
    pytest.importorskip("presidio_analyzer")
    for _ in range(30):
        s = PresidioScrubber(lambda kind, value: new_token(), [], keep=["Example Health"])
        out = s.scrub(LETTERHEAD_STATEMENT).text
        assert out.startswith("Riverbend Orthopedics\ntok_"), out
        assert extract(out).fields["provider"].value == "Riverbend Orthopedics"
        for value in ("455 River Road", "Springfield", "880142", "Sample", "Jordan", "014-2290"):
            assert value not in out, value


@pytest.mark.parametrize("letterhead", ["Kessler Orthopedics", "Bennett Radiology", "Greene Physical Therapy"])
def test_a_practice_named_after_a_person_is_kept(letterhead):
    """spaCy reads these as people even in the original text; a word like Radiology makes them a practice."""
    pytest.importorskip("presidio_analyzer")
    s = PresidioScrubber(lambda kind, value: new_token(), [])
    out = s.scrub(f"{letterhead}\nPO Box 1234\nRiverton, OR 97001\nDear Maria Gonzalez,\nAmount due: $40.00").text
    assert out.startswith(letterhead + "\n") and "Riverton" not in out and "Gonzalez" not in out
