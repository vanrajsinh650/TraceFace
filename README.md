# TraceFace

**HH Goa 2026 — Task 3: Face Identification & Blockchain Verification**

```
Face Image
    ↓
InsightFace Detection + ArcFace Embedding
    ↓
Real Reverse Image Search (PimEyes → Google/Yandex/Bing)
    ↓
Social/Web Candidate Filtering
    ↓
Independent Face Verification (ALL candidate faces)
    ↓
Deterministic Evidence Package
    ↓
SHA-256 Hash
    ↓
Blockchain Anchor (Polygon Amoy)
    ↓
Hash Verification: VERIFIED / TAMPERED
```

---

## Quick Start

```bash
# 1. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env: set POLYGON_RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS

# 3. (Optional) Add PimEyes cookies
# Export from logged-in PimEyes session → traceface/search/pimeyes_cookies.json

# 4. Run
python main.py --image path/to/face.jpg

# 5. Run without blockchain (for testing)
python main.py --image path/to/face.jpg --no-blockchain
```

---

## Example Output

```
TraceFace — Face Identification & Blockchain Verification
Input: face.jpg (142KB)

[1/7] Face Detection + ArcFace Embedding
  ✓ Detected 1 face(s)
  ✓ Query face: bbox=(45, 23, 210, 198), confidence=0.987
  ✓ Embedding: 512-dim ArcFace vector

[2/7] Reverse Image / Web Search
  [Search] Trying PimEyes (primary)...
  ✓ Found 12 candidate URLs (provider: pimeyes)

[3/7] Candidate Filtering & Image Download
  Trying [1]: instagram.com — https://instagram.com/...
    → Downloaded 89KB

[4/7] Independent Face Verification (candidate 1)
  Candidate faces detected: 1
  Best similarity score: 0.7342 (threshold: 0.35)
  ✓ MATCH — score 0.7342 >= threshold 0.35

[5/7] Creating Evidence Package
  ✓ Evidence package created

[6/7] Computing SHA-256 Hash
  ✓ Evidence SHA-256: a3f9c1...

[7/7] Blockchain Anchor (Polygon Amoy)
  ✓ Anchored! Tx: 0xabc123...
  ✓ Block: 12345678
  ✓ Blockchain verification: VERIFIED

────────────────────────────────────────────────────────────
  TRACEFACE RESULT
────────────────────────────────────────────────────────────
  Status:            MATCH
  Source:            instagram.com
  URL:               https://instagram.com/...
  Face score:        0.7342 (threshold: 0.35)
  Faces checked:     1
  Search provider:   pimeyes
  Model:             buffalo_l
  Evidence SHA-256:  a3f9c1...
  Transaction:       0xabc123...
  Blockchain:        VERIFIED
────────────────────────────────────────────────────────────
```

---

## Architecture

| Stage | Technology | Source |
|-------|-----------|--------|
| Face detection + embedding | InsightFace buffalo_l (ArcFace) | eye_of_web |
| Primary search | PimEyes direct API | JARVIS |
| Fallback search | PicImageSearch (Google/Yandex/Bing) | JARVIS |
| Face verification | Cosine similarity on 512-dim vectors | eye_of_web |
| Evidence hashing | SHA-256 (hashlib) | canonical JSON |
| Blockchain | Polygon Amoy (web3.py) | blockchain-evidence |
| Smart contract | EvidenceStorage.sol (MIT) | blockchain-evidence |

---

## Deploy Smart Contract

See [contracts/README.md](contracts/README.md) for Hardhat/Foundry deploy instructions.

---

## Attribution

This project integrates code from:
- **eye_of_web** by Mehmet Yüksel Şekeroğlu — MIT License
- **JARVIS** by affaan-m — License unverified (attribution maintained)
- **blockchain-evidence** by Gooichand/EVID-DGC — Apache 2.0

See `reference/REFERENCE_MAP.md` for full attribution details.
