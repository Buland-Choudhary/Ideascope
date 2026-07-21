/**
 * Static denylist scan for generated scene code (docs/PLAN.md §7).
 *
 * A defense-in-depth check run before a scene is ever mounted — the sandboxed
 * iframe + CSP are the real boundary, but rejecting obviously-dangerous or
 * network-touching code early gives a cleaner failure and a second line of
 * defense. This is intentionally conservative: it can produce false positives,
 * which at generation time simply trigger a regenerate (not a silent pass).
 */

const FORBIDDEN_PATTERNS: { pattern: RegExp; reason: string }[] = [
  { pattern: /\bfetch\s*\(/, reason: "network access (fetch)" },
  { pattern: /\bXMLHttpRequest\b/, reason: "network access (XMLHttpRequest)" },
  { pattern: /\bWebSocket\b/, reason: "network access (WebSocket)" },
  { pattern: /\bimport\s*\(/, reason: "dynamic import" },
  { pattern: /\beval\s*\(/, reason: "eval" },
  { pattern: /\bnew\s+Function\b/, reason: "Function constructor" },
  { pattern: /\bdocument\s*\.\s*cookie\b/, reason: "cookie access" },
  { pattern: /\blocalStorage\b/, reason: "localStorage access" },
  { pattern: /\bsessionStorage\b/, reason: "sessionStorage access" },
  { pattern: /\bwindow\s*\.\s*parent\b/, reason: "parent-frame access" },
  { pattern: /\bwindow\s*\.\s*top\b/, reason: "top-frame access" },
  { pattern: /\bpostMessage\s*\(/, reason: "direct postMessage (runtime owns the bridge)" },
];

export interface DenylistResult {
  ok: boolean;
  reason?: string;
}

export function scanSceneCode(code: string): DenylistResult {
  for (const { pattern, reason } of FORBIDDEN_PATTERNS) {
    if (pattern.test(code)) {
      return { ok: false, reason };
    }
  }
  return { ok: true };
}
