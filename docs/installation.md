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

## Mining

To run the miner
```bash
pm2 start neurons/miner.py --name miner --interpreter python3 -- 
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, defautl = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_root_path <OPTIONAL: path where you want the DB files stored, default = "~/bittensor-db">  # This is where the partition will be created storing network data.
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --threshold <OPTIONAL: threshold i.e. 0.01, default =  0.01>  # The threshold for the partitioning algorithm which is the maximum amount of space the miner can use based on available.
    --netuid <OPTIONAL: the subnet netuid, defualt = 7> # This is the netuid of the storage subnet.
    --subtensor.network local # <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> : The chain endpoint to use to generate the partition.  (highly recommend running subtensor locally)
    --steps_per_reallocate <OPTIONAL: the number of steps before reallocating, default = 1000> # The number of steps before reallocating.
    # --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. default = False> # If true, the partitioning process restarts instead using a checkpoint.
```

## Validating

To run the validator
```bash
pm2 start neurons/validator.py --name validator --interpreter python3 -- 
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, default = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_root_path <OPTIONAL: path where you want the DB files stored, default = "~/bittensor-db">  # This is where the partition will be created storing network data.
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --netuid <OPTIONAL: the subnet netuid, defualt = 7> # This is the netuid of the storage subnet you are serving on.
    --subtensor.network local # <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> : The chain endpoint to use to generate the partition. (highly recommend running subtensor locally)
    --validator
```
