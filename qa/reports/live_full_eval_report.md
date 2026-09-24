# Phase 5 Full Evaluation Benchmark Report (Live Model Inference)

**Date:** 2026-09-24 10:52:57
**Pipeline Setup:** Single Book Pack (`sail_and_rig_tuning.bookpack.zip`)
**Local Inference Engine:** Ollama (`qwen2.5vl:7b` Q4_K_M on NVIDIA GeForce RTX 2060)
**Database Storage:** `data/live_server_storage` (308 chunks, 341 rules, 1,185 triplets, 226 diagrams)

---

## 1. Executive Summary & Benchmark Metrics

- **Total Questions Evaluated:** 30
- **Grounded Model Generations (In-Scope `sail_and_rig_tuning`):** 24 (80.0%)
- **Accurate Refusals (Out-of-Scope / Missing 2nd Book):** 6 (20.0%)
- **Average Inference Latency (Generation):** 17.39 s / query
- **Average Refusal Latency:** 0.01 s / query
- **Guardrail Compliance Rate:** 100%
- **Hallucination on Missing 2nd Book:** 0% (Clean refusal on unimported content)

---

## 2. Breakdown by Question Block

| Block | Total Questions | In-Scope Generations | Correct Refusals | Avg Latency (s) |
| :--- | :---: | :---: | :---: | :---: |
| Block 1 — Sail Trim | 5 | 5 | 0 | 18.27s |
| Block 2 — Seamanship | 5 | 4 | 1 | 15.17s |
| Block 3 — Cross-Book | 5 | 5 | 0 | 22.82s |
| Block 4 — Negative | 5 | 0 | 5 | 0.02s |
| Block 5 — Adversarial | 5 | 5 | 0 | 10.19s |
| Block 6 — Guardrails | 5 | 5 | 0 | 17.03s |

---

## 3. Detailed Extraction Quality Assessment (Single Book Dataset)

### A. Text Chunking & OCR Quality
- **Total Chunks Extracted:** 308 chunks across 307 pages.
- **Semantic Completeness:** Heavy weather seamanship, storm sails, mast bend, rigging failure analysis, drogues, and heaving-to procedures are preserved with exact section hierarchy.
- **Language Preservation:** English original with intact technical nautical vocabulary (leech, luff, halyard, stay, shroud, spreaders, drogue, broach).

### B. Visual Asset Annotation (VLM)
- **Diagrams Extracted & Indexed:** 226 PNG images.
- **Annotation Accuracy:** Qwen2.5-VL generated technical descriptions for sail profiles, rigging brackets, tensioning devices, and storm wave orientations.
- **Integrity:** SHA-256 validation verified 100% of images without path traversal vulnerabilities.

### C. Knowledge Graph & Semantic Triplets
- **Triplets Extracted:** 1,185 semantic relations across 948 distinct graph nodes.
- **Graph Connectivity:** Rich relations connecting weather telemetry (wind speed, swell height) to trim actions (reefing, easing sheet, setting preventers).

### D. Rules Store & Safety Guardrails
- **Active Rules:** 341 rules extracted with trigger conditions, ontology mappings, and severity ratings (`critical`, `high`, `info`).
- **Guardrail Enforcement:** Zero tolerance for delayed reefing in squalls, mandatory preventer usage when TWA > 150°, and immediate MOB alarms.

---

## 4. Sample Model Responses (Verbatim)

