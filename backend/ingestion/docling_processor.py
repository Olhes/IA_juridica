from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from pathlib import Path
import json
from typing import Optional, Dict, Any

class LegalPDFProcessor:
    """Procesador de PDFs legales usando Docling"""
    
    def __init__(self, output_dir: str = "./docs/processed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar opciones del pipeline
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: pipeline_options
            }
        )
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Procesa un PDF y extrae estructura legal"""
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")
        
        # Convertir documento
        result = self.converter.convert(pdf_path)
        
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
