import torch #import para evitar bug de docling 2.5.2 con PyTorch
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from pathlib import Path
from typing import Dict, Any
import asyncio
from ingestion.conversion import ConversionArtifact
from ingestion.legal_structure import parse_legal_structure

class LegalPDFProcessor:
    """Conversión Docling; estructura jurídica candidata, no revisión legal."""
    
    def __init__(self, output_dir: str = "./docs/processed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Mantener configuración de conversión existente; las opciones de jerarquía
        # se evalúan aparte antes de cambiar Markdown/evidencia ya registrada.
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )
    
    async def process_pdf(self, pdf_path: str, *, write_output: bool = True) -> str:
        """
        Procesa un PDF y retorna el contenido en markdown (asíncrono)
        
        Argumentos:
            pdf_path: Ruta al archivo PDF
            write_output: Indica si se debe guardar el Markdown en output_dir (valor predeterminado para llamadas independientes)
            
        Retorna:
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
        
        if write_output:
            output_file = self.output_dir / f"{pdf_path.stem}.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
        
        # Retornar solo el markdown como espera main.py línea 95
        return markdown_content
    
    async def process_pdf_detailed(self, pdf_path: str) -> Dict[str, Any]:
        """
        Versión detallada que retorna metadata adicional
        
        Argumentos:
            pdf_path: Ruta al archivo PDF
            
        Retorna:
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

    async def process_pdf_artifact(self, pdf_path: str) -> ConversionArtifact:
        """Una sola conversión; Markdown y JSON provienen del mismo documento.

        No escribe archivos: upload/batch publican evidencia tras sus controles.
        El fallback sin JSON permite adaptadores antiguos y queda diagnosticado.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF no encontrado: {path}")
        result = await asyncio.get_running_loop().run_in_executor(None, self.converter.convert, path)
        document = result.document
        layout = document.export_to_dict(mode="json") if hasattr(document, "export_to_dict") else None
        return ConversionArtifact(document.export_to_markdown(), layout)
    
    def _extract_legal_structure(self, document) -> Dict[str, Any]:
        """Compatibilidad detallada sin el antiguo truncamiento a 50 artículos."""
        layout = document.export_to_dict(mode="json") if hasattr(document, "export_to_dict") else None
        structure = parse_legal_structure(document.export_to_markdown(), layout)
        structure["articles"] = [n["label"] for n in structure["nodes"] if n["kind"] == "article"]
        structure["sections"] = [n["label"] for n in structure["nodes"] if n["kind"] in {"seccion", "subseccion"}]
        structure["definitions"] = []  # No inferir definiciones jurídicas automáticamente.
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
