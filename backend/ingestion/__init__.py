# Importar de forma lazy para evitar errores circulares
__all__ = ["LegalPDFProcessor", "LegalIngestionPipeline"]

def __getattr__(name):
    if name == "LegalPDFProcessor":
        from .docling_processor import LegalPDFProcessor
        return LegalPDFProcessor
    elif name == "LegalIngestionPipeline":
        from .pipeline import LegalIngestionPipeline
        return LegalIngestionPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
