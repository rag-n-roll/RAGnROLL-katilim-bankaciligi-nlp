"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ChatGeneration,
  ChatMeta,
  streamChat,
} from "../../services/api";
import styles from "../live.module.css";
import {
  applyActiveChatUpdate,
  applyStreamEvent,
  createStreamState,
  isActiveChatRequest,
  nextChatRequestToken,
  resetChatSession,
} from "./sessionGuard";

const suggestions = [
  "Türkiye'deki katılım bankalarını sayar mısın?",
  "Kuveyt Türk kampanyalarında hangi avantajlar var?",
  "Murabaha nedir?",
];

const CONNECTION_ERROR =
  "Bağlantı kurulamadı. Lütfen kısa süre sonra yeniden deneyin; güncel finansal bilgi için bankanızın resmî kanalını kullanın.";

function generationLabel(generation?: ChatGeneration) {
  if (!generation) return "Kaynaklar hazırlanıyor";
  return generation.mode === "llm"
    ? "Kanıta bağlı üretim"
    : "Güvenli doğrulanmış yanıt";
}

type Exchange = {
  question: string;
  answer: string;
  meta?: ChatMeta;
  generation?: ChatGeneration;
  streaming: boolean;
  error?: string;
};

export default function ChatbotPage() {
  const [message, setMessage] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const requestToken = useRef(0);
  const conversationEnd = useRef<HTMLDivElement | null>(null);
  const messageInput = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [exchanges]);

  function updateLatest(
    activeToken: number,
    update: (exchange: Exchange) => Exchange
  ) {
    setExchanges((items) =>
      applyActiveChatUpdate(
        requestToken.current,
        activeToken,
        items,
        (currentItems: Exchange[]) => {
          const latest = currentItems[currentItems.length - 1];
          if (!latest) return currentItems;
          return [...currentItems.slice(0, -1), update(latest)];
        }
      )
    );
  }

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || loading || controller.current) return;
    const activeToken = nextChatRequestToken(requestToken.current);
    requestToken.current = activeToken;
    const activeController = new AbortController();
    controller.current = activeController;
    setLoading(true);
    setMessage("");
    setExchanges((items) => [
      ...items,
      { question: trimmed, answer: "", streaming: true },
    ]);
    let streamState = createStreamState(activeToken);
    let completed = false;
    try {
      await streamChat(
        trimmed,
        {
          onMeta: (meta) =>
            updateLatest(activeToken, (item) => ({ ...item, meta })),
          onDelta: (text, eventInfo) => {
            const event = {
              requestId: eventInfo?.requestId ?? null,
              eventId: eventInfo?.eventId ?? `delta-${Date.now()}`,
              sequence: eventInfo?.sequence ?? (streamState.lastSequence + 1),
              text,
            };
            streamState = applyStreamEvent(streamState, activeToken, event);
            updateLatest(activeToken, (item) => ({
              ...item,
              answer: streamState.answer,
            }));
          },
          onReplace: (text, eventInfo) => {
            streamState = {
              ...streamState,
              answer: text,
              seenEventIds: eventInfo?.eventId
                ? new Set(streamState.seenEventIds).add(eventInfo.eventId)
                : streamState.seenEventIds,
              lastSequence: eventInfo?.sequence ?? streamState.lastSequence,
            };
            updateLatest(activeToken, (item) => ({ ...item, answer: text }));
          },
          onDone: (generation) => {
            if (!isActiveChatRequest(requestToken.current, activeToken)) return;
            completed = true;
            updateLatest(activeToken, (item) => ({
              ...item,
              generation,
              streaming: false,
            }));
          },
        },
        activeController.signal
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
        if (isActiveChatRequest(requestToken.current, activeToken)) {
          updateLatest(activeToken, (item) => ({
            ...item,
            answer: "",
            generation: undefined,
            streaming: false,
            error,
          }));
        }
      }
    } finally {
      if (isActiveChatRequest(requestToken.current, activeToken)) {
        setLoading(false);
        controller.current = null;
      }
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  function stop() {
    controller.current?.abort();
  }

  function resetConversation() {
    const resetState = resetChatSession(requestToken.current);
    const activeController = controller.current;
    requestToken.current = resetState.requestToken;
    controller.current = null;
    activeController?.abort();
    setExchanges(resetState.exchanges);
    setMessage(resetState.message);
    setLoading(resetState.loading);
    if (resetState.focusInput) {
      requestAnimationFrame(() => messageInput.current?.focus());
    }
  }

  return (
    <main className={styles.main} aria-busy={loading}>
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Kaynakla sınırlandırılmış üretim</span>
          <h1>Kanıta dayalı asistan</h1>
          <p>Doğrulanmış kampanya verileri ve bilgi tabanı üzerinden kanıta bağlı yanıtlar sunar.</p>
        </div>
        <div className={styles.chatHeaderActions}>
          <button
            aria-label="Yeni sohbet başlat"
            className={styles.resetChatButton}
            onClick={resetConversation}
            type="button"
          >
            Yeni sohbet
          </button>
          <span className={styles.liveStatus}><span /> Kanıta bağlı</span>
        </div>
      </header>
      <section className={styles.chatLayout}>
        <article className={`${styles.card} ${styles.chat}`}>
          <div
            className={styles.transcript}
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            aria-busy={loading}
          >
            {exchanges.length === 0 && (
              <div className={styles.chatWelcome}>
                <span className={styles.assistantMark}>RnR</span>
                <h2>Size nasıl yardımcı olabilirim?</h2>
                <p>Finansman oranlarını karşılaştırabilir, kampanya koşullarını inceleyebilir veya katılım bankacılığı terimlerini sorabilirsiniz.</p>
              </div>
            )}
            {exchanges.map((exchange, index) => (
              <div className={styles.exchange} key={`${exchange.question}-${index}`}>
                <div className={`${styles.message} ${styles.userMessage}`}>{exchange.question}</div>
                <div className={`${styles.message} ${styles.assistantMessage}`}>
                  <div className={styles.answerHeader}>
                    <span className={styles.assistantMark}>RnR</span>
                    <div>
                      <strong>RAGnROLL Asistan</strong>
                      <small>
                        {generationLabel(exchange.generation)}
                      </small>
                    </div>
                  </div>
                  {!exchange.answer && exchange.streaming && (
                    <span className={styles.typing} aria-label="Yanıt hazırlanıyor"><i /><i /><i /></span>
                  )}
                  {exchange.error && <span className={styles.inlineError} role="alert">{exchange.error}</span>}
                  {exchange.answer && (
                    <>
                      <p className={styles.answerText}>{exchange.answer}<span className={exchange.streaming ? styles.cursor : undefined} /></p>
                      {exchange.meta && (
                        <div className={styles.answerMeta}>
                          <span className={styles.badge}>{exchange.meta.plan.route}</span>
                          <span className={styles.confidence}>Güven %{Math.round(exchange.meta.confidence * 100)}</span>
                        </div>
                      )}
                      {exchange.meta?.warnings.map((warning) => <span className={`${styles.badge} ${styles.warningBadge}`} key={warning}>{warning}</span>)}
                      {!!exchange.meta?.sources.length && (
                        <details className={styles.sources}>
                          <summary>{exchange.meta.sources.length} kanıt kaynağını görüntüle</summary>
                          <div className={styles.sourceGrid}>
                            {exchange.meta.sources.map((source, sourceIndex) => source.source_url ? (
                              <a className={styles.sourceCard} href={source.source_url} key={`${source.source_url}-${sourceIndex}`} rel="noreferrer" target="_blank"><span>K{sourceIndex + 1}</span><div><strong>{source.bank_name || source.title || source.campaign_id}</strong><small>Resmî kaynağı aç ↗</small></div></a>
                            ) : (
                              <div className={styles.sourceCard} key={`${source.term_id}-${sourceIndex}`}><span>K{sourceIndex + 1}</span><div><strong>{source.title || source.term_id}</strong><small>Yerel terminoloji kaydı</small></div></div>
                            ))}
                          </div>
                        </details>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
            <div ref={conversationEnd} />
          </div>
          <form className={styles.chatControls} onSubmit={submit}>
            <label className={styles.visuallyHidden} htmlFor="chat-message">Sorunuz</label>
            <textarea className={styles.chatInput} id="chat-message" maxLength={4000} minLength={1} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!loading) void ask(message); } }} placeholder="Katılım bankacılığı hakkında sorunuzu yazın…" ref={messageInput} rows={2} value={message} />
            {loading ? (
              <button className={styles.stopButton} onClick={stop} type="button">Durdur</button>
            ) : (
              <button className={styles.sendButton} disabled={!message.trim()} type="submit" aria-label="Gönder">↑</button>
            )}
          </form>
          <p className={styles.disclaimer}>Yanıtlar bilgilendirme amaçlıdır; güncel koşulları bankanın resmî kanalından doğrulayın.</p>
        </article>
        <aside className={`${styles.card} ${styles.suggestionPanel}`}>
          <span className={styles.eyebrow}>Başlangıç önerileri</span>
          <h2>Ne sorabilirsiniz?</h2>
          <div className={styles.list}>
            {suggestions.map((question) => <button className={styles.listButton} disabled={loading} key={question} onClick={() => void ask(question)} type="button">{question}</button>)}
          </div>
          <div className={styles.safetyNote}><strong>Kanıt koruması</strong><p>Üretim servisine ulaşılamazsa veya kaynak dışı yanıt oluşursa doğrulanmış yerel cevap otomatik gösterilir.</p></div>
        </aside>
      </section>
    </main>
  );
}
