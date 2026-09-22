# SIA Maritime Ontology (v0.1.0)

Domain ontology of maritime terminology, yacht archetypes, telemetry signals, operational actions, and safety failure modes for the MKP-R (Maritime Knowledge Pipeline with Rules) project.

## Structure

* `sia_ontology.yaml` — Core entities (operational domains, vessel hull archetypes, telemetry signals, actions, failure modes).
* `sia_relations.yaml` — Predicates and relation taxonomy between maritime entities, claims, and rules.
* `mapping.yaml` — Multi-lingual synonym dictionary (EN & RU) mapping natural language keywords to canonical English ontology IDs.

## Pipeline Integration

1. **Extraction (`claims.py`):** Maps extracted facts from text chunks to canonical ontology IDs.
2. **Clustering (`cluster.py`):** Groups facts by vessel archetypes and operational domains.
3. **Synthesis (`synthesize.py`):** Validates rule triggers and actions against canonical ontology schema.
4. **Server (`mkp-server`):** Powers semantic filtering in `query_rules` and knowledge graph lookups.
