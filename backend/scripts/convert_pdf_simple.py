#!/usr/bin/env python3
"""
Script simple para convertir PDFs a markdown usando PyMuPDF (más ligero que Docling)
"""

import sys
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF no instalado. Instala con: pip install pymupdf")
    sys.exit(1)

def pdf_to_markdown(pdf_path: str, output_path: str = None) -> str:
    """Convierte PDF a markdown usando PyMuPDF"""
    
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {pdf_path}")
    
    if output_path is None:
        output_path = pdf_path.with_suffix('.md')
    else:
        output_path = Path(output_path)
    
    print(f"📄 Procesando: {pdf_path.name}")
    
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    markdown_content = []
    
    for page_num in range(page_count):
        page = doc[page_num]
        text = page.get_text()
        
        if text.strip():
            # Agregar separador de página
            markdown_content.append(f"\n\n--- Página {page_num + 1} ---\n\n")
            markdown_content.append(text)
    
    doc.close()
    
    # Guardar markdown
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(''.join(markdown_content))
    
    print(f"✅ Convertido exitosamente")
    print(f"   Salida: {output_path}")
    print(f"   Páginas: {page_count}")
    
    return str(output_path)

def main():
    parser = argparse.ArgumentParser(description="Conversor simple de PDF a Markdown")
    parser.add_argument("pdf_path", help="Ruta al archivo PDF")
    parser.add_argument("--output", "-o", help="Ruta de salida (opcional)")
    
    args = parser.parse_args()
    
    try:
        pdf_to_markdown(args.pdf_path, args.output)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
