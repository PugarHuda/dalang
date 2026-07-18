"""Token-gating on X Layer — opt-in access control by on-chain balance (dep-free).

Set DALANG_TOKENGATE_CONTRACT (an ERC-20 or ERC-721 on X Layer) to require callers to
hold >= DALANG_TOKENGATE_MIN of it. The caller passes their `wallet`; the server reads
balanceOf(wallet) over JSON-RPC (DALANG_RPC_URL) and allows or rejects. Read-only — no
keys, no writes. Fail-closed: an RPC error denies (never grants access on a failed read).
Off by default (unset → no gate).

NOTE: DALANG_TOKENGATE_MIN is in RAW ON-CHAIN UNITS. For an ERC-721 it's an NFT count
(MIN=1 = "holds any"). For an 18-decimal ERC-20, "1 whole token" is MIN=1000000000000000000,
not 1 — set the decimals-adjusted value or every dust holder passes.
"""
import json, os, re, urllib.request

_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BALANCEOF = "0x70a08231"  # balanceOf(address) selector — same for ERC-20 and ERC-721

def _cfg() -> dict:
    return {
        "contract": os.environ.get("DALANG_TOKENGATE_CONTRACT", ""),
        "min": int(os.environ.get("DALANG_TOKENGATE_MIN", "1")),
        "rpc": os.environ.get("DALANG_RPC_URL", "https://rpc.xlayer.tech"),
    }

def enabled() -> bool:
    return bool(os.environ.get("DALANG_TOKENGATE_CONTRACT"))

def _eth_call(rpc: str, to: str, data: str) -> str:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    req = urllib.request.Request(rpc, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    if res.get("error"):
        raise RuntimeError(res["error"].get("message", "rpc error"))
    return res.get("result", "0x")

def balance_of(wallet: str, contract: str = "", rpc: str = "") -> int:
    c = _cfg()
    data = _BALANCEOF + wallet[2:].lower().rjust(64, "0")  # selector + 32-byte right-aligned address
    res = _eth_call(rpc or c["rpc"], contract or c["contract"], data)
    return int(res, 16) if res and res != "0x" else 0

def check(wallet: str) -> tuple[bool, str]:
    """True if `wallet` holds >= the configured minimum of the gate token on X Layer."""
    if not _ADDR.match(wallet or ""):
        return False, "a valid wallet address (0x…) is required"
    try:
        bal = balance_of(wallet)
    except Exception as e:  # fail-closed: never grant compute on an unverifiable read
        return False, f"token-gate check failed: {e}"
    need = _cfg()["min"]
    if bal < need:
        return False, f"wallet holds {bal}; needs >= {need} of the gate token"
    return True, ""

def demo() -> None:
    global _eth_call
    orig = _eth_call
    seen = {}
    def fake(rpc, to, data):
        seen["rpc"], seen["to"], seen["data"] = rpc, to, data
        return "0x0000000000000000000000000000000000000000000000000000000000000003"  # balance 3
    _eth_call = fake
    try:
        os.environ["DALANG_TOKENGATE_CONTRACT"] = "0xToken"
        os.environ["DALANG_TOKENGATE_MIN"] = "2"
        ok, why = check("0x" + "ab" * 20)
        assert ok, why
        # data = selector + left-padded lowercased address (32 bytes)
        assert seen["data"] == _BALANCEOF + ("ab" * 20).rjust(64, "0")
        assert len(seen["data"]) == 10 + 64
        os.environ["DALANG_TOKENGATE_MIN"] = "5"       # balance 3 < 5 -> deny
        assert not check("0x" + "ab" * 20)[0]
        assert not check("not-an-address")[0]           # bad address -> deny
        _eth_call = lambda *a: (_ for _ in ()).throw(RuntimeError("rpc down"))
        assert not check("0x" + "cd" * 20)[0]            # rpc error -> fail-closed
        print("tokengate self-check ok")
    finally:
        _eth_call = orig
        os.environ.pop("DALANG_TOKENGATE_CONTRACT", None)
        os.environ.pop("DALANG_TOKENGATE_MIN", None)

if __name__ == "__main__":
    demo()
