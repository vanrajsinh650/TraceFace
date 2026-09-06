# TraceFace

> **TraceFace is a provenance-first face discovery pipeline that turns web search results into a cryptographically verifiable evidence graph, anchored on-chain through a deterministic Merkle commitment.**

**HH Goa 2026 — Task 3: Face Discovery, Evidence Fusion & Cryptographic Ledger**

> **Core Guarantee**: TraceFace proves that the evidence package presented for verification matches the cryptographic commitment anchored on Ethereum Sepolia, and it detects subsequent modification of that evidence.

Most face search pipelines simply find a matching candidate and push an arbitrary hash to a blockchain. TraceFace preserves the complete chain of investigative provenance: concurrent multi-engine discovery, provider corroboration, candidate normalization, independent multi-face ArcFace verification, explainable multi-signal confidence scoring, and a deterministic Merkle Evidence Tree anchored to Ethereum Sepolia.

```text
               1. Multi-engine parallel discovery
                               ↓
               2. Evidence graph + explainable confidence
                               ↓
               3. Merkle-root blockchain integrity + live tamper test
```

---

## Two Ways to Evaluate TraceFace

### 1. Run the Real Pipeline (Live Mode)

```bash
python main.py --image your_image.jpg --max-candidates 3
```

This performs **genuine live face discovery**: real InsightFace/ArcFace embedding, real multi-engine reverse-image search (Yandex, Google, Bing), real candidate verification, real evidence fusion, and real Ethereum Sepolia blockchain anchoring.

> **Note**: Live search results may differ between runs because external search providers can return different results, rate-limit requests, timeout, change indexes, or become temporarily unavailable. An arbitrary judge image is **not** guaranteed to produce the same candidate as our published proof.

### 2. Verify the Published Blockchain Proof (Proof Mode)

```bash
python main.py proof-verify fixtures/demo_evidence.json
```

This is **deterministic**. It independently verifies the exact cryptographic commitment that TraceFace has published on Ethereum Sepolia:

- Reconstructs canonical evidence representation
- Recomputes evidence SHA-256
- Rebuilds Merkle root from candidate leaves
- Validates Merkle inclusion proof
- Queries the Ethereum Sepolia smart contract (read-only)
- Confirms the committed root exists on-chain

**No private wallet, funded account, or API keys are required.** Only public blockchain read access (provided by free public RPCs).

---

## Hackathon Requirement Mapping

| Requirement | TraceFace Implementation |
|---|---|
| Face identification | InsightFace buffalo_l / ArcFace 512D embedding |
| Genuine web/social search | Real multi-provider reverse-image search (Yandex, Google, Bing, PimEyes) |
| Matching post | Discovered candidate preserved in evidence package with SHA-256 + dHash fingerprint |
| Blockchain | Ethereum Sepolia (Chain ID: 11155111) — real on-chain anchoring |
| Tamper verification | Deterministic Merkle tree + on-chain root comparison + inclusion proofs |
| GitHub | Full source repository with reproducible setup |
| Website | Not required by task specification |

> **Live Mode** = discovery (real face detection → real search → real matching → real anchoring)
>
> **Proof Mode** = independent verification (recompute → compare → blockchain lookup)

---

## Technical Pipeline

```mermaid
flowchart TD
    A[Input Query Image] --> B[InsightFace buffalo_l / ArcFace 512D]
    A --> C[Dual Fingerprinting: Exact SHA-256 + Perceptual dHash]
    B --> D[Parallel Search Fan-Out]
    
    subgraph Multi-Engine Fan-out
        D --> E1[Yandex Engine]
        D --> E2[Google Lens]
        D --> E3[Bing Visual Search]
        D --> E4[PimEyes Direct API]
    end

    E1 --> F[Candidate Normalization & Deduplication]
    E2 --> F
    E3 --> F
    E4 --> F

    F --> G[Coarse-to-Fine Pre-filtering]
    G --> H[Independent ArcFace Face Verification]
    H --> I[Multi-Signal Evidence Confidence Scoring]
    I --> J[Deterministic Evidence Graph]
    
    subgraph Cryptographic Ledger
        J --> K[Candidate Evidence Leaves]
        K --> L[RFC 6962-Inspired Merkle Tree]
        L --> M[Merkle Evidence Root]
        M --> N[Candidate Inclusion Proof]
    end

    M --> O[Ethereum Sepolia Blockchain Anchor]
    O --> P[Independent Re-Verification: VERIFIED / TAMPERED]
```

