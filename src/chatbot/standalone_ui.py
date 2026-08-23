"""Standalone single-file web UI for the RAGnROLL chatbot.

Run from the project root:
    python -m src.chatbot.standalone_ui

Then open:
    http://127.0.0.1:8501
"""

from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from src.chatbot.rag_langchain import LangChainRAG


HOST = "127.0.0.1"
PORT = 8501

_rag: "LangChainRAG | None" = None
_rag_lock = Lock()
_answer_lock = Lock()
_memory_lock = Lock()
_conversation_memory: dict[str, str] = {
    "last_bank": "",
    "previous_bank": "",
    "pending_campaign_bank": "",
    "last_campaign_area": "",
    "last_question": "",
}


def reset_conversation_memory() -> None:
    with _memory_lock:
        for key in _conversation_memory:
            _conversation_memory[key] = ""


HTML = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RAGnROLL Chatbot Test</title>
  <style>
    :root {
      --nav: #173a49;
      --nav-dark: #0e2c39;
      --ink: #142b3b;
      --muted: #657482;
      --line: #dfe8eb;
      --panel: #ffffff;
      --page: #f5f8f9;
      --teal: #63bdb8;
      --teal-soft: #e8f8f6;
      --gold: #e4b94e;
      --danger: #b42318;
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      height: 100%;
    }

    body {
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      overflow: hidden;
    }

    .topbar {
      height: 86px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 46px;
      background: linear-gradient(90deg, var(--nav-dark), var(--nav));
      color: white;
    }

    .brand {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 32px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .nav {
      display: flex;
      align-items: center;
      gap: 34px;
      font-size: 18px;
    }

    .nav a {
      color: white;
      text-decoration: none;
      opacity: 0.96;
    }

    .nav .active {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 14px 22px;
      border: 1px solid var(--teal);
      border-radius: 12px;
      color: var(--teal);
      background: rgba(99, 189, 184, 0.09);
    }

    .shell {
      width: min(1560px, calc(100% - 88px));
      height: calc(100vh - 146px);
      margin: 30px auto;
      display: grid;
      grid-template-columns: minmax(0, 1.85fr) minmax(360px, 0.95fr);
      gap: 18px;
      align-items: stretch;
    }

    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 34px rgba(23, 58, 73, 0.08);
    }

    .chat {
      height: 100%;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

.chat-head {
      min-height: 120px;
      position: relative;
      display: flex;
      align-items: center;
      gap: 20px;
      padding: 26px 34px;
      border-bottom: 1px solid var(--line);
      overflow: hidden;
    }

    .new-chat {
      position: absolute;
      right: 44px;
      top: 32px;
      z-index: 2;
      width: 56px;
      height: 56px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(99, 189, 184, 0.55);
      border-radius: 50%;
      background: var(--teal-soft);
      color: var(--teal);
      font-size: 30px;
      line-height: 1;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(23, 58, 73, 0.09);
      transition: transform 0.16s ease, border-color 0.16s ease;
    }

    .new-chat:hover {
      transform: translateY(-1px);
      border-color: var(--teal);
    }

    .chat-head h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 44px;
      letter-spacing: 0;
    }

    .spark {
      width: 62px;
      height: 62px;
      display: grid;
      place-items: center;
      flex: 0 0 auto;
      border-radius: 50%;
      color: var(--teal);
      background: var(--teal-soft);
      font-size: 30px;
      font-weight: 700;
    }

    .ribbons {
      position: absolute;
      right: 26px;
      bottom: -10px;
      width: 420px;
      height: 100px;
      pointer-events: none;
    }

    .ribbons span {
      position: absolute;
      right: 0;
      width: 410px;
      height: 72px;
      border-top: 1px solid rgba(99, 189, 184, 0.24);
      border-radius: 50%;
    }

    .ribbons span:nth-child(2) {
      top: 22px;
      width: 360px;
      border-color: rgba(99, 189, 184, 0.15);
    }

    .ribbons span:nth-child(3) {
      top: 48px;
      width: 310px;
      border-color: rgba(228, 185, 78, 0.35);
    }

    .messages {
      flex: 1;
      height: 0;
      padding: 24px 30px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      overflow-y: auto;
      background: #fcfdfd;
      scroll-behavior: smooth;
    }

    .row {
      display: flex;
      gap: 14px;
      align-items: flex-start;
    }

    .row.user {
      justify-content: flex-end;
    }

    .avatar {
      width: 46px;
      height: 46px;
      display: grid;
      place-items: center;
      flex: 0 0 auto;
      border-radius: 50%;
      background: var(--teal-soft);
      color: var(--teal);
      font-size: 22px;
      font-weight: 700;
    }

    .bubble {
      position: relative;
      width: fit-content;
      max-width: 68%;
      min-width: 240px;
      padding: 17px 20px 30px;
      border-radius: 13px;
      border: 1px solid var(--line);
      background: white;
      font-size: 16px;
      line-height: 1.55;
      white-space: pre-wrap;
      box-shadow: 0 4px 12px rgba(23, 58, 73, 0.04);
    }

    .assistant-stack {
      width: min(68%, 920px);
      display: grid;
      gap: 10px;
    }

    .assistant-stack .bubble {
      max-width: 100%;
      width: 100%;
    }

    .thinking {
      width: fit-content;
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #f8fbfb;
      color: var(--muted);
      font-size: 14px;
      box-shadow: 0 3px 10px rgba(23, 58, 73, 0.03);
    }

    .thinking[open] {
      width: 100%;
    }

    .thinking summary {
      padding: 11px 14px;
      cursor: pointer;
      list-style: none;
      color: var(--ink);
      font-weight: 700;
    }

    .thinking summary::-webkit-details-marker {
      display: none;
    }

    .thinking summary::before {
      content: "▸";
      display: inline-block;
      margin-right: 8px;
      color: var(--teal);
      transition: transform 0.18s ease;
    }

    .thinking[open] summary::before {
      transform: rotate(90deg);
    }

    .thinking-body {
      padding: 0 14px 13px 34px;
      line-height: 1.55;
    }

    .thinking-status {
      color: var(--ink);
      font-weight: 600;
      margin-bottom: 7px;
    }

    .thinking-note {
      margin-bottom: 8px;
    }

    .answer-text {
      min-height: 24px;
      padding-right: 18px;
      white-space: pre-wrap;
    }

    .typing-dots {
      display: inline-flex;
      gap: 5px;
      align-items: center;
      min-height: 24px;
    }

    .typing-dots span {
      width: 7px;
      height: 7px;
      display: block;
      border-radius: 50%;
      background: var(--teal);
      opacity: 0.35;
      animation: dotPulse 1.1s infinite ease-in-out;
    }

    .typing-dots span:nth-child(2) {
      animation-delay: 0.16s;
    }

    .typing-dots span:nth-child(3) {
      animation-delay: 0.32s;
    }

    @keyframes dotPulse {
      0%, 80%, 100% {
        transform: translateY(0);
        opacity: 0.35;
      }

      40% {
        transform: translateY(-5px);
        opacity: 0.95;
      }
    }

    .user .bubble {
      border-color: transparent;
      background: var(--teal-soft);
      max-width: 52%;
      min-width: 260px;
    }

    .time {
      position: absolute;
      right: 16px;
      bottom: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .checks {
      color: var(--teal);
      margin-left: 5px;
    }

    .composer {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      padding: 16px 30px 12px;
      background: white;
      border-top: 1px solid rgba(223, 232, 235, 0.6);
    }

    .round-btn {
      width: 54px;
      height: 54px;
      border: 1px solid var(--line);
      border-radius: 50%;
      background: white;
      color: var(--teal);
      font-size: 34px;
      cursor: default;
      box-shadow: 0 6px 20px rgba(23, 58, 73, 0.08);
    }

    .input-wrap {
      height: 54px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 58px;
      align-items: center;
      padding-left: 18px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: white;
      box-shadow: 0 6px 20px rgba(23, 58, 73, 0.08);
    }

    input {
      width: 100%;
      border: 0;
      outline: 0;
      color: var(--ink);
      font-size: 16px;
    }

    input::placeholder {
      color: #a3adb5;
    }

    .send {
      height: 52px;
      border: 0;
      background: transparent;
      color: var(--teal);
      font-size: 30px;
      cursor: pointer;
    }

    .send.stop {
      color: var(--danger);
      font-size: 25px;
    }

    .send:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }

    .notice {
      min-height: 22px;
      padding: 0 30px 12px;
      color: var(--danger);
      font-size: 13px;
    }

    .fineprint {
      padding: 0 24px 14px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }

    .side {
      display: grid;
      grid-template-rows: 315px minmax(0, 1fr);
      gap: 14px;
      max-height: 100%;
      overflow: hidden;
      padding-right: 2px;
    }

    .info {
      min-height: 0;
      padding: 20px;
      overflow: hidden;
    }

    .info-head {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 20px;
    }

    .info h2,
    .questions h2 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 28px;
      line-height: 1.1;
    }

    .tag {
      display: inline-flex;
      margin-top: 8px;
      padding: 6px 11px;
      border-radius: 8px;
      color: var(--teal);
      background: var(--teal-soft);
      font-size: 13px;
    }

    .info-body {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 170px;
      gap: 12px;
      align-items: center;
    }

    .info p {
      margin: 0 0 18px;
      font-size: 15px;
      line-height: 1.45;
    }

    .features {
      display: grid;
      gap: 12px;
      color: var(--muted);
      font-size: 14px;
    }

    .bot-art {
      min-height: 190px;
      position: relative;
      display: grid;
      place-items: center;
    }

    .bot-head {
      width: 140px;
      height: 104px;
      display: grid;
      place-items: center;
      border: 7px solid #afe6e2;
      border-radius: 44%;
      background: white;
      box-shadow: 0 12px 28px rgba(99, 189, 184, 0.2);
      z-index: 2;
    }

    .face {
      width: 104px;
      height: 68px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 18px;
      border-radius: 28px;
      background: #122f3d;
    }

    .eye {
      width: 22px;
      height: 32px;
      border-radius: 50%;
      background: var(--teal);
      box-shadow: 0 0 16px rgba(99, 189, 184, 0.8);
    }

    .bot-body {
      position: absolute;
      bottom: 0;
      width: 170px;
      height: 84px;
      border-radius: 52% 52% 26% 26%;
      background: linear-gradient(160deg, var(--teal-soft), #9bdad5);
    }

    .questions {
      min-height: 0;
      padding: 18px 20px;
      overflow: hidden;
    }

    .questions-title {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }

    .question-list {
      display: grid;
      gap: 10px;
    }

    .question {
      min-height: 50px;
      display: grid;
      grid-template-columns: 28px minmax(0, 1fr) 22px;
      gap: 14px;
      align-items: center;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 13px;
      background: white;
      color: var(--ink);
      text-align: left;
      font-size: 14px;
      cursor: pointer;
    }

    .question span:first-child {
      width: 16px;
      height: 16px;
      border: 2px solid #a9d9d6;
      border-radius: 4px;
    }

    .question strong {
      color: var(--teal);
      font-size: 22px;
      text-align: right;
    }

    @media (max-width: 1100px) {
      .shell {
        grid-template-columns: 1fr;
      }

      .chat {
        height: 760px;
      }

      .info-body {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 760px) {
      .topbar {
        height: auto;
        padding: 20px;
        flex-direction: column;
        gap: 16px;
      }

      body {
        overflow: auto;
      }

      .nav {
        flex-wrap: wrap;
        justify-content: center;
      }

      .shell {
        width: calc(100% - 24px);
        height: auto;
        margin: 12px auto;
      }

      .side {
        max-height: none;
        overflow: visible;
      }

      .chat-head h1 {
        font-size: 34px;
      }

      .ribbons,
      .bot-art {
        display: none;
      }

      .bubble,
      .user .bubble {
        max-width: 88%;
        min-width: 0;
      }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">Katılım Bankacılığı</div>
    <nav class="nav">
      <a href="#">Ana Sayfa</a>
      <a href="#">Karşılaştırma</a>
      <a href="#">Kampanyalar</a>
      <a class="active" href="#"><span>✦</span> AI Asistan</a>
    </nav>
  </header>

  <main class="shell">
    <section class="card chat">
      <div class="chat-head">
        <div class="spark">✦</div>
        <h1>AI Asistanı</h1>
        <button id="newChatButton" class="new-chat" type="button" title="Yeni sohbet" aria-label="Yeni sohbet">+</button>
        <div class="ribbons"><span></span><span></span><span></span></div>
      </div>

      <div id="messages" class="messages"></div>

      <form id="form" class="composer">
        <button class="round-btn" type="button">+</button>
        <div class="input-wrap">
          <input id="messageInput" autocomplete="off" placeholder="Sorunuzu yazın..." />
          <button id="sendButton" class="send" type="submit">➤</button>
        </div>
      </form>

      <div id="notice" class="notice"></div>
      <div class="fineprint">Yanıtlar bilgilendirme amaçlıdır. Detaylı bilgi için bankanızla iletişime geçiniz.</div>
    </section>

    <aside class="side">
      <section class="card info">
        <div class="info-head">
          <div class="spark">✦</div>
          <div>
            <h2>AI Asistan</h2>
            <div class="tag">Yapay Zekâ Destekli</div>
          </div>
        </div>

        <div class="info-body">
          <div>
            <p>Katılım Bankacılığı ürünleri hakkında sorularınızı yanıtlar, en uygun seçenekleri bulmanıza yardımcı olur.</p>
            <div class="features">
              <div>☂ 7/24 Akıllı Destek</div>
              <div>♡ Güvenilir ve Güncel Bilgi</div>
              <div>⚙ Size Özel Öneriler</div>
            </div>
          </div>

          <div class="bot-art" aria-hidden="true">
            <div class="bot-head">
              <div class="face"><span class="eye"></span><span class="eye"></span></div>
            </div>
            <div class="bot-body"></div>
          </div>
        </div>
      </section>

      <section class="card questions">
        <div class="questions-title">
          <div class="spark" style="width:42px;height:42px;font-size:22px;background:white;">✦</div>
          <h2>Hazır Sorular</h2>
        </div>
        <div class="question-list">
          <button class="question" type="button" data-question="Türkiye'deki katılım bankalarını sayar mısın?"><span></span><em>Türkiye'deki katılım bankalarını sayar mısın?</em><strong>›</strong></button>
          <button class="question" type="button" data-question="Katılma hesabı nedir?"><span></span><em>Katılma hesabı nedir?</em><strong>›</strong></button>
          <button class="question" type="button" data-question="Murabaha nedir?"><span></span><em>Murabaha nedir?</em><strong>›</strong></button>
          <button class="question" type="button" data-question="Kuveyt Türk kampanyalarında hangi avantajlar var?"><span></span><em>Kuveyt Türk kampanyalarında hangi avantajlar var?</em><strong>›</strong></button>
        </div>
      </section>
    </aside>
  </main>

  <script>
    const messages = document.getElementById("messages");
    const form = document.getElementById("form");
    const input = document.getElementById("messageInput");
    const sendButton = document.getElementById("sendButton");
    const newChatButton = document.getElementById("newChatButton");
    const notice = document.getElementById("notice");
    const welcomeMessage = "Merhaba ben PUSULA AI! Bana katılım bankacılığı, kampanyalar, kâr payı, finansman veya banka karşılaştırmaları hakkında soru sorabilirsin.";
    let activeController = null;
    let isGenerating = false;

    function time() {
      return new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(new Date());
    }

    function addMessage(role, text, pending = false) {
      const row = document.createElement("div");
      row.className = `row ${role}`;

      if (role === "bot") {
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.textContent = "✦";
        row.appendChild(avatar);
      }

      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = text;
      bubble.dataset.pending = pending ? "true" : "false";

      const stamp = document.createElement("span");
      stamp.className = "time";
      stamp.innerHTML = role === "user" ? `${time()} <span class="checks">✓✓</span>` : time();
      bubble.appendChild(stamp);
      row.appendChild(bubble);
      messages.appendChild(row);
      messages.scrollTop = messages.scrollHeight;
      return bubble;
    }

    function addBotResponseShell() {
      const row = document.createElement("div");
      row.className = "row bot";

      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.textContent = "✦";
      row.appendChild(avatar);

      const stack = document.createElement("div");
      stack.className = "assistant-stack";

      const thinking = document.createElement("details");
      thinking.className = "thinking";

      const summary = document.createElement("summary");
      summary.textContent = "Düşünme süreci";

      const thinkingBody = document.createElement("div");
      thinkingBody.className = "thinking-body";
      thinkingBody.innerHTML = [
        '<div class="thinking-status">ChromaDB kaynakları taranıyor</div>',
        '<div class="thinking-note">Cevap, projedeki RAG kaynaklarından seçilen ilgili bilgilerle hazırlanır.</div>',
        '<div class="thinking-note">Uygun kaynaklardan yanıt hazırlanıyor.</div>'
      ].join("");

      thinking.appendChild(summary);
      thinking.appendChild(thinkingBody);

      const bubble = document.createElement("div");
      bubble.className = "bubble";

      const answerText = document.createElement("div");
      answerText.className = "answer-text";
      answerText.innerHTML = '<span class="typing-dots" aria-label="Yanıt bekleniyor"><span></span><span></span><span></span></span>';
      bubble.appendChild(answerText);

      const stamp = document.createElement("span");
      stamp.className = "time";
      stamp.textContent = time();
      bubble.appendChild(stamp);

      stack.appendChild(thinking);
      stack.appendChild(bubble);
      row.appendChild(stack);
      messages.appendChild(row);
      messages.scrollTop = messages.scrollHeight;

      return { bubble, answerText, thinking, thinkingBody, summary };
    }

    async function send(text) {
      const question = text.trim();
      if (!question) return;

      if (isGenerating) {
        return;
      }

      notice.textContent = "";
      input.value = "";
      isGenerating = true;
      activeController = new AbortController();
      sendButton.disabled = false;
      sendButton.classList.add("stop");
      sendButton.textContent = "■";
      sendButton.title = "Yanıtı durdur";
      addMessage("user", question);
      const responseShell = addBotResponseShell();

      let receivedAnyChunk = false;
      let chatMode = "rag";
      const progressTimer = window.setInterval(() => {
        const status = responseShell.thinkingBody.querySelector(".thinking-status");
        if (!status) return;

        if (chatMode === "casual") {
          status.textContent = receivedAnyChunk ? "Sohbet yanıtını yazıyorum" : "Mesajını değerlendiriyorum";
          return;
        }

        if (!receivedAnyChunk) {
          status.textContent = "ChromaDB kaynakları taranıyor";
        } else {
          status.textContent = "Uygun kaynaklardan yanıt hazırlanıyor";
        }
      }, 1800);

      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: question }),
          signal: activeController.signal
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        chatMode = response.headers.get("X-Chat-Mode") || "rag";

        if (chatMode === "casual") {
          const status = responseShell.thinkingBody.querySelector(".thinking-status");
          const notes = responseShell.thinkingBody.querySelectorAll(".thinking-note");

          if (status) {
            status.textContent = "Mesajını değerlendiriyorum";
          }

          notes.forEach((note) => {
            note.textContent = "Kısa sohbet mesajları kaynak taramasına gönderilmez.";
          });

          responseShell.summary.textContent = "Sohbet";
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let answer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          if (!chunk) continue;

          receivedAnyChunk = true;
          answer += chunk;
          responseShell.summary.textContent = chatMode === "casual" ? "Sohbet" : "Düşünme süreci";
          responseShell.answerText.textContent = answer;
          messages.scrollTop = messages.scrollHeight;
        }

        responseShell.answerText.textContent = answer.trim() || "Yanıt alınamadı. Lütfen tekrar deneyin.";
        const status = responseShell.thinkingBody.querySelector(".thinking-status");
        if (status) {
          status.textContent = chatMode === "casual" ? "Sohbet yanıtı yazıldı" : "Yanıt hazırlandı";
        }
        responseShell.summary.textContent = chatMode === "casual" ? "Sohbet" : "Düşünme süreci";
        responseShell.thinking.open = false;
      } catch (error) {
        if (error.name === "AbortError") {
          responseShell.answerText.textContent = "Yanıt durduruldu. Sorunu yeniden yazabilir ya da başka bir soru sorabilirsin.";
          responseShell.summary.textContent = "Düşünme süreci";
          const status = responseShell.thinkingBody.querySelector(".thinking-status");
          if (status) {
            status.textContent = "Yanıt kullanıcı tarafından durduruldu.";
          }
          responseShell.thinking.open = false;
          return;
        }

        responseShell.answerText.textContent = "Chatbot API'sine ulaşılamadı.";
        responseShell.summary.textContent = "Düşünme süreci";
        const status = responseShell.thinkingBody.querySelector(".thinking-status");
        if (status) {
          status.textContent = "Sunucu yanıtı alınamadı.";
        }
        notice.textContent = "Backend yanıt vermedi. Terminalde standalone_ui.py çalışıyor mu kontrol edin.";
      } finally {
        window.clearInterval(progressTimer);
        isGenerating = false;
        activeController = null;
        sendButton.classList.remove("stop");
        sendButton.textContent = "➤";
        sendButton.title = "Gönder";
        sendButton.disabled = !input.value.trim();
        input.focus();
        messages.scrollTop = messages.scrollHeight;
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (isGenerating && activeController) {
        activeController.abort();
        return;
      }
      send(input.value);
    });

    input.addEventListener("input", () => {
      if (isGenerating) {
        sendButton.disabled = false;
        return;
      }

      sendButton.disabled = !input.value.trim();
    });

    document.querySelectorAll(".question").forEach((button) => {
      button.addEventListener("click", () => send(button.dataset.question || ""));
    });

    async function resetChat() {
      if (activeController) {
        activeController.abort();
      }

      try {
        await fetch("/api/reset", { method: "POST" });
      } catch (error) {
        notice.textContent = "Sohbet sıfırlanırken sunucuya ulaşılamadı.";
      }

      messages.innerHTML = "";
      notice.textContent = "";
      input.value = "";
      addMessage("bot", welcomeMessage);
      sendButton.disabled = true;
      input.focus();
    }

    newChatButton.addEventListener("click", resetChat);

    addMessage("bot", welcomeMessage);
    sendButton.disabled = true;
  </script>
