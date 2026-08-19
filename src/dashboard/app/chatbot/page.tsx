"use client";

import { FormEvent, useRef, useState } from "react";
import styles from "./page.module.css";

type Message = {
  id: string;
  role: "user" | "bot";
  text: string;
  time: string;
};

const suggestions = [
  "En yüksek kâr payı hangi bankada?",
  "Taşıt finansmanında en uygun seçenek hangisi?",
  "Masrafsız kart kampanyaları neler?",
  "Yatırım kampanyalarını karşılaştır",
];

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

function currentTime() {
  return new Intl.DateTimeFormat("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function createMessage(role: Message["role"], text: string): Message {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    time: currentTime(),
  };
}

export default function ChatbotPage() {
  const [messages, setMessages] = useState<Message[]>([
    createMessage(
      "bot",
      "Merhaba! Katılım bankacılığı, kampanyalar ve ürün karşılaştırmaları hakkında soru sorabilirsin.",
    ),
  ]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function sendQuestion(value: string) {
    const text = value.trim();

    if (!text || isLoading) {
      return;
    }

    setError("");
    setQuestion("");
    setIsLoading(true);
    setMessages((current) => [...current, createMessage("user", text)]);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: text }),
      });

      if (!response.ok) {
        throw new Error(`Chat API ${response.status}`);
      }

      const data = (await response.json()) as { answer?: string };
      setMessages((current) => [
        ...current,
        createMessage(
          "bot",
          data.answer || "Yanıt alınamadı. Lütfen tekrar deneyin.",
        ),
      ]);
    } catch {
      setError(
        `Chatbot API'sine ulaşılamadı. Backend'in ${API_BASE_URL} adresinde açık olduğundan emin olun.`,
      );
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(question);
  }

  return (
    <main className={styles.main}>
      <section className={styles.assistantLayout}>
        {/* SOL: CHAT */}
        <section className={styles.chatPanel}>
          <div className={styles.chatTitle}>
            <div className={styles.robotMini}>✦</div>
            <h1>AI Asistanı</h1>

            <div className={styles.headerDecoration}>
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>

          <div className={styles.messages}>
            {messages.map((message) =>
              message.role === "user" ? (
                <div key={message.id} className={styles.userRow}>
                  <div className={styles.userBubble}>
                    <p>{message.text}</p>

                    <div className={styles.messageMeta}>
                      {message.time} <span>✓✓</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div key={message.id} className={styles.botRow}>
                  <div className={styles.botAvatar}>✦</div>

                  <div className={styles.botBubble}>
                    <p>{message.text}</p>

                    <div className={styles.botTime}>{message.time}</div>
                  </div>
                </div>
              ),
            )}

            {isLoading && (
              <div className={styles.botRow}>
                <div className={styles.botAvatar}>✦</div>

                <div className={styles.botBubble}>
                  <p>Yanıt hazırlanıyor...</p>
                </div>
              </div>
            )}
          </div>

          <form className={styles.inputArea} onSubmit={handleSubmit}>
            <button className={styles.plusButton} type="button">
              ＋
            </button>

            <div className={styles.inputWrapper}>
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Sorunuzu yazın..."
                disabled={isLoading}
              />

              <button
                className={styles.sendButton}
                type="submit"
                disabled={isLoading || !question.trim()}
              >
                ➤
              </button>
            </div>
          </form>

          {error && <div className={styles.errorMessage}>{error}</div>}

          <div className={styles.disclaimer}>
            🔒 Yanıtlar bilgilendirme amaçlıdır. Detaylı bilgi için lütfen
            bankanızla iletişime geçiniz.
          </div>
        </section>

        {/* SAĞ TARAF */}
        <aside className={styles.rightColumn}>
          <section className={styles.infoCard}>
            <div className={styles.infoHeading}>
              <div className={styles.bigSparkle}>✦</div>

              <div>
                <h2>AI Asistan</h2>
                <span>Yapay Zekâ Destekli</span>
              </div>
            </div>

            <div className={styles.infoContent}>
              <div>
                <p>
                  Katılım Bankacılığı ürünleri hakkında sorularınızı yanıtlar,
                  en uygun seçenekleri bulmanıza yardımcı olur.
                </p>

                <ul className={styles.features}>
                  <li>💬 7/24 Akıllı Destek</li>
                  <li>🛡 Güvenilir ve Güncel Bilgi</li>
                  <li>⚙ Size Özel Öneriler</li>
                </ul>
              </div>

              <div className={styles.robotVisual}>
                <div className={styles.robotHead}>
                  <div className={styles.robotFace}>
                    <span></span>
                    <span></span>
                  </div>
                </div>

                <div className={styles.robotBody}></div>
              </div>
            </div>
          </section>

          <section className={styles.questionsCard}>
            <div className={styles.questionsTitle}>
              <span>✦</span>
              <h2>Hazır Sorular</h2>
            </div>

            <div className={styles.questionList}>
              {suggestions.map((question) => (
                <button
                  key={question}
                  className={styles.questionButton}
                  type="button"
                  onClick={() => void sendQuestion(question)}
                  disabled={isLoading}
                >
                  <span className={styles.questionIcon}>▢</span>

                  <span>{question}</span>

                  <strong>›</strong>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
