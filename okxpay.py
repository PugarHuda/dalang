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
import asyncio, base64, json, os, urllib.request

PAID_TOOL = "generate_animatic"
MCP_PATH = os.environ.get("DALANG_MCP_PATH", "/mcp")

def _cfg() -> dict:
    return {
        "payTo": os.environ.get("DALANG_X402_PAYTO", ""),
        "asset": os.environ.get("DALANG_X402_ASSET", ""),          # USDT/USDG contract on X Layer
        # network: the facilitator's literal. OKX A2MCP's exact string is unverified from
        # here (okx.com is unreachable); X Layer CAIP-2 is "eip155:196". Override to match.
        "network": os.environ.get("DALANG_X402_NETWORK", "x-layer"),
        "amount": os.environ.get("DALANG_X402_AMOUNT", "490000"),  # atomic units ($0.49 USDT, 6dp)
        "facilitator": os.environ.get("DALANG_X402_FACILITATOR", ""),
        "description": os.environ.get("DALANG_X402_DESCRIPTION", "One DALANG animatic"),
        # timeout must exceed the worst-case render (cinematic ~240s + assembly) or a slow
        # render finishes AFTER the authorization expires -> settle fails on a good render.
        "timeout": int(os.environ.get("DALANG_X402_TIMEOUT", "600")),
        # the "exact" (EIP-3009) scheme needs the asset's EIP-712 domain in `extra` so the
        # client can build a matching transferWithAuthorization signature (USDC: version "2").
        "asset_name": os.environ.get("DALANG_X402_ASSET_NAME", ""),
        "asset_version": os.environ.get("DALANG_X402_ASSET_VERSION", "1"),
    }

def enabled() -> bool:
    return bool(os.environ.get("DALANG_X402_PAYTO"))

def challenge(resource: str) -> dict:
    """The x402 challenge: {x402Version, resource, accepts:[…]}.

    `amount` AND `maxAmountRequired` both carry the atomic price — the coinbase/x402 v1
    body names it maxAmountRequired, while OKX's listing review requires `amount`; sending
    both satisfies either reader.
    """
    c = _cfg()
    extra = {"name": c["asset_name"], "version": c["asset_version"]} if c["asset_name"] else {}
    return {"x402Version": 2,
            # v2 models a resource as an object; v1 clients read the string copy inside accepts
            "resource": {"url": resource, "description": c["description"],
                         "mimeType": "application/json"},
            "accepts": [{
                "scheme": "exact", "network": c["network"],
                "amount": c["amount"], "maxAmountRequired": c["amount"],
                "asset": c["asset"], "payTo": c["payTo"], "resource": resource,
                "description": c["description"], "mimeType": "application/json",
                "maxTimeoutSeconds": c["timeout"], "extra": extra}]}

def challenge_header(resource: str) -> bytes:
    """base64 of the challenge, for the PAYMENT-REQUIRED response header — a caller that
    reads only headers must still obtain the payment requirements."""
    return base64.b64encode(json.dumps(challenge(resource), separators=(",", ":")).encode())

def payment_requirements(resource: str) -> dict:
    """The x402 v1 402 body: what the caller must pay and where (X Layer)."""
    return challenge(resource) | {"error": "payment required: send PAYMENT-SIG (or X-PAYMENT)"}

def _sdk_client():
    """OKX's official seller SDK client, or None when credentials aren't configured.

    The plain /verify + /settle calls below answer 403 without OKX-signed auth — the
    facilitator requires the API key, secret and passphrase from the OKX Developer Portal.
    Set OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE and this path takes over
    (`pip install okxweb3-app-x402`).
    """
    k = os.environ.get("OKX_API_KEY", "")
    s = os.environ.get("OKX_SECRET_KEY", "")
    p = os.environ.get("OKX_PASSPHRASE", "")
    if not (k and s and p):
        return None
    try:
        from x402.http.okx_facilitator_client import OKXFacilitatorClientSync, OKXFacilitatorConfig
        from x402.http.okx_auth import OKXAuthConfig
        return OKXFacilitatorClientSync(OKXFacilitatorConfig(
            auth=OKXAuthConfig(api_key=k, secret_key=s, passphrase=p)))
    except Exception:
        return None  # SDK absent -> fall back to the raw facilitator call


