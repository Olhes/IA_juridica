import torch #import para evitar bug de docling 2.5.2 con PyTorch
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from pathlib import Path
from typing import Dict, Any
import asyncio

class LegalPDFProcessor:
    """Procesador de PDFs legales usando Docling 2.5.2"""
    
    def __init__(self, output_dir: str = "./docs/processed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Inicializar converter SIN pipeline_options para Docling 2.5.2
        # La versión 2.5.2 NO soporta PdfPipelineOptions con backend
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )
    
    async def process_pdf(self, pdf_path: str) -> str:
        """
        Procesa un PDF y retorna el contenido en markdown (asíncrono)
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            str: Contenido procesado en markdown
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")
        
        # Ejecutar conversión en thread pool para no bloquear event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.converter.convert, pdf_path)
        
        # Extraer contenido como markdown
        markdown_content = result.document.export_to_markdown()
        
        # Guardar markdown procesado
        output_file = self.output_dir / f"{pdf_path.stem}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        # Retornar solo el markdown como espera main.py línea 95
        return markdown_content
    
    async def process_pdf_detailed(self, pdf_path: str) -> Dict[str, Any]:
        """
        Versión detallada que retorna metadata adicional
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            Dict con markdown, metadata y estructura legal
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")
        
        # Ejecutar conversión en thread pool para no bloquear event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.converter.convert, pdf_path)
        
        # Extraer contenido como markdown
        markdown_content = result.document.export_to_markdown()
        
        # Extraer estructura legal
        legal_structure = self._extract_legal_structure(result.document)
        
        # Guardar markdown procesado
        output_file = self.output_dir / f"{pdf_path.stem}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        return {
            "source_file": str(pdf_path),
            "output_file": str(output_file),
            "markdown": markdown_content,
            "legal_structure": legal_structure,
            "metadata": {
                "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                "tables": len(result.document.tables) if hasattr(result.document, 'tables') else 0
            }
        }
    
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