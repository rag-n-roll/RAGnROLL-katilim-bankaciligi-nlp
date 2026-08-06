# Model Training Data

This directory contains the datasets prepared for training, validating, and evaluating the NLP models used in the TEKNOFEST 2026 AI Language Agents project for the Participation Banking domain.

The datasets were created using the terminology, ontology, and knowledge graph developed in the previous project phases. They serve as the primary resources for building and evaluating intent classification, named entity recognition, structured information extraction, dialogue understanding, and tool-calling capabilities.

---

## Directory Contents

| File | Description |
|------|-------------|
| `classifier_dataset.jsonl` | Training dataset for intent classification. |
| `ner_dataset.jsonl` | Annotated dataset for Named Entity Recognition (NER). |
| `extraction_dataset.jsonl` | Dataset for structured information extraction. |
| `multi_turn_dialogues.jsonl` | Multi-turn conversation dataset for dialogue understanding. |
| `tool_calling_examples.jsonl` | Tool-calling examples for AI agent workflows. |
| `golden_evaluation_set.jsonl` | Benchmark dataset used for model evaluation and regression testing. |
| `label_schema.json` | Label definitions used across all datasets. |
| `quality_report.json` | Dataset quality analysis and validation report. |
| `phase4_dataset_overview.xlsx` | Human-readable overview of the generated datasets. |

---

## Dataset Summary

The datasets support multiple NLP tasks required by the project:

- Intent Classification
- Named Entity Recognition (NER)
- Structured Information Extraction
- Multi-turn Dialogue Understanding
- Tool Calling
- Model Evaluation


---

## Purpose

These datasets were prepared to support the development of an end-to-end AI language agent capable of understanding participation banking terminology, extracting structured information, retrieving domain knowledge, and generating accurate responses.

The data is intended for:

- Training NLP models
- Fine-tuning Large Language Models (LLMs)
- Benchmark evaluation
- Retrieval-Augmented Generation (RAG)
- Multi-agent workflows
  
