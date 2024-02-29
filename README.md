<div align="center">

---
# Storage Subnet on Bittensor <!-- omit in toc -->

[Discord](https://discord.gg/bittensor) • [Network](https://taostats.io/) • [Research](https://bittensor.com/whitepaper) • [Installation](./docs/installation.md)
---
[![Discord Chat](https://img.shields.io/discord/308323056592486420.svg)](https://discord.gg/bittensor)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 

</div>

# 1. Introduction

Bittensor aims to revolutionize the AI landscape by providing a decentralized network where nodes can share machine learning resources. This document outlines the process of designing, implementing, and deploying a specialized storage subnet within the Bittensor network, inspired by Filecoin and IPFS.

# 2. System Overview

## 2.1 Bittensor Network

Bittensor is a decentralized network that facilitates the sharing of machine learning resources. It operates as a Peer-to-Peer Intelligence Market, where intelligence is priced by other intelligence systems across the internet. The network uses a digital ledger to record ranks and provide incentives in a decentralized way.

## 2.2 Storage Subnet

The storage subnet will allow nodes to contribute storage space, employing a prototype incentive mechanism similar to Filecoin. It will offer decentralized storage solutions, allowing nodes to serve their hard drive space to the network, proven to validators utilizing Yuma consensus.

# 3. Design

## 3.1 Subnet Architecture

- **Nodes**: Nodes in the storage subnet will have roles similar to Filecoin, including miners (storage providers), validators and clients (storage consumers).
    * **Miners**: Miners will serve their hard drive space to the network, storing encrypted data and proving its existence to validators. They commit to storing data for a specified duration. Miners earn TAO from network emissions for providing storage and serving client requests.
    * **Validators**: Validators validate storage proofs from miners to ensure data integrity. They validate transactions and add them to the blockchain and earn TAO from network emissions for validating and maintaining network security.
    * **Clients**: Clients will be able to store and retrieve data from the network. Optionally, they provide feedback or ratings on miner performance.
- **Interaction Mechanisms**: Nodes will communicate using P2P networking and data transmission protocols.
- **Consensus Mechanism**: The subnet will operate under Bittensor's Yuma consensus mechanism.

## 3.2 Storage Mechanism

- **Data Storage**: Data will be distributed across nodes, ensuring redundancy and availability.
- **Proof of Storage**: Miners will prove the existence of data to validators using a proof of storage mechanism.
    * **Periodic Proofs**: Validators ask miners provide proof of storage periodically and miners submit cryptographic proofs of stored data to their assigned validators.
    * **Validation**: Validators check these proofs. If valid, both miners and validators earn TAO from network emissions.
- **Data Retrieval**: A mechanism will be designed for efficient data retrieval, leveraging Bittensor's peer-to-peer intelligence market.

## 3.3 Incentive Mechanism

Nodes will be rewarded based on their contribution to storage and the efficiency of data retrieval. The incentive function will limit rewards to peers that haven't reached consensus in the network.

# 4. Implementation

## 4.1 Subnet Registration Module

- **Hotkey Registration**: The subnet registration module is responsible for registering the subnet's hotkey on the Bittensor chain. This is done by using the `btcli s register` command in the `bittensor` package.

- **Subnet Registration**: The subnet registration module is also responsible for registering the subnet on the Bittensor chain. This is done by using the `btcli s create` command in the `bittensor` package.

## 4.2 Mining Module
The miner (`neurons/miner.py`) is responsible for serving data to the network. It does this by partitioning a portion of the user's hard drive and filling it with data. The size of the partition is determined by the `threshold` parameter, which represents the proportion of available space that should be used to store data. The miner also periodically reallocates its database based on the available memory and the network state. The miner is also responsible for generating proofs of storage and submitting them to validators. The miner is rewarded for its contribution to the network by earning TAO from network emissions.

The miner uses SQLite databases to store and retrieve data. It maintains a separate database connection for each validator in the network. The `retrieve` and `store` functions are used to handle data retrieval and storage requests from validators. The miner also maintains a separate database connection for the partitioning algorithm. 

## 4.3 Validation Module
The validator (`neurons/validator.py`) is responsible for verifying the integrity of the data served by the miner. It does this by comparing the hash of the retrieved data with a stored hash. 
If the hashes do not match, it indicates that the data has been tampered with. The validator is rewarded for its contribution to the network by earning TAO from network emissions. 

The validator also maintains a separate database connection for each miner in the network. The `retrieve` and `store` functions are used to handle data retrieval and storage requests from miners.
The validator also maintains a separate database connection for the partitioning algorithm.

## 4.4 Partitioning Algorithm
The partitioning algorithm is responsible for partitioning the user's hard drive and filling it with data. It uses a greedy algorithm to partition the hard drive into chunks of size `CHUNK_SIZE`.

The algorithm is run periodically to reallocate the database based on the available memory and the network state. The algorithm is also run at startup to initialize the database.

## 4.5 Proof of Storage
The proof of storage mechanism is responsible for proving the existence of data to validators. It does this by generating a cryptographic proof of the stored data and submitting it to the assigned validator.

The validator then checks this proof.
- If the proof is valid, it means that the miner is indeed storing the data, and both the miner and validator earn TAO from network emissions. 
- If the proof is not valid, it means that the miner might not be storing the data it claims to be storing, and no rewards are given.

The proof of storage mechanism is run periodically to generate proofs for all stored data.

## 4.6 Data Storage
The miner uses the `store` function to handle data storage requests from validators. When a validator sends a storage request, the miner stores the data in the appropriate SQLite database.

The miner also generates a cryptographic proof of the stored data, known as a Proof of Storage. This proof is submitted to the validator to verify that the miner is indeed storing the data it claims to be storing.

## 4.7 Data Retrieval
Data retrieval is also handled by the miner node. When a client (or a validator) requests data, the miner uses the `retrieve` function to fetch the requested data from the SQLite database.

The miner retrieves the data in chunks, based on the size of the chunks when they were stored. The data is then returned to the client or validator that requested it.

It's important to note that the miner is rewarded for serving client requests, so it's incentivized to handle data retrieval requests efficiently and accurately.

## 4.8 Incentive Mechanism
Incentive mechanism is based on the contribution of nodes to the network. Both miners and validators earn TAO, the network's native token, from network emissions.

- **Miners**: Miners earn TAO for providing storage and serving client requests. The amount of TAO earned is proportional to the amount of storage they provide and the number of client requests they serve. Miners also generate and submit proofs of storage to validators, and they earn TAO when these proofs are validated.

- **Validators**: Validators earn TAO for validating storage proofs from miners and maintaining network security. When a validator validates a storage proof, both the miner who submitted the proof and the validator earn TAO.

The reward mechanism is run periodically to distribute rewards to nodes for their contributions to the network. The exact frequency of these reward distributions is up to design, but it can be determined by the network's consensus protocol.

It's important to note that if a miner's proof of storage is not valid, it indicates that the miner might not be storing the data it claims to be storing, and no rewards are given. This ensures that miners are incentivized to honestly and accurately report their storage contributions.


# 5. Default Configuration
## 5.1 Allocator (allocate.py)
- **db_root_path**: Default value is `'~/tensorage-db'`. This is the path where the SQLite databases for data storage and retrieval are stored.
- **size_in_gb**: Default value is `100GB`. This is the default size to store data.
- **validator**: Default value is `False`. If `True`, only generate hash DB for validators.
- **disable_prompt**: Default value is `False`. If `True`, not wait for user input to confirm the allocation.
- **disable_verify**: Default value is `False`. If `True`, not verify allocation data.
- **restart**: Default value is `False`. If `True`, restart the DB.
- **workers**: Default value is `[CPU threads]`. Number of concurrent workers to use.
- **subtensor.network**: Default value is `'finney'`. The chain endpoint to use to generate the partition.
- **wallet.name**: Default value is `'default'`. This is the name of the wallet used by the miner and validator.
- **wallet.hotkey**: Default value is `'default'`. This is the hotkey of the wallet used by the miner and validator.

## 5.2 Validator (validator.py)
- **db_root_path**: Default value is `'~/tensorage-db'`. This is the path where the SQLite databases for data storage and retrieval are stored.
- **workers**: Default value is `[CPU threads]`. Number of concurrent workers to use.
- **restart**: Default value is `False`. If `True`, restart the DB.
- **no_store_weights**: Default value is `False`. If `False`, the validator will store newly-set weights.
- **no_restore_weights**: Default value is `False`. If `False`, the validator will keep the weights from the previous run.
- **no_bridge**: Default value is `False`. Run without bridging to the network.
- **logging.debug**: Default value is `False`. Run in debug mode.
- **logging.trace**: Default value is `False`. Run in trace mode.
- **subtensor.network**: Default value is `'finney'`. The chain endpoint to use to generate the partition.
- **wallet.name**: Default value is `'default'`. This is the name of the wallet used by the miner and validator.
- **wallet.hotkey**: Default value is `'default'`. This is the hotkey of the wallet used by the miner and validator.

## 5.3 Miner (miner.py)
- **db_root_path**: Default value is `'~/tensorage-db'`. This is the path where the SQLite databases for data storage and retrieval are stored.
- **size_in_gb**: Default value is `100GB`. This is the default size to store data.
- **seconds_per_reallocate**: Default value is `600 seconds`. This is the time between space updates based on changes to the subnet hotkeys.
- **workers**: Default value is `[CPU threads]`. Number of concurrent workers to use.
- **restart**: Default value is `False`. If `True`, restart the DB.
- **logging.debug**: Default value is `False`. Run in debug mode.
- **logging.trace**: Default value is `False`. Run in trace mode.
- **subtensor.network**: Default value is `'finney'`. The chain endpoint to use to generate the partition.
- **wallet.name**: Default value is `'default'`. This is the name of the wallet used by the miner and validator.
- **wallet.hotkey**: Default value is `'default'`. This is the hotkey of the wallet used by the miner and validator.

Please note that these default values can be overridden by command-line arguments when running the allocator, miner or validator.


# 6. Deployment

You can find step-by-step guideline [here...](./docs/installation.md)

Minimum device requirement

`For miner`
- 1 TB of Hard Disk, 4 GB of RAM, 8 vCPUs

`For validator`
- 500 GB of Hard Disk, 8 GB of RAM, 64 vCPUs

# License
This repository is licensed under the MIT License.
```text
The MIT License (MIT)
Copyright © 2023 Yuma Rao

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the “Software”), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
```
