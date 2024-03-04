# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 salahawk <tylermcguy@gmail.com>
# Copyright © 2024 Naked Snake <naked-snake-18>

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

import os
import time
import torch
import shutil
import typing
import pickle
import hashlib
import sqlite3
import argparse
import traceback
import bittensor as bt
import multiprocessing
from random import randint
from rich.table import Table
from contextlib import closing
from rich.console import Console
from concurrent.futures import ThreadPoolExecutor

# Import this repository.
import allocate
import tensorage
from utils import check_version

ALPHA = 0.9
STEP_TIME = 20
SCORES_TIME = 600
CHUNK_SIZE = 1 << 22  # 4194304 (4 MB)
DEFAULT_N_CHUNKS = 128  # 512MB per hotkey (256 x 512MB = 128GB disk alocated)
VALIDATION_INCREASING_RATE = 256  # 1GB
VALIDATION_DECREASING_RATE = 64  # 256MB


def get_config() -> bt.config:
    """
    Parse params and preparare config object.

    Returns:
        - bittensor.config: Nested config object created from parser arguments.
    """
    # Create parser and add all params.
    parser = argparse.ArgumentParser(description="Configure the validator.")
    parser.add_argument("--db_root_path", default="~/tensorage-db", help="Path to the data database.")
    parser.add_argument("--restart", action="store_true", default=False, help="If set, the validator will reallocate its DB entirely.")
    parser.add_argument("--workers", default=multiprocessing.cpu_count(), type=int, help="The number of concurrent workers to use for hash generation.")
    parser.add_argument("--no_store_weights", action="store_true", default=False, help="If False, the validator will store newly-set weights.")
    parser.add_argument("--no_restore_weights", action="store_true", default=False, help="If False, the validator will keep the weights from the previous run.")

    # Override default netuid.
    parser.add_argument("--netuid", type=int, default=7, help="Netuid to rebase into.")

    # Adds subtensor specific arguments i.e. --subtensor.chain_endpoint ... --subtensor.network ...
    bt.subtensor.add_args(parser)

    # Adds logging specific arguments i.e. --logging.debug ..., --logging.trace .. or --logging.logging_dir ...
    bt.logging.add_args(parser)

    # Adds wallet specific arguments i.e. --wallet.name ..., --wallet.hotkey ./. or --wallet.path ...
    bt.wallet.add_args(parser)

    # Adds axon specific arguments i.e. --axon.port...
    bt.axon.add_args(parser)

    # Parse config.
    config = bt.config(parser)

    # Ensure the logging directory exists.
    config.full_path = os.path.join(os.path.expanduser(config.logging.logging_dir), config.wallet.name, config.wallet.hotkey, f"netuid{config.netuid}", "validator")
    if not os.path.exists(config.full_path):
        os.makedirs(config.full_path, exist_ok=True)

    return config


def log_table(scores: torch.Tensor, n_chunks_list: typing.List[int], hotkeys: typing.List[str], title: str = "Score"):
    """
    It shows a score table to console.

    Args:
        - scores (torch.Tensor): List of tensors with scores of all hotkeys.
        - n_chunks_list (typing.List[int]): List with the number of chunks for each hotkey.
        - hotkeys (typing.List[str]): List of all hotkeys in the metagraph.
        - title (str): Title of the table.
    """
    # Initialize the table and add headers.
    table = Table(title=title)
    table.add_column("Uid", justify="right", style="cyan")
    table.add_column("Score", justify="right", style="cyan")
    table.add_column("Hotkey", justify="right", style="cyan")
    table.add_column("N. Chunks", justify="right", style="cyan")

    # Add each row of data.
    [table.add_row(str(i), str(score), str(hotkeys[i]), str(n_chunks_list[i])) for i, score in enumerate(scores)]

    # Show table in default console.
    console = Console()
    console.print(table)


