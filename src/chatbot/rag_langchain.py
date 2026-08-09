"""
Teknofest Katılım Bankacılığı RAG Pipeline
LangChain 1.x + Ollama + Chroma
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM

# Ayarlar
OLLAMA_MODEL = "gemma2"
EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


class LangChainRAG:
    def __init__(self):
        print("Embedding modeli yükleniyor...")

        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL
        )

        print("Ollama bağlanıyor...")

        self.llm = OllamaLLM(
            model=OLLAMA_MODEL,
            temperature=0.1
        )

        print("Chroma hazırlanıyor...")

        self.vector_store = Chroma(
            collection_name="katilim_bankaciligi",
            embedding_function=self.embeddings,
            persist_directory="./chroma_db"
        )

    def add_texts(self, texts, metadatas=None):
        documents = []

        for i, text in enumerate(texts):
            metadata = {}

            if metadatas:
                metadata = metadatas[i]

            documents.append(
                Document(
                    page_content=text,
                    metadata=metadata
                )
            )

        self.vector_store.add_documents(documents)

        print("Veriler eklendi.")

    def ask_question(self, question):
        docs = self.vector_store.similarity_search(
            question,
            k=3
        )

        context = "\n\n".join(
            [
                doc.page_content
                for doc in docs
            ]
        )

        prompt = f"""
Sen katılım bankacılığı uzmanı bir asistansın.

Sadece aşağıdaki bağlamı kullan.

Bağlam dışında bilgi verme.

Eğer cevap bağlamda yoksa:
"Bu bilgi sağlanan dokümanlarda bulunmamaktadır."
de.

Bağlam:

{context}

Soru:

{question}

Cevap:
"""

        answer = self.llm.invoke(prompt)

        return answer


if __name__ == "__main__":
    rag = LangChainRAG()

    rag.add_texts(
        texts=[
            """
            Ziraat Katılım, çiftçilere özel tarım finansmanı kampanyası
            başlatmıştır. Bu finansman kâr payı esaslıdır.
            """
        ],
        metadatas=[
            {
                "banka": "Ziraat Katılım",
                "kategori": "Tarım"
            }
        ]
    )

    print("\nSoru soruluyor...\n")

    cevap = rag.ask_question("İcara nedir?")

    print("CEVAP:")
    print(cevap)
