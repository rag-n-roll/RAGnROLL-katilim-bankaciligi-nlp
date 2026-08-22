"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ChatGeneration,
  ChatMeta,
  streamChat,
} from "../../services/api";
import styles from "../live.module.css";

const suggestions = [
  "Faizsiz ev finansmanında en düşük oran hangisi?",
  "Kuveyt Türk ile Albaraka Türk taşıt finansmanını karşılaştır",
  "Murabaha nedir?",
];

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
  const conversationEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [exchanges]);

  function updateLatest(update: (exchange: Exchange) => Exchange) {
    setExchanges((items) => [
      ...items.slice(0, -1),
      update(items[items.length - 1]),
    ]);
  }

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setMessage("");
    setExchanges((items) => [
      ...items,
      { question: trimmed, answer: "", streaming: true },
    ]);
    controller.current = new AbortController();
    try {
      await streamChat(
        trimmed,
        {
          onMeta: (meta) => updateLatest((item) => ({ ...item, meta })),
          onDelta: (text) =>
            updateLatest((item) => ({ ...item, answer: item.answer + text })),
          onReplace: (text) =>
            updateLatest((item) => ({ ...item, answer: text })),
          onDone: (generation) =>
            updateLatest((item) => ({
              ...item,
              generation,
              streaming: false,
            })),
        },
        controller.current.signal
      );
    } catch (reason) {
      const stopped = reason instanceof DOMException && reason.name === "AbortError";
      const error = stopped
        ? "Yanıt akışı kullanıcı tarafından durduruldu."
        : reason instanceof Error
          ? reason.message
          : "Yanıt üretilemedi.";
      updateLatest((item) => ({ ...item, streaming: false, error }));
    } finally {
      setLoading(false);
      controller.current = null;
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  function stop() {
    controller.current?.abort();
  }

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <h1>Kanıta dayalı asistan</h1>
          <p>Gemma yanıtları doğrulanmış kampanya verileri ve yerel bilgi tabanı üzerinden gerçek zamanlı yazar.</p>
        </div>
        <span className={styles.liveStatus}><span /> Yerel ve gizli</span>
      </header>
      <section className={styles.chatLayout}>
        <article className={`${styles.card} ${styles.chat}`} aria-live="polite">
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
                      {exchange.generation?.mode === "llm"
                        ? "Gemma · kanıta bağlı üretim"
                        : exchange.generation
                          ? "Güvenli yerel yanıt"
                          : "Kaynaklar hazırlanıyor"}
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
          <form className={styles.chatControls} onSubmit={submit}>
            <textarea className={styles.chatInput} aria-label="Sorunuz" maxLength={4000} minLength={1} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!loading) void ask(message); } }} placeholder="Katılım bankacılığı hakkında sorunuzu yazın…" rows={2} value={message} />
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
          <div className={styles.safetyNote}><strong>Kanıt koruması</strong><p>Model ulaşılamazsa veya kaynak dışı yanıt üretirse doğrulanmış yerel cevap otomatik gösterilir.</p></div>
        </aside>
      </section>
    </main>
  );
}
