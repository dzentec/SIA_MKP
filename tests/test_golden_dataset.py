"""Validation tests for the 30-question Golden Dataset (REQ-QA-01)."""

import json
from pathlib import Path


def test_golden_dataset_structure_and_stratification():
    ds_file = Path("qa/golden_dataset.json")
    assert ds_file.exists(), "qa/golden_dataset.json must exist"

    with open(ds_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    # 1. Total questions
    assert len(dataset) == 30, f"Expected exactly 30 questions, got {len(dataset)}"

    # 2. Check required fields for all questions
    diagram_types = set()
    languages = set()
    books = set()
    graph_queries = 0

    for item in dataset:
        assert "id" in item
        assert "query" in item and len(item["query"]) > 10
        assert item["lang"] in ("ru", "en")
        assert "expected_book" in item
        assert "expected_page" in item
        assert "expected_location_ref" in item
        assert "must_contain_terms" in item and len(item["must_contain_terms"]) > 0

        languages.add(item["lang"])
        books.add(item["expected_book"])
        if item.get("diagram_type"):
            diagram_types.add(item["diagram_type"])

        if item.get("query_type") == "graph" or (item.get("expected_triples") and len(item["expected_triples"]) > 0):
            graph_queries += 1

    # 3. Stratification asserts
    # Diagram types: maneuver, knot, equipment, polar, map, table_figure
    expected_types = {"maneuver", "knot", "equipment", "polar", "map", "table_figure"}
    for exp_t in expected_types:
        assert exp_t in diagram_types, f"Missing diagram_type in golden dataset: {exp_t}"

    # Languages: both RU and EN present
    assert "ru" in languages and "en" in languages

    # Books: both EPUB and PDF represented
    assert "dedekam_seamanship" in books
    assert "dedekam_sail_trim" in books

    # Graph queries: >= 3
    assert graph_queries >= 3, f"Expected >= 3 graph queries, found {graph_queries}"
