/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Hugging Face Space ("user/raven-api") or URL of the voice server; the build for Pages sets it. */
  readonly VITE_RAVEN_SPACE?: string
}