</body>
</html>
"""


def get_rag() -> LangChainRAG:
    global _rag

    if _rag is None:
        with _rag_lock:
            if _rag is None:
                from src.chatbot.rag_langchain import LangChainRAG

                _rag = LangChainRAG()

    return _rag


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


BANK_ALIASES = (
    ("kuveyt türk", "Kuveyt Türk"),
    ("kuveytturk", "Kuveyt Türk"),
    ("albaraka", "Albaraka Türk"),
    ("türkiye finans", "Türkiye Finans"),
    ("turkiye finans", "Türkiye Finans"),
    ("finans katılım", "Türkiye Finans"),
    ("finans katilim", "Türkiye Finans"),
    ("ziraat katılım", "Ziraat Katılım"),
    ("ziraat katilim", "Ziraat Katılım"),
    ("vakıf katılım", "Vakıf Katılım"),
    ("vakif katilim", "Vakıf Katılım"),
    ("emlak katılım", "Türkiye Emlak Katılım"),
    ("emlak katilim", "Türkiye Emlak Katılım"),
    ("hayat finans", "Hayat Finans"),
    ("dünya katılım", "Dünya Katılım"),
    ("dunya katilim", "Dünya Katılım"),
    ("adıl katılım", "Adıl Katılım"),
    ("adil katilim", "Adıl Katılım"),
    ("t.o.m. katılım", "T.O.M. Katılım"),
    ("tom katılım", "T.O.M. Katılım"),
)

AREA_ALIASES = (
    ("vade farksız taksit", "vade farksız taksit"),
    ("vade farksiz taksit", "vade farksız taksit"),
    ("ihtiyaç finansmanı", "ihtiyaç finansmanı"),
    ("ihtiyac finansmani", "ihtiyaç finansmanı"),
    ("ihtiyaç finansmani", "ihtiyaç finansmanı"),
    ("ihtiyac finansmanı", "ihtiyaç finansmanı"),
    ("ev finansmanı", "konut finansmanı"),
    ("ev finansmani", "konut finansmanı"),
    ("konut finansmanı", "konut finansmanı"),
    ("konut finansmani", "konut finansmanı"),
    ("taşıt finansmanı", "taşıt finansmanı"),
    ("tasit finansmani", "taşıt finansmanı"),
    ("seyahat planları", "seyahat"),
    ("seyehat planları", "seyahat"),
    ("seyahat planlari", "seyahat"),
    ("seyehat planlari", "seyahat"),
    ("sağlam kart", "sağlam kart"),
    ("saglam kart", "sağlam kart"),
    ("ihtiyaç kart", "ihtiyaç kart"),
    ("ihtiyac kart", "ihtiyaç kart"),
    ("mobil uygulama", "mobil uygulama"),
    ("nakit iade", "nakit iade"),
    ("döviz işlemleri", "döviz işlemleri"),
    ("doviz islemleri", "döviz işlemleri"),
    ("döviz işlemi", "döviz işlemleri"),
    ("doviz islemi", "döviz işlemleri"),
    ("döviz", "döviz işlemleri"),
    ("doviz", "döviz işlemleri"),
    ("kıymetli maden", "döviz işlemleri"),
    ("kiymetli maden", "döviz işlemleri"),
    ("altın", "döviz işlemleri"),
    ("altin", "döviz işlemleri"),
    ("kur", "döviz işlemleri"),
    ("kiralık kasa", "kiralık kasa"),
    ("kiralik kasa", "kiralık kasa"),
    ("güvenli ödeme", "güvenli ödeme"),
    ("guvenli odeme", "güvenli ödeme"),
    ("kart", "kart"),
    ("mobil", "mobil"),
    ("fatura", "fatura"),
    ("davet", "davet"),
    ("miles", "seyahat"),
    ("smiles", "seyahat"),
    ("mil", "seyahat"),
    ("seyahat", "seyahat"),
    ("seyehat", "seyahat"),
    ("uçak", "seyahat"),
    ("ucak", "seyahat"),
    ("taşıt", "taşıt finansmanı"),
    ("tasit", "taşıt finansmanı"),
    ("araç", "taşıt finansmanı"),
    ("arac", "taşıt finansmanı"),
    ("konut", "konut finansmanı"),
    ("çeyiz", "evlilik"),
    ("ceyiz", "evlilik"),
    ("balayı", "evlilik"),
    ("balayi", "evlilik"),
    ("evlilik", "evlilik"),
    ("finansman", "finansman"),
    ("taksit", "taksit"),
    ("puan", "puan"),
    ("indirim", "indirim"),
    ("umre", "umre"),
    ("alışveriş", "alışveriş"),
    ("alisveris", "alışveriş"),
)


def search_text(value: object) -> str:
    return str(value).lower().replace("i̇", "i")


def extract_bank_name(message: str) -> str:
    q = search_text(message)

    for alias, display_name in BANK_ALIASES:
        if alias in q:
            return display_name

    return ""


def extract_campaign_target(message: str) -> str:
    bank = extract_bank_name(message)

    if bank:
        return bank

    before_campaign = re.split(
        r"kampanya|avantaj|fırsat",
        message,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ?'’ıninunün")

    return before_campaign


def extract_area(message: str) -> str:
    q = search_text(message).strip()

    for alias, canonical in AREA_ALIASES:
        if alias in q:
            return canonical

    return ""


def build_followup_question(bank: str, area: str) -> str:
    if area in {
        "ihtiyaç finansmanı",
        "konut finansmanı",
        "taşıt finansmanı",
        "döviz işlemleri",
    }:
        return f"{bank} {area} avantajları nelerdir?"

    return f"{bank} {area} kampanyalarında hangi avantajlar var?"


FOLLOWUP_FILLER_PATTERN = re.compile(
    r"\b(için|icin|olsun|hakkında|hakkinda|ile|ilgili|bak|bakar mısın|bakar misin)\b",
    flags=re.IGNORECASE,
)


def clean_followup_detail(message: str) -> str:
    detail = FOLLOWUP_FILLER_PATTERN.sub(" ", message)
    detail = re.sub(r"\s+", " ", detail).strip(" ?.")
    return detail


def normalize_short_reaction(message: str) -> str:
    q = search_text(message).strip(" !?.")
    q = re.sub(r"(.)\1{2,}", r"\1", q)
    q = re.sub(r"(.)\1+$", r"\1", q)
    return q


def is_casual_reaction(message: str) -> bool:
    q = normalize_short_reaction(message)

    if q in {
        "güzel",
        "guzel",
        "güzelmiş",
        "guzelmis",
        "iyiymiş",
        "iyiymis",
        "tamam",
        "anladım",
        "anladim",
        "ok",
        "süper",
        "super",
        "teşekkürler",
        "tesekkurler",
        "teşekkür ederim",
        "tesekkur ederim",
        "sağ ol",
        "sag ol",
        "sağ olun",
        "sag olun",
    }:
        return True

    if len(q.split()) <= 4 and any(
        phrase in q
        for phrase in (
            "güzel düşün",
            "guzel dusun",
            "iyi düşün",
            "iyi dusun",
            "mantıklı",
            "mantikli",
            "iyi olmuş",
            "iyi olmus",
            "güzel olmuş",
            "guzel olmus",
            "başarılı",
            "basarili",
        )
    ):
        return True

    return False


def casual_reaction_response(message: str) -> str:
    q = normalize_short_reaction(message)

    if q in {
        "teşekkürler",
        "tesekkurler",
        "teşekkür ederim",
        "tesekkur ederim",
        "sağ ol",
        "sag ol",
        "sağ olun",
        "sag olun",
    }:
        return "Rica ederim. Başka bir konuda da yardımcı olabilirim."

    if q in {"tamam", "anladım", "anladim", "ok"}:
        return "Tamamdır."

    if any(
        phrase in q
        for phrase in (
            "güzel düşün",
            "guzel dusun",
            "iyi düşün",
            "iyi dusun",
            "mantıklı",
            "mantikli",
            "iyi olmuş",
            "iyi olmus",
            "güzel olmuş",
            "guzel olmus",
            "başarılı",
            "basarili",
        )
    ):
        with _memory_lock:
            last_bank = _conversation_memory.get("last_bank", "")
            last_area = _conversation_memory.get("last_campaign_area", "")

        if last_bank and last_area:
            return (
                f"Evet, {last_bank} bu konuda farklı ihtiyaçları "
                "düşünmüş görünüyor."
            )

        return "Evet, güzel düşünülmüş görünüyor."

    return "Geri bildiriminiz için teşekkür ederiz; bu bizim için değerli."


def is_contextual_detail_followup(
    message: str,
    last_area: str,
) -> bool:
    q = search_text(message)

    if not last_area:
        return False

    if extract_bank_name(message) or is_comparison_request(message):
        return False

    if any(phrase in q for phrase in ("nedir", "ne demek", "tanım", "tanımı")):
        return False

    current_area = extract_area(message)

    if current_area and current_area != last_area:
        return False

    detail_terms_by_area = {
        "evlilik": (
            "çeyiz",
            "ceyiz",
            "ev eşyası",
            "ev esyasi",
            "ev kur",
            "giyim",
            "balayı",
            "balayi",
            "düğün",
            "dugun",
        ),
        "fatura": (
            "telefon",
            "internet",
            "elektrik",
            "su",
            "doğalgaz",
            "dogalgaz",
            "gsm",
        ),
        "kart": (
            "market",
            "giyim",
            "akaryakıt",
            "akaryakit",
            "online",
            "alışveriş",
            "alisveris",
            "taksit",
        ),
        "mobil": (
            "müşteri olma",
            "musteri olma",
            "hesap açma",
            "hesap acma",
            "mobil müşteri",
            "mobil musteri",
        ),
        "seyahat": (
            "uçak",
            "ucak",
            "otel",
            "tur",
            "yurt dışı",
            "yurt disi",
            "mil",
            "miles",
            "smiles",
        ),
        "döviz işlemleri": (
            "altın",
            "altin",
            "kur",
            "döviz",
            "doviz",
            "kıymetli maden",
            "kiymetli maden",
        ),
    }

    if any(term in q for term in detail_terms_by_area.get(last_area, ())):
        return True

    return False


def build_contextual_detail_question(
    bank: str,
    area: str,
    message: str,
) -> str:
    detail = clean_followup_detail(message)

    area_label = "evlilik paketi" if area == "evlilik" else area

    if detail:
        detail_text = search_text(detail)

        if area != "evlilik" and area in detail_text:
            return f"{bank} {detail} avantajları nelerdir?"

        return f"{bank} {area_label} {detail} avantajları nelerdir?"

    return build_followup_question(bank, area)


def is_comparison_request(message: str) -> bool:
    q = search_text(message)

    return any(
        phrase in q
        for phrase in (
            "karşılaştır",
            "karsilastir",
            "ikisini",
            "hangisi daha",
            "farkı ne",
            "farki ne",
            "arasında fark",
            "arasinda fark",
        )
    )


def broad_campaign_clarification(message: str) -> str | None:
    q = search_text(message)

    has_campaign_topic = any(
        word in q
        for word in (
            "kampanya",
            "kampanyalarında",
            "avantaj",
            "avantajlar",
            "fırsat",
            "fırsatlar",
        )
    )

    if not has_campaign_topic:
        return None

    asks_broadly = any(
        phrase in q
        for phrase in (
            "hangi avantaj",
            "ne avantaj",
            "neler var",
            "hangi fırsat",
            "kampanyalarında",
            "kampanyaları",
        )
    )

    specific_area = bool(extract_area(message))

    if asks_broadly and not specific_area:
        target = extract_campaign_target(message)

        with _memory_lock:
            _conversation_memory["pending_campaign_bank"] = target

            if target:
                _conversation_memory["last_bank"] = target

        subject = f"{target} için" if target else "Kampanyalar için"

        return (
            f"{subject} hangi alana bakmamı istersin? "
            "Alanı yazarsan kampanyaları ona göre arayayım.\n\n"
            "Mesela şunlardan başlayabiliriz; başka bir alan yazarsan "
            "onu da ararım:\n"
            "- Kart\n"
            "- Taşıt finansmanı\n"
            "- Mobil uygulama\n"
            "- Nakit iade\n"
            "- Vade farksız taksit"
        )

    return None


def remember_broad_campaign_context(message: str) -> None:
    if broad_campaign_clarification(message) is None:
        return


def resolve_with_memory(message: str) -> tuple[str, str | None]:
    bank = extract_bank_name(message)
    area = extract_area(message)
    q = search_text(message)

    with _memory_lock:
        _conversation_memory["last_question"] = message

        if any(phrase in q for phrase in ("nedir", "ne demek", "tanım", "tanımı")):
            return message, None

        pending_bank = _conversation_memory.get("pending_campaign_bank", "")
        last_bank = _conversation_memory.get("last_bank", "")
        previous_bank = _conversation_memory.get("previous_bank", "")
        last_area = _conversation_memory.get("last_campaign_area", "")

        if bank:
            if last_bank and last_bank != bank:
                _conversation_memory["previous_bank"] = last_bank
                previous_bank = last_bank

            _conversation_memory["last_bank"] = bank
            last_bank = bank

        if is_comparison_request(message) and previous_bank and last_bank:
            area_for_compare = area or last_area

            if area_for_compare:
                return (
                    f"{previous_bank} ve {last_bank} "
                    f"{area_for_compare} avantajlarını karşılaştır.",
                    None,
                )

            return (
                f"{previous_bank} ve {last_bank} kampanya avantajlarını karşılaştır.",
                None,
            )

        if last_bank and is_contextual_detail_followup(message, last_area):
            return (
                build_contextual_detail_question(
                    last_bank,
                    last_area,
                    message,
                ),
                None,
            )

        if pending_bank and area:
            target_bank = bank or pending_bank
            _conversation_memory["pending_campaign_bank"] = ""
            _conversation_memory["last_bank"] = target_bank
            _conversation_memory["last_campaign_area"] = area
            return build_followup_question(target_bank, area), None

        area_only = area and len(q.split()) <= 4 and not any(
            word in q
            for word in ("kampanya", "avantaj", "fırsat")
        )

        if area_only and not last_bank:
            _conversation_memory["last_campaign_area"] = area
            return (
                message,
                None,
            )

        if area_only and last_bank:
            _conversation_memory["last_campaign_area"] = area
            return build_followup_question(last_bank, area), None

        uses_previous_area = any(
            phrase in q
            for phrase in ("o alan", "o alanda", "aynı alan", "aynı tür", "bu alan")
        )

        if bank and uses_previous_area and last_area:
            _conversation_memory["last_bank"] = bank
            return build_followup_question(bank, last_area), None

        if area and any(
            word in q
            for word in ("kampanya", "avantaj", "fırsat")
        ):
            _conversation_memory["last_campaign_area"] = area

            if bank:
                _conversation_memory["last_bank"] = bank
            elif last_bank:
                return build_followup_question(last_bank, area), None

        if bank and area:
            _conversation_memory["last_campaign_area"] = area

        if not bank and uses_previous_area and last_bank and last_area:
            return build_followup_question(last_bank, last_area), None

    return message, None


def stream_text(handler: BaseHTTPRequestHandler, text: str) -> None:
    for part in re.findall(r"\S+\s*", text):
        handler.wfile.write(part.encode("utf-8"))
        handler.wfile.flush()
        time.sleep(0.035)


def stream_casual_text(handler: BaseHTTPRequestHandler, text: str) -> None:
    time.sleep(0.9)

    for part in re.findall(r"\S+\s*", text):
        handler.wfile.write(part.encode("utf-8"))
        handler.wfile.flush()
        time.sleep(0.11)


class ChatbotHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in {"/", "/chatbot"}:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            json_response(self, 200, {"status": "ok"})
            return

        json_response(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/reset":
            reset_conversation_memory()
            json_response(self, 200, {"ok": True})
            return

        if path not in {"/api/chat", "/api/chat/stream"}:
            json_response(self, 404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
            message = str(payload.get("message") or "").strip()

            if not message:
                json_response(self, 422, {"error": "message is required"})
                return

            remember_broad_campaign_context(message)

            resolved_message, _ = resolve_with_memory(message)

            if path == "/api/chat/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                with _answer_lock:
                    wrote_any_chunk = False

                    for chunk in get_rag().ask_question_stream(resolved_message):
                        if not str(chunk).strip():
                            continue

                        wrote_any_chunk = True
                        data = str(chunk).encode("utf-8")
                        try:
                            self.wfile.write(data)
                            self.wfile.flush()
                        except (
                            BrokenPipeError,
                            ConnectionResetError,
                            ConnectionAbortedError,
                        ):
                            break

                    if not wrote_any_chunk:
                        stream_text(
                            self,
                            "Bu bilgi sağlanan dokümanlarda bulunmamaktadır.",
                        )
                return

            with _answer_lock:
                answer = get_rag().ask_question(resolved_message)

            if not answer.strip():
                answer = (
                    "Bu bilgi sağlanan dokümanlarda bulunmamaktadır."
                )

            json_response(self, 200, {"answer": answer})
        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
        ):
            return
        except Exception as exc:  # noqa: BLE001 - UI should receive a readable error.
            json_response(self, 500, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[standalone-ui] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ChatbotHandler)
    server.daemon_threads = True
    print(f"Standalone chatbot UI hazir: http://{HOST}:{PORT}")
    print("Cikmak icin Ctrl+C")
    server.serve_forever()


if __name__ == "__main__":
    main()
