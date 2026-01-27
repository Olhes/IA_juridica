from docling import DocumentProcessor
from docling.datamodel.base_models import DoclingDocument
from docling.datamodel.pipeline_options import PdfPipelineOptions
from pathlib import Path
import json
import re
from typing import Dict, List, Any
from loguru import logger

class LegalPDFProcessor:
    """Procesador especializado para PDFs legales usando Docling"""
    
    def __init__(self):
        # Configurar opciones de pipeline para documentos legales
        self.pipeline_options = PdfPipelineOptions(
            do_ocr=True,  # Habilitar OCR para PDFs escaneados
            do_table_structure=True,  # Extraer estructura de tablas
            generate_page_images=False,  # No necesitamos imágenes
            document_hash=True,  # Para detectar cambios
        )
        
        self.processor = DocumentProcessor(
            pipeline_options=self.pipeline_options
        )
        
        # Patrones para extraer entidades legales
        self.legal_patterns = {
            'article': r'Artículo\s+(\d+)[º°]?\s*[-.]?\s*(.+?)(?=Artículo|\n\n|\Z)',
            'law': r'Ley\s+(\d+)[º°]?\s*[-.]?\s*(.+?)(?=Ley|\n\n|\Z)',
            'code': r'Código\s+(\w+)\s*[-.]?\s*(.+?)(?=Código|\n\n|\Z)',
            'section': r'(TÍTULO|CAPÍTULO|SECCIÓN|SUBSECCIÓN)\s+([IVX]+|[0-9]+)\s*[-.]?\s*(.+?)(?=TÍTULO|CAPÍTULO|SECCIÓN|Artículo|\n\n|\Z)'
        }
    
    async def process_pdf(self, pdf_path: str) -> str:
        """
        Procesa un PDF legal y retorna markdown estructurado
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            Markdown estructurado con metadatos legales
        """
        try:
            logger.info(f"Procesando PDF: {pdf_path}")
            
            # Procesar documento con Docling
            doc: DoclingDocument = self.processor.process_document(Path(pdf_path))
            
            # Extraer contenido estructurado
            structured_content = self._extract_legal_structure(doc)
            
            # Convertir a markdown con formato legal
            markdown_content = self._to_legal_markdown(structured_content, pdf_path)
            
            logger.info(f"PDF procesado exitosamente: {len(markdown_content)} caracteres")
            return markdown_content
            
        except Exception as e:
            logger.error(f"Error procesando PDF {pdf_path}: {str(e)}")
            raise
    
    def _extract_legal_structure(self, doc: DoclingDocument) -> Dict[str, Any]:
        """Extrae estructura legal del documento procesado"""
        
        structure = {
            'title': '',
            'metadata': {},
            'articles': [],
            'sections': [],
            'tables': [],
            'full_text': ''
        }
        
        # Extraer título del documento
        if doc.titles:
            structure['title'] = doc.titles[0].text if doc.titles else "Documento Legal"
        
        # Extraer metadatos
        structure['metadata'] = {
            'total_pages': len(doc.pages) if doc.pages else 0,
            'has_tables': len(doc.tables) > 0 if doc.tables else False,
            'has_images': len(doc.pictures) > 0 if doc.pictures else False,
        }
        
        # Procesar texto completo y extraer entidades
        full_text = ""
        for page in doc.pages:
            if page.text:
                full_text += page.text + "\n\n"
        
        structure['full_text'] = full_text
        
        # Extraer artículos usando regex
        articles = self._extract_articles(full_text)
        structure['articles'] = articles
        
        # Extraer secciones
        sections = self._extract_sections(full_text)
        structure['sections'] = sections
        
        # Extraer tablas si existen
        if doc.tables:
            structure['tables'] = self._extract_tables(doc.tables)
        
        return structure
    
    def _extract_articles(self, text: str) -> List[Dict[str, Any]]:
        """Extrae artículos del texto legal"""
        articles = []
        
        # Buscar artículos
        article_matches = re.finditer(
            self.legal_patterns['article'], 
            text, 
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        
        for match in article_matches:
            article_num = match.group(1).strip()
            article_content = match.group(2).strip()
            
            # Limpiar contenido
            article_content = re.sub(r'\s+', ' ', article_content)
            
            articles.append({
                'number': article_num,
                'content': article_content,
                'type': 'article',
                'relationships': self._extract_relationships(article_content)
            })
        
        return articles
    
    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extrae secciones del documento"""
        sections = []
        
        section_matches = re.finditer(
            self.legal_patterns['section'], 
            text, 
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        
        for match in section_matches:
            section_type = match.group(1).strip()
            section_num = match.group(2).strip()
            section_title = match.group(3).strip()
            
            sections.append({
                'type': section_type.lower(),
                'number': section_num,
                'title': section_title,
                'level': self._get_section_level(section_type)
            })
        
        return sections
    
    def _extract_tables(self, tables) -> List[Dict[str, Any]]:
        """Extrae tablas del documento"""
        extracted_tables = []
        
        for i, table in enumerate(tables):
            # Convertir tabla a formato estructurado
            table_data = {
                'id': f"table_{i+1}",
                'rows': [],
                'headers': []
            }
            
            # Aquí procesarías la tabla según la API de Docling
            # Implementación básica
            if hasattr(table, 'data'):
                table_data['data'] = table.data
            
            extracted_tables.append(table_data)
        
        return extracted_tables
    
    def _extract_relationships(self, content: str) -> List[str]:
        """Extrae relaciones legales del contenido"""
        relationships = []
        
        # Buscar referencias a otros artículos
        ref_patterns = [
            r'Artículo\s+(\d+)',
            r'Ley\s+(\d+)',
            r'Código\s+(\w+)',
            r'conforme\s+al\s+(.+)',
            r'de\s+acuerdo\s+con\s+(.+)'
        ]
        
        for pattern in ref_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            relationships.extend(matches)
        
        return list(set(relationships))  # Eliminar duplicados
    
    def _get_section_level(self, section_type: str) -> int:
        """Determina el nivel jerárquico de la sección"""
        levels = {
            'título': 1,
            'capítulo': 2,
            'sección': 3,
            'subsección': 4
        }
        return levels.get(section_type.lower(), 5)
    
    def _to_legal_markdown(self, structure: Dict[str, Any], pdf_path: str) -> str:
        """Convierte estructura legal a markdown formateado"""
        
        # Extraer nombre del archivo para metadatos
        filename = Path(pdf_path).stem
        
        markdown = f"""# {structure['title']}

## 📋 Metadatos del Documento
- **Archivo:** {filename}
- **Páginas:** {structure['metadata']['total_pages']}
- **Fecha de procesamiento:** {self._get_current_date()}
- **Tipo:** Documento Legal Estructurado

## 🏗️ Estructura del Documento
"""
        
        # Agregar secciones
        if structure['sections']:
            markdown += "\n### 📚 Secciones\n\n"
            for section in structure['sections']:
                indent = "  " * (section['level'] - 1)
                markdown += f"{indent}- **{section['type'].title()} {section['number']}:** {section['title']}\n"
        
        # Agregar artículos
        if structure['articles']:
            markdown += "\n### 📜 Artículos\n\n"
            for article in structure['articles']:
                markdown += f"""#### Artículo {article['number']}

{article['content']}

**Relaciones:** {', '.join(article['relationships']) if article['relationships'] else 'Ninguna'}

---

"""
        
        # Agregar tablas si existen
        if structure['tables']:
            markdown += "\n### 📊 Tablas\n\n"
            for i, table in enumerate(structure['tables']):
                markdown += f"**Tabla {i+1}:** {table.get('id', 'Sin ID')}\n\n"
        
        # Agregar texto completo como referencia
        markdown += f"""
## 📄 Texto Completo (Referencia)

{structure['full_text'][:2000]}{'...' if len(structure['full_text']) > 2000 else ''}

---

*Documento procesado con Docling - Sistema IA Jurídica*
*Fecha: {self._get_current_date()}*
"""
        
        return markdown
    
    def _get_current_date(self) -> str:
        """Obtiene fecha actual formateada"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def validate_legal_document(self, structure: Dict[str, Any]) -> Dict[str, Any]:
        """Valida que el documento sea legalmente válido"""
        
        validation_result = {
            'is_legal': False,
            'confidence': 0.0,
            'issues': [],
            'recommendations': []
        }
        
        # Verificar si tiene artículos (indicador de documento legal)
        if structure['articles']:
            validation_result['is_legal'] = True
            validation_result['confidence'] += 0.4
        
        # Verificar si tiene secciones legales
        legal_sections = ['título', 'capítulo', 'artículo']
        section_count = sum(1 for s in structure['sections'] if s['type'] in legal_sections)
        if section_count > 0:
            validation_result['confidence'] += 0.3
        
        # Verificar lenguaje legal
        legal_keywords = ['ley', 'artículo', 'código', 'reglamento', 'disposición']
        keyword_count = sum(1 for word in legal_keywords if word in structure['full_text'].lower())
        if keyword_count > 2:
            validation_result['confidence'] += 0.3
        
        # Redondear confianza
        validation_result['confidence'] = min(validation_result['confidence'], 1.0)
        
        return validation_result
