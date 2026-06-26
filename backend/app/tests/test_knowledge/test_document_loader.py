"""Document-loader unit tests.

Verifies that CURATED_DOCUMENTS contains the synthesised research-article
findings added in Task 4 (MDPI case study + PMC trust/acceptance).
"""
from __future__ import annotations


def test_curated_documents_include_article_findings():
    from app.services.knowledge.document_loader import CURATED_DOCUMENTS

    sources = {d.source for d in CURATED_DOCUMENTS}
    assert "https://www.mdpi.com/2076-3417/11/1/313" in sources
    assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/" in sources

    trust = next(d for d in CURATED_DOCUMENTS
                 if d.source == "https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/")
    assert "explica" in trust.content.lower() or "transpar" in trust.content.lower()
