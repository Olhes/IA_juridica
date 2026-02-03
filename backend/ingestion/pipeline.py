import asyncio
from pathlib import Path
from typing import Dict, List, Any
from loguru import logger
from tqdm import tqdm

from ingestion.docling_processor import LegalPDFProcessor
from rag.lightrag_engine import LegalRAGEngine
from utils.file_utils import FileUtils
from config.settings import settings

class LegalIngestionPipeline:
    """Pipeline completo para ingesta de documentos legales"""
    
    def __init__(self):
        self.pdf_processor = LegalPDFProcessor()
        self.rag_engine = LegalRAGEngine()
        self.file_utils = FileUtils()
        
        # Directorios
        self.raw_dir = Path("docs/raw_pdfs")
        self.processed_dir = Path("docs/processed")
        self.failed_dir = Path("docs/failed")
        
        # Asegurar que existan los directorios
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Crea directorios necesarios"""
        for directory in [self.raw_dir, self.processed_dir, self.failed_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    async def process_all_pdfs(self) -> Dict[str, Any]:
        """
        Procesa todos los PDFs en el directorio raw_pdfs
        
        Returns:
            Dict con resultados del procesamiento
        """
        logger.info("Iniciando procesamiento batch de PDFs")
        
        # Obtener todos los PDFs
        pdf_files = list(self.raw_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning("No se encontraron PDFs en docs/raw_pdfs")
            return {
                "processed_count": 0,
                "failed_count": 0,
                "details": []
            }
        
        results = {
            "processed": [],
            "failed": [],
            "details": []
        }
        
        # Procesar cada PDF
        for pdf_file in tqdm(pdf_files, desc="Procesando PDFs"):
            try:
                result = await self.process_single_pdf(pdf_file)
                results["processed"].append(result)
                logger.info(f"✅ Procesado: {pdf_file.name}")
                
            except Exception as e:
                error_result = {
                    "filename": pdf_file.name,
                    "error": str(e),
                    "status": "failed"
                }
                results["failed"].append(error_result)
                
                # Mover archivo a directorio de fallidos
                failed_path = self.failed_dir / pdf_file.name
                pdf_file.rename(failed_path)
                
                logger.error(f"❌ Falló: {pdf_file.name} - {str(e)}")
        
        # Actualizar sistema RAG con todos los documentos procesados
        if results["processed"]:
            await self.rag_engine.rebuild_index()
        
        summary = {
            "processed_count": len(results["processed"]),
            "failed_count": len(results["failed"]),
            "details": results["processed"] + results["failed"]
        }
        
        logger.info(f"Procesamiento completado: {summary['processed_count']} exitosos, {summary['failed_count']} fallidos")
        return summary
    
    async def process_single_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Procesa un solo PDF
        
        Args:
            pdf_path: Path al archivo PDF
            
        Returns:
            Dict con resultado del procesamiento
        """
        filename = pdf_path.stem
        
        try:
            # 1. Procesar con Docling
            logger.info(f"Procesando {filename} con Docling...")
            markdown_content = await self.pdf_processor.process_pdf(str(pdf_path))
            
            # 2. Guardar markdown procesado
            processed_path = self.processed_dir / f"{filename}.md"
            with open(processed_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            # 3. Extraer metadatos
            metadata = self._extract_metadata(markdown_content, filename)
            
            # 4. Agregar al sistema RAG
            await self.rag_engine.add_document(
                content=markdown_content,
                metadata=metadata,
                document_id=filename
            )
            
            # 5. Validar calidad del procesamiento
            validation = self._validate_processing(markdown_content)
            
            result = {
                "filename": filename,
                "status": "success",
                "processed_path": str(processed_path),
                "metadata": metadata,
                "validation": validation,
                "content_length": len(markdown_content),
                "articles_count": markdown_content.count("#### Artículo"),
                "sections_count": markdown_content.count("### 📚")
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error procesando {pdf_path}: {str(e)}")
            raise
    
    def _extract_metadata(self, markdown_content: str, filename: str) -> Dict[str, Any]:
        """Extrae metadatos del contenido procesado"""
        
        metadata = {
            "filename": filename,
            "processed_date": self._get_current_date(),
            "content_type": "legal_document",
            "language": "spanish",
            "jurisdiction": "peru",
            "keywords": [],
            "article_count": 0,
            "section_count": 0
        }
        
        # Extraer título
        title_match = markdown_content.split("\n")[0]
        if title_match.startswith("# "):
            metadata["title"] = title_match[2:].strip()
        else:
            metadata["title"] = filename
        
        # Contar artículos y secciones
        metadata["article_count"] = markdown_content.count("#### Artículo")
        metadata["section_count"] = markdown_content.count("### 📚")
        
        # Extraer palabras clave
        keywords = self._extract_keywords(markdown_content)
        metadata["keywords"] = keywords
        
        # Detectar tipo de documento
        doc_type = self._detect_document_type(markdown_content, filename)
        metadata["document_type"] = doc_type
        
        return metadata
    
    def _extract_keywords(self, content: str) -> List[str]:
        """Extrae palabras clave del contenido legal"""
        
        legal_keywords = [
            "ley", "artículo", "código", "reglamento", "disposición",
            "derecho", "obligación", "sanción", "procedimiento",
            "jurisdicción", "competencia", "recurso", "apelación",
            "demanda", "denuncia", "medida", "protección"
        ]
        
        found_keywords = []
        content_lower = content.lower()
        
        for keyword in legal_keywords:
            if keyword in content_lower:
                found_keywords.append(keyword)
        
        # Agregar palabras clave específicas del contenido
        specific_patterns = [
            r"violencia\s+\w+",  # violencia familiar, violencia doméstica
            r"pensión\s+de\s+alimentos",
            r"régimen\s+de\s+visitas",
            r"medidas\s+de\s+protección"
        ]
        
        import re
        for pattern in specific_patterns:
            matches = re.findall(pattern, content_lower)
            found_keywords.extend(matches)
        
        return list(set(found_keywords))[:10]  # Limitar a 10 keywords
    
    def _detect_document_type(self, content: str, filename: str) -> str:
        """Detecta el tipo de documento legal"""
        
        filename_lower = filename.lower()
        content_lower = content.lower()
        
        # Patrones para detectar tipo de documento
        type_patterns = {
            "codigo": ["codigo", "code"],
            "ley": ["ley", "law"],
            "reglamento": ["reglamento", "regulation"],
            "sentencia": ["sentencia", "caso", "jurisprudencia"],
            "formato": ["formato", "modelo", "template"],
            "directiva": ["directiva", "directivo"],
            "resolucion": ["resolucion", "resolución"]
        }
        
        for doc_type, patterns in type_patterns.items():
            for pattern in patterns:
                if pattern in filename_lower or pattern in content_lower:
                    return doc_type
        
        return "documento_legal"
    
    def _validate_processing(self, markdown_content: str) -> Dict[str, Any]:
        """Valida la calidad del procesamiento"""
        
        validation = {
            "is_valid": True,
            "confidence": 1.0,
            "issues": [],
            "warnings": []
        }
        
        # Verificar contenido mínimo
        if len(markdown_content) < 500:
            validation["issues"].append("Contenido muy corto")
            validation["confidence"] -= 0.3
        
        # Verificar estructura básica
        if not markdown_content.startswith("# "):
            validation["warnings"].append("Sin título claro")
            validation["confidence"] -= 0.1
        
        # Verificar artículos
        if "#### Artículo" not in markdown_content:
            validation["warnings"].append("No se detectaron artículos")
            validation["confidence"] -= 0.2
        
        # Verificar metadatos
        if "## 📋 Metadatos" not in markdown_content:
            validation["warnings"].append("Sin metadatos estructurados")
            validation["confidence"] -= 0.1
        
        # Verificar si hay caracteres extraños
        if "" in markdown_content:  # Caracteres de reemplazo
            validation["issues"].append("Caracteres de codificación detectados")
            validation["confidence"] -= 0.2
        
        # Ajustar confianza final
        validation["confidence"] = max(0, validation["confidence"])
        validation["is_valid"] = validation["confidence"] >= 0.6
        
        return validation
    
    def _get_current_date(self) -> str:
        """Obtiene fecha actual formateada"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async def reprocess_failed_documents(self) -> Dict[str, Any]:
        """Reintenta procesar documentos que fallaron"""
        
        failed_files = list(self.failed_dir.glob("*.pdf"))
        
        if not failed_files:
            return {"message": "No hay documentos fallidos para reprocesar"}
        
        logger.info(f"Reprocesando {len(failed_files)} documentos fallidos")
        
        # Mover archivos de vuelta a raw_pdfs
        for failed_file in failed_files:
            new_path = self.raw_dir / failed_file.name
            failed_file.rename(new_path)
        
        # Procesar nuevamente
        return await self.process_all_pdfs()
    
    async def get_processing_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del procesamiento"""
        
        processed_files = list(self.processed_dir.glob("*.md"))
        failed_files = list(self.failed_dir.glob("*.pdf"))
        raw_files = list(self.raw_dir.glob("*.pdf"))
        
        stats = {
            "total_raw": len(raw_files),
            "total_processed": len(processed_files),
            "total_failed": len(failed_files),
            "success_rate": 0,
            "documents_by_type": {},
            "total_articles": 0,
            "total_sections": 0
        }
        
        if stats["total_raw"] > 0:
            stats["success_rate"] = stats["total_processed"] / stats["total_raw"]
        
        # Analizar documentos procesados
        for processed_file in processed_files:
            try:
                with open(processed_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Contar artículos y secciones
                stats["total_articles"] += content.count("#### Artículo")
                stats["total_sections"] += content.count("### 📚")
                
                # Extraer tipo de documento (implementar lógica)
                # Por ahora, contar por nombre de archivo
                filename = processed_file.stem.lower()
                if "codigo" in filename:
                    stats["documents_by_type"]["codigo"] = stats["documents_by_type"].get("codigo", 0) + 1
                elif "ley" in filename:
                    stats["documents_by_type"]["ley"] = stats["documents_by_type"].get("ley", 0) + 1
                else:
                    doc_type = "otros"
                    stats["documents_by_type"][doc_type] = stats["documents_by_type"].get(doc_type, 0) + 1
                    
            except Exception as e:
                logger.warning(f"Error analizando {processed_file}: {str(e)}")
        
        return stats
