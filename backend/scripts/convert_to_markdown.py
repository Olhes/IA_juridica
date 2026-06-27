#!/usr/bin/env python3
"""
Script para convertir PDFs a markdown con Docling (sin embeddings ni RAG)
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Agregar el directorio backend al path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from ingestion.docling_processor import LegalPDFProcessor

async def convert_single_file(pdf_path: str, output_dir: str = None) -> dict:
    """Convierte un solo PDF a markdown"""
    
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {pdf_path}")
    
    if not pdf_path.suffix.lower() == '.pdf':
        raise ValueError(f"El archivo debe ser un PDF: {pdf_path}")
    
    # Configurar directorio de salida
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = pdf_path.parent
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📄 Procesando: {pdf_path.name}")
    
    processor = LegalPDFProcessor(output_dir=str(output_dir))
    
    try:
        markdown_content = await processor.process_pdf(str(pdf_path))
        
        output_file = output_dir / f"{pdf_path.stem}.md"
        
        print(f"✅ Convertido exitosamente")
        print(f"   Salida: {output_file}")
        print(f"   Longitud: {len(markdown_content)} caracteres")
        
        return {
            "filename": pdf_path.name,
            "output_path": str(output_file),
            "content_length": len(markdown_content),
            "status": "success"
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise

async def convert_directory(directory: str, output_dir: str = None) -> dict:
    """Convierte todos los PDFs en un directorio"""
    
    directory = Path(directory)
    
    if not directory.exists():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")
    
    # Configurar directorio de salida
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = directory / "markdown_output"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Encontrar todos los PDFs
    pdf_files = list(directory.rglob("*.pdf"))
    
    if not pdf_files:
        print(f"❌ No se encontraron PDFs en {directory}")
        return {"processed_count": 0, "failed_count": 0}
    
    print(f"📂 Encontrados {len(pdf_files)} PDFs en {directory}")
    print()
    
    processed_count = 0
    failed_count = 0
    
    for pdf_file in pdf_files:
        try:
            # Mantener estructura de subdirectorios
            relative_path = pdf_file.relative_to(directory)
            file_output_dir = output_dir / relative_path.parent
            file_output_dir.mkdir(parents=True, exist_ok=True)
            
            await convert_single_file(str(pdf_file), str(file_output_dir))
            processed_count += 1
            
        except Exception as e:
            print(f"❌ Error procesando {pdf_file.name}: {e}")
            failed_count += 1
    
    print()
    print(f"📊 Resumen:")
    print(f"   ✅ Procesados: {processed_count}")
    print(f"   ❌ Fallidos: {failed_count}")
    
    return {
        "processed_count": processed_count,
        "failed_count": failed_count
    }

async def main():
    """Función principal para línea de comandos"""
    
    parser = argparse.ArgumentParser(description="Conversor de PDFs a Markdown con Docling")
    parser.add_argument("command", choices=["convert", "convert-dir"], help="Comando a ejecutar")
    parser.add_argument("--file", "-f", help="Archivo PDF a convertir")
    parser.add_argument("--dir", "-d", help="Directorio con PDFs a convertir")
    parser.add_argument("--output", "-o", help="Directorio de salida (opcional)")
    
    args = parser.parse_args()
    
    try:
        if args.command == "convert":
            if not args.file:
                print("❌ Se requiere --file para convertir un archivo")
                sys.exit(1)
            
            result = await convert_single_file(args.file, args.output)
            
        elif args.command == "convert-dir":
            if not args.dir:
                print("❌ Se requiere --dir para convertir un directorio")
                sys.exit(1)
            
            result = await convert_directory(args.dir, args.output)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
