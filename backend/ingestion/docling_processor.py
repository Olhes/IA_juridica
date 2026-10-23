import torch #import para evitar bug de docling 2.5.2 con PyTorch
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio

class LegalDocumentProcessor:
    """Procesador de documentos legales usando Docling 2.133.0
    Soporta: PDF, DOCX, PPTX, XLSX, imágenes (PNG, JPEG, TIFF), HTML, y más
    """

    # Formatos soportados por Docling
    SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
    SUPPORTED_DOC_FORMATS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".html", ".htm", ".md", ".txt"}

    def __init__(self, output_dir: str = "./docs/processed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Inicializar converter con todos los formatos soportados
        # Docling 2.133.0 soporta múltiples formatos automáticamente
        self.converter = DocumentConverter()
    
    async def process_document(self, file_path: str, *, write_output: bool = True) -> str:
        """
        Procesa un documento (PDF, imagen, DOCX, etc.) y retorna el contenido en markdown (asíncrono)

        Argumentos:
            file_path: Ruta al archivo (PDF, imagen, DOCX, etc.)
            write_output: Indica si se debe guardar el Markdown en output_dir

        Retorna:
            str: Contenido procesado en markdown
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        # Verificar formato
        file_ext = file_path.suffix.lower()
        if file_ext not in self.SUPPORTED_IMAGE_FORMATS and file_ext not in self.SUPPORTED_DOC_FORMATS:
            raise ValueError(
                f"Formato no soportado: {file_ext}. "
                f"Formatos soportados: {self.SUPPORTED_IMAGE_FORMATS | self.SUPPORTED_DOC_FORMATS}"
            )

        # Ejecutar conversión en thread pool para no bloquear event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.converter.convert, file_path)

        # Extraer contenido como markdown
        markdown_content = result.document.export_to_markdown()

        if write_output:
            output_file = self.output_dir / f"{file_path.stem}.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)

        return markdown_content
    
    async def process_document_detailed(self, file_path: str) -> Dict[str, Any]:
        """
        Versión detallada que retorna metadata adicional

        Argumentos:
            file_path: Ruta al archivo (PDF, imagen, DOCX, etc.)

        Retorna:
            Dict con markdown, metadata y estructura legal
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        # Verificar formato
        file_ext = file_path.suffix.lower()
        if file_ext not in self.SUPPORTED_IMAGE_FORMATS and file_ext not in self.SUPPORTED_DOC_FORMATS:
            raise ValueError(f"Formato no soportado: {file_ext}")

        # Ejecutar conversión en thread pool para no bloquear event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.converter.convert, file_path)

        # Extraer contenido como markdown
        markdown_content = result.document.export_to_markdown()

        # Extraer estructura legal
        legal_structure = self._extract_legal_structure(result.document)

        # Guardar markdown procesado
        output_file = self.output_dir / f"{file_path.stem}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        return {
            "source_file": str(file_path),
            "output_file": str(output_file),
            "file_type": "image" if file_ext in self.SUPPORTED_IMAGE_FORMATS else "document",
            "markdown": markdown_content,
            "legal_structure": legal_structure,
            "metadata": {
                "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                "tables": len(result.document.tables) if hasattr(result.document, 'tables') else 0
            }
        }

    # Alias para mantener compatibilidad con código existente
    async def process_pdf(self, pdf_path: str, *, write_output: bool = True) -> str:
        """Alias para process_document (compatibilidad)"""
        return await self.process_document(pdf_path, write_output=write_output)

    async def process_pdf_detailed(self, pdf_path: str) -> Dict[str, Any]:
        """Alias para process_document_detailed (compatibilidad)"""
        return await self.process_document_detailed(pdf_path)
    
    def _extract_legal_structure(self, document) -> Dict[str, Any]:
        """Extrae estructura legal del documento"""
        structure = {
            "articles": [],
            "sections": [],
            "definitions": []
        }
        
        # Extraer texto y buscar patrones legales
        text = document.export_to_markdown()
        
        # Buscar artículos (Artículo 1, Art. 2, etc.)
        import re
        articles = re.findall(r'(Art[íi]culo\s+\d+[°º]?[\.\-\:]?\s*[^\n]+)', text, re.IGNORECASE)
        structure["articles"] = articles[:50]  # Limitar a 50
        
        return structure
    
    def _to_legal_markdown(self, document, structure: Dict) -> str:
        """Convierte a markdown con formato legal"""
        markdown = document.export_to_markdown()
        
        # Agregar metadatos al inicio
        header = f"""---
tipo: documento_legal
articulos_encontrados: {len(structure.get('articles', []))}
---

"""
        return header + markdown
