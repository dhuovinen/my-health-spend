"""QR codes as inline SVG for authenticator enrolment (pure Python, segno). The SVG carries no style attribute
and no script, so it renders under the app's Content Security Policy (PRV-08)."""

import segno


def qr_svg(data: str) -> str:
    """An SVG QR code for `data` that scales to its container (a viewBox, no fixed size), black on white."""
    return segno.make(data, error="m").svg_inline(scale=1, border=4, dark="#000", light="#fff", omitsize=True,
                                                  svgclass="qr", lineclass=None, title="QR code")
