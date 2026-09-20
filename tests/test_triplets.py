"""Unit tests for triplet extraction and normalization."""

import json
from unittest.mock import MagicMock
from mkp_common.models import ChunkRecord
from mkp_builder.triplets import (
    TripletExtractor,
    normalize_entity_name,
    normalize_predicate,
)


def test_normalization():
    assert normalize_entity_name("  Genoa Sheet  ") == "genoa sheet"
    assert normalize_entity_name("ГРОТ ") == "грот"
    assert normalize_predicate("controlled by") == "УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ"
    assert normalize_predicate("requires action") == "ТРЕБУЕТ_ДЕЙСТВИЯ"
    assert normalize_predicate("СВЯЗАН_С") == "СВЯЗАН_С"


def test_triplet_extractor_mock():
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps({
        "triplets": [
            {
                "subject": {"name": "Mainsail", "type": "Sail", "lang": "en"},
                "predicate": "CONTROLLED_BY",
                "object": {"name": "Mainsheet", "type": "Rigging", "lang": "en"},
            },
            {
                "subject": {"name": "mainsail", "type": "Sail", "lang": "en"},
                "predicate": "CONTROLLED_BY",
                "object": {"name": "mainsheet", "type": "Rigging", "lang": "en"},
            }
        ]
    })

    extractor = TripletExtractor(client=mock_client)
    records = extractor.extract_from_text(
        text="The mainsail is trimmed using the mainsheet.",
        chunk_id="chunk_01",
        book_id="dedekam",
        page_number=42,
        location_ref="pdf:p42",
    )

    # Deduplication should reduce 2 duplicates to 1
    assert len(records) == 1
    rec = records[0]
    assert rec.subject.name == "mainsail"
    assert rec.predicate == "УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ"
    assert rec.object.name == "mainsheet"
    assert rec.provenance["chunk_id"] == "chunk_01"
    assert rec.provenance["location_ref"] == "pdf:p42"
