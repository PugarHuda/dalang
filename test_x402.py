"""x402 payment-gate tests (pure, no ffmpeg/network) — verifies DALANG speaks the
OKX A2MCP / X Layer paid-endpoint protocol: only the paid tools/call is gated, the
handshake and tools/list stay free, and a verified X-PAYMENT passes through.

    python test_x402.py     # exits non-zero on any failure
"""
import asyncio, base64, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DALANG_X402_PAYTO", "0xABCdef0000000000000000000000000000000001")
os.environ.setdefault("DALANG_X402_ASSET", "0xUSDTonXLayer")
os.environ.setdefault("DALANG_X402_FACILITATOR", "https://facilitator.example")
import x402

FAILS = []
def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)

async def _downstream(scope, receive, send):
    m = await receive()  # must receive the replayed body
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b'{"ok":true,"bodylen":%d}' % len(m.get("body", b""))})

def call(body_obj, headers=None, path="/mcp", method="POST"):
    mw = x402.X402Middleware(_downstream)
    scope = {"type": "http", "method": method, "path": path, "scheme": "https",
             "headers": [(b"host", b"dalang.example")] + [(k.encode(), v.encode()) for k, v in (headers or {}).items()]}
    body = json.dumps(body_obj).encode()
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    out = {"headers": {}}
    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = {k.decode(): v.decode() for k, v in msg.get("headers", [])}
        elif msg["type"] == "http.response.body":
            out["body"] = msg.get("body", b"")
    asyncio.new_event_loop().run_until_complete(mw(scope, receive, send))
    return out

def main():
    print("== x402 config ==")
    check("enabled when DALANG_X402_PAYTO set", x402.enabled())
    req = x402.payment_requirements("https://dalang.example/mcp")["accepts"][0]
    check("requirements: exact scheme", req["scheme"] == "exact")
    check("requirements: X Layer network + payTo + amount",
          req["network"] and req["payTo"].startswith("0x") and req["maxAmountRequired"] == "490000")

    print("\n== is_paid_call detection ==")
    paid = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "generate_animatic", "arguments": {}}}
    check("paid tools/call detected", x402.is_paid_call(json.dumps(paid).encode()))
    check("initialize not paid", not x402.is_paid_call(b'{"method":"initialize"}'))
    check("tools/list not paid", not x402.is_paid_call(b'{"method":"tools/list"}'))

    print("\n== middleware gating ==")
    r = call(paid)
    body = json.loads(r["body"])
    check("paid call, no X-PAYMENT -> 402", r["status"] == 402)
    check("402 body is x402 v1 + payment requirements",
          body.get("x402Version") == 1 and body["accepts"][0]["scheme"] == "exact")
    check("initialize -> free passthrough (200)", call({"jsonrpc": "2.0", "id": 0, "method": "initialize"})["status"] == 200)
    check("tools/list -> free (200)", call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["status"] == 200)
    check("GET (SSE handshake) -> free", call({}, method="GET")["status"] == 200)

    print("\n== settle only AFTER a successful render (charge-on-failure guard) ==")
    settled_calls = []
    x402.verify = lambda hdr, res: (bool(hdr), "" if hdr else "missing")  # stub facilitator /verify
    def stub_settle(hdr, res):
        settled_calls.append(1)
        return True, {"success": True, "txHash": "0xdeadbeef"}
    x402.settle = stub_settle
    xp = base64.b64encode(json.dumps({"x402Version": 1, "scheme": "exact", "network": "x-layer", "payload": {}}).encode()).decode()

    # successful downstream (200, no error) -> settle runs, proof header attached
    r = call(paid, {"x-payment": xp})
    check("paid + success -> 200", r["status"] == 200)
    check("settle called once on success", len(settled_calls) == 1)
    check("X-PAYMENT-RESPONSE header carries settlement proof", "0xdeadbeef" in base64.b64decode(r["headers"].get("x-payment-response", "")).decode())

    # downstream that returns an {"error": ...} -> served, but NOT settled (no charge on failure)
    async def _err_downstream(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"error":"render failed"}'})
    settled_calls.clear()
    mw = x402.X402Middleware(_err_downstream)
    scope = {"type": "http", "method": "POST", "path": "/mcp", "scheme": "https",
             "headers": [(b"host", b"d"), (b"x-payment", xp.encode())]}
    async def rcv(): return {"type": "http.request", "body": json.dumps(paid).encode(), "more_body": False}
    got = {}
    async def snd(m):
        if m["type"] == "http.response.start": got["status"] = m["status"]
    asyncio.new_event_loop().run_until_complete(mw(scope, rcv, snd))
    check("render error served (200), NOT settled -> no charge on failure", got["status"] == 200 and len(settled_calls) == 0)

    print("\n" + ("test_x402: ALL PASSED" if not FAILS else f"test_x402 FAILURES: {FAILS}"))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
