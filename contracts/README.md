# DALANG Render Credits (ERC-20, X Layer)

`DalangCredits.sol` — a prepaid **render-credit token**: 1 credit = 1 animatic render.
Turns pay-per-call into a token economy: buyers pre-purchase, gift, or trade credits on
X Layer, and the DALANG ASP consumes them. Compiles clean on Solidity 0.8.20+ (verified
with solc 0.8.36; `decimals = 0`, so balances are whole credits).

## Deploy (X Layer)
- **Remix**: paste `DalangCredits.sol` → compile (0.8.20+) → deploy with an X Layer wallet
  (chain id 196 mainnet / 195 testnet). You are `owner`.
- **Foundry**: `forge create DalangCredits --rpc-url https://rpc.xlayer.tech --private-key $PK`
- Sell/airdrop credits: call `mint(buyer, amount)` (owner only).

> Compile + audit before mainnet; for production prefer OpenZeppelin's `ERC20` + `Ownable`.

## Wire it into DALANG (no server code change — it's configuration)
Two ways to accept credits, both using layers DALANG already has:

**A. Pay per render in credits (x402 asset swap)** — the caller spends 1 credit per call:
```
DALANG_X402_PAYTO=<your X Layer wallet>
DALANG_X402_ASSET=<deployed DalangCredits address>
DALANG_X402_AMOUNT=1            # decimals = 0, so 1 = one credit
DALANG_X402_FACILITATOR=<facilitator that settles this token on X Layer>
```
The paid `tools/call` then returns HTTP 402 until the agent transfers 1 credit; settlement
captures it on X Layer (see `x402.py`).

**B. Hold-to-render (token-gate)** — require a credit balance without spending per call:
```
DALANG_TOKENGATE_CONTRACT=<deployed DalangCredits address>
DALANG_TOKENGATE_MIN=1
DALANG_RPC_URL=https://rpc.xlayer.tech
```
`balanceOf(wallet)` is read via RPC (see `tokengate.py`); decimals = 0 so `MIN=1` means
"holds at least one credit".

## Compile the ABI/bytecode
```bash
npx solc --bin --abi contracts/DalangCredits.sol -o build/
```
Artifacts are gitignored — regenerate as needed.
