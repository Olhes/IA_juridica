#!/usr/bin/env python
"""
Test script para pipeline optimizado de procesamiento de PDFs
"""
import asyncio
import time
from pathlib import Path
import sys

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
from config.performance_settings import performance_settings
from loguru import logger

async def main():
    """Ejecuta prueba de rendimiento del pipeline optimizado"""
    
    print("🚀 INICIANDO PRUEBA DE RENDIMIENTO OPTIMIZADO")
    print("=" * 60)
    
    # Mostrar configuración de rendimiento
    print(f"⚙️  Configuración:")
    print(f"   - Workers: {performance_settings.MAX_WORKERS}")
    print(f"   - Memoria límite: {performance_settings.MAX_MEMORY_USAGE_GB:.1f}GB")
    print(f"   - Timeout: {performance_settings.PROCESSING_TIMEOUT_SECONDS}s")
    print(f"   - Cache: {performance_settings.ENABLE_PROCESSING_CACHE}")
    print(f"   - Perfil: {performance_settings.get_performance_profile()}")
    print()
    
    # Verificar PDFs disponibles
    raw_dir = Path("docs/raw_pdfs")
    pdf_files = list(raw_dir.glob("**/*.pdf"))
    
    if not pdf_files:
        print("❌ No hay PDFs en docs/raw_pdfs")
        print("💡 Coloca algunos PDFs para probar")
        return
    
    print(f"📄 PDFs encontrados: {len(pdf_files)}")
    for pdf in pdf_files[:5]:  # Mostrar primeros 5
        size_mb = pdf.stat().st_size / (1024*1024)
        print(f"   - {pdf.relative_to(raw_dir)} ({size_mb:.1f}MB)")
    
    if len(pdf_files) > 5:
        print(f"   ... y {len(pdf_files)-5} más")
    print()
    
    # Inicializar pipeline optimizado
    print("🔧 Inicializando pipeline optimizado...")
    start_time = time.time()
    
    pipeline = OptimizedLegalIngestionPipeline(
        max_workers=performance_settings.MAX_WORKERS
    )
    
    init_time = time.time() - start_time
    print(f"✅ Pipeline inicializado en {init_time:.2f}s")
    print()
    
    # Ejecutar procesamiento
    print("🏃‍♂️ Ejecutando procesamiento PARALELO...")
    print("-" * 60)
    
    processing_start = time.time()
    
    try:
        results = await pipeline.process_all_pdfs_parallel()
        
        processing_time = time.time() - processing_start
        
        print("-" * 60)
        print("📊 RESULTADOS:")
        print(f"   ✅ Procesados: {results['processed_count']}")
        print(f"   ❌ Fallidos: {results['failed_count']}")
        print(f"   ⏱️  Tiempo total: {processing_time:.2f}s")
        print(f"   🚀 Workers usados: {results.get('workers_used', 'N/A')}")
        
        if results['processed_count'] > 0:
            avg_time_per_doc = processing_time / results['processed_count']
            print(f"   📈 Tiempo/promedio: {avg_time_per_doc:.2f}s por documento")
            
            # Estimación de speedup
            estimated_sequential_time = avg_time_per_doc * results['processed_count'] * results.get('workers_used', 1)
            speedup = estimated_sequential_time / processing_time if processing_time > 0 else 1
            print(f"   ⚡ Speedup estimado: {speedup:.1f}x más rápido")
        
        print()
        
        # Mostrar detalles de procesamiento
        if results.get('details'):
            print("📋 DETALLES:")
            for detail in results['details'][:10]:  # Primeros 10
                status_emoji = "✅" if detail['status'] == 'success' else "❌"
                filename = detail['filename']
                
                if detail['status'] == 'success':
                    proc_time = detail.get('processing_time', 0)
                    content_len = detail.get('content_length', 0)
                    print(f"   {status_emoji} {filename} ({proc_time:.1f}s, {content_len} chars)")
                else:
                    error = detail.get('error', 'Unknown error')
                    print(f"   {status_emoji} {filename} - {error}")
            
            if len(results['details']) > 10:
                print(f"   ... y {len(results['details'])-10} más")
        
        # Recomendaciones de rendimiento
        print()
        print("💡 RECOMENDACIONES:")
        recommendations = pipeline.get_performance_recommendations()
        for key, value in recommendations.items():
            print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"❌ Error durante procesamiento: {e}")
        logger.exception("Error en procesamiento optimizado")
    
    print()
    print("🎉 PRUEBA COMPLETADA")

if __name__ == "__main__":
    asyncio.run(main())
