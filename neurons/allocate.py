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
import json
import shutil
import typing
import sqlite3
import hashlib
import argparse
import subprocess
import bittensor as bt
import multiprocessing
from datetime import datetime as dt
from concurrent.futures import ThreadPoolExecutor

# Import this repository.
from utils import check_version

MIN_SIZE_IN_GB = 100
CHUNK_SIZE = 1 << 22  # 4194304 (4 MB)


def get_config() -> bt.config:
    """
    Parse params and preparare config object.

    Returns:
        - bittensor.config: Nested config object created from parser arguments.
    """
    # Create parser and add all params.
    parser = argparse.ArgumentParser(description="Configure the database generation.")
    parser.add_argument("--db_root_path", default="~/tensorage-db", help="Path to the data database.")
    parser.add_argument("--size_in_gb", type=float, default=MIN_SIZE_IN_GB, help="Size of path to fill.")
    parser.add_argument("--disable_prompt", action="store_true", default=False, help="Does not wait for user input to confirm the allocation.")
    parser.add_argument("--disable_verify", action="store_true", default=False, help="Does not verify allocation data.")
    parser.add_argument("--restart", action="store_true", default=False, help="Restart the DB.")
    parser.add_argument("--workers", type=int, default=multiprocessing.cpu_count(), help="Number of concurrent workers to use.")

    # Override default netuid.
    parser.add_argument("--netuid", type=int, default=7, help="Netuid to rebase into.")

    # Adds subtensor specific arguments i.e. --subtensor.chain_endpoint ... --subtensor.network ...
    bt.subtensor.add_args(parser)

    # Adds logging specific arguments i.e. --logging.debug ..., --logging.trace .. or --logging.logging_dir ...
    bt.logging.add_args(parser)

    # Adds wallet specific arguments i.e. --wallet.name ..., --wallet.hotkey ./. or --wallet.path ...
    bt.wallet.add_args(parser)

    # Parse config.
    config = bt.config(parser)

    # Ensure the logging directory exists.
    config.full_path = os.path.join(os.path.expanduser(config.logging.logging_dir), config.wallet.name, config.wallet.hotkey, f"netuid{config.netuid}", "miner")
    if not os.path.exists(config.full_path):
        os.makedirs(config.full_path, exist_ok=True)

    return config


def get_available_space(path: str) -> int:
    """
    Calculate the available space in a given directory.

    Args:
        - path (str): The directory path.

    Returns:
        - int: Available space in bytes.
    """
    stat = os.statvfs(path)
    return stat.f_frsize * stat.f_bavail


def human_readable_size(size: int) -> str:
    """
    Convert a size in bytes to a human-readable format.

    Args:
        - size (int): Size in bytes.

    Returns:
        - str: Human-readable size.
    """
    thresholds = [1 << 40, 1 << 30, 1 << 20, 1 << 10]  # GB, MB, KB thresholds in bytes
    units = ['TB', 'GB', 'MB', 'KB', 'bytes']

    for threshold, unit in zip(thresholds, units):
        if size >= threshold:
            return f"{size / threshold:.2f} {unit}"

    return f"{size} bytes"


def confirm_generation(allocations: typing.List[dict]) -> bool:
    """
    Prompt the user to confirm the generation.

    Args:
        - allocations (typing.List[dict]): This is a list of dictionaries. Each dictionary contains details about an allocation.

    Returns:
        - bool: True if user confirms generation, False otherwise.
    """
    total_dbs = len(allocations)
    total_size = sum([alloc['n_chunks'] * CHUNK_SIZE for alloc in allocations])
    bt.logging.info(f"Are you sure you want to partition {total_dbs} databases with total size {human_readable_size(total_size)}? (yes/no)")
    return input().lower() in ['yes", "y']


