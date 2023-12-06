# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 salahawk <tylermcguy@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

# Storage Subnet Validator code:

# Step 1: Import necessary libraries and modules
import os
import time
import torch
import random
import argparse
import traceback
import pickle
# import wandb
import bittensor as bt

# Custom modules
import copy
import hashlib
import sqlite3
from tqdm import tqdm

# import this repo
import storage
import allocate

CHUNK_SIZE = 1 << 22  # 4 MB
DEFAULT_N_CHUNKS = (
    1 << 8
)  # the minimum number of chunks a miner should provide at least is 1GB (CHUNK_SIZE * DEFAULT_N_CHUNKS)
MIN_N_CHUNKS = 10


# Step 2: Set up the configuration parser
# This function is responsible for setting up and parsing command-line arguments.
def get_config():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db_root_path",
        default=os.path.expanduser("~/bittensor-db"),
        help="Validator hashes",
    )
    parser.add_argument(
        "--no_bridge", action="store_true", help="Run without bridging to the network."
    )
    # Adds override arguments for network and netuid.
    parser.add_argument("--netuid", type=int, default=7, help="The chain subnet uid.")
    # Adds subtensor specific arguments i.e. --subtensor.chain_endpoint ... --subtensor.network ...
    bt.subtensor.add_args(parser)
    # Adds logging specific arguments i.e. --logging.debug ..., --logging.trace .. or --logging.logging_dir ...
    bt.logging.add_args(parser)
    # Adds wallet specific arguments i.e. --wallet.name ..., --wallet.hotkey ./. or --wallet.path ...
    bt.wallet.add_args(parser)
    # Parse the config (will take command-line arguments if provided)
    config = bt.config(parser)

    # Step 3: Set up logging directory
    # Logging is crucial for monitoring and debugging purposes.
    config.full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/{}".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey,
            config.netuid,
            "validator",
        )
    )
    # Ensure the logging directory exists.
    if not os.path.exists(config.full_path):
        os.makedirs(config.full_path, exist_ok=True)

    # Ensure the db_root_path directory exists.
    if not os.path.exists(config.db_root_path):
        os.makedirs(config.db_root_path, exist_ok=True)

    # Return the parsed config.
    return config


