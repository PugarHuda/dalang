"""x402 payment layer — makes DALANG a native paid endpoint for OKX A2MCP / X Layer.

Opt-in: set DALANG_X402_PAYTO (your X Layer wallet). When enabled, a `tools/call`
for the paid tool over HTTP must carry a verified `X-PAYMENT` header; otherwise the
server answers HTTP **402** with x402 payment requirements (USDT/USDG on X Layer) —
exactly the "x402-based paid endpoint" form OKX A2MCP settles via the Agent Payments
Protocol. Verification/settlement is delegated to a configured facilitator (the x402
design), so no private keys ever touch this server. Off by default → the free /
access_key flow is unchanged.

Spec: coinbase/x402 v1. The handshake and tools/list stay free; only the paid
tools/call is gated.
"""
import base64, json, os, urllib.request

PAID_TOOL = "generate_animatic"
MCP_PATH = os.environ.get("DALANG_MCP_PATH", "/mcp")

def _cfg() -> dict:
    return {
        "payTo": os.environ.get("DALANG_X402_PAYTO", ""),
        "asset": os.environ.get("DALANG_X402_ASSET", ""),          # USDT/USDG contract on X Layer
        "network": os.environ.get("DALANG_X402_NETWORK", "x-layer"),
        "amount": os.environ.get("DALANG_X402_AMOUNT", "490000"),  # atomic units ($0.49 USDT, 6dp)
        "facilitator": os.environ.get("DALANG_X402_FACILITATOR", ""),
        "description": os.environ.get("DALANG_X402_DESCRIPTION", "One DALANG animatic"),
        "timeout": int(os.environ.get("DALANG_X402_TIMEOUT", "300")),
    }

def enabled() -> bool:
    return bool(os.environ.get("DALANG_X402_PAYTO"))

def payment_requirements(resource: str) -> dict:
    """The x402 v1 402 body: what the caller must pay and where (X Layer)."""
    c = _cfg()
    return {"x402Version": 1, "error": "X-PAYMENT header is required", "accepts": [{
        "scheme": "exact", "network": c["network"], "maxAmountRequired": c["amount"],
        "asset": c["asset"], "payTo": c["payTo"], "resource": resource,
        "description": c["description"], "mimeType": "application/json",
        "maxTimeoutSeconds": c["timeout"], "extra": {}}]}

def verify(x_payment_b64: str, resource: str) -> tuple[bool, str]:
    """Verify an X-PAYMENT header via the configured facilitator's /verify (x402).
    No facilitator -> reject: we never serve paid compute on an unverifiable claim."""
    if not x_payment_b64:
        return False, "missing X-PAYMENT header"
    try:
        payload = json.loads(base64.b64decode(x_payment_b64))
    except Exception:
        return False, "malformed X-PAYMENT header"
    if payload.get("x402Version") != 1 or payload.get("scheme") != "exact":
        return False, "unsupported payment scheme"
    fac = _cfg()["facilitator"]
    if not fac:
        return False, "no facilitator configured"
    body = json.dumps({"x402Version": 1, "paymentPayload": payload,
                       "paymentRequirements": payment_requirements(resource)["accepts"][0]}).encode()
    try:
        req = urllib.request.Request(fac.rstrip("/") + "/verify", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read())
        return bool(res.get("isValid")), res.get("invalidReason", "")
    except Exception as e:  # a facilitator outage must not silently grant free compute
        return False, f"facilitator error: {e}"

def is_paid_call(body: bytes) -> bool:
    """True only for a JSON-RPC tools/call of the paid tool — the handshake,
    tools/list, and free tools pass through unpaid."""
    try:
        msg = json.loads(body)
    except Exception:
        return False
    return (msg.get("method") == "tools/call"
            and isinstance(msg.get("params"), dict)
            and msg["params"].get("name") == PAID_TOOL)

def _header(scope, name: bytes) -> str:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return v.decode("latin-1")
    return ""

class X402Middleware:
    """ASGI middleware: gate the paid tools/call with x402, everything else free."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("path") != MCP_PATH:
            return await self.app(scope, receive, send)
        # buffer the JSON-RPC body so we can both inspect it and replay it downstream
        chunks, more = [], True
        while more:
            m = await receive()
            chunks.append(m.get("body", b""))
            more = m.get("more_body", False)
        body = b"".join(chunks)
        if is_paid_call(body):
            resource = f"{scope.get('scheme','https')}://{_header(scope, b'host') or 'localhost'}{MCP_PATH}"
            ok, reason = verify(_header(scope, b"x-payment"), resource)
            if not ok:
                out = json.dumps(payment_requirements(resource) | {"error": reason}).encode()
                await send({"type": "http.response.start", "status": 402,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(out)).encode())]})
                await send({"type": "http.response.body", "body": out})
                return
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}
        await self.app(scope, replay, send)
