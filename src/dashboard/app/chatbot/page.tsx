"use client";

import { FormEvent, useState } from "react";
import { sendChat } from "../../services/api";
import styles from "../live.module.css";

const suggestions = [
  "Faizsiz ev finansmanında en düşük oran hangisi?",
  "Kuveyt Türk ile Albaraka Türk taşıt finansmanını karşılaştır",
  "Murabaha nedir?",
];

type Answer = Awaited<ReturnType<typeof sendChat>>;
type Exchange = { question: string; response?: Answer; error?: string };

export default function ChatbotPage() {
  const [message, setMessage] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(false);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setExchanges((items) => [...items, { question: trimmed }]);
    try {
      const response = await sendChat(trimmed);
      setExchanges((items) => [
        ...items.slice(0, -1),
        { question: trimmed, response },
      ]);
    } catch (reason) {
      const error = reason instanceof Error ? reason.message : "Yanıt üretilemedi.";
      setExchanges((items) => [...items.slice(0, -1), { question: trimmed, error }]);
    } finally {
      setLoading(false);
      setMessage("");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <h1>Kanıta dayalı asistan</h1>
          <p>Kesin ve karşılaştırmalı sorular yapılandırılmış veriye; tanım soruları kaynak metinlere yönlendirilir.</p>
        </div>
      </header>
      <section className={styles.grid}>
        <article className={`${styles.card} ${styles.chat}`} aria-live="polite">
          {exchanges.length === 0 && <p className={styles.status}>Bir soru yazın veya hazır sorulardan birini seçin.</p>}
          {exchanges.map((exchange, index) => (
            <div key={`${exchange.question}-${index}`}>
              <div className={`${styles.message} ${styles.userMessage}`}>{exchange.question}</div>
              <div className={styles.message}>
                {!exchange.response && !exchange.error && "Kaynaklar taranıyor…"}
                {exchange.error && <span role="alert">{exchange.error}</span>}
                {exchange.response && (
                  <>
                    <strong>{exchange.response.plan.route} · güven %{Math.round(exchange.response.confidence * 100)}</strong>
                    <p>{exchange.response.answer}</p>
                    {exchange.response.warnings.map((warning) => <span className={`${styles.badge} ${styles.warningBadge}`} key={warning}>{warning}</span>)}
                    {exchange.response.sources.map((source, sourceIndex) => source.source_url ? (
                      <a className={styles.source} href={source.source_url} key={`${source.source_url}-${sourceIndex}`} rel="noreferrer" target="_blank">Kaynak {sourceIndex + 1}: {source.bank_name || source.title || source.campaign_id}</a>
                    ) : (
                      <span className={styles.source} key={`${source.term_id}-${sourceIndex}`}>Terminoloji kaynağı: {source.title || source.term_id}</span>
                    ))}
                  </>
                )}
              </div>
            </div>
          ))}
          <form className={styles.controls} onSubmit={submit}>
            <input className={styles.input} aria-label="Sorunuz" maxLength={4000} minLength={1} onChange={(event) => setMessage(event.target.value)} placeholder="Sorunuzu yazın…" value={message} />
            <button className={styles.button} disabled={loading || !message.trim()} type="submit">Gönder</button>
          </form>
        </article>
        <aside className={styles.card}>
          <h2>Hazır sorular</h2>
          <div className={styles.list}>
            {suggestions.map((question) => <button className={styles.listButton} disabled={loading} key={question} onClick={() => void ask(question)} type="button">{question}</button>)}
          </div>
          <p className={styles.muted} style={{ marginTop: 16 }}>Yanıtlar bilgilendirme amaçlıdır. Sistem müşteri işlemi yapmaz ve kaynakta olmayan sayısal değeri tamamlamaz.</p>
        </aside>
      </section>
    </main>
  );
}
