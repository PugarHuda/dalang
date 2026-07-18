// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DALANG Render Credits — 1 credit = 1 animatic render.
/// @notice Minimal ERC-20 (decimals = 0, whole credits) for X Layer. The operator mints
/// and sells credits; the DALANG ASP then either (a) accepts this token as the x402
/// payment asset — set DALANG_X402_ASSET to this address and DALANG_X402_AMOUNT=1 — so an
/// agent spends 1 credit per render, or (b) gates renders on holding >= 1 via
/// DALANG_TOKENGATE_CONTRACT. Buyers can pre-purchase, gift, or trade credits on X Layer.
/// @dev Canonical minimal ERC-20 + owner mint + holder burn. Solidity 0.8 checks overflow.
///      COMPILE + AUDIT before mainnet; prefer OpenZeppelin's ERC20/Ownable in production.
contract DalangCredits {
    string public constant name = "DALANG Render Credits";
    string public constant symbol = "DALANG";
    uint8 public constant decimals = 0; // whole credits: 1 credit = 1 render

    uint256 public totalSupply;
    address public owner;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    /// @notice Mint credits to a buyer (operator only, e.g. after off-chain/on-chain purchase).
    function mint(address to, uint256 amount) external onlyOwner {
        require(to != address(0), "zero addr");
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    /// @notice Burn your own credits (e.g. on render consumption if the ASP requires a burn).
    function burn(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "insufficient");
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "allowance");
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero addr");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(to != address(0), "zero addr");
        require(balanceOf[from] >= amount, "insufficient");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}
