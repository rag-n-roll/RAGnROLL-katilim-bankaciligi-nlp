"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import {
  streamChat,
  type ChatMeta,
  type ChatGeneration,
  type ChatSource,
  type StreamEventInfo,
} from "../../services/api";
import {
  applyActiveChatUpdate,
  applyStreamEvent,
  createStreamState,
  isActiveChatRequest,
  nextChatRequestToken,
  resetChatSession,
} from "./sessionGuard.js";

type MessageExchange = {
  question: string;
  answer: string;
  streaming?: boolean;
  meta?: ChatMeta;
  generation?: ChatGeneration;
  error?: string;
  time?: string;
  sources?: ChatSource[];
};

const SUGGESTIONS = [
  "Türkiye'deki katılım bankalarını sayar mısın?",
  "Kuveyt Türk kampanyalarında hangi avantajlar var?",
  "Murabaha nedir?",
  "Katılım bankacılığında kâr payı havuzu nasıl işler?",
  "Masrafsız kart ve hesap seçenekleri nelerdir?",
  "Konut finansmanında katılım bankacılığı ilkeleri nelerdir?",
];

const CONNECTION_ERROR =
  "Bağlantı kurulamadı. Lütfen kısa süre sonra yeniden deneyin; güncel finansal bilgi için bankanızın resmî kanalını kullanın.";

function generationLabel(generation?: ChatGeneration) {
  if (!generation) return "Kaynaklar hazırlanıyor";
  return generation.mode === "llm"
    ? "Kanıta bağlı üretim"
    : "Güvenli doğrulanmış yanıt";
}

