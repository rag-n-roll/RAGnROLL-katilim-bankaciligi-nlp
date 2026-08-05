import Link from "next/link";

export default function Navbar() {
  return (
    <nav
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "16px 32px",
        borderBottom: "1px solid #dddddd",
      }}
    >
      <Link
        href="/"
        style={{
          fontSize: "20px",
          fontWeight: "bold",
          textDecoration: "none",
          color: "black",
        }}
      >
        Katılım Bankacılığı
      </Link>

      <div
        style={{
          display: "flex",
          gap: "24px",
        }}
      >
        <Link href="/" style={{ textDecoration: "none", color: "black" }}>
          Ana Sayfa
        </Link>

        <Link
          href="/compare"
          style={{ textDecoration: "none", color: "black" }}
        >
          Karşılaştırma
        </Link>

        <Link
          href="/campaigns"
          style={{ textDecoration: "none", color: "black" }}
        >
          Kampanyalar
        </Link>

        <Link
          href="/chatbot"
          style={{ textDecoration: "none", color: "black" }}
        >
          Chatbot
        </Link>
      </div>
    </nav>
  );
}