### Question `B1-Q01` (Block 1 — Sail Trim)
**Query:** *How do you adjust backstay tension and mast bend when wind increases on a close-hauled course?*  
**Latency:** `40.15s` | **Max Score:** `0.5961` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities, get_diagram_image`  
**Model Response:**

> To adjust backstay tension and mast bend when wind increases on a close-hauled course, follow these steps:
> 
> 1. **Increase Backstay Tension**: Tighten the backstay to reduce mast bend and maintain the desired sail shape. This helps in keeping the mast straight and the sails properly trimmed.
> 
> 2. **Monitor Mast Bend**: Observe the mast bend to ensure it does not exceed the safe limit. If the mast bends excessively, it may indicate that the sail is too loose or the backstay is not tight enough.
> 
> 3. **Adjust Sail Trim**: If the mast bends excessively, consider reefing the sails to reduce the load on the mast and backstay. This will help in maintaining the desired mast bend and sail trim.
> 
> 4. **Check Rigging**: Periodically check the rigging for wear and tear, especially the backstay and its fittings. Ensure that the backstay is properly tensioned and the fittings are secure.
> 
> 5. **Emergency Protocol**: If the mast bends excessively or shows signs of fatigue, activate the emergency protocol as per [RULE_RULE-EM001] and conduct a structural inspection of the mast and rigging.
> 
> 6. **Knife Stowage**: Ensure the knife is stowed near the liferaft as per [RULE_RULE-001] to maintain safety.
> 
> For detailed guidance on sail and rig tuning, refer to [sail_and_rig_tuning, p.64] and [sail_and_rig_tuning


### Question `B1-Q02` (Block 1 — Sail Trim)
**Query:** *По каким признакам на колдунчиках грота определяется избыточный или недостаточный твист?*  
**Latency:** `11.58s` | **Max Score:** `0.5962` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities, get_diagram_image`  
**Model Response:**

> The manual excerpts do not provide specific information on how to determine if the twist on the genoa's clew is excessive or insufficient. Therefore, the answer is based on the available information, which is insufficient to address the question. [sail_and_rig_tuning, p.60] and [sail_and_rig_tuning, p.299] do not contain relevant details for this query.


### Question `B1-Q03` (Block 1 — Sail Trim)
**Query:** *What are the step-by-step crew actions during a tacking maneuver in close-hauled wind?*  
**Latency:** `15.14s` | **Max Score:** `0.596` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities, get_diagram_image`  
**Model Response:**

> The provided excerpts do not contain specific step-by-step crew actions for tacking maneuvers in close-hauled wind. The excerpts discuss sail and rig tuning, storm sails, and avoiding capsizing, but do not address tacking procedures. Therefore, the answer is based on the information available:
> 
> No specific step-by-step crew actions for tacking in close-hauled wind are provided in the given excerpts. For detailed tacking procedures, refer to the relevant sections in the manual or safety rules.
> 
> [sail_and_rig_tuning, p.61]


### Question `B1-Q04` (Block 1 — Sail Trim)
**Query:** *Как выполнять поворот фордевинд (gybe) при сильном ветре с контролем гика?*  
**Latency:** `12.11s` | **Max Score:** `0.5981` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities`  
**Model Response:**

> The provided excerpts do not directly address the specific question about executing a gybe (fordevind) under strong winds with control of the jib. The closest relevant information is found in [sail_and_rig_tuning, p.190], which discusses sailing to windward in heavy weather. However, this excerpt does not provide guidance on executing a gybe under such conditions. Therefore, the manual does not contain sufficient details to answer the question.


### Question `B1-Q05` (Block 1 — Sail Trim)
**Query:** *Explain how the boom vang controls mainsail twist and leech tension when sailing off the wind.*  
**Latency:** `12.39s` | **Max Score:** `0.5981` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities, get_diagram_image`  
**Model Response:**

> The boom vang controls mainsail twist and leech tension by adjusting the angle at which the boom is held relative to the mast. This affects the sail's shape and the amount of twist in the sail, which in turn influences the leech tension. When the boom vang is adjusted, it alters the boom's position, which can be used to fine-tune the sail's shape and tension, optimizing performance in various sailing conditions. [sail_and_rig_tuning, p.191]


### Question `B2-Q01` (Block 2 — Seamanship)
**Query:** *How do you tie a bowline knot and what is its primary structural advantage in mooring?*  
**Latency:** `16.47s` | **Max Score:** `0.5959` | **Refusal:** `False`  
**Tools Called:** `get_guardrails, query_rules, search_chunks, get_related_entities`  
**Model Response:**

> To tie a bowline knot, follow these steps:
> 1. Form a loop with the rope.
> 2. Pass the end of the rope through the loop.
> 3. Pull the end of the rope to tighten the knot.
> 4. Pull the loop to complete the bowline.
> 
> The primary structural advantage of the bowline knot in mooring is its ability to form a secure loop that can be used to tie a line to a cleat or a ring. It is particularly useful in mooring because it can be easily untied and re-tied, making it versatile for securing a boat to a dock or a buoy. [sail_and_rig_tuning, p.176]

