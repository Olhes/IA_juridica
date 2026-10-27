"""Catálogo editorial de fuentes oficiales, distinto del contenido normativo."""

import json
from pathlib import Path
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).with_name("peru_resources.json")


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Versión de catálogo no soportada")
    resources = catalog["resources"]
    ids = [resource["id"] for resource in resources]
    if len(ids) != len(set(ids)):
        raise ValueError("Identificadores de recurso duplicados")
    for resource in resources:
        url = urlsplit(resource["url"])
        host = url.hostname or ""
        if url.scheme != "https" or not (
            host == "gob.pe"
            or host.endswith(".gob.pe")
            or host == "elperuano.pe"
            or host.endswith(".elperuano.pe")
        ):
            raise ValueError("El catálogo solo admite fuentes oficiales HTTPS")
        if not resource["topics"] or resource["kind"] not in {
            "norm",
            "service",
            "directory",
        }:
            raise ValueError("Recurso sin tema o tipo válido")
    return resources
