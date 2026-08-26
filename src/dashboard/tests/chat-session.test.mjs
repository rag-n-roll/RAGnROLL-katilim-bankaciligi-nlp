import assert from "node:assert/strict";
import test from "node:test";

import {
  applyActiveChatUpdate,
  applyStreamEvent,
  createStreamState,
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

test("aynı event_id cevaba yalnız bir kez uygulanır (test_duplicate_sse_event_is_applied_once)", () => {
  let state = createStreamState(7);
  const event = { requestId: "req-1", eventId: "req-1:1", sequence: 1, text: "Yanıt" };
  state = applyStreamEvent(state, 7, event);
  state = applyStreamEvent(state, 7, event);
  assert.equal(state.answer, "Yanıt");
  assert.equal(state.seenEventIds.size, 1);
});

test("test_duplicate_sse_event_is_applied_once", () => {
  let state = createStreamState(7);
  const event = { requestId: "req-1", eventId: "req-1:1", sequence: 1, text: "Yanıt" };
  state = applyStreamEvent(state, 7, event);
  state = applyStreamEvent(state, 7, event);
  assert.equal(state.answer, "Yanıt");
  assert.equal(state.seenEventIds.size, 1);
});