def _sdk_models(payload: dict, resource: str):
    """Coerce either payload dialect into the SDK's models: OKX's client sends `accepted`
    and an object `resource`, a plain coinbase/x402 client sends neither."""
    from x402.schemas.payments import PaymentPayload, PaymentRequirements
    accepts = payment_requirements(resource)["accepts"][0]
    req = PaymentRequirements.model_validate(accepts)
    p = dict(payload)
    p.setdefault("accepted", accepts)
    if isinstance(p.get("resource"), str):
        p.pop("resource")
    return PaymentPayload.model_validate(p), req


def verify(x_payment_b64: str, resource: str) -> tuple[bool, str]:
    """Verify the payment header via OKX's facilitator (official SDK when credentials are
    set). No facilitator -> reject: we never serve paid compute on an unverifiable claim."""
    if not x_payment_b64:
        return False, "missing payment: send PAYMENT-SIGNATURE (or X-PAYMENT)"
    try:
        payload = json.loads(base64.b64decode(x_payment_b64))
    except Exception:
        return False, "malformed X-PAYMENT header"
    if not isinstance(payload, dict):  # valid base64 of a non-object (array/primitive) -> reject cleanly
        return False, "malformed X-PAYMENT header"
    # OKX's dialect nests the scheme inside `accepted`; coinbase/x402 puts it at the top
    # level. Checking only the top level rejected a real OKX payment before it ever reached
    # the facilitator.
    scheme = payload.get("scheme") or (payload.get("accepted") or {}).get("scheme")
    # v1 payloads arrive on X-PAYMENT, v2 on PAYMENT-SIGNATURE — accept both versions.
    if str(payload.get("x402Version")) not in ("1", "2") or scheme != "exact":
        return False, "unsupported payment scheme"
    client = _sdk_client()
    if client is not None:
        try:
            res = client.verify(*_sdk_models(payload, resource))
            return bool(getattr(res, "is_valid", False)), getattr(res, "invalid_reason", "") or ""
        except Exception as e:
            return False, f"facilitator error: {e}"

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

def settle(x_payment_b64: str, resource: str) -> tuple[bool, dict]:
    """Capture a verified payment via the facilitator's /settle (x402). Returns
    (success, settlement); the settlement dict goes back in X-PAYMENT-RESPONSE so the
    caller has on-chain proof (tx hash) that this render was paid."""
    try:
        payload = json.loads(base64.b64decode(x_payment_b64))
    except Exception:
        return False, {"error": "malformed payment header"}

    client = _sdk_client()
    if client is not None:
        try:
            res = client.settle(*_sdk_models(payload, resource))
            ok = bool(getattr(res, "success", False))
            out = res.model_dump(by_alias=True) if hasattr(res, "model_dump") else {"success": ok}
            return ok, out
        except Exception as e:
            return False, {"error": f"settlement failed: {e}"}

    fac = _cfg()["facilitator"]
    if not fac:
        return False, {"error": "no facilitator configured"}
    body = json.dumps({"x402Version": 1, "paymentPayload": payload,
                       "paymentRequirements": payment_requirements(resource)["accepts"][0]}).encode()
    try:
        req = urllib.request.Request(fac.rstrip("/") + "/settle", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read())
        return bool(res.get("success")), res
    except Exception as e:
        return False, {"error": f"settlement failed: {e}"}

