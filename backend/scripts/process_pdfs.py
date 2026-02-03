#!/usr/bin/env python3.12
"""
Script para procesar PDFs legales con Docling
"""

import asyncio
import sys
import argparse
from pathlib import Path
from loguru import logger

# Agregar el directorio backend al path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from ingestion.pipeline import LegalIngestionPipeline
from config.settings import settings

class PDFProcessor:
    """Procesador de PDFs para línea de comandos"""
    
    def __init__(self):
        self.pipeline = LegalIngestionPipeline()
    
    async def process_single_file(self, file_path: str) -> dict:
        """Procesa un solo archivo PDF"""
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        if not file_path.suffix.lower() == '.pdf':
            raise ValueError(f"El archivo debe ser un PDF: {file_path}")
        
        logger.info(f"Procesando archivo: {file_path.name}")
        
        try:
            result = await self.pipeline.process_single_pdf(file_path)
            logger.info(f"✅ Archivo procesado: {file_path.name}")
            return result
        except Exception as e:
            logger.error(f"❌ Error procesando {file_path.name}: {str(e)}")
            raise
    
    async def process_directory(self, directory: str = None) -> dict:
        """Procesa todos los PDFs en un directorio"""
        
        if directory is None:
            directory = settings.RAW_PDF_DIR
        
        directory = Path(directory)
        
        if not directory.exists():
            raise FileNotFoundError(f"Directorio no encontrado: {directory}")
        
        logger.info(f"Procesando directorio: {directory}")
        
        results = await self.pipeline.process_all_pdfs()
        
        logger.info(f"✅ Procesamiento completado:")
        logger.info(f"   Procesados: {results['processed_count']}")
        logger.info(f"   Fallidos: {results['failed_count']}")
        
        return results
    
    async def get_stats(self) -> dict:
        """Obtiene estadísticas del procesamiento"""
        
        stats = await self.pipeline.get_processing_stats()
        
        print("\n📊 Estadísticas del Sistema:")
        print(f"   PDFs crudos: {stats['total_raw']}")
        print(f"   Procesados: {stats['total_processed']}")
        print(f"   Fallidos: {stats['total_failed']}")
        print(f"   Tasa éxito: {stats['success_rate']:.2%}")
        print(f"   Artículos totales: {stats['total_articles']}")
        print(f"   Secciones totales: {stats['total_sections']}")
        
        if stats['documents_by_type']:
            print("\n📚 Documentos por tipo:")
            for doc_type, count in stats['documents_by_type'].items():
                print(f"   {doc_type}: {count}")
        
        return stats
    
    async def reprocess_failed(self) -> dict:
        """Reintenta procesar archivos fallidos"""
        
        logger.info("Reprocesando archivos fallidos...")
        
        results = await self.pipeline.reprocess_failed_documents()
        
        if isinstance(results, dict):
            logger.info(f"✅ Reprocesamiento completado:")
            logger.info(f"   Procesados: {results['processed_count']}")
            logger.info(f"   Fallidos: {results['failed_count']}")
        else:
            logger.info("ℹ️  No hay archivos fallidos para reprocesar")
        
        return results
    
    async def validate_processed_files(self) -> dict:
        """Valida archivos procesados"""
        
        processed_dir = Path(settings.PROCESSED_DIR)
        
        if not processed_dir.exists():
            return {"error": "Directorio de procesados no existe"}
        
        markdown_files = list(processed_dir.glob("*.md"))
        
        validation_results = {
            "total_files": len(markdown_files),
            "valid_files": 0,
            "invalid_files": 0,
            "issues": []
        }
        
        for md_file in markdown_files:
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Validaciones básicas
                issues = []
                
                if len(content) < 500:
                    issues.append("Contenido muy corto")
                
                if not content.startswith("# "):
                    issues.append("Sin título claro")
                
                if "#### Artículo" not in content:
                    issues.append("Sin artículos detectados")
                
                if issues:
                    validation_results["invalid_files"] += 1
                    validation_results["issues"].append({
                        "file": md_file.name,
                        "issues": issues
                    })
                else:
                    validation_results["valid_files"] += 1
                    
            except Exception as e:
                validation_results["invalid_files"] += 1
                validation_results["issues"].append({
                    "file": md_file.name,
                    "issues": [f"Error leyendo archivo: {str(e)}"]
                })
        
        return validation_results

async def main():
    """Función principal para línea de comandos"""
    
    parser = argparse.ArgumentParser(description="Procesador de PDFs legales con Docling")
    parser.add_argument("command", choices=[
        "process", "process-dir", "stats", "reprocess", "validate"
    ], help="Comando a ejecutar")
    parser.add_argument("--file", "-f", help="Archivo PDF a procesar")
    parser.add_argument("--dir", "-d", help="Directorio con PDFs a procesar")
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verbose")
    
    args = parser.parse_args()
    
    # Configurar logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()
    logger.add(sys.stdout, level=log_level)
    
    # Inicializar procesador
    processor = PDFProcessor()
    
    try:
        if args.command == "process":
            if not args.file:
                print("❌ Se requiere --file para procesar un archivo")
                sys.exit(1)
            
            result = await processor.process_single_file(args.file)
            print(f"\n✅ Archivo procesado: {result['filename']}")
            print(f"   Ruta: {result['processed_path']}")
            print(f"   Artículos: {result['articles_count']}")
            print(f"   Secciones: {result['sections_count']}")
        
        elif args.command == "process-dir":
            result = await processor.process_directory(args.dir)
            print(f"\n✅ Directorio procesado:")
            print(f"   Procesados: {result['processed_count']}")
            print(f"   Fallidos: {result['failed_count']}")
        
        elif args.command == "stats":
            await processor.get_stats()
        
        elif args.command == "reprocess":
            result = await processor.reprocess_failed()
            if isinstance(result, dict):
                print(f"\n✅ Reprocesamiento:")
                print(f"   Procesados: {result['processed_count']}")
                print(f"   Fallidos: {result['failed_count']}")
        
        elif args.command == "validate":
            result = await processor.validate_processed_files()
            print(f"\n📊 Validación:")
            print(f"   Total archivos: {result['total_files']}")
            print(f"   Válidos: {result['valid_files']}")
            print(f"   Inválidos: {result['invalid_files']}")
            
            if result['issues']:
                print("\n⚠️  Problemas encontrados:")
                for issue in result['issues'][:5]:  # Limitar a 5
                    print(f"   📄 {issue['file']}: {', '.join(issue['issues'])}")
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