def allocate(db_root_path: str, wallet: bt.wallet, metagraph: bt.metagraph, size_in_gb: float = MIN_SIZE_IN_GB, restart: bool = False) -> typing.List[dict]:
    """
    This function calculates the allocation of space for each hotkey in the metagraph.

    Args:
        - db_root_path (str): The path to the data database.
        - wallet (bt.wallet): The wallet object containing the name and hotkey.
        - metagraph (bt.metagraph): The metagraph object containing the hotkeys.
        - size_in_gb (float): The size for the allocation.
        - restart (bool): If True, it deletes all allocation before start.

    Returns:
        - list: A list of dictionaries. Each dictionary contains the allocation details for a hotkey.
    """

    # DB directory.
    wallet_db_path = os.path.expanduser(os.path.join(db_root_path, wallet.name, wallet.hotkey_str, "miner"))

    # Delete all DBs if restart flag is true.
    if restart:
        if os.path.exists(wallet_db_path):
            bt.logging.info(f"Restarting...")
            try:
                shutil.rmtree(wallet_db_path)
                bt.logging.info(f"Folder '{wallet_db_path}' and its contents successfully deleted.")

            except OSError as e:
                bt.logging.error(f"Error: {e}")

    # Create DB directory if not exists.
    if not os.path.exists(wallet_db_path):  # Ensure the wallet_db_path directory exists.
        os.makedirs(wallet_db_path, exist_ok=True)

    # Calculate the filling space.
    available_space = get_available_space(wallet_db_path)
    desired_filling_space = size_in_gb * 1024 * 1024 * 1024
    already_space = sum(f.stat().st_size for f in os.scandir(wallet_db_path) if f.is_file())

    if desired_filling_space - already_space <= available_space:
        filling_space = desired_filling_space

    else:
        raise Exception(f"Not enough space. Available: {human_readable_size(available_space)}. Desired: {human_readable_size(desired_filling_space)}")

    # Get the own hotkey from the wallet.
    own_hotkey = wallet.hotkey.ss58_address

    # Calculate the size of the database for each hotkey.
    db_size = filling_space / len(metagraph.hotkeys)

    # Calculate the number of chunks for each database.
    n_chunks = max(int(db_size / CHUNK_SIZE), 1)

    # Initialize an empty list to store the allocations.
    allocations = [{"db_path": os.path.join(wallet_db_path, f"DB-{own_hotkey}-{hotkey}"), "n_chunks": n_chunks, "own_hotkey": own_hotkey, "hotkey": hotkey} for hotkey in metagraph.hotkeys]

    # Delete old database if hotkey is not registered.
    for filename in os.listdir(wallet_db_path):
        hotkey = filename.replace(f"DB-{own_hotkey}-", "")
        if hotkey not in metagraph.hotkeys:
            os.remove(os.path.join(wallet_db_path, filename))

    # Return the allocations list.
    bt.logging.trace(f"Allocations: {json.dumps(allocations, indent=4)}")
    return allocations


def generate(allocations: typing.List[dict], disable_prompt: bool = False, only_hash: bool = False, workers: int = multiprocessing.cpu_count(), capture_output: bool = True):
    """
    This function is responsible for generating data and hashes DBs. It uses multi-threading to speed up the process.

    Args:
        - allocations (typing.List[dict]): This is a list of dictionaries. Each dictionary contains details about an allocation.
        - disable_prompt (bool): If this is set to True, the function will not ask for user confirmation before proceeding. By default, it's set to False.
        - only_hash (bool): If True, only generate hash DB for validators.
        - workers (int): This is the number of concurrent workers that will be used for generation. By default, it's set to CPU threads.
        - capture_output (bool): If True, no output is shown.
    """
    # First, we confirm the allocation step. This is done by calling the confirm_generation function. If the user does not confirm, the program will exit.
    if not disable_prompt and not confirm_generation(allocations=allocations):
        exit()

    # Finally, we run the generation process. This is done using a ThreadPoolExecutor, which allows us to run multiple tasks concurrently.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for allocation in allocations:
            executor.submit(run_rust_generate, allocation, only_hash, capture_output)


