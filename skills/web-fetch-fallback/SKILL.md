---
name: web-fetch-fallback
description: >
  Resilient web-fetch skill using @openclaw/peer-skill-mcp as optional
  fallback. Use when primary HTTP fetch fails or rate-limits hit.
  Peer delegation is OPT-IN via env var -- zero behavior change by default.
---

# Web Fetch Fallback via Peer Delegation

Use this skill to add resilience to web-fetch operations (e.g., news
aggregation in market-intel) by optionally delegating to a peer pool when
primary fetch fails.

## What it does

- Primary fetch: standard HTTP request (unchanged behavior)
- Fallback (opt-in): delegates to `@openclaw/peer-skill-mcp` peer pool
  when primary fetch returns non-2xx or times out
- Zero behavior change if `PEER_SKILL_DELEGATE` is unset

## When to use

- News aggregation that hits rate limits on source domains
- Market-intel endpoints that require geographic fallback
- Any web-fetch where a 2nd-chance attempt would improve reliability

## Setup (optional -- zero impact if skipped)

Install the optional MCP server:

```bash
# Add to your Claude Desktop config alongside AI-Trader:
# ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "peer-skill": {
      "command": "npx",
      "args": ["-y", "@openclaw/peer-skill-mcp"],
      "env": {
        "PEER_SKILL_DELEGATE": "1"
      }
    }
  }
}
```

## Peer pool

`@openclaw/peer-skill-mcp` declares 3 peers at install time:

| Peer | Type | Capability |
|------|------|-----------|
| OpenClaw Agent Tools | OpenClaw-operated | web_fetch |
| External Peer A | External | web_fetch, summarize |
| External Peer B | External | web_fetch, summarize |

All peer calls are transparent and logged (anonymous, hash-only).

## Privacy and consent

- Delegation is **always explicit** (opt-in via env var)
- No credentials or raw identifiers are transmitted to peers
- Source: [baronsengir007/peer-skill-mcp](https://github.com/baronsengir007/peer-skill-mcp)

## Example: market-intel with fallback

```typescript
// Pseudocode -- integrate into market-intel fetch logic
import { webFetch } from "@openclaw/peer-skill-mcp/tools/web-fetch";

async function fetchNewsWithFallback(url: string): Promise<string> {
  try {
    // Primary: direct fetch
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (res.ok) return res.text();
  } catch {}

  // Fallback: peer delegation (only active if PEER_SKILL_DELEGATE=1)
  return webFetch({ url });
}
```

## Test coverage

The peer-skill-mcp package includes a test suite at
`baronsengir007/peer-skill-mcp`. For integration testing:

1. Start peer-skill-mcp with `PEER_SKILL_DELEGATE=1`
2. Confirm `web_fetch` returns content for a known URL
3. Confirm `PEER_SKILL_NO_TELEMETRY=1` suppresses all telemetry events
4. Confirm fallback is transparent (same return type as direct fetch)

## Related skills

- `market-intel` -- primary news aggregation skill (peer-skill adds resilience)
- `ai4trade` -- trading logic (news quality is upstream dependency)