def main(config: bt.config):
    """
    Main function.

    Args:
        - config (bittensor.config): Nested config object created from parser arguments.
    """
    # Set up logging with the provided configuration and directory.
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info(f"Running validator for subnet: {config.netuid} on network: {config.subtensor.chain_endpoint} with config:")

    # The wallet holds the cryptographic key pairs for the validator.
    wallet = bt.wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")

    # The subtensor is our connection to the Bittensor blockchain.
    subtensor = bt.subtensor(config=config)
    bt.logging.info(f"Subtensor: {subtensor}")

    # The metagraph holds the state of the network, letting us know about other miners.
    metagraph = subtensor.metagraph(config.netuid)
    bt.logging.info(f"Metagraph: {metagraph}")

    # Returns current version.
    async def ping(synapse: tensorage.protocol.Ping) -> tensorage.protocol.Ping:
        """
        Answer the call indicating that it's a validator and its version.

        Args:
            - synapse (tensorage.protocol.Ping): Synapse object with ping data.

        Returns:
            - tensorage.protocol.Ping: Synapse object with ping data.
        """
        synapse.data = f"validator-{tensorage.__version__}"
        return synapse

    # Returns a default message if any other validator requests data.
    async def retrieve(synapse: tensorage.protocol.Retrieve) -> tensorage.protocol.Retrieve:
        """
        Answer the call indicating that it's a validator and its UID.

        Args:
            - synapse (tensorage.protocol.Retrieve): Synapse object with ping data.

        Returns:
            - tensorage.protocol.Retrieve: Synapse object with ping data.
        """
        synapse.data = f"I am a validator on SN 7! UID: {metagraph.hotkeys.index(wallet.hotkey.ss58_address)}"
        return synapse

    # Check if hotkey is registered.
    if wallet.hotkey.ss58_address not in metagraph.hotkeys:
        bt.logging.error(f"\nYour validator: {wallet} if not registered to chain connection: {subtensor} \nRun btcli register and try again.")
        exit()

    # The axon handles request processing, allowing validators to send this process requests.
    axon = bt.axon(config=config, wallet=wallet)
    bt.logging.info(f"Axon {axon}")

    # Attach determiners which functions are called when servicing a request.
    bt.logging.info(f"Attaching functions to axon.")
    axon.attach(ping).attach(retrieve)

    # Serve passes the axon information to the network + netuid we are hosting on. This will auto-update if the axon port of external ip have changed.
    bt.logging.info(f"Serving axon 'ping' and 'retrieve' on network: {config.subtensor.chain_endpoint} with netuid: {config.netuid}")
    axon.serve(netuid=config.netuid, subtensor=subtensor)

    # Start starts the validator's axon, making it active on the network.
    bt.logging.info(f"Starting axon server on port: {config.axon.port}")
    axon.start()

    # Set up initial scoring weights for validation.
    bt.logging.info("Building validation weights.")
    scores = torch.ones_like(metagraph.S, dtype=torch.float32)

    # Set DBs directory.
    wallet_db_path = os.path.join(config.db_root_path, config.wallet.name, config.wallet.hotkey, "validator")

    # Delete all DBs if restart flag is true.
    if config.restart:
        if os.path.exists(wallet_db_path):
            bt.logging.info(f"Restarting...")
            try:
                shutil.rmtree(wallet_db_path)
                bt.logging.info(f"Folder '{wallet_db_path}' and its contents successfully deleted.")

            except OSError as e:
                bt.logging.error(f"Error: {e}")

    # Create DBs directory if not exists.
    if not os.path.exists(wallet_db_path):  # Ensure the wallet_db_path directory exists.
        os.makedirs(wallet_db_path, exist_ok=True)

    # Load previously stored allocations.
    old_allocations = []
    allocations_pkl = os.path.join(wallet_db_path, "..", "validator-allocations.pkl")
    if not config.no_restore_weights:
        if os.path.exists(allocations_pkl):
            with open(allocations_pkl, 'rb') as f:
                old_allocations = pickle.load(f)

            bt.logging.success("✅ Successfully restored previously-saved weights.")

        else:
            bt.logging.info("Previous weights state not found.")

    else:
        bt.logging.info("Ignoring previous weights state.")

    # Get the own hotkey from the wallet.
    own_hotkey = wallet.hotkey.ss58_address

    # Generate allocations for the validator.
    allocations = []
    for hotkey in metagraph.hotkeys:
        # Look for old verified allocations for current hotkey.
        n_chunks = DEFAULT_N_CHUNKS
        for allocation in old_allocations:
            if allocation['hotkey'] == hotkey:
                n_chunks = max(1, allocation['n_chunks'])
                break

        allocations.append({"db_path": os.path.join(wallet_db_path, f"DB-{own_hotkey}-{hotkey}"), "n_chunks": n_chunks, "own_hotkey": own_hotkey, "hotkey": hotkey})

    # Delete DB if hotkey is not registered.
    for filename in os.listdir(wallet_db_path):
        hotkey = filename.replace(f"DB-{own_hotkey}-", "")
        if hotkey not in metagraph.hotkeys:
            os.remove(os.path.join(wallet_db_path, filename))

    # Generate the hash allocations.
    allocate.generate(allocations=allocations, disable_prompt=True, only_hash=True, workers=config.workers)

    def validate_allocation(i: int, allocation: dict):
        """
        Validates how much space each hotkey has allocated.

        Args:
            - i (int): Index of enumerated list "allocations".
            - allocation (dict): A dictionary containing allocation details.
        """
        # Don't self validate and skip 0.0.0.0 axons.
        if allocation['hotkey'] == own_hotkey or metagraph.axons[i].ip == "0.0.0.0":
            return

        # Init hashes to compare.
        computed_hash = None
        validation_hash = ""

        # Select first or random chunk to validate.
        chunk_i = 0 if allocation['n_chunks'] < 2 else randint(max(0, allocation['n_chunks'] - VALIDATION_DECREASING_RATE), allocation['n_chunks'] - 1)

        # Query the miner for the data. TODO: Add timeout param and solve "Timeout context manager should be used inside a task" error.
        miner_data = bt.dendrite(wallet=wallet).query(metagraph.axons[i], tensorage.protocol.Retrieve(key=chunk_i), deserialize=True)

        # If the miner can respond with the data, we need to verify it.
        if miner_data is not None:
            # Calculate hash of data received.
            computed_hash = hashlib.sha256(miner_data.encode()).hexdigest()

            # Get the hash of the data to validate from the database.
            db = sqlite3.connect(allocation["db_path"])
            try:
                validation_hash = db.cursor().execute(f"SELECT hash FROM DB{allocation['own_hotkey']}{allocation['hotkey']} WHERE id = {chunk_i}").fetchone()[0]

            except Exception as e:
                bt.logging.error(f"❌ Failed to get validation hash for chunk_{chunk_i} in file {allocation['db_path']}: {e}")
                return
            db.close()

        # Check if the miner has provided the correct response.
        if computed_hash == validation_hash:
            # The miner has provided the correct response. We can increase our known verified allocation and our estimated allocation for the miner.
            allocation['n_chunks'] = int(chunk_i + VALIDATION_INCREASING_RATE)
            bt.logging.success(f"✅ Miner [uid {i}] provided correct chunk_{chunk_i}. Increasing allocation to: {allocation['n_chunks']}.")
            allocate.run_rust_generate(allocation, only_hash=True)

        else:
            # The miner has provided an incorrect response. We need to decrease our estimation.
            allocation['n_chunks'] = max(chunk_i - VALIDATION_DECREASING_RATE, 1)
            bt.logging.error(f"❌ Miner [uid {i}] provided incorrect chunk_{chunk_i}. Reducing allocation to: {allocation['n_chunks']}.")

    # The main validation Loop.
    step = 0
    bt.logging.info("🚀 Starting validator loop.")
    while True:
        # Measure the time it takes to validate all the miners running on the subnet.
        start_time = time.time()

        try:
            # Iterate over all hotkeys on the network and validate them.
            with ThreadPoolExecutor(max_workers=config.workers) as executor:
                [executor.submit(validate_allocation, i, allocation) for i, allocation in enumerate(allocations)]

            # Log the time it took to validate all miners.
            bt.logging.info(f"Finished validation step {step} in {time.time() - start_time} seconds.")

            if not config.no_store_weights:  # Save verified allocations.
                with open(allocations_pkl, 'wb') as f:
                    pickle.dump(allocations, f)
                bt.logging.success("✅ Successfully stored verified allocations locally.")

                # TODO: Store verified allocations on wandb.
                # # Initialize a new run in Weights & Biases
                # run = wandb.init(project="salahawk/tensorage", job_type="store_data")
                # # Create a new artifact with timestamp
                # artifact = wandb.Artifact(f'allocations_{int(time.time())}', type='dataset')
                # # Add the file to the artifact
                # artifact.add_file(allocations_pkl)
                # # Log the artifact
                # run.log_artifact(artifact)
                # bt.logging.success("✅ Successfully stored verified allocations on wandb.")

            # Resync our local state with the latest state from the blockchain.
            metagraph = subtensor.metagraph(config.netuid)

            # Update allocations if hotkey of uid change.
            for i, hotkey in enumerate(metagraph.hotkeys):
                # No hotkey change for this uid.
                if allocations[i]['hotkey'] == hotkey:
                    continue

                # Old hotkey was deregistered and new hotkey registered on this uid so reset the allocation for this uid.
                bt.logging.info(f"✨ Found new hotkey: {hotkey}.")

                # Delete old DB file.
                os.remove(allocations[i]['db_path'])

                # Generate new allocation.
                db_path = os.path.join(wallet_db_path, f"DB-{own_hotkey}-{hotkey}")
                allocations[i] = {"db_path": db_path, "n_chunks": DEFAULT_N_CHUNKS, "own_hotkey": own_hotkey, "hotkey": hotkey}
                allocate.run_rust_generate(allocations[i], only_hash=True)

            # Periodically update the weights on the Bittensor blockchain.
            if step % int(SCORES_TIME / STEP_TIME) == 0:
                # Calculate score with n_chunks of allocations.
                for index, uid in enumerate(metagraph.uids):
                    try:
                        allocation_index = next(i for i, obj in enumerate(allocations) if obj['hotkey'] == metagraph.neurons[uid].axon_info.hotkey)
                        score = allocations[allocation_index]['n_chunks']

                    except StopIteration:
                        score = 0

                    scores[index] = ALPHA * scores[index] + (1 - ALPHA) * score

                # TODO: Define how the validator normalizes scores before setting weights.
                weights = torch.nn.functional.normalize(scores, p=1.0, dim=0)
                bt.logging.info("Setting weights:")
                log_table(scores=weights, n_chunks_list=[allocation['n_chunks'] for allocation in allocations], hotkeys=metagraph.hotkeys)

                # This is a crucial step that updates the incentive mechanism on the Bittensor blockchain. Miners with higher scores (or weights) receive a larger share of TAO rewards on this subnet.
                if subtensor.set_weights(netuid=config.netuid, wallet=wallet, uids=metagraph.uids, weights=weights):
                    bt.logging.success("✅  Successfully set weights.")

                else:
                    bt.logging.error("❌  Failed to set weights.")

            # End the current step and prepare for the next iteration.
            step += 1

            # Wait for validate again.
            bt.logging.info(f"Waiting {STEP_TIME} seconds for the next step.")
            time.sleep(STEP_TIME)

        # If we encounter an unexpected error, log it for debugging.
        except RuntimeError as e:
            bt.logging.error(e)
            traceback.print_exc()

        # If the user interrupts the program, gracefully exit.
        except KeyboardInterrupt:
            axon.stop()
            bt.logging.success("Keyboard interrupt detected. Exiting validator.")
            exit()

        # Check version and restart PM2 if it's upgraded.
        check_version()


# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    # Check version and restart PM2 if it's upgraded.
    check_version()

    # Parse the configuration.
    config = get_config()
    bt.logging.info(config)

    # Run the main function.
    main(config)
