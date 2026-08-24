import assert from "node:assert/strict";
import test from "node:test";

import {
  applyActiveChatUpdate,
  nextChatRequestToken,
  resetChatSession,
} from "../app/chatbot/sessionGuard.js";

test("yeni sohbet geç stream olaylarını yok sayar ve odağı girdiye ister", () => {
  let currentToken = 0;
  const streamingToken = nextChatRequestToken(currentToken);
  currentToken = streamingToken;
  let exchanges = [
    { question: "Aktif soru", answer: "Başlangıç", streaming: true },
  ];

  const resetState = resetChatSession(currentToken);
  currentToken = resetState.requestToken;
  exchanges = resetState.exchanges;

  const lateUpdates = [
    (items) => [
      ...items,
      { question: "Geç delta", answer: "yanıt", streaming: true },
    ],
    (items) => [
      ...items,
      { question: "Geç done", answer: "yanıt", streaming: false },
    ],
    (items) => [
      ...items,
      { question: "Geç error", answer: "", streaming: false, error: "hata" },
    ],
  ];

  for (const update of lateUpdates) {
    exchanges = applyActiveChatUpdate(
      currentToken,
      streamingToken,
      exchanges,
      update
    );
  }

  assert.deepEqual(exchanges, []);
  assert.equal(resetState.message, "");
  assert.equal(resetState.loading, false);
  assert.equal(resetState.focusInput, true);
});