---

## Discovered Post & Blockchain Commitment Flow

The hackathon requires recording the discovered post or its cryptographic fingerprint to the blockchain. TraceFace fulfills this through a hierarchical cryptographic commitment:

```text
Matched post
     ↓
SHA-256 / perceptual fingerprint
     ↓
evidence leaf
     ↓
Merkle root
     ↓
Ethereum Sepolia
     ↓
on-chain verification
```

> **"The matched post's cryptographic fingerprint is explicitly included as a committed evidence leaf; Ethereum Sepolia anchors the Merkle root representing the complete evidence set."**

The smart contract record locks:
- **Merkle Root**: Cryptographic commitment over all candidates and search provenance.
- **Matched Post URL**: Canonical URL of the discovered web/social post.
- **Matched Post Fingerprint**: Exact SHA-256 and perceptual dHash of the matched image.
- **Investigation Metadata**: Scores, timestamps, and model identifiers.

---

## Architecture Highlights

- **Parallel Multi-Engine Discovery**: Designed for concurrent provider execution across Yandex, Google, Bing, and PimEyes (`asyncio.gather`) with independent per-engine timeouts and failure isolation.
- **Result Normalization & Deduplication**: Canonical URL parsing, query tracking parameter removal (`utm_*`, `fbclid`, `ref`), and multi-provider agreement tracking (`"providers": ["google", "yandex"]`).
- **Coarse-to-Fine Processing**: Designed for efficient candidate pre-filtering (payload validation, minimum dimensions, extreme aspect ratio rejection) before running deep 512D ArcFace embeddings.
- **Multi-Signal Evidence Confidence**: Transparent 0–100 score combining ArcFace cosine similarity (45 pts), runner-up margin (20 pts), provider agreement (15 pts), platform authenticity (10 pts), and image fidelity (10 pts).
- **Deterministic Merkle Tree**: RFC 6962-inspired domain separation (`0x00` leaf, `0x01` internal node), deterministic sorting, and duplicate-last odd node handling.
- **Cryptographic Inclusion Proofs**: Proves mathematically that a specific candidate was part of the evidence set committed on-chain.
- **Zero-Dependency Perceptual Fingerprint**: Built-in 64-bit difference hash (`dhash-64`) to confirm visual equivalence alongside exact SHA-256 byte integrity.

---

## Supported Environments & Compatibility Matrix

| Operating System | Supported | Architecture | Python Versions | Notes |
|---|---|---|---|---|
| **Linux (Ubuntu, Debian, Arch, Fedora)** | ✅ Tested & Supported | x86_64, aarch64 | 3.10 – 3.14 | Tested with Python 3.14 on Linux x86_64 |
| **Windows 10 / 11 (Native PowerShell)** | ✅ Tested & Supported | x86_64 | 3.10 – 3.12 | Uses UTF-8 path handling, `.venv\Scripts\Activate.ps1` |
| **Windows WSL2** | ✅ Tested & Supported | x86_64 | 3.10 – 3.14 | Identical to Linux environment |
| **macOS (Apple Silicon & Intel)** | ✅ Supported | arm64, x86_64 | 3.10 – 3.12 | Standard Python wheels available via pip |
| **iOS / Mobile** | ❌ Not Supported | ARM | N/A | Desktop/server runtime only (requires native ONNX/InsightFace binaries) |

> **Recommended Python**: **Python 3.12** is recommended across all platforms for the most mature binary wheel ecosystem.

---

## Installation & Setup

### Option A: Automated One-Command Bootstrap (Recommended)

#### Linux / macOS / WSL:
```bash
git clone https://github.com/vanrajsinh650/TraceFace.git
cd TraceFace
chmod +x scripts/setup.sh
./scripts/setup.sh
```

#### Windows (PowerShell):
```powershell
git clone https://github.com/vanrajsinh650/TraceFace.git
cd TraceFace
.\scripts\setup.ps1
```

---

### Option B: Manual Setup

#### 1. Clone the repository
```bash
git clone https://github.com/vanrajsinh650/TraceFace.git
cd TraceFace
```

#### 2. Create and activate a virtual environment
**Linux / macOS / WSL**:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
**Windows PowerShell**:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

