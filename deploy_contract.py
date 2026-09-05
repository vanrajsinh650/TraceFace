#!/usr/bin/env python3
"""
TraceFace — Deploy EvidenceStorage to Ethereum Sepolia (using compiled bytecode)
Usage: python deploy_contract.py
Requires: SEPOLIA_RPC_URL + PRIVATE_KEY in .env
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SEPOLIA_CHAIN_ID = 11155111
SEPOLIA_EXPLORER = "https://sepolia.etherscan.io"


def deploy() -> None:
    rpc_url = os.environ.get("SEPOLIA_RPC_URL", "")
    private_key = os.environ.get("PRIVATE_KEY", "")

    if not private_key:
        print("ERROR: PRIVATE_KEY not set in .env")
        sys.exit(1)

    # Load compiled contract
    abi_path = Path("contracts/EvidenceStorage.abi.json")
    bin_path = Path("contracts/EvidenceStorage.bin")

    if not abi_path.exists() or not bin_path.exists():
        print("ERROR: Compiled contract artifacts missing in contracts/")
        sys.exit(1)

    abi = json.loads(abi_path.read_text())
    bytecode = bin_path.read_text().strip()
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    try:
        from web3 import Web3
    except ImportError:
        print("ERROR: pip install web3")
        sys.exit(1)

    # Connect with fallbacks
    endpoints = [
        rpc_url or "",
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://rpc.sepolia.org",
        "https://1rpc.io/sepolia",
        "https://sepolia.gateway.tenderly.co",
    ]
    endpoints = [e for e in endpoints if e]

    w3 = None
    for ep in endpoints:
        try:
            _w3 = Web3(Web3.HTTPProvider(ep, request_kwargs={"timeout": 12}))
            if _w3.is_connected():
                actual_chain_id = _w3.eth.chain_id
                if actual_chain_id == SEPOLIA_CHAIN_ID:
                    w3 = _w3
                    print(f"Connected: {ep}")
                    print(f"Chain ID:  {actual_chain_id} (Ethereum Sepolia)")
                    break
                else:
                    print(f"  {ep}: Unexpected chain ID {actual_chain_id} (expected {SEPOLIA_CHAIN_ID})")
        except Exception as e:
            print(f"  {ep}: {e}")

    if w3 is None:
        print("ERROR: Cannot connect to Ethereum Sepolia (Chain ID 11155111)")
        sys.exit(1)

    pk = private_key if private_key.startswith("0x") else "0x" + private_key
    account = w3.eth.account.from_key(pk)
    balance = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance, "ether")

    print(f"Deployer: {account.address}")
    print(f"Balance:  {balance_eth:.6f} Sepolia ETH")

    if balance == 0:
        print()
        print("WALLET HAS NO SEPOLIA ETH. Get testnet ETH from:")
        print("  https://sepoliafaucet.com or https://faucets.chain.link/sepolia")
        print(f"  Address: {account.address}")
        sys.exit(1)

    print("Deploying EvidenceStorage to Ethereum Sepolia...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    gas_estimate = contract.constructor().estimate_gas({"from": account.address})
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    est_total_gas_cost = gas_estimate * int(gas_price * 1.25)
    if balance < est_total_gas_cost:
        print(f"ERROR: Insufficient balance for estimated deployment gas ({w3.from_wei(est_total_gas_cost, 'ether')} ETH needed)")
        sys.exit(1)

    txn = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(gas_estimate * 1.3),
        "gasPrice": int(gas_price * 1.25),
        "chainId": SEPOLIA_CHAIN_ID,
    })

    signed = account.sign_transaction(txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Tx hash: {tx_hash.hex()}")
    print("Waiting for confirmation on Sepolia...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        print(f"ERROR: Deployment transaction reverted (status={receipt.status})")
        sys.exit(1)

    addr = receipt.contractAddress

    print()
    print("=" * 66)
    print("CONTRACT DEPLOYED ON ETHEREUM SEPOLIA")
    print(f"Address:  {addr}")
    print(f"Tx:       {receipt.transactionHash.hex()}")
    print(f"Block:    {receipt.blockNumber}")
    print(f"Explorer: {SEPOLIA_EXPLORER}/address/{addr}")
    print()
    print("Add to .env:")
    print(f"  CONTRACT_ADDRESS={addr}")
    print("=" * 66)

    # Automatically persist to .env only after confirmation
    env_file = Path(".env")
    if env_file.exists():
        text = env_file.read_text()
        if "CONTRACT_ADDRESS=" in text:
            import re
            new_text = re.sub(r"CONTRACT_ADDRESS=.*", f"CONTRACT_ADDRESS={addr}", text)
            if "SEPOLIA_RPC_URL=" not in new_text:
                new_text = f"SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com\n" + new_text
            env_file.write_text(new_text)
            print("✓ Automatically updated CONTRACT_ADDRESS in .env")


if __name__ == "__main__":
    deploy()
