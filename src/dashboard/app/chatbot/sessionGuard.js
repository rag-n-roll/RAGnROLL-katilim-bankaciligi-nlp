export function nextChatRequestToken(currentToken) {
  return currentToken + 1;
}

export function isActiveChatRequest(currentToken, requestToken) {
  return currentToken === requestToken;
}

export function applyActiveChatUpdate(
  currentToken,
  requestToken,
  state,
  update
) {
  return isActiveChatRequest(currentToken, requestToken) ? update(state) : state;
}

export function resetChatSession(currentToken) {
  return {
    requestToken: nextChatRequestToken(currentToken),
    exchanges: [],
    message: "",
    loading: false,
    focusInput: true,
  };
}

export function createStreamState(requestToken) {
  return { requestToken, requestId: null, answer: "", seenEventIds: new Set(), lastSequence: 0 };
}

export function applyStreamEvent(state, currentToken, event) {
  if (state.requestToken !== currentToken) return state;
  if (state.seenEventIds.has(event.eventId)) return state;
  if (event.sequence <= state.lastSequence) return state;
  const seenEventIds = new Set(state.seenEventIds).add(event.eventId);
  return {
    ...state,
    requestId: event.requestId,
    answer: state.answer + (event.text ?? ""),
    seenEventIds,
    lastSequence: event.sequence,
  };
}
