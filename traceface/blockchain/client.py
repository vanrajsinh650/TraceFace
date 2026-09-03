"""
TraceFace — Blockchain Client (Polygon Amoy)
=============================================
Python port of: blockchain-evidence/services/blockchain/blockchainService.js
Original source: https://github.com/Gooichand/blockchain-evidence (Apache 2.0)

Uses web3.py (v6+) to interact with the EvidenceStorage smart contract on Polygon Amoy.

Required environment variables (.env):
  POLYGON_RPC_URL    — Amoy RPC endpoint (e.g., https://rpc-amoy.polygon.technology)
  PRIVATE_KEY        — Ethereum wallet private key (WITHOUT 0x prefix)
  CONTRACT_ADDRESS   — Deployed EvidenceStorage contract address

SECURITY:
  - NEVER store the private key in source code.
  - NEVER commit .env to git.
  - Only store SHA-256 hashes on-chain — not raw embeddings or biometric data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# EvidenceStorage ABI — from blockchain-evidence/contracts/EvidenceStorage.abi.json
# Includes only the functions we need: storeEvidence, getEvidence, verifyHash
_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "_fileHash", "type": "string"},
            {"internalType": "string", "name": "_metadata", "type": "string"},
        ],
        "name": "storeEvidence",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_evidenceId", "type": "uint256"}],
        "name": "getEvidence",
        "outputs": [
            {"internalType": "string", "name": "fileHash", "type": "string"},
            {"internalType": "string", "name": "metadata", "type": "string"},
            {"internalType": "address", "name": "uploadedBy", "type": "address"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bool", "name": "isSealed", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "_fileHash", "type": "string"}],
        "name": "verifyHash",
        "outputs": [
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "uint256", "name": "evidenceId", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_user", "type": "address"},
            {"internalType": "string", "name": "_role", "type": "string"},
        ],
        "name": "authorizeUser",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Polygon Amoy chain ID
_AMOY_CHAIN_ID = 80002
_AMOY_EXPLORER = "https://amoy.polygonscan.com"


class BlockchainAnchorResult:
    """Result of a blockchain anchor (store) operation."""

    def __init__(
        self,
        tx_hash: str,
        block_number: int,
        evidence_id: int,
        gas_used: int,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        self.tx_hash = tx_hash
        self.block_number = block_number
        self.evidence_id = evidence_id
        self.gas_used = gas_used
        self.success = success
        self.error = error

    def explorer_url(self) -> str:
        return f"{_AMOY_EXPLORER}/tx/{self.tx_hash}"


class BlockchainVerifyResult:
    """Result of a blockchain verification (hash lookup) operation."""

    def __init__(
        self,
        exists: bool,
        evidence_id: int,
        stored_hash: str,
        local_hash: str,
        verified: bool,
        error: Optional[str] = None,
    ) -> None:
        self.exists = exists
        self.evidence_id = evidence_id
        self.stored_hash = stored_hash
        self.local_hash = local_hash
        self.verified = verified  # True only if exists AND stored_hash == local_hash
        self.error = error

    @property
    def status(self) -> str:
        if self.error:
            return f"ERROR: {self.error}"
        if not self.exists:
            return "NOT FOUND — hash not anchored on this contract"
        if self.verified:
            return "VERIFIED"
        return "TAMPERED — stored hash does not match local hash"


class BlockchainClient:
    """
    Polygon Amoy blockchain client for EvidenceStorage contract.

    Python port of blockchain-evidence/services/blockchain/blockchainService.js
    Original source: https://github.com/Gooichand/blockchain-evidence (Apache 2.0)

    Usage:
        client = BlockchainClient()
        anchor = await client.anchor(evidence_hash, metadata_json)
        verify = await client.verify(evidence_hash, local_hash)
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
    ) -> None:
        self._rpc_url = rpc_url or os.environ.get("POLYGON_RPC_URL", "")
        self._private_key = private_key or os.environ.get("PRIVATE_KEY", "")
        self._contract_address = contract_address or os.environ.get("CONTRACT_ADDRESS", "")
        self._w3 = None
        self._contract = None
        self._account = None

    def _check_config(self) -> Optional[str]:
        """Return error message if config is incomplete, else None."""
        missing = []
        if not self._rpc_url:
            missing.append("POLYGON_RPC_URL")
        if not self._private_key:
            missing.append("PRIVATE_KEY")
        if not self._contract_address:
            missing.append("CONTRACT_ADDRESS")
        if missing:
            return f"Missing environment variables: {', '.join(missing)}"
        return None

    # Fallback RPC endpoints tried in order if primary fails
    _FALLBACK_RPCS = [
        "https://polygon-amoy-bor-rpc.publicnode.com",
        "https://rpc.ankr.com/polygon_amoy",
    ]

    def _connect(self) -> Optional[str]:
        """Initialize web3.py connection and contract. Returns error string or None."""
        if self._w3 is not None:
            return None

        config_error = self._check_config()
        if config_error:
            return config_error

        try:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware
        except ImportError:
            return "web3 not installed. Run: pip install web3"

        # Try primary RPC URL, then fallbacks
        endpoints_to_try = [self._rpc_url] + self._FALLBACK_RPCS
        last_error = ""

        for endpoint in endpoints_to_try:
            try:
                w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 10}))
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

                if not w3.is_connected():
                    last_error = f"Cannot connect to RPC: {endpoint}"
                    continue

                # Build account from private key
                pk = self._private_key
                if not pk.startswith("0x"):
                    pk = "0x" + pk
                account = w3.eth.account.from_key(pk)

                # Build contract
                checksum_addr = Web3.to_checksum_address(self._contract_address)
                contract = w3.eth.contract(address=checksum_addr, abi=_ABI)

                # All good — commit
                self._w3 = w3
                self._account = account
                self._contract = contract
                print(f"[Blockchain] Connected to Polygon Amoy via {endpoint}")
                return None

            except Exception as e:
                last_error = f"RPC {endpoint} failed: {e}"
                continue

        self._w3 = None
        return f"All RPC endpoints failed. Last error: {last_error}"

    def get_wallet_address(self) -> Optional[str]:
        """Return the wallet address (public, safe to display)."""
        err = self._connect()
        if err or self._account is None:
            return None
        return self._account.address

    def anchor(self, evidence_hash: str, metadata: dict) -> BlockchainAnchorResult:
        """
        Anchor an evidence hash on the blockchain.

        Stores: storeEvidence(evidence_hash, json.dumps(metadata))

        Args:
            evidence_hash: SHA-256 hex digest of the canonical evidence JSON
            metadata: Dict with non-sensitive metadata (score, url, timestamp, etc.)

        Returns:
            BlockchainAnchorResult with tx_hash, block_number, evidence_id
        """
        err = self._connect()
        if err:
            return BlockchainAnchorResult(
                tx_hash="", block_number=0, evidence_id=0, gas_used=0,
                success=False, error=err,
            )

        # Prefix hash with "0x" if not present, for clarity in metadata
        hash_str = evidence_hash if evidence_hash.startswith("0x") else evidence_hash
        metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))

        try:
            from web3 import Web3

            # Build transaction
            nonce = self._w3.eth.get_transaction_count(self._account.address)
            chain_id = self._w3.eth.chain_id

            # Estimate gas
            gas_estimate = self._contract.functions.storeEvidence(
                hash_str, metadata_json
            ).estimate_gas({"from": self._account.address})

            txn = self._contract.functions.storeEvidence(
                hash_str, metadata_json
            ).build_transaction({
                "from": self._account.address,
                "nonce": nonce,
                "gas": int(gas_estimate * 1.2),  # 20% buffer
                "gasPrice": self._w3.eth.gas_price,
                "chainId": chain_id,
            })

            # Sign and send
            signed = self._account.sign_transaction(txn)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

            print(f"[Blockchain] Transaction sent: {tx_hash.hex()}")
            print("[Blockchain] Waiting for confirmation (2 blocks)...")

            # Wait for receipt (2 confirmations)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status != 1:
                return BlockchainAnchorResult(
                    tx_hash=tx_hash.hex(),
                    block_number=receipt.blockNumber,
                    evidence_id=0,
                    gas_used=receipt.gasUsed,
                    success=False,
                    error="Transaction reverted (status=0)",
                )

            # Parse EvidenceStored event to get evidenceId
            evidence_id = 0
            try:
                logs = self._contract.events.EvidenceStored().process_receipt(receipt)
                if logs:
                    evidence_id = int(logs[0]["args"]["evidenceId"])
            except Exception:
                # If event parsing fails, look up via verifyHash
                try:
                    result = self._contract.functions.verifyHash(hash_str).call()
                    evidence_id = int(result[1])
                except Exception:
                    pass

            return BlockchainAnchorResult(
                tx_hash=tx_hash.hex(),
                block_number=receipt.blockNumber,
                evidence_id=evidence_id,
                gas_used=receipt.gasUsed,
                success=True,
            )

        except Exception as e:
            return BlockchainAnchorResult(
                tx_hash="", block_number=0, evidence_id=0, gas_used=0,
                success=False, error=str(e),
            )

    def verify(self, local_hash: str) -> BlockchainVerifyResult:
        """
        Verify a local evidence hash against the blockchain.

        Steps:
        1. Call verifyHash(local_hash) on the contract
        2. If found, fetch stored evidence via getEvidence(evidenceId)
        3. Compare stored fileHash == local_hash
        4. Return VERIFIED or TAMPERED

        Args:
            local_hash: SHA-256 hex digest to look up

        Returns:
            BlockchainVerifyResult
        """
        err = self._connect()
        if err:
            return BlockchainVerifyResult(
                exists=False, evidence_id=0, stored_hash="",
                local_hash=local_hash, verified=False, error=err,
            )

        try:
            # Step 1: Check if hash exists
            verify_result = self._contract.functions.verifyHash(local_hash).call()
            exists = bool(verify_result[0])
            evidence_id = int(verify_result[1])

            if not exists:
                return BlockchainVerifyResult(
                    exists=False, evidence_id=0, stored_hash="",
                    local_hash=local_hash, verified=False,
                )

            # Step 2: Get stored evidence
            evidence = self._contract.functions.getEvidence(evidence_id).call()
            stored_hash = evidence[0]  # fileHash

            # Step 3: Compare
            verified = stored_hash == local_hash

            return BlockchainVerifyResult(
                exists=True,
                evidence_id=evidence_id,
                stored_hash=stored_hash,
                local_hash=local_hash,
                verified=verified,
            )

        except Exception as e:
            return BlockchainVerifyResult(
                exists=False, evidence_id=0, stored_hash="",
                local_hash=local_hash, verified=False, error=str(e),
            )

    def get_explorer_url(self, tx_hash: str) -> str:
        """Return Polygon Amoy explorer URL for a transaction hash."""
        return f"{_AMOY_EXPLORER}/tx/{tx_hash}"