def is_paid_call(body: bytes) -> bool:
    """True only for a JSON-RPC tools/call of the paid tool — the handshake,
    tools/list, and free tools pass through unpaid."""
    try:
        msg = json.loads(body)
    except Exception:
        return False
    if not isinstance(msg, dict):  # JSON-RPC batches are arrays; primitives/null are legal JSON too
        return False               # -> not a single paid tools/call, and .get() below would crash
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
        chunks, total, more = [], 0, True
        while more:
            m = await receive()
            b = m.get("body", b"")
            total += len(b)
            if total > 6_000_000:  # MCP JSON-RPC is small; cap so a huge POST can't exhaust memory
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"request body too large"}'})
                return
            chunks.append(b)
            more = m.get("more_body", False)
        body = b"".join(chunks)

        def make_replay():  # a fresh receive() that replays the buffered body once
            sent = False
            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}
            return replay

        if not is_paid_call(body):
            return await self.app(scope, make_replay(), send)

        resource = f"{scope.get('scheme','https')}://{_header(scope, b'host') or 'localhost'}{MCP_PATH}"
        # Header names, straight from the SDK's own constants: a v2 payload arrives on
        # PAYMENT-SIGNATURE, a v1 payload on X-PAYMENT (PAYMENT-SIG appears in the docs
        # prose). Reading only X-PAYMENT meant an OKX-native caller could pay and still be
        # answered 402 forever.
        xp = (_header(scope, b"payment-signature") or _header(scope, b"payment-sig")
              or _header(scope, b"x-payment"))

        async def reject(reason):  # emit the x402 402 challenge, no compute run
            out = json.dumps(payment_requirements(resource) | {"error": reason}).encode()
            await send({"type": "http.response.start", "status": 402,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"payment-required", challenge_header(resource)),
                                    (b"www-authenticate", b'Payment realm="x402"'),
                                    (b"access-control-expose-headers", b"PAYMENT-REQUIRED"),
                                    (b"content-length", str(len(out)).encode())]})
            await send({"type": "http.response.body", "body": out})

        ok, reason = await asyncio.to_thread(verify, xp, resource)  # verify BEFORE compute
        if not ok:
            return await reject(reason)

        # Run the render, buffering its response, so we settle (capture funds) ONLY after
        # a successful render — a failed/timed-out render must not charge the caller. (MCP
        # stateless tool calls return a single JSON response, so buffering is safe.)
        buffered, status = [], 500
        async def capture(msg):
            nonlocal status
            if msg["type"] == "http.response.start":
                status = msg["status"]
            buffered.append(msg)
        await self.app(scope, make_replay(), capture)

        # Success = 2xx AND the response carries a server-only success sentinel. A render
        # always emits content_sha256; an {"error": ...} dict never does. We must NOT sniff
        # for the absence of "error" — that string is caller-controllable (a voiceover/title
        # of "error"), which would let a caller dodge settlement and replay for free renders.
        resp_body = b"".join(m.get("body", b"") for m in buffered if m["type"] == "http.response.body")
        # Match the QUOTED JSON key, not the bare token: an error message that merely echoes a
        # caller's "content_sha256" text (e.g. a brief surfaced in a Venice 4xx body) must not be
        # scored a success and settled. A real render emits "content_sha256":"0x…" as a key.
        rendered_ok = 200 <= status < 300 and b'"content_sha256"' in resp_body
        if not rendered_ok:  # guard/render error -> serve it, never settle (no charge on failure)
            for m in buffered:
                await send(m)
            return
        # Render succeeded -> capture funds BEFORE delivering. SINGLE attempt, no retry: the
        # x402 authorization is single-use (EIP-3009 nonce), so re-submitting a settle whose
        # HTTP response was merely lost risks a double-capture or a false "nonce already used"
        # failure on a payment that actually landed.
        settled, sresult = await asyncio.to_thread(settle, xp, resource)  # capture on X Layer
        if not settled:  # compute is spent, but withhold the paid artifact — never give a free render.
            # Don't claim "not charged": a timed-out settle may have landed on-chain.
            return await reject(f"render complete but settlement was not confirmed "
                                f"({sresult.get('error', 'settlement rejected')}); "
                                "check your wallet before retrying to avoid a double payment")
        xpr = base64.b64encode(json.dumps(sresult).encode())  # on-chain proof (tx hash)
        for m in buffered:
            if m["type"] == "http.response.start":
                # PAYMENT-RESPONSE is what OKX's SDK reads; x-payment-response is the
                # coinbase/x402 spelling. Emit both so either client sees the proof.
                m["headers"] = list(m.get("headers", [])) + [(b"payment-response", xpr),
                                                            (b"x-payment-response", xpr)]
            await send(m)  # flush the paid render to the caller
