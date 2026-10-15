// The visitor's Gemini API key, kept only in this browser. If storage is blocked it lives for the session only.
const KEY = 'raven.geminiKey'

export function loadKey(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null // storage blocked (private window): the key gate asks again
  }
}

export function saveKey(key: string) {
  try {
    localStorage.setItem(KEY, key)
  } catch {
    // storage blocked: the key still works until the page is closed
  }
}

export function clearKey() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // storage blocked: nothing was saved
  }
}
