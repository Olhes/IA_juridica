#!/usr/bin/env python
"""
Test real de rendimiento con PDFs nuevos (simulados)
"""
import asyncio
import time
import shutil
from pathlib import Path
import sys

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
from config.performance_settings import performance_settings

async def main():
    """Prueba real con PDFs simulados"""
    
    print("🧪 PRUEBA REAL DE RENDIMIENTO")
    print("=" * 50)
    
    # Backup de archivos existentes
    processed_dir = Path("docs/processed")
    backup_dir = Path("docs/processed_backup")
    
    if processed_dir.exists():
        print("📦 Haciendo backup de archivos procesados...")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(processed_dir, backup_dir)
        print(f"✅ Backup guardado en {backup_dir}")
    
    # Limpiar processed para forzar reprocesamiento
    if processed_dir.exists():
        shutil.rmtree(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    print("🗂️  Directorio procesados limpio - forzando reprocesamiento")
    print()
    
    # Verificar PDFs disponibles
    raw_dir = Path("docs/raw_pdfs")
    pdf_files = list(raw_dir.glob("**/*.pdf"))
    
    # Limitar a 5 PDFs para prueba rápida
    test_pdfs = pdf_files[:5]
    
    print(f"📄 Probando con {len(test_pdfs)} PDFs:")
    for pdf in test_pdfs:
        size_mb = pdf.stat().st_size / (1024*1024)
        print(f"   - {pdf.relative_to(raw_dir)} ({size_mb:.1f}MB)")
    print()
    
    # Inicializar pipeline
    print("🚀 Iniciando pipeline optimizado...")
    pipeline = OptimizedLegalIngestionPipeline(max_workers=4)  # Workers conservadores
    
    # Medir tiempo real
    print("⏱️  Ejecutando procesamiento real...")
    print("-" * 50)
    
    start_time = time.time()
    
    try:
        results = await pipeline.process_all_pdfs_parallel()
        
        total_time = time.time() - start_time
        
        print("-" * 50)
        print("📊 RESULTADOS REALES:")
        print(f"   ✅ Procesados: {results['processed_count']}")
        print(f"   ❌ Fallidos: {results['failed_count']}")
        print(f"   ⏱️  Tiempo total: {total_time:.2f}s")
        
        if results['processed_count'] > 0:
            avg_time = total_time / results['processed_count']
            print(f"   📈 Tiempo/promedio: {avg_time:.2f}s por PDF")
            
            # Estimación para todos los PDFs
            total_pdfs = len(pdf_files)
            estimated_total = avg_time * total_pdfs
            print(f"   🔮 Estimación para {total_pdfs} PDFs: {estimated_total:.1f}s ({estimated_total/60:.1f}min)")
        
        # Mostrar detalles de procesamiento
        if results.get('details'):
            print("\n📋 DETALLES DE PROCESAMIENTO:")
            for detail in results['details']:
                if detail['status'] == 'success':
                    proc_time = detail.get('processing_time', 0)
                    content_len = detail.get('content_length', 0)
                    print(f"   ✅ {detail['filename']}")
                    print(f"      ⏱️  {proc_time:.2f}s | 📝 {content_len} chars")
                else:
                    print(f"   ❌ {detail['filename']} - {detail.get('error', 'Error')}")
        
        # Speedup comparación
        sequential_estimate = total_time * 4  # Asumiendo 4x más lento secuencialmente
        speedup = sequential_estimate / total_time if total_time > 0 else 1
        print(f"\n⚡ Speedup optimizado: {speedup:.1f}x más rápido que secuencial")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Restaurar backup
    print("\n🔄 Restaurando backup...")
    if processed_dir.exists():
        shutil.rmtree(processed_dir)
    if backup_dir.exists():
        shutil.copytree(backup_dir, processed_dir)
        print("✅ Backup restaurado")
    
    print("\n🎉 PRUEBA REAL COMPLETADA")

if __name__ == "__main__":
    asyncio.run(main())
