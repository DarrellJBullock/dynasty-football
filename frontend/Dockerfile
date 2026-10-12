# The web app: Next.js's self-contained server (output: "standalone").
# Build from frontend/:  docker build -t dynasty-web --build-arg RELEASE=$(git rev-parse HEAD) .
# Run with API_URL (or API_HOSTPORT) pointing at the game server.

FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Inlined into the browser bundle: the (public) Sentry DSN and the build's commit.
ARG NEXT_PUBLIC_SENTRY_DSN=""
ARG RELEASE=""
ENV NEXT_OUTPUT=standalone \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_RELEASE=$RELEASE
RUN npm run build && mkdir -p public

FROM node:22-slim
WORKDIR /app
ARG RELEASE=""
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0 RELEASE=$RELEASE
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
# Static files: the Unity viewer's build (public/unity/), when CI built it.
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
