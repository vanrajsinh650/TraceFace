"""
TraceFace — Blockchain Client & Cryptographic Re-Verifier (Ethereum Sepolia)
=============================================================================
Ported and evolved from: blockchain-evidence/services/blockchain/blockchainService.js
Original source: https://github.com/Gooichand/blockchain-evidence (Apache 2.0)

Interacts with EvidenceStorage.sol on Ethereum Sepolia testnet.
Anchors the deterministic Merkle Evidence Root and metadata commitments.
Performs independent re-verification and tamper detection.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# EvidenceStorage ABI — from contracts/EvidenceStorage.abi.json
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
]

_SEPOLIA_CHAIN_ID = 11155111
_SEPOLIA_EXPLORER = "https://sepolia.etherscan.io"


class BlockchainAnchorResult:
    """Result of a blockchain anchor operation."""

    def __init__(
        self,
        tx_hash: str,
        block_number: int,
        evidence_id: int,
        gas_used: int,
        success: bool,
        merkle_root: str = "",
        error: Optional[str] = None,
    ) -> None:
        self.tx_hash = tx_hash
        self.block_number = block_number
        self.evidence_id = evidence_id
        self.gas_used = gas_used
        self.success = success
        self.merkle_root = merkle_root
        self.error = error

    def explorer_url(self) -> str:
        if self.tx_hash:
            return f"{_SEPOLIA_EXPLORER}/tx/{self.tx_hash}"
        return ""


class BlockchainVerifyResult:
    """Result of blockchain verification for a Merkle root or evidence hash."""

    def __init__(
        self,
        exists: bool,
        evidence_id: int,
        stored_hash: str,
        local_hash: str,
        verified: bool,
        metadata: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.exists = exists
        self.evidence_id = evidence_id
        self.stored_hash = stored_hash
        self.local_hash = local_hash
        self.verified = verified
        self.metadata = metadata
        self.error = error

    @property
    def status(self) -> str:
        if self.error:
            return f"ERROR: {self.error}"
        if not self.exists:
            return "NOT_FOUND"
        if self.verified:
            return "VERIFIED"
        return "TAMPERED"


class BlockchainClient:
    """
    Ethereum Sepolia client for EvidenceStorage contract.
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
    ) -> None:
        self._rpc_url = rpc_url or os.environ.get("SEPOLIA_RPC_URL", "")
        self._private_key = private_key or os.environ.get("PRIVATE_KEY", "")
        self._contract_address = contract_address or os.environ.get("CONTRACT_ADDRESS", "")
        self._w3 = None
        self._contract = None
        self._account = None

    @property
    def is_configured(self) -> bool:
        return bool(self._rpc_url and self._private_key and self._contract_address)

    def _check_config(self) -> Optional[str]:
        missing = []
        if not self._rpc_url:
            missing.append("SEPOLIA_RPC_URL")
        if not self._private_key:
            missing.append("PRIVATE_KEY")
        if not self._contract_address:
            missing.append("CONTRACT_ADDRESS")
        if missing:
            return f"Missing environment variables: {', '.join(missing)}"
        return None

    _FALLBACK_RPCS = [
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://rpc.sepolia.org",
        "https://1rpc.io/sepolia",
        "https://sepolia.gateway.tenderly.co",
    ]

    def _connect(self) -> Optional[str]:
        if self._w3 is not None:
            return None

        config_error = self._check_config()
        if config_error:
            return config_error

        try:
            from web3 import Web3
        except ImportError:
            return "web3 not installed. Run: pip install web3"

        endpoints = [self._rpc_url] + [e for e in self._FALLBACK_RPCS if e != self._rpc_url]
        last_error = ""

        for endpoint in endpoints:
            try:
                w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 12}))
                if not w3.is_connected():
                    last_error = f"Cannot connect to RPC: {endpoint}"
                    continue

                actual_chain_id = w3.eth.chain_id
                if actual_chain_id != _SEPOLIA_CHAIN_ID:
                    last_error = (
                        f"Chain ID mismatch at {endpoint}: "
                        f"expected {_SEPOLIA_CHAIN_ID} (Sepolia), got {actual_chain_id}"
                    )
                    continue

                pk = self._private_key
                if not pk.startswith("0x"):
                    pk = "0x" + pk
                account = w3.eth.account.from_key(pk)
                checksum_addr = Web3.to_checksum_address(self._contract_address)
                contract = w3.eth.contract(address=checksum_addr, abi=_ABI)

                self._w3 = w3
                self._account = account
                self._contract = contract
                return None
            except Exception as e:
                last_error = str(e)
                continue

        return f"All Sepolia RPC connections failed: {last_error}"

    def get_wallet_address(self) -> Optional[str]:
        err = self._connect()
        if err or self._account is None:
            return None
        return self._account.address

    def anchor(self, merkle_root: str, metadata: dict[str, Any]) -> BlockchainAnchorResult:
        """
        Anchor the Merkle root and metadata commitment on Ethereum Sepolia.
        """
        err = self._connect()
        if err:
            return BlockchainAnchorResult(
                tx_hash="", block_number=0, evidence_id=0, gas_used=0,
                success=False, merkle_root=merkle_root, error=err,
            )

        root_str = merkle_root if merkle_root.startswith("0x") else "0x" + merkle_root
        metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))

        try:
            balance = self._w3.eth.get_balance(self._account.address)
            if balance == 0:
                return BlockchainAnchorResult(
                    tx_hash="", block_number=0, evidence_id=0, gas_used=0,
                    success=False, merkle_root=merkle_root,
                    error=f"Wallet {self._account.address} has 0 Sepolia ETH. Fund from https://sepoliafaucet.com",
                )

            nonce = self._w3.eth.get_transaction_count(self._account.address)
            gas_estimate = self._contract.functions.storeEvidence(
                root_str, metadata_json
            ).estimate_gas({"from": self._account.address})

            gas_price = self._w3.eth.gas_price

            txn = self._contract.functions.storeEvidence(
                root_str, metadata_json
            ).build_transaction({
                "from": self._account.address,
                "nonce": nonce,
                "gas": int(gas_estimate * 1.3),
                "gasPrice": int(gas_price * 1.25),
                "chainId": _SEPOLIA_CHAIN_ID,
            })

            signed = self._account.sign_transaction(txn)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status != 1:
                return BlockchainAnchorResult(
                    tx_hash=tx_hash.hex(),
                    block_number=receipt.blockNumber,
                    evidence_id=0,
                    gas_used=receipt.gasUsed,
                    success=False,
                    merkle_root=merkle_root,
                    error="Transaction reverted on-chain",
                )

            evidence_id = 0
            try:
                logs = self._contract.events.EvidenceStored().process_receipt(receipt)
                if logs:
                    evidence_id = int(logs[0]["args"]["evidenceId"])
            except Exception:
                try:
                    res = self._contract.functions.verifyHash(root_str).call()
                    evidence_id = int(res[1])
                except Exception:
                    pass

            return BlockchainAnchorResult(
                tx_hash=tx_hash.hex(),
                block_number=receipt.blockNumber,
                evidence_id=evidence_id,
                gas_used=receipt.gasUsed,
                success=True,
                merkle_root=merkle_root,
            )
        except Exception as e:
            return BlockchainAnchorResult(
                tx_hash="", block_number=0, evidence_id=0, gas_used=0,
                success=False, merkle_root=merkle_root, error=str(e),
            )

    def verify(self, merkle_root: str) -> BlockchainVerifyResult:
        """
        Query smart contract to verify if a Merkle root exists on Ethereum Sepolia.
        """
        err = self._connect()
        if err:
            return BlockchainVerifyResult(
                exists=False, evidence_id=0, stored_hash="",
                local_hash=merkle_root, verified=False, error=err,
            )

        root_str = merkle_root if merkle_root.startswith("0x") else "0x" + merkle_root

        try:
            verify_res = self._contract.functions.verifyHash(root_str).call()
            exists = bool(verify_res[0])
            evidence_id = int(verify_res[1])

            if not exists:
                # Also try without 0x prefix if stored as raw hex
                raw_res = self._contract.functions.verifyHash(merkle_root.lstrip("0x")).call()
                if raw_res[0]:
                    exists = True
                    evidence_id = int(raw_res[1])

            if not exists:
                return BlockchainVerifyResult(
                    exists=False, evidence_id=0, stored_hash="",
                    local_hash=merkle_root, verified=False,
                )

            ev = self._contract.functions.getEvidence(evidence_id).call()
            stored_hash = ev[0]
            meta_str = ev[1]
            metadata = None
            try:
                metadata = json.loads(meta_str)
            except Exception:
                pass

            verified = (stored_hash.lower() == root_str.lower() or
                        stored_hash.lower() == merkle_root.lower())

            return BlockchainVerifyResult(
                exists=True,
                evidence_id=evidence_id,
                stored_hash=stored_hash,
                local_hash=merkle_root,
                verified=verified,
                metadata=metadata,
            )
        except Exception as e:
            return BlockchainVerifyResult(
                exists=False, evidence_id=0, stored_hash="",
                local_hash=merkle_root, verified=False, error=str(e),
            )

    def get_explorer_url(self, tx_hash: str) -> str:
        return f"{_SEPOLIA_EXPLORER}/tx/{tx_hash}"
