# Storage Subnet
This is a prototype incentive mechanism for storage where miners serve their harddrive space onto the network and prove its existence to validators. Miners are rewarded proportionally to the amount of space they can prove they have, and also allow encrypted data to be stored there by validators. The amount of space available to each validator is proportional to the amount of stake they have on the network.


# Installation

### Install `pm2`
```bash
apt update && apt upgrade -y
apt install nodejs npm -y
npm i -g pm2
```

### Clone the repository from Github
```bash
git clone https://github.com/tensorage/tensorage
```

### Install package dependencies for the repository
```bash
cd tensorage
apt install python3-pip -y
python3 -m pip install -e .
```

### Build rust binary
```bash
cd neurons/generate_db
apt install rustc -y
apt install cargo -y
apt-get install libsqlite3-dev
cargo build --release
```

## Running subtensor locally

### Install Docker
```bash
apt install docker.io -y
apt install docker-compose -y
```

### Run Subtensor locally
```bash
git clone https://github.com/opentensor/subtensor.git
cd subtensor
docker-compose up --detach
```

## Allocating (not required, but recommended for miners)
```bash
python3 neurons/allocate.py
    --db_path <OPTIONAL: path where you want the DB files stored, default = ~/bittensor-db>  # This is where the partition will be created storing network data.
    --netuid <OPTIONAL: the subnet netuid, defualt = 7> # This is the netuid of the storage subnet you are serving on.
    --threshold <OPTIONAL: threshold i.e. 0.9, default =  0.9>  # The threshold for the partitioning algorithm which is the maximum amount of space the miner can use based on available.
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, defautl = default> # Must be created using the bittensor-cli, btcli new_hotkey
    --no_prompt <OPTIONAL: does not wait for user input to confirm the allocation, default = False> # If true, the partitioning process will not wait for user input to confirm the allocation.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --workers <OPTIONAL: number of concurrent workers to use, default = 256> # The number of concurrent workers to use to generate the partition.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> # The chain endpoint to use to generate the partition.
    --logging.debug <OPTIONAL: run in debug mode, default = False> # If true, the partitioning process will run in debug mode.
    --validator <OPTIONAL: run the partitioning process as a validator, default = False> # If true, the partitioning process will run as a validator.
```

## Register your hotkey
You can find steps here on [Official Bittensor Documentation](https://docs.bittensor.com/subnets/register-and-participate])

## Mining

To run the miner
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 -- 
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, defautl = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_root_path <OPTIONAL: path where you want the DB files stored, default = "~/bittensor-db">  # This is where the partition will be created storing network data.
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --threshold <OPTIONAL: threshold i.e. 0.9, default =  0.9>  # The threshold for the partitioning algorithm which is the maximum amount of space the miner can use based on available.
    --netuid <OPTIONAL: the subnet netuid, defualt = 7> # This is the netuid of the storage subnet.
    --subtensor.network local # <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> : The chain endpoint to use to generate the partition.  (highly recommend running subtensor locally)
    --steps_per_reallocate <OPTIONAL: the number of steps before reallocating, default = 1000> # The number of steps before reallocating.
    # --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. default = False> # If true, the partitioning process restarts instead using a checkpoint.
```

- Example 1 (with default values):
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 -- --wallet.name default --wallet.hotkey default --logging.debug
```

- Example 2 (with custom values):
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 -- 
    --wallet.name default
    --wallet.hotkey default
    --db_root_path ~/bittensor-db
    --logging.debug
    --threshold 0.9
    --netuid 7
    --subtensor.network local
    --restart
```

## Validating

To run the validator
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- 
    --validator
    --no_store_weights # Optional: If you don't want to store the weights on your harddrive, default = False
    --no_restore_weights # Optional: If you don't want to restore the weights by old runs from your harddrive, default = False
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --logging.trace # Run in trace mode, alternatively --logging.debug for debug mode
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, default = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_root_path <OPTIONAL: path where you want the DB files stored, default = "~/bittensor-db">  # This is where the partition will be created storing network data.
    --netuid <OPTIONAL: the subnet netuid, defualt = 7> # This is the netuid of the storage subnet you are serving on.
    --subtensor.network local # <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> : The chain endpoint to use to generate the partition. (highly recommend running subtensor locally)
    --miner_min_chunks <OPTIONAL: the minimum number of chunks miners should provide to your validator, default = 256> # The minimum number of chunks miners should provide to this validator
    --miner_max_chunks <OPTIONAL: the maximum number of chunks miners can provide to your validator, default = 2560000000> # The maximum number of chunks miners should provide to this validator
```

- Example 1 (with default values):
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- --validator --wallet.name default --wallet.hotkey default --logging.debug --logging.trace
```

- Example 2 (with custom values):
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- 
    --validator
    --wallet.name default
    --wallet.hotkey default
    --db_root_path ~/bittensor-db
    --logging.debug
    --logging.trace
    --netuid 7
    --subtensor.network local
    --miner_min_chunks 256
    --miner_max_chunks 2560000000
```
