/// <reference types="vite/client" />

declare const __APP_VERSION__: string;
declare const __APP_STAGE__: string;

interface ImportMetaEnv {
  readonly VITE_SENTRY_DSN?: string;
}