#### 4. Run Pre-flight Diagnostics (Doctor)
Run the self-diagnosing `doctor` command to verify your Python environment, packages, ONNX runtime, and network connectivity:
```bash
python main.py doctor
```
Add `--verbose` for detailed tracebacks if any component reports an error:
```bash
python main.py doctor --verbose
```

#### 5. Environment Variables (.env) — Live Mode Only
> **Important**: **Proof Mode (`proof-verify`) does NOT require `.env` or any wallet credentials.**
> Only configure `.env` if you intend to run live on-chain anchoring transactions.

```bash
cp .env.example .env
# Edit .env with your Sepolia RPC URL, private key, etc.
```

---

## Troubleshooting Guide

| Issue / Symptom | Root Cause | Solution |
|---|---|---|
| `InsightFace unavailable` | Missing model cache or failed import | Run `python main.py doctor --verbose`. The `buffalo_l` model (~280 MB) auto-downloads to `~/.insightface/models/` on first use. If network blocks it, download manually. |
| `ONNX Runtime CPU provider missing` | Broken ONNX install | Run `pip install --force-reinstall onnxruntime`. Ensure 64-bit Python is used. |
| `UnicodeDecodeError` on Windows | Default system ANSI code page | TraceFace explicitly uses UTF-8 encoding across all file operations. Ensure your terminal supports UTF-8 (`chcp 65001`). |
| External search provider error (`bing`, `google`) | Upstream rate-limit or captcha | TraceFace features per-provider failure isolation (`asyncio.gather(return_exceptions=True)`). The pipeline automatically continues with available engines (e.g. Yandex). |
| `Sepolia RPC unavailable` | Public endpoint rate limit | TraceFace rotates across multiple public fallback RPCs (`publicnode`, `rpc.sepolia.org`, `1rpc.io`). Re-run or set a custom `SEPOLIA_RPC_URL` in `.env`. |
| `Missing environment variables: PRIVATE_KEY` | Using write mode without credentials | Run `python main.py proof-verify fixtures/demo_evidence.json` for read-only proof verification. For live pipeline without gas, pass `--no-blockchain`. |


## CLI Commands

### 1. Live Discovery & Evidence Anchoring (LIVE MODE)
```bash
# Run pipeline with included sample face (offline ledger, no gas needed):
python main.py --image fixtures/sample_face.jpg --max-candidates 3 --no-blockchain

# Or run with your own photo and live blockchain anchoring:
python main.py --image path/to/face.jpg --max-candidates 3
```

### 2. Public Blockchain Proof Verification (PROOF MODE)
Deterministically verifies the published TraceFace evidence commitment against Ethereum Sepolia. No private key or funded wallet required:
```bash
python main.py proof-verify fixtures/demo_evidence.json
```

### 3. Cryptographic Re-Verification
Independently recomputes all SHA-256 hashes, canonical JSON, and Merkle tree roots from local evidence, verifying against on-chain records:
```bash
python main.py verify results/evidence_<hash>.json
```

### 4. Live Tamper Demonstration
Demonstrates that TraceFace detects any controlled tampering (e.g. modified similarity score, altered URL, or tampered metadata):
```bash
python main.py tamper-demo fixtures/demo_evidence.json
```

### 5. Merkle Inclusion Proof Inspection
Displays and mathematically verifies the audit path locking the matched candidate into the Merkle Root:
```bash
python main.py proof fixtures/demo_evidence.json
```

> **Note on Evidence Files**: Generated evidence JSON files in `results/` are intentionally gitignored to prevent committing investigation artifacts. The published proof fixture at `fixtures/demo_evidence.json` is version-controlled and can be used with `proof-verify`, `verify`, `tamper-demo`, and `proof`.

---

## Quick Start for Judges & Reviewers

```bash
# STEP A — Verify published blockchain proof (deterministic, 0 config required)
python main.py proof-verify fixtures/demo_evidence.json

# STEP B — See tamper detection in action
python main.py tamper-demo fixtures/demo_evidence.json

# STEP C — Inspect Merkle inclusion proof
python main.py proof fixtures/demo_evidence.json

# STEP D — Run live face discovery on the included sample face
python main.py --image fixtures/sample_face.jpg --max-candidates 3 --no-blockchain
```

