"""mitmproxy addon: bridge Xcode 27's RFC-8252 loopback OAuth redirect to Slack's
localhost-only registration for the hosted Slack MCP server.

Xcode's mcpbridge sends redirect_uri=http://127.0.0.1:3118/callback (loopback IP
literal, per RFC 8252 §8.3). Slack's MCP app only registered http://localhost:3118/callback,
so it rejects the authorize request. This rewrites the host string in flight, on THIS
machine only — Slack's servers are never modified:

  * outbound -> slack.com  : 127.0.0.1:3118 -> localhost:3118  (so Slack accepts it)
  * inbound  <- slack.com  : localhost:3118 -> 127.0.0.1:3118  (so the 302 lands on
                                                                Xcode's real listener)

Each rewrite logs a one-line confirmation (no tokens/codes) so you can tell at a glance
whether it fired during sign-in:  tail -f logs/mitmdump.log

Run with:  mitmdump -s rewrite.py -p 8080 --allow-hosts 'slack\.com'
"""

import logging

from mitmproxy import http

LOOP_IP = "127.0.0.1:3118"
LOOP_HOST = "localhost:3118"


def request(flow: http.HTTPFlow) -> None:
    if "slack.com" not in flow.request.pretty_host:
        return
    # Authorize request carries redirect_uri in the query string.
    if LOOP_IP in flow.request.pretty_url:
        flow.request.url = flow.request.pretty_url.replace(LOOP_IP, LOOP_HOST)
        logging.info("[slack-rewrite] request URL %s -> %s on %s", LOOP_IP, LOOP_HOST, flow.request.path.split("?")[0])
    # Token exchange carries redirect_uri in the POST body (form-encoded or JSON).
    if flow.request.content and LOOP_IP.encode() in flow.request.content:
        flow.request.content = flow.request.content.replace(LOOP_IP.encode(), LOOP_HOST.encode())
        logging.info("[slack-rewrite] request body %s -> %s on %s", LOOP_IP, LOOP_HOST, flow.request.path.split("?")[0])


def response(flow: http.HTTPFlow) -> None:
    if "slack.com" not in flow.request.pretty_host:
        return
    # Send the browser's callback back to Xcode's real 127.0.0.1 loopback listener.
    location = flow.response.headers.get("location", "")
    if LOOP_HOST in location:
        flow.response.headers["location"] = location.replace(LOOP_HOST, LOOP_IP)
        logging.info("[slack-rewrite] response Location %s -> %s (%s)", LOOP_HOST, LOOP_IP, flow.response.status_code)
