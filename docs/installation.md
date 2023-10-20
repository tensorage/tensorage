# Storage Subnet
This is a prototype incentive mechanism for storage where miners serve their harddrive space onto the network and prove its existence to validators. Miners are rewarded proportionally to the amount of space they can prove they have, and also allow encrypted data to be stored there by validators. The amount of space available to each validator is proportional to the amount of stake they have on the network.


# Installation

### Install `pm2`
```bash
apt update && apt upgrade
apt install nodejs npm
npm i -g pm2
```

### Clone the repository from Github
```bash
git clone https://github.com/salahawk/storage-subnet
```

### Create a virtual environment for the repository
```bash
python -m venv venv
```
This will create a virtual environment for the repository (`venv` directory will be created under the root of the repository)

### Activate the virtual environment
```bash
sudo source ./venv/bin/activate
```

### Install package dependencies for the repository
```bash
pip install -r requirements.txt
```

### Build rust binary
```bash
cd neurons/generate_db
apt install rustc
apt install cargo
cargo build --release
```

## Allocating 

Allocates space on your machine based on the amount of stake other neurons have on the network. The allocation process is done by partitioning the space on your machine into chunks and assigning each chunk to a validator. The amount of space allocated to each validator is proportional to the amount of stake they have on the network. The allocation process is done by running the following command.

```bash
cd neurons/ # Navigate to the neurons directory.
cd generate_db; cargo build --release # Builds the rust binary.
python allocate.py # Runs the partitioning process.
    --db_path <OPTIONAL: path where you want the DB files stored, default = ~/bittensor-db>  # This is where the partition will be created storing network data.
    --netuid <OPTIONAL: the subnet netuid, defualt = 1> # This is the netuid of the storage subnet you are serving on.
    --threshold <OPTIONAL: threshold i.e. 0.01, default =  0.01>  # The threshold for the partitioning algorithm which is the maximum amount of space the miner can use based on available.
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, default = default> # Must be created using the bittensor-cli, btcli new_hotkey
    --no_prompt <OPTIONAL: does not wait for user input to confirm the allocation, default = False> # If true, the partitioning process will not wait for user input to confirm the allocation.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --workers <OPTIONAL: number of concurrent workers to use, default = 10> # The number of concurrent workers to use to generate the partition.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> # The chain endpoint to use to generate the partition.
    --logging.debug <OPTIONAL: run in debug mode, default = False> # If true, the partitioning process will run in debug mode.
    --validator <OPTIONAL: run the partitioning process as a validator, default = False> # If true, the partitioning process will run as a validator.

# Should create the files like the following, if --validator is set, skips verification process
>> <db_path>
>> └── <wallet_name>
>>     └── <wallet_hotkey_name>
>>         ├── DB-<wallet_hotkey>-<validator(uid_0)_hotkey>
>>         ├── DB-<wallet_hotkey>-<validator(uid_1)_hotkey>
>>         ├── DB-<wallet_hotkey>-<validator(uid_2)_hotkey>
>>         └── ...
```


## Mining

To run the miner
```bash
pm2 start neurons/miner.py --name miner --interpreter python -- 
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, defautl = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_path <OPTIONAL: path where you want the DB files stored, default = ~/bittensor-db>  # This is where the partition will be created storing network data.
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --threshold <OPTIONAL: threshold i.e. 0.01, default =  0.01>  # The threshold for the partitioning algorithm which is the maximum amount of space the miner can use based on available.
    --netuid <OPTIONAL: the subnet netuid, defualt = 1> # This is the netuid of the storage subnet you are serving on.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> # The chain endpoint to use to generate the partition.
    --restart <OPTIONAL: restart the partitioning process from the beginning, otherwise restarts from the last created chunk. default = False> # If true, the partitioning process restarts instead using a checkpoint.
    --steps_per_reallocate <OPTIONAL: the number of steps before reallocating, default = 1000> # The number of steps before reallocating.
```

## Validating

To run the validator
```bash
pm2 start neurons/validator.py --name validator --interpreter python -- 
    --wallet.name <OPTIONAL: your miner wallet, default = default> # Must be created using the bittensor-cli, btcli wallet new_coldkey
    --wallet.hotkey <OPTIONAL: your validator hotkey, default = default> # Must be created using the bittensor-cli btcli wallet new_hotkey
    --db_path <OPTIONAL: path where you want the DB files stored, default = ~/bittensor-db>  # This is where the partition will be created storing network data.
    --logging.debug # Run in debug mode, alternatively --logging.trace for trace mode
    --netuid <OPTIONAL: the subnet netuid, defualt = 1> # This is the netuid of the storage subnet you are serving on.
    --subtensor.network <OPTIONAL: the bittensor chain endpoint, default = finney, local, test> # The chain endpoint to use to generate the partition.
```