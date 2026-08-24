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
