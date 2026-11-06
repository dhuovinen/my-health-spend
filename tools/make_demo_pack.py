"""Write the synthetic demo pack in samples/demo/ (docs/DEMO.md): one story told by four documents.

Jordan Sample saw Riverbend Orthopedics on 2026-08-14. The statement arrived first and asked for the full
$480.00 charge; Jordan paid it with the HSA card. The insurer's EOB then said the network discount was $180.00
and Jordan owed $300.00 (all deductible): the bill ignored the discount, and $180.00 was overpaid. A second EOB,
photographed with a phone, shows an $800.00 MRI at Lakeside Imaging that hasn't been billed yet.

Every name, number and address is made up. Usage (rewrites the files; the pack is committed):

    uv run tools/make_demo_pack.py [--out samples/demo]
"""

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.pdfs import make_pdf, render_text  # noqa: E402

# The heading under the letterhead matters: with the address token right below it, Presidio sometimes reads a
# bare provider name as a person and the letterhead is lost (about 1 upload in 4 for this layout).
STATEMENT = """Riverbend Orthopedics
PATIENT STATEMENT
455 River Road, Springfield
Statement date: 09/10/2026
Account number: 880142
Patient: Sample, Jordan
Phone: (555) 014-2290
Due date: 10/05/2026
Date        Code   Description                      Charges   Insurance   Adjustments   Payments   Balance
08/14/2026 99214 Office visit, established patient $260.00 $0.00 $0.00 $0.00 $260.00
08/14/2026 73562 X-ray, knee, 3 views $220.00 $0.00 $0.00 $0.00 $220.00
Total charges: $480.00
Insurance payments: $0.00
Amount due: $480.00
Make checks payable to Riverbend Orthopedics. We also accept HSA and FSA cards.
"""

EOB = """Example Health
EXPLANATION OF BENEFITS          THIS IS NOT A BILL
Patient: Jordan Sample     Member ID: W987-654-321
Provider: Riverbend Orthopedics
Claim number: C-2026-0814
Date of service: 08/14/2026
Date processed: 09/24/2026
Amount billed: $480.00
Plan discount: $180.00
Allowed amount: $300.00
Plan paid: $0.00
Deductible: $300.00
Your responsibility: $300.00
In-network
Date        Code   Service       Billed   Allowed   Plan paid   You owe
08/14/2026 99214 Office visit $260.00 $160.00 $0.00 $160.00
08/14/2026 73562 X-ray, knee $220.00 $140.00 $0.00 $140.00
The provider may not bill you more than Your responsibility for in-network services.
"""

PHOTO_EOB = """Example Health
EXPLANATION OF BENEFITS
THIS IS NOT A BILL
Patient: Jordan Sample
Member ID: W987-654-321
Provider: Lakeside Imaging
Claim number: C-2026-0922
Date of service: 09/22/2026
Date processed: 10/02/2026
Amount billed: $1,850.00
Plan discount: $1,050.00
Allowed amount: $800.00
Plan paid: $0.00
Deductible: $800.00
Your responsibility: $800.00
In-network
09/22/2026 73721 MRI knee $1,850.00 $800.00 $0.00 $800.00
"""

HSA_CSV = """Date,Description,Amount,Balance
10/01/2026,Employee Contribution,250.00,1770.00
09/15/2026,"RIVERBEND ORTHOPEDICS, SPRINGFIELD (Card Transaction ID: 7301)",-480.00,1520.00
09/01/2026,Employee Contribution,250.00,2000.00
08/01/2026,Employee Contribution,250.00,1750.00
07/31/2026,Balance Forward,0.00,1500.00
"""

FILES = {
    "1-riverbend-statement.pdf": lambda: make_pdf(STATEMENT),
    "2-riverbend-eob.pdf": lambda: make_pdf(EOB),
    "3-lakeside-eob-photo.png": lambda: phone_photo(PHOTO_EOB),
    "4-hsa-transactions.csv": lambda: HSA_CSV.encode(),
}


def phone_photo(text: str) -> bytes:
    """The page on a darker desk, slightly turned and soft, the way a phone photo of a letter looks."""
    from PIL import Image, ImageFilter

    page = render_text(text).convert("L").point(lambda v: 238 if v > 200 else v)  # off-white paper
    page = page.rotate(1.2, expand=True, fillcolor=96, resample=Image.Resampling.BICUBIC)
    desk = Image.new("L", (page.width + 120, page.height + 160), 96)
    desk.paste(page, (60, 80))
    buf = io.BytesIO()
    desk.filter(ImageFilter.GaussianBlur(0.6)).convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def write_pack(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, make in FILES.items():
        (out / name).write_bytes(make())
        written.append(out / name)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "samples" / "demo")
    for path in write_pack(parser.parse_args().out):
        print(f"wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
