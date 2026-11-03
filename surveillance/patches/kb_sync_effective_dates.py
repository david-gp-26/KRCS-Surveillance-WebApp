"""Knowledge Base chunks gain valid_from / valid_to (effective dates filtered inside Qdrant)."""
from surveillance.knowledge_base import sync_all_payloads


def execute():
	sync_all_payloads()