---

## Public Blockchain Records

- **Network**: Ethereum Sepolia Testnet (Chain ID: `11155111`)
- **Contract**: `contracts/EvidenceStorage.sol` (single canonical contract; deployed to Sepolia)
- **Explorer**: [sepolia.etherscan.io](https://sepolia.etherscan.io)
- **Deployed Address**: [`0x57306beBD4A3aFdec95b32fF39f9046aA338e8A2`](https://sepolia.etherscan.io/address/0x57306beBD4A3aFdec95b32fF39f9046aA338e8A2)
- **Deployment Tx**: [`0x2ebc9f69bb71a4d417d244faa51f11643a3199bb1f89355a0ed2b6321e846611`](https://sepolia.etherscan.io/tx/0x2ebc9f69bb71a4d417d244faa51f11643a3199bb1f89355a0ed2b6321e846611) (Block: 11639090)
- **Published Proof Anchor Tx**: [`0x93b1dfce859dbb19e21a629196f66e40cfa0803b45da63a700cf9d6ad349d899`](https://sepolia.etherscan.io/tx/0x93b1dfce859dbb19e21a629196f66e40cfa0803b45da63a700cf9d6ad349d899) (Block: 11639954)
- **Published Merkle Root**: `46cb0e2ad6f227cb4766a3af3b817720095ec18e876824f1be2950c9504c7aec`
- **Functions**:
  - `storeEvidence(string _fileHash, string _metadata)`: Commits the Merkle Root and JSON metadata.
  - `verifyHash(string _fileHash)`: Queries if a root exists on-chain and returns evidence ID.
  - `getEvidence(uint256 _evidenceId)`: Retrieves the anchored record.

To deploy your own contract instance:
```bash
python deploy_contract.py
```

---

## Unit Testing

Run the deterministic test suite:
```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py" -v
```

Test coverage includes:
- Merkle tree determinism, odd-leaf counts, and single-leaf handling.
- Cryptographic inclusion proof verification and forged proof rejection.
- Dual fingerprinting (exact SHA-256 and perceptual dHash Hamming distance).
- Multi-signal evidence scoring calculations and breakdown reports.
- URL canonicalization and multi-engine deduplication.
- Evidence graph building and deterministic serialization.
- Re-verification and controlled tamper detection.
- Public proof fixture cryptographic consistency and security scanning.

---

## Privacy, Security & Limitations

1. **Not Real-World Identity Certification**: Face embedding similarity measures mathematical feature distance between two images under specific lighting, pose, and resolution. It is not legal proof of personhood or real-world identity.
2. **Search Engine False Positives/Negatives**: Public search engines (Google, Yandex, Bing) rely on visual similarity indexes and web crawls which may include lookalikes, stock images, or irrelevant results.
3. **Integrity vs. Truth**: Anchoring a Merkle root to Ethereum Sepolia proves that the investigation evidence package presented matches the cryptographic commitment anchored on-chain and has not been altered since anchoring. It demonstrates what the pipeline retrieved and committed at that time, but does **not** certify that the underlying online posts or claims are factually truthful, nor does the blockchain independently witness the live contents of external URLs.
4. **Live Search Variability**: A live run uses current external search providers, so candidate results, provider availability, timing, and investigation IDs may differ between runs. The public proof fixture is provided separately so judges can deterministically verify the cryptographic commitment that TraceFace has published on Ethereum Sepolia.
5. **Credential Safety**: Private keys and API credentials must never be committed to source control. Use environment variables.
6. **Intended Use**: TraceFace is an academic/hackathon proof-of-concept for transparent digital evidence ledgers.

---

## Attribution & Licenses

TraceFace builds upon open-source foundations:
- **InsightFace**: Deep face analysis and ArcFace embeddings.
- **PicImageSearch**: Multi-engine reverse search interfaces.
- **eye_of_web** by Mehmet Yüksel Şekeroğlu — MIT License (InsightFace initialization & cosine similarity principles).
- **JARVIS** by affaan-m — Attribution maintained (PimEyes flow & reverse search orchestration).
- **blockchain-evidence** by Gooichand / EVID-DGC — Apache 2.0 (EvidenceStorage smart contract design).
- **RFC 6962**: Inspiration for domain-separated binary Merkle trees (`0x00` leaf, `0x01` internal node prefixes).