def run_rust_generate(allocation: dict, only_hash: bool = False, capture_output: bool = True):
    """
    This function runs a Rust script to generate the data and hashes databases.

    Args:
        - allocation (dict): A dictionary containing allocation details.
        - only_hash (bool): If True, only generate hash DB for validators.
        - capture_output (bool): If True, no output is shown.
    """
    # Get the directory containing the Rust script.
    rust_script_name = "storer_db_project"
    cargo_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_db", "target", "release")
    rust_executable = os.path.join(cargo_directory, rust_script_name)

    # Check if Rust script is compiled.
    if not os.path.exists(rust_executable):
        raise Exception("Rust executable not found. Please compile first (cargo build --release).")

    # Construct the command to run the Rust script. The command includes the path to the script, the path to the database, the number of chunks, the size of each chunk, and the table name for the database.
    cmd = [rust_executable,
           '--db_path', allocation['db_path'],
           '--n_chunks', str(allocation['n_chunks']),
           '--chunk_size', str(CHUNK_SIZE),
           '--table_name', f"{allocation['own_hotkey']}{allocation['hotkey']}"]

    # If the hash flag is True, add the "--hash" option to the command.
    if only_hash:
        cmd.append('--only_hash')

    # Run the command in the cargo directory. The output of the command is not captured.
    result = subprocess.run(cmd, cwd=cargo_directory, capture_output=capture_output, text=True)

    # If there is an error message in the output of the command, log an error message.
    if result.stderr:
        bt.logging.error(f"Failed to generate database: {allocation['db_path']}")


def verify(allocations):
    """
    Verify the integrity of the generated data and hashes.

    Args:
        - allocations (typing.List[dict]): This is a list of dictionaries. Each dictionary contains details about an allocation.
    """
    for allocation in allocations:
        if os.path.exists(allocation['db_path']):
            # Connect to the SQLite databases for data and hashes.
            connection = sqlite3.connect(allocation['db_path'])
            cursor = connection.cursor()

            key = 0
            while True:
                # Fetch data from the database using the current key.
                cursor.execute(f"SELECT data, hash FROM DB{allocation['own_hotkey']}{allocation['hotkey']} WHERE id = {key}")
                row = cursor.fetchone()

                # If no data is found for the current key, exit the loop.
                if not row:
                    break

                # Compute the hash of the fetched data.
                computed_hash = hashlib.sha256(row[0].encode("utf8")).hexdigest()

                # Check if the computed hash matches the stored hash.
                if computed_hash == row[1]:
                    bt.logging.success(f"Hash match for key {key}! computed hash: {computed_hash}, stored hash: {row[1]}")

                else:
                    bt.logging.error(f"Hash mismatch for key {key}!, computed hash: {computed_hash}, stored hash: {row[1]}")
                    return

                # Increment the key for the next iteration.
                key += 1

            # Log the successful verification of the data.
            bt.logging.success(f"Verified {allocation['db_path']}.")

            # Close the database connection.
            connection.close()


def main(config: bt.config):
    """
    Main function.

    Args:
        - config (bittensor.config): Nested config object created from parser arguments.
    """
    bt.logging(config=config, logging_dir=config.full_path)

    # Log the configuration for reference.
    bt.logging.info(config)

    # Load Bittensor objects.
    wallet = bt.wallet(config=config)
    subtensor = bt.subtensor(config=config)
    metagraph = subtensor.metagraph(netuid=config.netuid)

    # Allocation.
    allocations = allocate(db_root_path=config.db_root_path, wallet=wallet, metagraph=metagraph, size_in_gb=config.size_in_gb, restart=config.restart)

    # Generation.
    start = dt.now()
    generate(allocations=allocations, disable_prompt=config.disable_prompt, workers=config.workers, capture_output=False)
    bt.logging.info(f"Time elapsed: ({str((dt.now() - start).total_seconds())}s)")

    # Verification.
    if not config.disable_verify:
        verify(allocations)


if __name__ == "__main__":
    # Check version and restart PM2 if it's upgraded.
    check_version()

    # Parse the configuration.
    config = get_config()
    bt.logging.info(config)

    # Run the main function.
    bt.logging.info("Starting allocation...")
    main(config)
