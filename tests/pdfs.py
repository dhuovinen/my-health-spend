"""Minimal real PDFs with a text layer, for synthetic test documents (one string per page, one line per row)."""


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(*pages: str) -> bytes:
    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    catalog = add("")  # filled in below
    pages_obj = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids = []
    for text in pages:
        rows = text.strip("\n").splitlines()
        ops = ["BT", "/F1 10 Tf", "12 TL", "40 760 Td"]
        for row in rows:
            ops.append(f"({_escape(row)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
                        f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"))
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    objects[pages_obj - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
                              f"/Count {len(kids)} >>").encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def render_text(text: str, size: int = 28, margin: int = 60):
    """A white page with black text, like a phone photo or a scan of a printed document."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=size)
    rows = text.strip("\n").splitlines()
    width = max(int(font.getlength(r)) for r in rows) + 2 * margin
    image = Image.new("RGB", (width, len(rows) * int(size * 1.6) + 2 * margin), "white")
    draw = ImageDraw.Draw(image)
    for i, row in enumerate(rows):
        draw.text((margin, margin + i * int(size * 1.6)), row, fill="black", font=font)
    return image


def make_image(text: str, fmt: str = "PNG") -> bytes:
    """A synthetic photo of `text` as PNG, JPEG or HEIC bytes."""
    import io

    if fmt == "HEIC":
        import pillow_heif

        pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    render_text(text).save(buf, "HEIF" if fmt == "HEIC" else fmt, **({"quality": 90} if fmt != "PNG" else {}))
    return buf.getvalue()


def make_scanned_pdf(*pages: str) -> bytes:
    """A PDF of page images with no text layer, like a scanner makes."""
    import io

    images = [render_text(p) for p in pages]
    buf = io.BytesIO()
    images[0].save(buf, "PDF", resolution=150, save_all=True, append_images=images[1:])
    return buf.getvalue()
