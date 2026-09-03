# EvidenceStorage Contract

Source: blockchain-evidence/contracts/EvidenceStorage.sol
Original repository: https://github.com/Gooichand/blockchain-evidence
License: MIT (SPDX-License-Identifier: MIT, from blockchain-evidence repo)

Attribution: Copyright 2025 EVID-DGC Blockchain Evidence Management System

---

## Deploy to Polygon Amoy (Testnet)

### Prerequisites
- Node.js + npm
- Hardhat or Foundry
- Testnet MATIC (from https://faucet.polygon.technology)

### Using Hardhat

```bash
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox
npx hardhat compile
npx hardhat run scripts/deploy.js --network amoy
```

hardhat.config.js:
```js
module.exports = {
  solidity: "0.8.19",
  networks: {
    amoy: {
      url: process.env.POLYGON_RPC_URL,
      accounts: [process.env.PRIVATE_KEY],
      chainId: 80002,
    },
  },
};
```

### Using Foundry (Forge)

```bash
forge create src/EvidenceStorage.sol:EvidenceStorage \
  --rpc-url $POLYGON_RPC_URL \
  --private-key $PRIVATE_KEY
```

### After deployment

Set the contract address in `.env`:
```
CONTRACT_ADDRESS=0x...deployed_address...
```

---

## Authorization

The deployer wallet is automatically authorized as admin.
Additional wallets can be authorized via:

```python
# TraceFace blockchain client will call this if needed
client._contract.functions.authorizeUser(address, "analyst").transact()
```

Or use the ABI directly via cast:
```bash
cast send $CONTRACT_ADDRESS "authorizeUser(address,string)" $WALLET_ADDRESS "analyst" \
  --rpc-url $POLYGON_RPC_URL --private-key $PRIVATE_KEY
```
