const DEFAULT_API_URL = "http://localhost:8000";

/**
 * The game server's address, for the web app's server side (proxy and server
 * components): API_URL, or API_HOSTPORT ("host:port" on a private network, as Render
 * hands it out). Read at request time, so one build serves any environment.
 */
export function gameServerUrl(): string {
  if (process.env.API_URL) return process.env.API_URL;
  if (process.env.API_HOSTPORT) return `http://${process.env.API_HOSTPORT}`;
  return DEFAULT_API_URL;
}