def main(config):
    # Set up logging with the provided configuration and directory.
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info(
        f"Running validator for subnet: {config.netuid} on network: {config.subtensor.chain_endpoint} with config:"
    )
    # Log the configuration for reference.
    bt.logging.info(config)

    # Step 4: Build Bittensor validator objects
    # These are core Bittensor classes to interact with the network.
    bt.logging.info("Setting up bittensor objects.")

    # The wallet holds the cryptographic key pairs for the validator.
    wallet = bt.wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")

    # The subtensor is our connection to the Bittensor blockchain.
    subtensor = bt.subtensor(config=config)
    bt.logging.info(f"Subtensor: {subtensor}")

    # Dendrite is the RPC client; it lets us send messages to other nodes (axons) in the network.
    dendrite = bt.dendrite(wallet=wallet)
    bt.logging.info(f"Dendrite: {dendrite}")

    # The metagraph holds the state of the network, letting us know about other miners.
    metagraph = subtensor.metagraph(config.netuid)
    bt.logging.info(f"Metagraph: {metagraph}")

    # Step 5: Connect the validator to the network
    if wallet.hotkey.ss58_address not in metagraph.hotkeys:
        bt.logging.error(
            f"\nYour validator: {wallet} if not registered to chain connection: {subtensor} \nRun btcli register and try again."
        )
        exit()
    else:
        # Each miner gets a unique identity (UID) in the network for differentiation.
        my_subnet_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        bt.logging.info(f"Running validator on uid: {my_subnet_uid}")

    # Step 6: Set up initial scoring weights for validation
    bt.logging.info("Building validation weights.")
    alpha = 0.9
    scores = torch.ones_like(metagraph.S, dtype=torch.float32)
    bt.logging.info(f"Weights: {scores}")

    # Load previously stored verified_allocations
    old_verified_allocations = []
    if os.path.exists(os.path.expanduser(f"{config.db_root_path}/verified_allocations.pkl")):
        with open(os.path.expanduser(f"{config.db_root_path}/verified_allocations.pkl"), 'rb') as f:
            old_verified_allocations = pickle.load(f)
    
    print(old_verified_allocations)

    # Generate allocations for the validator.
    next_allocations = []
    verified_allocations = []
    for hotkey in tqdm(metagraph.hotkeys):
        db_path = os.path.expanduser(
            f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/DB-{hotkey}-{wallet.hotkey.ss58_address}"
        )
        
        # Look for old verified allocations for current hotkey
        n_chunks = 0
        for allocation in old_verified_allocations:
            if allocation['miner'] == hotkey:
                n_chunks = allocation['n_chunks']
                break

        next_allocations.append(
            {
                "path": db_path,
                "n_chunks": n_chunks if n_chunks else DEFAULT_N_CHUNKS,
                "seed": f"{hotkey}{wallet.hotkey.ss58_address}",
                "miner": hotkey,
                "validator": wallet.hotkey.ss58_address,
                "hash": True,
            }
        )
        verified_allocations.append(
            {
                "path": db_path,
                "n_chunks": 0,
                "seed": f"{hotkey}{wallet.hotkey.ss58_address}",
                "miner": hotkey,
                "validator": wallet.hotkey.ss58_address,
                "hash": True,
            }
        )

    # Generate the hash allocations.
    allocate.generate(
        allocations=next_allocations,  # The allocations to generate.
        no_prompt=True,  # If True, no prompt will be shown
        workers=10,  # The number of concurrent workers to use for generation. Default is 10.
        restart=True,  # Dont restart the generation from empty files.
    )

    # Step 7: The Main Validation Loop
    bt.logging.info("Starting validator loop.")
    step = 0
    while True:
        try:
            # Iterate over all miners on the network and validate them.
            for i, alloc in tqdm(enumerate(next_allocations)):
                bt.logging.debug(f"Starting validation for miner [uid {i}]")
                # Dont self validate.
                if alloc["miner"] == wallet.hotkey.ss58_address:
                    continue

                # Select a random chunk to validate.
                verified_n_chunks = verified_allocations[i]["n_chunks"]
                new_n_chunks = alloc["n_chunks"]
                if verified_n_chunks >= new_n_chunks:
                    chunk_i = str(
                        random.randint(int(new_n_chunks * 0.8), new_n_chunks - 1)
                    )
                else:
                    chunk_i = str(random.randint(verified_n_chunks, new_n_chunks - 1))
                bt.logging.debug(f"Validating miner [uid {i}] (chunk_{chunk_i})")

                # Get the hash of the data to validate from the database.
                db = sqlite3.connect(alloc["path"])
                try:
                    validation_hash = (
                        db.cursor()
                        .execute(
                            f"SELECT hash FROM DB{alloc['seed']} WHERE id=?", (chunk_i,)
                        )
                        .fetchone()[0]
                    )
                except:
                    bt.logging.error(
                        f"❌ Failed to get validation hash for chunk_{chunk_i}"
                    )
                    continue
                db.close()

                # Query the miner for the data.
                miner_data = dendrite.query(
                    metagraph.axons[i],
                    storage.protocol.Retrieve(key=chunk_i),
                    deserialize=True,
                )

                if miner_data == None:
                    # The miner could not respond with the data.
                    # We reduce the estimated allocation for the miner.
                    next_allocations[i]["n_chunks"] = max(
                        int(next_allocations[i]["n_chunks"] * 0.9), MIN_N_CHUNKS
                    )
                    verified_allocations[i]["n_chunks"] = min(
                        next_allocations[i]["n_chunks"],
                        verified_allocations[i]["n_chunks"],
                    )
                    bt.logging.debug(
                        f"💤 Miner [uid {i}] did not respond with data, reducing allocation to: {next_allocations[i]['n_chunks']}"
                    )

                else:
                    # The miner was able to respond with the data, but we need to verify it.
                    computed_hash = hashlib.sha256(miner_data.encode()).hexdigest()

                    # Check if the miner has provided the correct response by doubling the dummy input.
                    if computed_hash == validation_hash:
                        # The miner has provided the correct response we can increase our known verified allocation.
                        # We can also increase our estimated allocation for the miner.
                        verified_allocations[i]["n_chunks"] = next_allocations[i][
                            "n_chunks"
                        ]
                        next_allocations[i]["n_chunks"] = int(
                            next_allocations[i]["n_chunks"] * 1.1
                        )
                        bt.logging.debug(
                            f"✅ Miner [uid {i}] provided correct response, increasing allocation to: {next_allocations[i]['n_chunks']}"
                        )
                    else:
                        # The miner has provided an incorrect response.
                        # We need to decrease our estimation..
                        next_allocations[i]["n_chunks"] = max(
                            int(next_allocations[i]["n_chunks"] * 0.9), MIN_N_CHUNKS
                        )
                        verified_allocations[i]["n_chunks"] = min(
                            next_allocations[i]["n_chunks"],
                            verified_allocations[i]["n_chunks"],
                        )
                        bt.logging.debug(
                            f"👎 Miner [uid {i}] provided incorrect response, reducing allocation to: {next_allocations[i]['n_chunks']}"
                        )

            allocate.generate(
                allocations=next_allocations,  # The allocations to generate.
                no_prompt=True,  # If True, no prompt will be shown
                restart=False,  # Dont restart the generation from empty files.
            )

            # Calculate score with n_chunks of verified_allocations
            for index, uid in enumerate(metagraph.uids):
                miner_hotkey = metagraph.neurons[uid].axon_info.hotkey
                try:
                    allocation_index = next(
                        i
                        for i, obj in enumerate(verified_allocations)
                        if obj["miner"] == miner_hotkey
                    )
                    score = verified_allocations[allocation_index]["n_chunks"]
                except StopIteration:
                    score = 0
                scores[index] = alpha * scores[index] + (1 - alpha) * score

            # Periodically update the weights on the Bittensor blockchain.
            # if (step + 1) % 5 == 0:  # estimated to be around 30 mins
            # TODO: Define how the validator normalizes scores before setting weights.
            weights = torch.nn.functional.normalize(scores, p=1.0, dim=0)
            bt.logging.info(f"Setting weights: {weights}")
            # This is a crucial step that updates the incentive mechanism on the Bittensor blockchain.
            # Miners with higher scores (or weights) receive a larger share of TAO rewards on this subnet.
            result = subtensor.set_weights(
                netuid=config.netuid,  # Subnet to set weights on.
                wallet=wallet,  # Wallet to sign set weights using hotkey.
                uids=metagraph.uids,  # Uids of the miners to set weights for.
                weights=weights,  # Weights to set for the miners.
                # wait_for_inclusion=True,
            )
            if result:
                bt.logging.success("✅ Successfully set weights.")
                
                # TODO: Store the weights locally.
                # Save verified_allocations
                with open(os.path.expanduser(f"{config.db_root_path}/verified_allocations.pkl"), 'wb') as f:
                    pickle.dump(verified_allocations, f)
                bt.logging.success("✅ Successfully stored weights locally.")

                # TODO: Store the weights on wandb.
                # # Initialize a new run in Weights & Biases
                # run = wandb.init(project="salahawk/tensorage", job_type="store_data")
                # # Create a new artifact with timestamp
                # artifact = wandb.Artifact(f'verified_allocations_{int(time.time())}', type='dataset')
                # # Add the file to the artifact
                # artifact.add_file(os.path.expanduser(f"{config.db_root_path}/verified_allocations.pkl"))
                # # Log the artifact
                # run.log_artifact(artifact)

                # bt.logging.success("✅ Successfully stored weights on wandb.")
            else:
                bt.logging.error("❌ Failed to set weights.")

            # End the current step and prepare for the next iteration.
            step += 1
            # Resync our local state with the latest state from the blockchain.
            metagraph = subtensor.metagraph(config.netuid)
            # Wait a block step.
            time.sleep(20)

        # If we encounter an unexpected error, log it for debugging.
        except RuntimeError as e:
            bt.logging.error(e)
            traceback.print_exc()

        # If the user interrupts the program, gracefully exit.
        except KeyboardInterrupt:
            bt.logging.success("Keyboard interrupt detected. Exiting validator.")
            exit()


# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    # Parse the configuration.
    config = get_config()
    # Run the main function.
    main(config)
