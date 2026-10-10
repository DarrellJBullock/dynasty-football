/**
 * Full page navigation. Use after changes that affect every page (creating or
 * switching the active franchise): the client router cache can otherwise keep showing
 * pages rendered for the previous franchise.
 */
export function hardNavigate(url: string): void {
  window.location.assign(url);
}