export default function ChatbotPage() {
  const [exchanges, setExchanges] = useState<MessageExchange[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [requestToken, setRequestToken] = useState(0);

  const activeController = useRef<AbortController | null>(null);
  const currentTokenRef = useRef(0);
  const messageInput = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    currentTokenRef.current = requestToken;
  }, [requestToken]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges]);

  const handleResetChat = () => {
    activeController.current?.abort();
    activeController.current = null;
    const reset = resetChatSession(currentTokenRef.current);
    currentTokenRef.current = reset.requestToken;
    setRequestToken(reset.requestToken);
    setExchanges(reset.exchanges as MessageExchange[]);
    setInput(reset.message);
    setLoading(reset.loading);
    if (reset.focusInput) {
      requestAnimationFrame(() => messageInput.current?.focus());
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const message = (textToSend ?? input).trim();
    if (!message || loading) return;

    setInput("");
    setLoading(true);

    const token = nextChatRequestToken(currentTokenRef.current);
    currentTokenRef.current = token;
    setRequestToken(token);

    const timeString = new Date().toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const newExchange: MessageExchange = {
      question: message,
      answer: "",
      streaming: true,
      time: timeString,
    };

    setExchanges((prev) => [...prev, newExchange]);

    const controller = new AbortController();
    activeController.current = controller;
    let streamState = createStreamState(token);
    let completed = false;

    try {
      await streamChat(
        message,
        {
          onMeta: (meta: ChatMeta) => {
            if (!isActiveChatRequest(currentTokenRef.current, token)) return;
            setExchanges((curr) =>
              applyActiveChatUpdate(currentTokenRef.current, token, curr, (items: MessageExchange[]) => {
                return items.map((item, idx) =>
                  idx === items.length - 1
                    ? { ...item, meta, sources: meta.sources }
                    : item
                );
              })
            );
          },
          onDelta: (text: string, eventInfo?: StreamEventInfo) => {
            if (!isActiveChatRequest(currentTokenRef.current, token)) return;
            const event = {
              requestId: eventInfo?.requestId ?? null,
              eventId: eventInfo?.eventId ?? `delta-${Date.now()}`,
              sequence: eventInfo?.sequence ?? (streamState.lastSequence + 1),
              text,
            };
            streamState = applyStreamEvent(streamState, token, event);
            setExchanges((curr) =>
              applyActiveChatUpdate(currentTokenRef.current, token, curr, (items: MessageExchange[]) => {
                return items.map((item, idx) =>
                  idx === items.length - 1
                    ? { ...item, answer: streamState.answer }
                    : item
                );
              })
            );
          },
          onReplace: (text: string, eventInfo?: StreamEventInfo) => {
            if (!isActiveChatRequest(currentTokenRef.current, token)) return;
            streamState = {
              ...streamState,
              answer: text,
              seenEventIds: eventInfo?.eventId
                ? new Set(streamState.seenEventIds).add(eventInfo.eventId)
                : streamState.seenEventIds,
              lastSequence: eventInfo?.sequence ?? streamState.lastSequence,
            };
            setExchanges((curr) =>
              applyActiveChatUpdate(currentTokenRef.current, token, curr, (items: MessageExchange[]) => {
                return items.map((item, idx) =>
                  idx === items.length - 1
                    ? { ...item, answer: text }
                    : item
                );
              })
            );
          },
          onDone: (generation: ChatGeneration) => {
            if (!isActiveChatRequest(currentTokenRef.current, token)) return;
            completed = true;
            setExchanges((curr) =>
              applyActiveChatUpdate(currentTokenRef.current, token, curr, (items: MessageExchange[]) => {
                return items.map((item, idx) =>
                  idx === items.length - 1
                    ? { ...item, streaming: false, generation }
                    : item
                );
              })
            );
          },
        },
        controller.signal
      );
    } catch (reason) {
      const stopped = reason instanceof DOMException && reason.name === "AbortError";
      const error = stopped
        ? "Yanıt akışı kullanıcı tarafından durduruldu."
        : reason instanceof Error &&
            reason.message &&
            reason.message !== "Failed to fetch" &&
            !reason.message.includes("fetch failed")
          ? reason.message
          : CONNECTION_ERROR;

      if (!completed) {
        if (isActiveChatRequest(currentTokenRef.current, token)) {
          setExchanges((curr) =>
            applyActiveChatUpdate(currentTokenRef.current, token, curr, (items: MessageExchange[]) => {
              return items.map((item, idx) =>
                idx === items.length - 1 && item.streaming
                  ? {
                      ...item,
                      answer: "",
                      generation: undefined,
                      streaming: false,
                      error,
                    }
                  : item
              );
            })
          );
        }
      }
    } finally {
      if (isActiveChatRequest(currentTokenRef.current, token)) {
        setLoading(false);
        activeController.current = null;
      }
    }
  };

  return (
    <main className={styles.main}>
      <section className={styles.assistantLayout}>
        <section className={styles.pageHeader}>
          <span className={styles.headerAiIcon} aria-hidden="true">
            ✦
          </span>
          <div className={styles.headerCopy}>
            <h1>Pusula AI</h1>
            <p>Katılım bankacılığında akıllı karar asistanınız</p>
          </div>
        </section>

        <section className={styles.chatPanel}>
          <div className={styles.messages} role="log" aria-live="polite">
            {exchanges.map((exchange, index) => (
              <div key={index} style={{ display: "contents" }}>
                <div className={styles.userRow}>
                  <div className={styles.userBubble}>
                    <p>{exchange.question}</p>
                    <div className={styles.messageMeta}>
                      {exchange.time ?? "Şimdi"} <span>✓✓</span>
                    </div>
                  </div>
                </div>

                <div className={styles.botRow}>
                  <div className={styles.botAvatar} aria-hidden="true">
                    ✦
                  </div>
                  <div className={styles.botBubble}>
                    {exchange.error ? (
                      <p style={{ color: "#b91c1c" }}>{exchange.error}</p>
                    ) : (
                      <p style={{ whiteSpace: "pre-line" }}>
                        {exchange.answer || (exchange.streaming ? "Yanıt hazırlanıyor..." : "")}
                      </p>
                    )}

                    {exchange.generation && (
                      <div style={{ marginTop: "6px", fontSize: "12px", opacity: 0.8 }}>
                        <small>{generationLabel(exchange.generation)}</small>
                      </div>
                    )}

                    {exchange.sources && exchange.sources.length > 0 && (
                      <div className={styles.sourcesBlock}>
                        <strong>Kaynak Kampanyalar:</strong>
                        <div className={styles.sourcesList}>
                          {exchange.sources.map((source, sIndex) => (
                            <span className={styles.sourceBadge} key={sIndex}>
                              {source.bank_name ? `${source.bank_name} – ` : ""}
                              {source.title ?? "Kampanya"}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className={styles.botTime}>{exchange.time ?? "Şimdi"}</div>
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className={styles.inputArea}>
            <button
              type="button"
              aria-label="Hazır soruları aç veya kapat"
              className={styles.plusButton}
              onClick={() => setShowSuggestions((shown) => !shown)}
            >
              ＋
            </button>

            <div className={styles.inputWrapper}>
              <label htmlFor="chat-message" style={{ display: "none" }}>
                Sorunuz
              </label>
              <input
                id="chat-message"
                ref={messageInput}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSendMessage();
                }}
                type="text"
                placeholder="Sorunuzu yazın..."
                disabled={loading}
              />
              <button
                type="button"
                aria-label="Mesajı gönder"
                onClick={() => handleSendMessage()}
                className={styles.sendButton}
                disabled={loading}
              >
                ➤
              </button>
            </div>
          </div>

          <div className={styles.disclaimer}>
            Kanıta bağlı üretim. Yanıtlar bilgilendirme amaçlıdır. Detaylı bilgi için
            lütfen bankanızla iletişime geçiniz.
          </div>

          <div className={styles.assistantBenefits}>
            <div>
              <span aria-hidden="true">✦</span>
              <strong>7/24 Akıllı Destek</strong>
              <small>İhtiyacınız olduğunda yanınızda</small>
            </div>
            <div>
              <span aria-hidden="true">✓</span>
              <strong>Güvenilir ve Güncel Bilgi</strong>
              <small>Veriye dayalı anlaşılır yanıtlar</small>
            </div>
            <div>
              <span aria-hidden="true">⌁</span>
              <strong>Size Özel Öneriler</strong>
              <small>Tercihlerinize uygun seçenekler</small>
            </div>
          </div>
        </section>

        <aside className={styles.aiSideRail}>
          <section className={styles.aiMarkCard}>
            <div className={styles.aiMarkOrbit} aria-hidden="true">
              <span>✦</span>
              <i>AI</i>
            </div>
            <h2>Pusula AI</h2>
            <p>Finansal kararlarınız için akıllı yol arkadaşınız.</p>
            <button
              type="button"
              className={styles.resetChatButton}
              aria-label="Yeni sohbet başlat"
              onClick={handleResetChat}
            >
              Yeni sohbet
            </button>
          </section>

          {showSuggestions && (
            <section className={styles.quickQuestions}>
              <div className={styles.quickQuestionsTitle}>
                <span aria-hidden="true">✦</span>
                <strong>Hazır Sorular</strong>
              </div>
              <div className={styles.quickQuestionList}>
                {SUGGESTIONS.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => handleSendMessage(question)}
                  >
                    <span>{question}</span>
                    <span aria-hidden="true">›</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </aside>
      </section>
    </main>
  );
}
