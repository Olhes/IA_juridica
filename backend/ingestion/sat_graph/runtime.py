"""Select the same SAT store for chat, review and backend ingestion."""
from .postgres import PostgresSATGraphStore


def runtime_sat_store():
    return PostgresSATGraphStore()
