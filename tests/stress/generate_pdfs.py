#!/usr/bin/env python3
"""Genera PDFs válidos de prueba de estrés sin dependencias externas."""
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "pdfs")

def make_pdf(filename, num_pages, text_per_page_kb):
    """Crea un PDF válido con ``num_pages`` páginas y texto repetitivo."""
    # Construir objetos de página
    pages_objs = []
    content_streams = []
    page_refs = []

    obj_num = 4  # empezamos en 4 (1=catalog, 2=pages, 3=resources, 4+=contenidos/paginas)

    for i in range(num_pages):
        # Texto repetitivo para rellenar espacio
        block = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        text = block * text_per_page_kb
        # Escapar paréntesis y backslashes para PDF
        text_escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        # Content stream de la página
        content = f"BT /F1 12 Tf 50 700 Td ({text_escaped}) Tj ET"
        content_bytes = content.encode("latin-1")
        content_streams.append(content_bytes)
        page_refs.append(obj_num)
        obj_num += 1

        # Contenido de la página (stream)
        pages_objs.append(
            f"{obj_num} 0 obj\n"
            f"<< /Length {len(content_bytes)} >>\n"
            f"stream\n{content_bytes.decode('latin-1')}\nendstream\nendobj\n"
        )
        obj_num += 1

        # Objeto página
        pages_objs.append(
            f"{obj_num} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {obj_num-1} 0 R >>\n"
            f"endobj\n"
        )
        obj_num += 1

    # Construir xref
    xref_offsets = []
    output_parts = []

    output_parts.append("%PDF-1.4\n")

    # Obj 1: Catalog
    xref_offsets.append(len("".join(output_parts).encode("latin-1")))
    output_parts.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Obj 2: Pages
    xref_offsets.append(len("".join(output_parts).encode("latin-1")))
    kids = " ".join(f"{r} 0 R" for r in page_refs)
    output_parts.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>\nendobj\n")

    # Obj 3: Resources (fuente dummy)
    xref_offsets.append(len("".join(output_parts).encode("latin-1")))
    output_parts.append("3 0 obj\n<< /ProcSet [/PDF /Text] /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>\nendobj\n")

    # Objetos de páginas y streams
    for part in pages_objs:
        xref_offsets.append(len("".join(output_parts).encode("latin-1")))
        output_parts.append(part)

    # Xref
    xref_pos = len("".join(output_parts).encode("latin-1"))
    output_parts.append("xref\n")
    output_parts.append(f"0 {obj_num}\n")
    output_parts.append("0000000000 65535 f \n")
    for offset in xref_offsets:
        output_parts.append(f"{offset:010d} 00000 n \n")

    # Trailer
    output_parts.append("trailer\n")
    output_parts.append(f"<< /Size {obj_num} /Root 1 0 R >>\n")
    output_parts.append(f"startxref\n{xref_pos}\n%%EOF\n")

    pdf_data = "".join(output_parts).encode("latin-1")
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_data)

    size_mb = len(pdf_data) / (1024 * 1024)
    print(f"Generado: {filepath} ({size_mb:.2f} MB)")


os.makedirs(OUTPUT_DIR, exist_ok=True)

# ~1 MB, ~3 MB, ~6 MB, ~9 MB
make_pdf("stress_1mb.pdf", 5, 3800)
make_pdf("stress_3mb.pdf", 10, 7500)
make_pdf("stress_6mb.pdf", 20, 7500)
make_pdf("stress_9mb.pdf", 30, 7500)

print("\nTodos los PDFs generados.")