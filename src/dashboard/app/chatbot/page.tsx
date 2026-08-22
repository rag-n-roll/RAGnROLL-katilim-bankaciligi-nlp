"use client";

import { useState } from "react";
import styles from "./page.module.css";

const suggestions = [
  "En yüksek kâr payı hangi bankada?",
  "Taşıt finansmanında en uygun seçenek hangisi?",
  "Masrafsız kart kampanyaları neler?",
  "Yatırım kampanyalarını karşılaştır",
  "Konut finansmanında en uzun vade hangi bankada?",
  "Süresi yakında dolacak kampanyaları göster",
  "Bana uygun katılma hesabını nasıl seçebilirim?",
];

export default function ChatbotPage() {
  const [input, setInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [sentMessages, setSentMessages] = useState<string[]>([]);
  const sendMessage = () => {
    const value = input.trim();
    if (!value) return;
    setSentMessages((messages) => [...messages, value]);
    setInput("");
  };

  return (
    <main className={styles.main}>
      <section className={styles.assistantLayout}>
        <section className={styles.pageHeader}>
          <span className={styles.headerAiIcon}>✦</span>
          <div className={styles.headerCopy}><h1>Pusula AI</h1><p>Katılım bankacılığında akıllı karar asistanınız</p></div>
        </section>
        {/* SOL: CHAT */}
        <section className={styles.chatPanel}>
          <div className={styles.messages}>
            <div className={styles.userRow}>
              <div className={styles.userBubble}>
                <p>Taşıt finansmanında en uygun seçenek hangisi?</p>

                <div className={styles.messageMeta}>
                  10:28 <span>✓✓</span>
                </div>
              </div>
            </div>

            <div className={styles.botRow}>
              <div className={styles.botAvatar}>✦</div>

              <div className={styles.botBubble}>
                <p>
                  Taşıt finansmanı için güncel en uygun seçenekler şunlardır:
                </p>

                <ul>
                  <li>
                    Vade 24 aya kadar: <strong>%2,49 kâr payı oranı</strong>
                  </li>
                  <li>
                    Vade 36 aya kadar: <strong>%2,69 kâr payı oranı</strong>
                  </li>
                  <li>
                    Vade 48 aya kadar: <strong>%2,79 kâr payı oranı</strong>
                  </li>
                </ul>

                <p>
                  Detaylı karşılaştırma için Karşılaştırma sayfasını
                  inceleyebilirsiniz.
                </p>

                <div className={styles.botTime}>10:28</div>
              </div>
            </div>

            <div className={styles.userRow}>
              <div className={styles.userBubble}>
                <p>Masrafsız kart kampanyaları neler?</p>

                <div className={styles.messageMeta}>
                  10:31 <span>✓✓</span>
                </div>
              </div>
            </div>

            <div className={styles.botRow}>
              <div className={styles.botAvatar}>✦</div>

              <div className={styles.botBubble}>
                <p>Masrafsız kart kampanyalarımız:</p>

                <ul>
                  <li>
                    <strong>Aidatsız Klasik Kart</strong> – Yıllık aidat yok
                  </li>

                  <li>
                    <strong>Genç Kart</strong> – Tüm harcamalarda masraf yok
                  </li>

                  <li>
                    <strong>Sanal Kart</strong> – Online alışverişlerde masrafsız
                    kullanım
                  </li>
                </ul>

                <p>
                  Tüm kart kampanyaları için Kampanyalar sayfasında
                  inceleyebilirsiniz.
                </p>

                <div className={styles.botTime}>10:31</div>
              </div>
            </div>
            {sentMessages.map((message, index) => (
              <div className={styles.liveMessageGroup} key={`${message}-${index}`}>
                <div className={styles.userRow}><div className={styles.userBubble}><p>{message}</p><div className={styles.messageMeta}>Şimdi <span>✓✓</span></div></div></div>
                <div className={styles.botRow}><div className={styles.botAvatar}>✦</div><div className={styles.botBubble}><p>Sorunuzu aldım. Pusula AI mevcut katılım bankacılığı verileri üzerinden seçenekleri değerlendiriyor.</p><p>Daha ayrıntılı sonuç için banka veya ürün türünü de belirtebilirsiniz.</p><div className={styles.botTime}>Şimdi</div></div></div>
              </div>
            ))}
          </div>

          <div className={styles.inputArea}>
            <button type="button" aria-label="Hazır soruları aç veya kapat" className={styles.plusButton} onClick={() => setShowSuggestions((shown) => !shown)}>＋</button>

            <div className={styles.inputWrapper}>
              <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") sendMessage(); }} type="text" placeholder="Sorunuzu yazın..." />

              <button type="button" aria-label="Mesajı gönder" onClick={sendMessage} className={styles.sendButton}>➤</button>
            </div>
          </div>

          <div className={styles.disclaimer}>
            🔒 Yanıtlar bilgilendirme amaçlıdır. Detaylı bilgi için lütfen
            bankanızla iletişime geçiniz.
          </div>
          <div className={styles.assistantBenefits}>
            <div><span>✦</span><strong>7/24 Akıllı Destek</strong><small>İhtiyacınız olduğunda yanınızda</small></div>
            <div><span>✓</span><strong>Güvenilir ve Güncel Bilgi</strong><small>Veriye dayalı anlaşılır yanıtlar</small></div>
            <div><span>⌁</span><strong>Size Özel Öneriler</strong><small>Tercihlerinize uygun seçenekler</small></div>
          </div>
        </section>

        <aside className={styles.aiSideRail}>
          <section className={styles.aiMarkCard}>
            <div className={styles.aiMarkOrbit}><span>✦</span><i>AI</i></div>
            <h2>Pusula AI</h2>
            <p>Finansal kararlarınız için akıllı yol arkadaşınız.</p>
          </section>
        {showSuggestions && <section className={styles.quickQuestions}>
          <div className={styles.quickQuestionsTitle}><span>✦</span><strong>Hazır Sorular</strong></div>
          <div className={styles.quickQuestionList}>{suggestions.map((question) => (
            <button key={question} type="button" onClick={() => setInput(question)}>{question}<span>›</span></button>
          ))}</div>
        </section>}
        </aside>

        {false && <aside className={styles.rightColumn}>
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
                <button key={question} className={styles.questionButton}>
                  <span className={styles.questionIcon}>▢</span>

                  <span>{question}</span>

                  <strong>›</strong>
                </button>
              ))}
            </div>
          </section>
        </aside>}
      </section>
    </main>
  );
}
