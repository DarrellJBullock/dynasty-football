import * as Sentry from "@sentry/nextjs";
import { dataCollection } from "@/lib/sentry";

// Browser error reports, when the build has a DSN. One image serves every environment,
// so the environment is the site's host name.
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({
    dsn,
    environment: window.location.hostname,
    release: process.env.NEXT_PUBLIC_RELEASE,
    dataCollection,
    tracesSampleRate: 0,
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
