"""Contrato ligero para conservar JSON Docling sin importar modelos OCR al arrancar."""

from dataclasses import dataclass
import inspect


@dataclass(frozen=True)
class ConversionArtifact:
    markdown: str
    docling_document: dict | None = None


async def convert_for_ingestion(processor, pdf_path: str) -> ConversionArtifact:
    # getattr_static evita que mocks/proxies inventen una capacidad inexistente.
    if callable(inspect.getattr_static(processor, "process_pdf_artifact", None)):
        artifact = await processor.process_pdf_artifact(pdf_path)
    else:
        artifact = ConversionArtifact(
            await processor.process_pdf(pdf_path, write_output=False)
        )
    if not isinstance(artifact, ConversionArtifact) or not isinstance(
        artifact.markdown, str
    ):
        raise ValueError("Contrato de conversión inválido")
    if artifact.docling_document is not None and not isinstance(
        artifact.docling_document, dict
    ):
        raise ValueError("DoclingDocument debe ser un objeto JSON")
    return artifact
