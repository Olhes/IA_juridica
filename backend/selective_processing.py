#!/usr/bin/env python
"""
Script interactivo para procesamiento selectivo de PDFs
"""
import asyncio
import sys
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.selective_processor import SelectivePDFProcessor

async def main():
    """Menú interactivo de procesamiento"""
    
    print("🎯 PROCESAMIENTO SELECTIVO DE PDFs")
    print("=" * 50)
    
    processor = SelectivePDFProcessor(max_workers=4)
    
    # Mostrar opciones disponibles
    options = processor.list_available_options()
    
    print("📂 CATEGORÍAS DISPONIBLES:")
    for category, files in options["categories"].items():
        print(f"   📁 {category}: {len(files)} archivos")
    
    print(f"\n📄 TOTAL ARCHIVOS: {options['total_files']}")
    print()
    
    print("🎮 ELIGE UNA OPCIÓN:")
    print("1. Procesar por categorías")
    print("2. Procesar por palabras clave")
    print("3. Procesar archivos específicos")
    print("4. Procesar solo los primeros N archivos")
    print("5. Procesar desarrollo rápido (8 archivos esenciales)")
    print("6. Ver lista completa de archivos")
    print("0. Salir")
    
    choice = input("\n👉 Elige opción (0-6): ").strip()
    
    if choice == "1":
        await process_by_categories(processor, options)
    elif choice == "2":
        await process_by_keywords(processor, options)
    elif choice == "3":
        await process_specific_files(processor, options)
    elif choice == "4":
        await process_first_n(processor, options)
    elif choice == "5":
        await process_development_quick(processor)
    elif choice == "6":
        show_all_files(options)
    elif choice == "0":
        print("👋 ¡Hasta luego!")
    else:
        print("❌ Opción inválida")

async def process_by_categories(processor, options):
    """Procesar por categorías"""
    print("\n📂 CATEGORÍAS DISPONIBLES:")
    for i, category in enumerate(options["categories"].keys(), 1):
        print(f"   {i}. {category}")
    
    selected = input("\n👉 Ingresa números separados por coma (ej: 1,3): ").strip()
    
    if not selected:
        print("❌ No seleccionaste nada")
        return
    
    try:
        indices = [int(x.strip()) for x in selected.split(",")]
        categories = [list(options["categories"].keys())[i-1] for i in indices]
        
        print(f"\n🚀 Procesando categorías: {categories}")
        results = await processor.process_by_category(categories=categories)
        
        print_results(results)
        
    except (ValueError, IndexError):
        print("❌ Selección inválida")

async def process_by_keywords(processor, options):
    """Procesar por palabras clave"""
    print(f"\n🔍 PALABRAS CLAVE COMUNES:")
    keywords = list(options["common_keywords"])[:20]  # Primeras 20
    for i, keyword in enumerate(keywords, 1):
        print(f"   {i}. {keyword}")
    
    selected = input("\n👉 Ingresa palabras clave separadas por coma: ").strip()
    
    if not selected:
        print("❌ No ingresaste palabras clave")
        return
    
    keywords = [x.strip() for x in selected.split(",")]
    
    print(f"\n🔍 Buscando: {keywords}")
    results = await processor.process_by_keywords(keywords=keywords)
    
    print_results(results)

async def process_specific_files(processor, options):
    """Procesar archivos específicos"""
    print(f"\n📄 ARCHIVOS DISPONIBLES:")
    for i, filename in enumerate(options["all_files"][:15], 1):  # Primeros 15
        print(f"   {i:2d}. {filename}")
    
    if len(options["all_files"]) > 15:
        print(f"   ... y {len(options["all_files"]) - 15} más")
    
    selected = input("\n👉 Ingresa números separados por coma: ").strip()
    
    if not selected:
        print("❌ No seleccionaste archivos")
        return
    
    try:
        indices = [int(x.strip()) for x in selected.split(",")]
        files = [options["all_files"][i-1] for i in indices]
        
        force = input("\n🔄 Forzar reprocesamiento? (s/N): ").strip().lower() == 's'
        
        print(f"\n📄 Procesando archivos: {files}")
        results = await processor.process_specific_files(files, force_reprocess=force)
        
        print_results(results)
        
    except (ValueError, IndexError):
        print("❌ Selección inválida")

async def process_first_n(processor, options):
    """Procesar primeros N archivos"""
    n = input("\n👉 ¿Cuántos archivos procesar? (1-21): ").strip()
    
    try:
        n = int(n)
        if n < 1 or n > 21:
            print("❌ Número inválido")
            return
        
        print(f"\n🚀 Procesando primeros {n} archivos...")
        results = await processor.process_by_category(max_files=n)
        
        print_results(results)
        
    except ValueError:
        print("❌ Número inválido")

async def process_development_quick(processor):
    """Procesamiento rápido para desarrollo"""
    print("\n🚀 MODO DESARROLLO RÁPIDO")
    print("Procesando 8 archivos esenciales para desarrollo...")
    
    # Archivos esenciales para desarrollo
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
    
    print_results(results)

def show_all_files(options):
    """Mostrar todos los archivos"""
    print(f"\n📄 TODOS LOS ARCHIVOS ({len(options['all_files'])}):")
    for i, filename in enumerate(options["all_files"], 1):
        print(f"   {i:2d}. {filename}")

def print_results(results):
    """Imprimir resultados de procesamiento"""
    print("\n" + "=" * 50)
    print("📊 RESULTADOS DEL PROCESAMIENTO")
    print("=" * 50)
    
    if "selected_files" in results:
        print(f"📋 Archivos seleccionados: {results['selected_files']}")
    if "categories" in results:
        print(f"📂 Categorías: {results['categories']}")
    if "keywords" in results:
        print(f"🔍 Palabras clave: {results['keywords']}")
    
    print(f"✅ Procesados exitosamente: {results['files_processed']}")
    print(f"❌ Fallidos: {results['files_failed']}")
    print(f"⏱️  Tiempo total: {results['total_time']:.2f} segundos")
    
    if results['files_processed'] > 0:
        avg_time = results['total_time'] / results['files_processed']
        print(f"📈 Promedio por archivo: {avg_time:.2f} segundos")
    
    print("\n🎉 ¡Procesamiento completado!")

if __name__ == "__main__":
    asyncio.run(main())
