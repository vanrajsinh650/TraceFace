#!/usr/bin/env python3
"""
TraceFace — Deploy EvidenceStorage to Polygon Amoy (using compiled bytecode)
Usage: python deploy_contract.py
Requires: POLYGON_RPC_URL + PRIVATE_KEY in .env
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


def deploy() -> None:
    rpc_url = os.environ.get("POLYGON_RPC_URL", "")
    private_key = os.environ.get("PRIVATE_KEY", "")

    if not private_key:
        print("ERROR: PRIVATE_KEY not set in .env")
        print("Create a new wallet: python -c \"from eth_account import Account; a = Account.create(); print(a.address, a.key.hex())\"")
        sys.exit(1)

    # Load compiled contract
    abi_path = Path("contracts/EvidenceStorage.abi.json")
    bin_path = Path("contracts/EvidenceStorage.bin")

    if not abi_path.exists() or not bin_path.exists():
        print("ERROR: Compile the contract first:")
        print("  python -c \"from solcx import install_solc, compile_source; ...\"")
        print("  Or run: python compile_contract.py")
        sys.exit(1)

    abi = json.loads(abi_path.read_text())
    bytecode = bin_path.read_text().strip()
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
    except ImportError:
        print("ERROR: pip install web3")
        sys.exit(1)

    # Connect with fallbacks
    endpoints = [
        rpc_url or "",
        "https://polygon-amoy-bor-rpc.publicnode.com",
        "https://rpc-amoy.polygon.technology",
    ]
    endpoints = [e for e in endpoints if e]

    w3 = None
    for ep in endpoints:
        try:
            _w3 = Web3(Web3.HTTPProvider(ep, request_kwargs={"timeout": 10}))
            _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            if _w3.is_connected():
                w3 = _w3
                print(f"Connected: {ep}")
                break
        except Exception as e:
            print(f"  {ep}: {e}")

    if w3 is None:
        print("ERROR: Cannot connect to Polygon Amoy")
        sys.exit(1)

    pk = private_key if private_key.startswith("0x") else "0x" + private_key
    account = w3.eth.account.from_key(pk)
    balance = w3.eth.get_balance(account.address)
    balance_matic = w3.from_wei(balance, "ether")

    print(f"Deployer: {account.address}")
    print(f"Balance:  {balance_matic:.6f} MATIC")

    if balance == 0:
        print()
        print("WALLET HAS NO MATIC. Get testnet MATIC from:")
        print(f"  https://faucet.polygon.technology")
        print(f"  Address: {account.address}")
        sys.exit(1)

    print("Deploying EvidenceStorage...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    gas_estimate = contract.constructor().estimate_gas({"from": account.address})
    nonce = w3.eth.get_transaction_count(account.address)

    txn = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(gas_estimate * 1.2),
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    })

    signed = account.sign_transaction(txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Tx hash: {tx_hash.hex()}")
    print("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    addr = receipt.contractAddress

    print()
    print("=" * 60)
    print("CONTRACT DEPLOYED")
    print(f"Address:  {addr}")
    print(f"Tx:       {receipt.transactionHash.hex()}")
    print(f"Block:    {receipt.blockNumber}")
    print(f"Explorer: https://amoy.polygonscan.com/address/{addr}")
    print()
    print("Add to .env:")
    print(f"  CONTRACT_ADDRESS={addr}")
    print("=" * 60)

    # Automatically persist to .env
    env_file = Path(".env")
    if env_file.exists():
        text = env_file.read_text()
        if "CONTRACT_ADDRESS=" in text:
            import re
            new_text = re.sub(r"CONTRACT_ADDRESS=.*", f"CONTRACT_ADDRESS={addr}", text)
            env_file.write_text(new_text)
            print(f"✓ Automatically updated CONTRACT_ADDRESS in .env")


if __name__ == "__main__":
    deploy()
