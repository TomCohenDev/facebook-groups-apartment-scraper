"""Optional LLM-based extraction — falls back gracefully if not configured."""
from __future__ import annotations

from app.classifier.apartment_rules import ApartmentExtraction, extract_apartment


def extract_with_llm(text: str) -> ApartmentExtraction:
    # LLM extraction is optional. The rules-based extractor is the default.
    # To enable LLM: implement an Anthropic/OpenAI call here, parse the JSON
    # response into ApartmentExtraction.
    return extract_apartment(text)
