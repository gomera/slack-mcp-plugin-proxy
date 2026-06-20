# Slack MCP plugin proxy

Local-only workaround so the **Slack MCP plugin** signs in from **Xcode 27** for **macOS**.

## The problem

Xcode 27's coding-agent bridge (`mcpbridge`) does OAuth using the loopback **IP literal**
`127.0.0.1` (per RFC 8252 §8.3), sending `redirect_uri=http://127.0.0.1:3118/callback`.
Slack's hosted MCP app registered **only** `http://localhost:3118/callback`, so it rejects
the request and sign-in fails. The host string is hardcoded in Xcode and the registration
lives on Slack's servers — neither is editable locally.

## The real fix 
The proper fix is Slack registering `127.0.0.1:3118` (or a loopback wildcard). Until then,
this proxy bridges the gap on your own machine. 

More info: https://github.com/slackapi/slack-mcp-plugin/issues/48

## The temporary workaround

`rewrite.py` is a [mitmproxy](https://mitmproxy.org) addon that rewrites the host string
in flight, on this machine only:

- outbound → slack.com : `127.0.0.1:3118` → `localhost:3118`  (so Slack accepts it)
- inbound  ← slack.com : `localhost:3118` → `127.0.0.1:3118`  (so the 302 callback lands on Xcode's listener)

Net effect: Slack always sees `localhost` (registered ✓), Xcode always sees `127.0.0.1`
(what it binds ✓), and `redirect_uri` stays consistent across the authorize and token steps.

The proxy is started with `--allow-hosts 'slack\.com'`, so **only slack.com is intercepted**.
All other traffic — including other OAuth flows — passes through untouched and undecrypted.

## One-time setup

```bash
brew install mitmproxy
mitmdump            # start once to generate ~/.mitmproxy/mitmproxy-ca-cert.pem, then Ctrl-C
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain ~/.mitmproxy/mitmproxy-ca-cert.pem
```

## Usage

```bash
./slack-proxy-on        # start proxy + route Wi-Fi through it (asks for sudo)
# -> trigger Slack sign-in in Xcode, click Allow
./slack-proxy-off       # stop proxy + restore normal networking
```

Re-run `on` / sign-in / `off` whenever Xcode needs to re-authenticate. Slack's MCP tokens
expire ~hourly with no refresh token (https://github.com/anthropics/claude-code/issues/29257),
so re-auth is expected — that's a Slack limitation, not this proxy.

### Notes

- Default interface is `Wi-Fi`. Override: `SLACK_PROXY_SERVICE="Thunderbolt Bridge" ./slack-proxy-on`.
- **VPN (e.g. Surfshark):** some VPN clients bypass the system web proxy. If the rewrite
  doesn't fire (check `logs/mitmdump.log`), disconnect the VPN during sign-in, or set the
  proxy on the VPN's network service instead of Wi-Fi.
- **Why turn it off:** the system proxy points at `127.0.0.1:8080`; if `mitmdump` isn't
  running, apps hit a dead proxy and networking breaks. Off = no dependency, and no trusted
  MITM in the path when you don't need it.
- **Remove the CA trust** when you're fully done with this workaround:
  `sudo security delete-certificate -c mitmproxy /Library/Keychains/System.keychain`

## Files

- `rewrite.py` — the mitmproxy rewrite addon
- `slack-proxy-on` / `slack-proxy-off` — start/stop helpers
- `logs/` — `mitmdump.log` (intercepted traffic) and `proxy.log` (timestamped on/off actions); git-ignored
- `.mitmdump.pid` — runtime pid of the proxy, at the repo root; git-ignored

## Watch it work

While signing in from Xcode, tail the log to confirm the rewrite fires:

```bash
tail -f logs/mitmdump.log
```

You should see `[slack-rewrite] ...` lines confirming each rewrite (authorize URL, the
302 Location, and the token-exchange body). No `slack.com` lines at all means traffic
isn't reaching the proxy — usually the VPN bypass noted above.

The on/off scripts log their own actions (and verify the proxy actually flipped) to
`logs/proxy.log`:

```bash
tail -f logs/proxy.log
```
