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

**B. Hold-to-render (token-gate) — WORKS TODAY, recommended.** Require a credit balance:
```
DALANG_TOKENGATE_CONTRACT=<deployed DalangCredits address>
DALANG_TOKENGATE_MIN=1
DALANG_RPC_URL=https://rpc.xlayer.tech
```
`balanceOf(wallet)` is read via RPC (see `tokengate.py`); decimals = 0 so `MIN=1` means
"holds at least one credit".

**A. Pay-per-render in credits (x402 asset) — needs one more step.** The x402 "exact"
scheme settles via **EIP-3009** (`transferWithAuthorization`), which a plain ERC-20 does
not expose. To use credits *as the x402 payment asset*, add EIP-3009 (+ EIP-712 domain +
nonces) to the token first, then set `DALANG_X402_ASSET=<address>`, `DALANG_X402_AMOUNT=1`,
`DALANG_X402_ASSET_NAME="DALANG Render Credits"`, `DALANG_X402_ASSET_VERSION="1"`. Until
then, use Option B — or pay x402 in USDC/USDT (which already implement EIP-3009).

## Compile the ABI/bytecode
```bash
npx solc --bin --abi contracts/DalangCredits.sol -o build/
```
Artifacts are gitignored — regenerate as needed.
