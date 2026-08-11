import styles from "./page.module.css";

const suggestions = [
  "En yüksek kâr payı hangi bankada?",
  "Taşıt finansmanında en uygun seçenek hangisi?",
  "Masrafsız kart kampanyaları neler?",
  "Yatırım kampanyalarını karşılaştır",
];

export default function ChatbotPage() {
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
          </div>

          <div className={styles.inputArea}>
            <button className={styles.plusButton}>＋</button>

            <div className={styles.inputWrapper}>
              <input type="text" placeholder="Sorunuzu yazın..." />

              <button className={styles.sendButton}>➤</button>
            </div>
          </div>

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
                <button key={question} className={styles.questionButton}>
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
