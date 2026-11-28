"""Synthetic insurance cards for tests (ING-11): made-up insurers, people and numbers, never a real card.

Each card is the text of its front and back as OCR would return it. `card_images` renders a side as a PNG
through `make_image`, for the OCR tests that run where Tesseract is installed.
"""

from tests.pdfs import make_image

# A new insurer the known-name list doesn't have; medical with pharmacy, a subscriber, two dependents.
EXAMPLE_FRONT = """
Example Health
Choice Plus PPO
Member: PAT SAMPLE   Member ID: XJK123456789
Subscriber: PAT SAMPLE   Group: 0123456
Dependents: JORDAN SAMPLE, ALEX SAMPLE
Eff. Date: 01/01/2026
PCP $30   Specialist $60   Urgent Care $75   ER $350
RxBIN 610014   RxPCN MEDADV   RxGrp RX1234
"""
EXAMPLE_BACK = """
Member Services: 1-800-555-0100
Provider Services: 1-800-555-0111
Pharmacy Help Desk: (800) 555-0122
24/7 Nurse Line: 800-555-0133
Claims: Example Health, PO Box 1234, Springfield, IL 62701
Payer ID: 12345
www.examplehealth.example
"""

# A known insurer name, an HDHP with limits printed, the members listed one per row with their own IDs.
CIGNA_FRONT = """
Cigna Healthcare
Open Access Plus HDHP
Name              ID Number
RIVER TESTER      U99887766-01
MORGAN TESTER     U99887766-02
Group Number: 3344556
Effective: Jan 1, 2026
Deductible Individual $3,200   Family $6,400
Out-of-Pocket Max Individual $5,000
Coinsurance 20%
PCP $0   Specialist $40
RxBIN 003858   RxPCN A4   RxGroup RXCIG1
"""
CIGNA_BACK = """
Customer Service
1-800-555-0144
Prior Authorization 1-800-555-0155
Submit claims to:
Cigna Claims
PO Box 99000
Dallas, TX 75201
Appeals: 100 Appeals Way, Dallas, TX 75202
Payer ID: 62308
Network: Open Access Plus
"""

# Next year's card for the Example plan: a new year, changed copays.
EXAMPLE_FRONT_2027 = EXAMPLE_FRONT.replace("01/01/2026", "01/01/2027").replace("PCP $30", "PCP $35")

DENTAL_FRONT = """
Sample Dental Plan
Dental PPO
Subscriber: PAT SAMPLE   Member ID: DNT555123456
Group: 778899
Eff. Date: 01/01/2026
"""
DENTAL_BACK = """
Customer Service: 1-800-555-0166
Claims: Sample Dental, PO Box 777, Madison, WI 53703
Payer ID: 44556
"""

VISION_FRONT = """
Sample Vision Care
Vision Plan
Member: PAT SAMPLE   Member ID: VIS123456789
Group: 998877
"""
VISION_BACK = "Customer Service: 1-800-555-0177"

# A person who is not in the household, on a card for a household member.
STRANGER_FRONT = EXAMPLE_FRONT.replace("JORDAN SAMPLE, ALEX SAMPLE", "JORDAN SAMPLE, CASEY STRANGER")

NOT_A_CARD = """
Grocery receipt
Bananas 1.29
Milk 3.49
Total 4.78
Thank you for shopping
"""


def card_images(front: str, back: str = "") -> tuple[bytes, bytes | None]:
    return make_image(front), (make_image(back) if back else None)
