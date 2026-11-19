"""
Módulo de Context Engineering - Sistema de chunking y prompts contextualizados
Coordina procesamiento de documentos con sensibilidad cultural y legal
"""

from .chunking_strategies import ContextualChunker, LegalChunkingStrategy
from .prompt_templates import format_legal_context, get_legal_system_prompt
from .context_engineering import ContextEngineer

__all__ = [
    'ContextualChunker',
    'LegalChunkingStrategy', 
    'format_legal_context',
    'get_legal_system_prompt',
    'ContextEngineer'
]
