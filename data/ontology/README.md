# TEKNOFEST Katılım Bankacılığı

Oluşturulan **1241 terimlik** Terminoloji sözlüğünü ontoloji ve bilgi grafiği yapısına dönüştürür.

## Çıktılar

- Ontoloji düğümleri: 1653
- Ontoloji kenarları: 1652
- İlişki grafiği kenarları: 266
- Alias bulunan terimler: 243
- Eş anlam grupları: 243
- Intent türleri: 12
- Prompt şablonları: 8
- RAG chunk sayısı: 1241

## Dosyalar

- `ontology.json`
- `relation_graph.json`
- `knowledge_graph_triples.jsonl`
- `alias_dictionary.json`
- `reverse_alias_index.json`
- `synonym_groups.json`
- `intent_schema.json`
- `term_intent_map.json`
- `prompt_templates.json`
- `rag_keyword_index.json`
- `rag_chunks.jsonl`
- `phase3_ontology_knowledge_graph.xlsx`

## Kullanım

- NER çıktısını standart terime bağlamak için `alias_dictionary.json`
- Terimler arası ilişki çıkarmak için `relation_graph.json`
- Graph veri tabanına aktarmak için `knowledge_graph_triples.jsonl`
- Intent sınıflandırması için `intent_schema.json` ve `term_intent_map.json`
- Agent ve LLM promptları için `prompt_templates.json`
- RAG retrieval için `rag_keyword_index.json` ve `rag_chunks.jsonl`
