#!/usr/bin/env python
"""
Comandos rápidos para procesamiento selectivo
"""
import asyncio
import sys
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.selective_processor import SelectivePDFProcessor

async def process_essentials():
    """Procesar 8 archivos esenciales para desarrollo rápido"""
    print("🚀 PROCESANDO 8 ARCHIVOS ESENCIALES")
    print("=" * 50)
    
    processor = SelectivePDFProcessor(max_workers=4)
    
    essential_files = [
        "Pensión_de_Alimentos_Guía_Integral.pdf",
        "Régimen_de_Visitas_Guía_Integral_Perú.pdf",
        "Manual quechua cusco collao administracion de justicia.pdf",
        "Formulario de demanda de alimentos para niños niñas adolescentes.pdf",
        "Violencia_Psicológica_Valor_Probatorio_Supremo.pdf",
        "Tenencia_Familiar_Tipos_y_Críticas.pdf",
        "Pensión de alimentos_ ¿qué abarca y cómo calcularla_ [ACTUALIZADO 2025] _ LP.pdf",
        "Régimen de visitas_ concepto, modalidades, demanda, incumplimiento. Bien explicado _ Juris.pe.pdf"
    ]
    
    results = await processor.process_specific_files(essential_files, force_reprocess=False)
    
    print(f"✅ Procesados: {results['files_processed']}")
    print(f"❌ Fallidos: {results['files_failed']}")
    print(f"⏱️  Tiempo: {results['total_time']:.2f}s")
    
    return results

async def process_by_category(category):
    """Procesar por categoría específica"""
    print(f"📂 PROCESANDO CATEGORÍA: {category}")
    print("=" * 50)
    
    processor = SelectivePDFProcessor(max_workers=4)
    
    results = await processor.process_by_category(categories=[category])
    
    print(f"✅ Procesados: {results['files_processed']}")
    print(f"❌ Fallidos: {results['files_failed']}")
    print(f"⏱️  Tiempo: {results['total_time']:.2f}s")
    
    return results

async def process_first_n(n):
    """Procesar primeros N archivos"""
    print(f"📊 PROCESANDO PRIMEROS {n} ARCHIVOS")
    print("=" * 50)
    
    processor = SelectivePDFProcessor(max_workers=4)
    
    results = await processor.process_by_category(max_files=n)
    
    print(f"✅ Procesados: {results['files_processed']}")
    print(f"❌ Fallidos: {results['files_failed']}")
    print(f"⏱️  Tiempo: {results['total_time']:.2f}s")
    
    return results

async def process_guides_only():
    """Procesar solo guías y manuales"""
    print("📚 PROCESANDO GUÍAS Y MANUALES")
    print("=" * 50)
    
    processor = SelectivePDFProcessor(max_workers=4)
    
    keywords = ["guía", "manual", "integral"]
    exclude_keywords = ["análisis", "jurisprudencia"]
    
    results = await processor.process_by_keywords(
        keywords=keywords, 
        exclude_keywords=exclude_keywords
    )
    
    print(f"✅ Procesados: {results['files_processed']}")
    print(f"❌ Fallidos: {results['files_failed']}")
    print(f"⏱️  Tiempo: {results['total_time']:.2f}s")
    
    return results

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Procesamiento selectivo rápido")
    parser.add_argument("--essentials", action="store_true", help="Procesar 8 archivos esenciales")
    parser.add_argument("--category", type=str, help="Procesar categoría específica")
    parser.add_argument("--first", type=int, help="Procesar primeros N archivos")
    parser.add_argument("--guides", action="store_true", help="Procesar solo guías y manuales")
    
    args = parser.parse_args()
    
    if args.essentials:
        asyncio.run(process_essentials())
    elif args.category:
        asyncio.run(process_by_category(args.category))
    elif args.first:
        asyncio.run(process_first_n(args.first))
    elif args.guides:
        asyncio.run(process_guides_only())
    else:
        print("Uso:")
        print("  py quick_process.py --essentials")
        print("  py quick_process.py --category pension_alimentos")
        print("  py quick_process.py --first 5")
        print("  py quick_process.py --guides")
