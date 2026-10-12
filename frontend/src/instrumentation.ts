import * as Sentry from "@sentry/nextjs";
import { dataCollection } from "@/lib/sentry";

/** Server-side error reports go to Sentry when SENTRY_DSN is set (read at runtime). */
export function register() {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT ?? "development",
    release: process.env.RELEASE,
    dataCollection,
    tracesSampleRate: 0,
  });
}

export const onRequestError = Sentry.captureRequestError;
