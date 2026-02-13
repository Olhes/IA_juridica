"""
Estrategias de chunking especializadas para documentos legales
Optimizadas para Docling y contexto rural peruano
"""

from typing import List, Dict, Any, Optional
import re
from pathlib import Path
from loguru import logger

class LegalChunkingStrategy:
    """Estrategia de chunking para documentos legales peruanos"""
    
    def __init__(self):
        # Patrones para documentos legales peruanos
        self.legal_patterns = {
            'articulo': r'Art[íi]culo\s+(\d+)[°º]?\s*[-.]?\s*',
            'seccion': r'[Ss]ecció[n]\s+([IVXLCDM]+|[A-Z]|\d+)\s*[:.]?\s*',
            'capitulo': r'[Cc]ap[íi]tulo\s+([IVXLCDM]+|[A-Z]|\d+)\s*[:.]?\s*',
            'titulo': r'[Tt][íi]tulo\s+([IVXLCDM]+|[A-Z]|\d+)\s*[:.]?\s*',
            'numeral': r'(\d+)\.?\s+',
            'inciso': r'[a-h]\)\s*',
            'demanda': r'[Dd]emanda\s+d[e]\s+(.+?)(?:\n|$)',
            'formulario': r'[Ff]ormulario\s+(.+?)(?:\n|$)'
        }
        
        # Palabras clave para contextos específicos
        self.context_keywords = {
            'alimentos': ['pensión', 'alimentos', 'obligado', 'hijo', 'menor'],
            'violencia': ['violencia', 'protección', 'medida', 'agravio', 'amenaza'],
            'identidad': ['dni', 'reniec', 'nacimiento', 'inscripción', 'nombre'],
            'demanda': ['demanda', 'juzgado', 'demandante', 'demandado', 'proceso']
        }
    
    def chunk_by_legal_structure(self, content: str, document_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Divide el contenido por estructura legal (artículos, secciones, etc.)
        """
        chunks = []
        
        # Detectar tipo de documento
        doc_type = self._detect_document_type(content, document_type)
        
        if doc_type == 'codigo':
            chunks = self._chunk_legal_code(content)
        elif doc_type == 'demanda':
            chunks = self._chunk_legal_form(content)
        elif doc_type == 'manual':
            chunks = self._chunk_manual(content)
        else:
            chunks = self._chunk_general(content)
        
        # Agregar metadatos a cada chunk
        for i, chunk in enumerate(chunks):
            chunk.update({
                'chunk_id': f"{doc_type}_{i+1}",
                'document_type': doc_type,
                'chunk_type': self._identify_chunk_type(chunk['content']),
                'legal_context': self._extract_legal_context(chunk['content']),
                'cultural_relevance': self._assess_cultural_relevance(chunk['content'])
            })
        
        return chunks
    
    def _detect_document_type(self, content: str, provided_type: Optional[str] = None) -> str:
        """Detecta el tipo de documento legal"""
        if provided_type:
            return provided_type.lower()
        
        content_lower = content.lower()
        
        # Patrones para detectar tipo
        if any(word in content_lower for word in ['código civil', 'código penal', 'código procesal']):
            return 'codigo'
        elif any(word in content_lower for word in ['demanda de', 'formulario de demanda']):
            return 'demanda'
        elif any(word in content_lower for word in ['manual', 'guía', 'instructivo']):
            return 'manual'
        else:
            return 'general'
    
    def _chunk_legal_code(self, content: str) -> List[Dict[str, Any]]:
        """Chunking especializado para códigos legales"""
        chunks = []
        
        # Dividir por artículos
        articulo_pattern = re.compile(self.legal_patterns['articulo'], re.IGNORECASE | re.MULTILINE)
        matches = list(articulo_pattern.finditer(content))
        
        if not matches:
            # Fallback: dividir por párrafos
            return self._chunk_by_paragraphs(content)
        
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            chunk_content = content[start:end].strip()
            
            chunks.append({
                'content': chunk_content,
                'article_number': match.group(1) if match.groups() else str(i + 1),
                'position': i,
                'word_count': len(chunk_content.split())
            })
        
        return chunks
    
    def _chunk_legal_form(self, content: str) -> List[Dict[str, Any]]:
        """Chunking para formularios y demandas"""
        chunks = []
        
        # Dividir por secciones del formulario
        sections = re.split(r'\n(?=[A-Z][A-Z\s]{2,}:)', content)
        
        for i, section in enumerate(sections):
            if section.strip():
                chunks.append({
                    'content': section.strip(),
                    'section_name': self._extract_section_name(section),
                    'position': i,
                    'word_count': len(section.split()),
                    'is_form_field': self._is_form_field(section)
                })
        
        return chunks
    
    def _chunk_manual(self, content: str) -> List[Dict[str, Any]]:
        """Chunking para manuales y guías"""
        chunks = []
        
        # Dividir por títulos y subtítulos
        title_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
        matches = list(title_pattern.finditer(content))
        
        if not matches:
            return self._chunk_by_paragraphs(content)
        
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            chunk_content = content[start:end].strip()
            
            chunks.append({
                'content': chunk_content,
                'title_level': len(match.group(1)),
                'title': match.group(2),
                'position': i,
                'word_count': len(chunk_content.split())
            })
        
        return chunks
    
    def _chunk_general(self, content: str) -> List[Dict[str, Any]]:
        """Chunking general por párrafos"""
        return self._chunk_by_paragraphs(content)
    
    def _chunk_by_paragraphs(self, content: str, max_chunk_size: int = 1000) -> List[Dict[str, Any]]:
        """Divide por párrafos con tamaño máximo"""
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = ""
        current_position = 0
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            if len(current_chunk) + len(paragraph) <= max_chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    chunks.append({
                        'content': current_chunk.strip(),
                        'position': current_position,
                        'word_count': len(current_chunk.split())
                    })
                    current_position += 1
                current_chunk = paragraph + "\n\n"
        
        if current_chunk:
            chunks.append({
                'content': current_chunk.strip(),
                'position': current_position,
                'word_count': len(current_chunk.split())
            })
        
        return chunks
    
    def _identify_chunk_type(self, content: str) -> str:
        """Identifica el tipo de chunk"""
        content_lower = content.lower()
        
        if any(pattern in content_lower for pattern in ['artículo', 'articulo']):
            return 'article'
        elif any(pattern in content_lower for pattern in ['sección', 'seccion']):
            return 'section'
        elif any(pattern in content_lower for pattern in ['formulario', 'campo']):
            return 'form_field'
        elif any(pattern in content_lower for pattern in ['paso', 'proceso']):
            return 'procedure'
        else:
            return 'general'
    
    def _extract_legal_context(self, content: str) -> Dict[str, Any]:
        """Extrae contexto legal del chunk"""
        context = {}
        content_lower = content.lower()
        
        # Detectar temas legales
        for theme, keywords in self.context_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                context['legal_theme'] = theme
                break
        
        # Detectar urgencia
        urgency_words = ['urgente', 'inmediato', 'emergencia', 'grave', 'crítico']
        if any(word in content_lower for word in urgency_words):
            context['urgency'] = 'high'
        elif any(word in content_lower for word in ['importante', 'necesario']):
            context['urgency'] = 'medium'
        else:
            context['urgency'] = 'low'
        
        # Detectar entidades
        entities = ['juzgado', 'comisaría', 'mimp', 'reniec', 'poder judicial']
        found_entities = [entity for entity in entities if entity in content_lower]
        if found_entities:
            context['entities'] = found_entities
        
        return context
    
    def _assess_cultural_relevance(self, content: str) -> Dict[str, Any]:
        """Evalúa relevancia cultural para comunidades quechuahablantes"""
        content_lower = content.lower()
        
        cultural_indicators = {
            'quechua_terms': ['ayllu', 'comunidad', 'campesino', 'rural', 'pueblo'],
            'indigenous_rights': ['comunidad nativa', 'territorio', 'consulta previa'],
            'rural_context': ['agricultura', 'ganadería', 'comunidad', 'zona rural']
        }
        
        relevance = {}
        for category, terms in cultural_indicators.items():
            found_terms = [term for term in terms if term in content_lower]
            if found_terms:
                relevance[category] = {
                    'present': True,
                    'terms': found_terms,
                    'score': len(found_terms) / len(terms)
                }
            else:
                relevance[category] = {'present': False, 'score': 0.0}
        
        return relevance
    
    def _extract_section_name(self, section: str) -> str:
        """Extrae el nombre de la sección"""
        lines = section.split('\n')
        for line in lines:
            line = line.strip()
            if line and ':' in line and len(line) < 100:
                return line.split(':')[0].strip()
        return "Sección sin nombre"
    
    def _is_form_field(self, section: str) -> bool:
        """Verifica si es un campo de formulario"""
        field_indicators = ['nombre:', 'dni:', 'dirección:', 'teléfono:', 'firma:']
        section_lower = section.lower()
        return any(indicator in section_lower for indicator in field_indicators)

class ContextualChunker:
    """Clase principal para chunking contextual"""
    
    def __init__(self):
        self.strategy = LegalChunkingStrategy()
        logger.info("ContextualChunker inicializado")
    
    def process_document(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Procesa un documento completo con chunking contextual
        
        Args:
            content: Contenido del documento (Markdown de Docling)
            metadata: Metadatos del documento
            
        Returns:
            Lista de chunks con contexto
        """
        try:
            # Extraer tipo de documento de metadatos
            doc_type = metadata.get('document_type', metadata.get('title', ''))
            
            # Aplicar estrategia de chunking
            chunks = self.strategy.chunk_by_legal_structure(content, doc_type)
            
            # Agregar metadatos del documento a cada chunk
            for chunk in chunks:
                chunk['document_metadata'] = metadata
                chunk['processing_timestamp'] = str(Path().resolve())
            
            logger.info(f"Documento procesado: {len(chunks)} chunks generados")
            return chunks
            
        except Exception as e:
            logger.error(f"Error procesando documento: {str(e)}")
            raise
    
    def get_chunking_stats(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Obtiene estadísticas del chunking"""
        if not chunks:
            return {"total_chunks": 0}
        
        stats = {
            "total_chunks": len(chunks),
            "total_words": sum(chunk.get('word_count', 0) for chunk in chunks),
            "avg_chunk_size": sum(chunk.get('word_count', 0) for chunk in chunks) / len(chunks),
            "chunk_types": {},
            "legal_themes": {},
            "cultural_relevance": {}
        }
        
        # Contar tipos de chunks
        for chunk in chunks:
            chunk_type = chunk.get('chunk_type', 'unknown')
            stats["chunk_types"][chunk_type] = stats["chunk_types"].get(chunk_type, 0) + 1
            
            # Contar temas legales
            legal_context = chunk.get('legal_context', {})
            if 'legal_theme' in legal_context:
                theme = legal_context['legal_theme']
                stats["legal_themes"][theme] = stats["legal_themes"].get(theme, 0) + 1
        
        return stats