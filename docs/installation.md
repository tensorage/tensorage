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

### Build Rust binary
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
    --db_root_path <OPTIONAL: path where you want the DB files stored. Default = ~/tensorage-db>  # This is where the partition will be created storing network data.
    --size_in_gb <OPTIONAL: size_in_gb i.e. 1024. Default = 100>  # This is the default size to store data.
    --disable_prompt <OPTIONAL: does not wait for user input to confirm the allocation. Default = False> # If True, the partitioning process will not wait for user input to confirm the allocation.
    --disable_verify <OPTIONAL: does not verify the allocated data. Default = False> # If True, the partitioning process verify all data allocated.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. Default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --workers <OPTIONAL: number of concurrent workers to use. Default = 256> # The number of concurrent workers to use to generate the partition.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint. Default = finney> # The chain endpoint to use to generate the partition.
    --wallet.name <OPTIONAL: your miner wallet. Default = default> # Must be created using the bittensor-cli, btcli w new_coldkey.
    --wallet.hotkey <OPTIONAL: your validator hotkey. Defautl = default> # Must be created using the bittensor-cli, btcli w new_hotkey.
```

Example:
```bash
python3 neurons/allocate.py
    --db_root_path ~/subnet07-db
    --size_in_gb 5000
    --disable_verify
    --workers 8
    --subtensor.network local
    --wallet.name coldkey
    --wallet.hotkey hotkey1
```

## Register your hotkey
You can find steps here on [Official Bittensor Documentation](https://docs.bittensor.com/subnets/register-and-participate]).

## Validating
To run the validator.
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- 
    --db_root_path <OPTIONAL: path where you want the DB files stored. Default = ~/tensorage-db>  # This is where the partition will be created storing network data.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. Default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --workers <OPTIONAL: number of concurrent workers to use. Default = 256> # The number of concurrent workers to use to generate the partition.
    --no_store_weights <OPTIONAL: no store the weights. Default = False> # If you don't want to store the weights on your harddrive.
    --no_restore_weights <OPTIONAL: no store the weights. Default = False> # If you don't want to restore the weights by old runs from your harddrive.
    --logging.debug <OPTIONAL: Run in debug mode. Default = False> # Run in debug mode.
    --logging.trace <OPTIONAL: Run in trace mode. Default = False> # Run in trace mode.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint. Default = finney> # The chain endpoint to use to generate the partition.
    --wallet.name <OPTIONAL: your miner wallet. Default = default> # Must be created using the bittensor-cli, btcli w new_coldkey.
    --wallet.hotkey <OPTIONAL: your validator hotkey. Defautl = default> # Must be created using the bittensor-cli, btcli w new_hotkey.
```

Example:
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- 
    --db_root_path ~/subnet07-db
    --workers 8
    --logging.debug
    --subtensor.network local
    --wallet.name coldkey
    --wallet.hotkey hotkey1
```

## Mining

To run the miner.
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 --
    --db_root_path <OPTIONAL: path where you want the DB files stored. Default = ~/tensorage-db>  # This is where the partition will be created storing network data.
    --size_in_gb <OPTIONAL: size_in_gb i.e. 1024. Default = 100>  # This is the default size to store data.
    --seconds_per_reallocate <OPTIONAL: the number of seconds before reallocating. Default = 600> # This is the time between space updates based on changes to the subnet hotkeys.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. Default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --workers <OPTIONAL: number of concurrent workers to use. Default = 256> # The number of concurrent workers to use to generate the partition.
    --logging.debug <OPTIONAL: Run in debug mode. Default = False> # Run in debug mode.
    --logging.trace <OPTIONAL: Run in trace mode. Default = False> # Run in trace mode.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint. Default = finney> # The chain endpoint to use to generate the partition.
    --wallet.name <OPTIONAL: your miner wallet. Default = default> # Must be created using the bittensor-cli, btcli w new_coldkey.
    --wallet.hotkey <OPTIONAL: your validator hotkey. Defautl = default> # Must be created using the bittensor-cli, btcli w new_hotkey.
```

Example:
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 --
    --db_root_path ~/subnet07-db
    --size_in_gb 5000
    --seconds_per_reallocate 900
    --workers 4
    --logging.debug
    --subtensor.network local
    --wallet.name coldkey
    --wallet.hotkey hotkey2
```
