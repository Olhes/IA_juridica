"""
Módulo de Context Engineering - Sistema de chunking y prompts contextualizados
Coordina procesamiento de documentos con sensibilidad cultural y legal
"""

from .chunking_strategies import ContextualChunker, LegalChunkingStrategy
from .prompt_templates import PromptManager, LegalPromptTemplates, PromptType
from .context_engineering import ContextEngineer

__all__ = [
    'ContextualChunker',
    'LegalChunkingStrategy', 
    'PromptManager',
    'LegalPromptTemplates',
    'PromptType',
    'ContextEngineer'
]
