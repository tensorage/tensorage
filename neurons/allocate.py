import os
import json
import torch
import shutil
import typing
import sqlite3
import hashlib
import argparse
import subprocess
import bittensor as bt
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

CHUNK_SIZE = 1 << 20


def get_config() -> bt.config:
    parser = argparse.ArgumentParser(
        description="Rebase the database based on available memory and also"
    )
    parser.add_argument(
        "--db_root_path",
        required=False,
        default="~/bittensor-db",
        help="Path to the data database.",
    )
    parser.add_argument(
        "--netuid", type=int, default=1, required=False, help="Netuid to rebase into"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0001,
        required=False,
        help="Size of path to fill",
    )
    parser.add_argument(
        "--validator",
        action="store_true",
        default=False,
        help="Allocate as a validator",
    )
    parser.add_argument(
        "--no_prompt",
        action="store_true",
        default=False,
        help="Does not wait for user input to confirm the allocation.",
    )
    parser.add_argument(
        "--restart", action="store_true", default=False, help="Restart the db."
    )
    parser.add_argument(
        "--workers",
        required=False,
        default=10,
        help="Number of concurrent workers to use.",
    )
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    return bt.config(parser)


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


def confirm_generation(allocations) -> bool:
    """
    Prompt the user to confirm the deletion of a directory.

    Returns:
        - bool: True if user confirms deletion, False otherwise.
    """
    total_dbs = len(allocations)
    total_size = sum([alloc["n_chunks"] * CHUNK_SIZE for alloc in allocations])
    bt.logging.info(f"Allocations:")
    for alloc in allocations:
        bt.logging.info("\n" + json.dumps(alloc, indent=4))
    bt.logging.info(
        f"Are you sure you want to partition {total_dbs} databases with total size {human_readable_size(total_size)}? (yes/no)"
    )
    response = input()
    return response.lower() in ["yes", "y"]


def human_readable_size(size: int) -> str:
    """
    Convert a size in bytes to a human-readable format.

    Args:
        - size (int): Size in bytes.

    Returns:
        - str: Human-readable size.
    """
    thresholds = [1 << 30, 1 << 20, 1 << 10]  # GB, MB, KB thresholds in bytes
    units = ["GB", "MB", "KB", "bytes"]

    for threshold, unit in zip(thresholds, units):
        if size >= threshold:
            return f"{size / threshold:.2f} {unit}"

    return f"{size} bytes"


def run_rust_generate(alloc, restart=False):
    """
    This function runs a Rust script to generate the data and hashes databases.

    Args:
        - alloc (dict): A dictionary containing allocation details. It includes the path to the database, the number of chunks, the size of each chunk, and the seed for the random number generator.
        - hash (bool): A flag indicating whether to generate a hash database. If True, a hash database is generated. If False, a data database is generated. Default is False.
        - restart (bool): A flag indicating whether to restart the database. If True, the existing database is deleted and a new one is created. If False, the existing database is used. Default is False.

    Returns:
        None
    """
    # Get the path to the database from the allocation details.
    db_path = alloc["path"]

    # If the database directory does not exist, create it.
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))

    # Construct the command to run the Rust script. The command includes the path to the script, the path to the database, the number of chunks, the size of each chunk, and the seed for the random number generator.
    cmd = [
        "./target/release/storer_db_project",
        "--path",
        db_path,
        "--n",
        str(alloc["n_chunks"]),
        "--size",
        str(CHUNK_SIZE),
        "--seed",
        alloc["seed"],
    ]

    # If the hash flag is True, add the "--hash" option to the command.
    if "hash" in alloc and alloc["hash"]:
        cmd.append("--hash")

    # If the restart flag is True, add the "--delete" option to the command. This will delete the existing database before creating a new one.
    if restart:
        cmd.append("--delete")

    bt.logging.debug(cmd)
    # Get the directory containing the Rust script.
    cargo_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "generate_db"
    )

    # Run the command in the cargo directory. The output of the command is not captured.
    result = subprocess.run(cmd, cwd=cargo_directory, capture_output=False, text=True)

    # If there is an error message in the output of the command, log an error message.
    if result.stderr:
        bt.logging.error(f"Failed to generate database: {db_path}")


def generate(
    allocations: typing.List[dict],  # List of allocation details.
    no_prompt=False,  # If True, the function will not prompt for user confirmation. Default is False.
    workers=10,  # The number of concurrent workers to use for generation. Default is 10.
    restart=False,  # If True, the database will be restarted. Default is False.
):
    """
    This function is responsible for generating data and hashes DBs. It uses multi-threading to speed up the process.

    Args:
        - wallet (bt.wallet): This is a wallet object that contains the name and hotkey.
        - allocations (typing.List[dict]): This is a list of dictionaries. Each dictionary contains details about an allocation.
        - no_prompt (bool): If this is set to True, the function will not ask for user confirmation before proceeding. By default, it's set to False.
        - workers (int): This is the number of concurrent workers that will be used for generation. By default, it's set to 10.
        - restart (bool): If this is set to True, the database will be restarted. By default, it's set to False.
    Returns:
        None
    """
    # First, we confirm the allocation step. This is done by calling the confirm_generation function.
    # If the user does not confirm, the program will exit.
    if not no_prompt:
        if not confirm_generation(allocations):
            exit()

    # Finally, we run the generation process. This is done using a ThreadPoolExecutor, which allows us to run multiple tasks concurrently.
    # For each allocation, we submit two tasks to the executor: one for generating the hash, and one for generating the data.
    # If only_hash is set to True, we skip the data generation task.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for alloc in allocations:
            executor.submit(run_rust_generate, alloc, restart)


def verify(data_allocations, hash_allocations):
    """
    Verify the integrity of the generated data and hashes.

    Args:
        - config (bt.config): Configuration object.
        - allocations (list): List of allocation details.
    Returns:
        None
    """

    max_allocs = max(len(data_allocations), len(hash_allocations))
    for data_alloc, hash_allocs in list(
        zip(data_allocations[:max_allocs], hash_allocations[:max_allocs])
    ):
        # Connect to the SQLite databases for data and hashes.
        data_conn = sqlite3.connect(data_alloc["path"])
        hashes_conn = sqlite3.connect(hash_allocs["path"])
        data_cursor = data_conn.cursor()
        hashes_cursor = hashes_conn.cursor()

        i = 0
        while True:
            data_key = str(i)

            # Fetch data from the data database using the current key.
            data_cursor.execute(
                f"SELECT data FROM DB{data_alloc['seed']} WHERE id=?", (data_key,)
            )
            data_value = data_cursor.fetchone()

            # Fetch the corresponding hash from the hashes database.
            hashes_cursor.execute(
                f"SELECT hash FROM DB{hash_allocs['seed']} WHERE id=?", (data_key,)
            )
            stored_hash = hashes_cursor.fetchone()

            # If no data is found for the current key, exit the loop.
            if not data_value:
                break

            # Compute the hash of the fetched data.
            computed_hash = hashlib.sha256(data_value[0].encode("utf-8")).hexdigest()

            # Check if the computed hash matches the stored hash.
            if computed_hash != stored_hash[0]:
                bt.logging.error(
                    f"Hash mismatch for key {i}!, computed hash: {computed_hash}, stored hash: {stored_hash[0]}"
                )
                return
            else:
                bt.logging.success(
                    f"Hash match for key {i}! computed hash: {computed_hash}, stored hash: {stored_hash[0]}"
                )

            # Increment the key for the next iteration.
            i += 1

        # Log the successful verification of the data.
        bt.logging.success(
            f"Verified {data_alloc['path']} with hashes from {hash_allocs['path']}"
        )

        # Close the database connections.
        data_conn.close()
        hashes_conn.close()


def allocate(
    db_root_path: str,  # Path to the data database.
    wallet: bt.wallet,  # Wallet object
    metagraph: bt.metagraph,  # Metagraph object
    threshold: float = 0.0001,  # Threshold for the allocation.
    hash: bool = False,  # If True, the allocation is for a hash database. If False, the allocation is for a data database. Default is False.
) -> typing.List[dict]:
    """
    This function calculates the allocation of space for each hotkey in the metagraph.

    Args:
        - db_path (str): The path to the data database.
        - wallet (bt.wallet): The wallet object containing the name and hotkey.
        - metagraph (bt.metagraph): The metagraph object containing the hotkeys.
        - threshold (float): The threshold for the allocation. Default is 0.0001.

    Returns:
        - list: A list of dictionaries. Each dictionary contains the allocation details for a hotkey.
    """
    # Calculate the path to the wallet database.
    wallet_db_path = os.path.join(db_root_path, wallet.name, wallet.hotkey_str)
    if not os.path.exists(wallet_db_path):
        os.makedirs(wallet_db_path)

    # Calculate the available space in the data database.
    available_space = get_available_space(wallet_db_path)

    # Calculate the filling space based on the available space and the threshold.
    filling_space = available_space * threshold

    # Initialize an empty list to store the allocations.
    allocations = []

    # Iterate over each hotkey in the metagraph.
    for i, hotkey in enumerate(metagraph.hotkeys):
        # Calculate the denominator for the allocation formula.
        denom = (metagraph.S + torch.ones_like(metagraph.S)).sum()

        # Calculate the size of the database for the current hotkey.
        db_size = (((metagraph.S[i] + 1) / denom) * filling_space).item()

        # Calculate the number of chunks for the current hotkey.
        n_chunks = int(db_size / CHUNK_SIZE) + 1

        # Get the miner key from the wallet.
        miner_key = wallet.hotkey.ss58_address

        # Get the validator key from the metagraph.
        validator_key = metagraph.hotkeys[i]

        # Generate the seed for the current hotkey.
        seed = f"{miner_key}{validator_key}"

        # Calculate the path to the database for the current hotkey.
        path = f"{wallet_db_path}/DB-{miner_key}-{validator_key}"

        # Append the allocation details for the current hotkey to the allocations list.
        allocations.append(
            {
                "path": path,
                "n_chunks": n_chunks,
                "seed": seed,
                "hash": hash,
                "miner": miner_key,
                "validator": validator_key,
            }
        )

    # Return the allocations list.
    return allocations


def main(config):
    bt.logging(config=config)
    bt.logging.info(config)
    sub = bt.subtensor(config=config)
    wallet = bt.wallet(config=config)
    metagraph = sub.metagraph(netuid=config.netuid)
    db_root_path = os.path.expanduser(config.db_root_path)
    allocations = allocate(
        db_root_path=db_root_path,
        wallet=wallet,
        metagraph=metagraph,
        threshold=config.threshold,
        hash=config.validator,
    )
    bt.logging.info(f"Allocations: {json.dumps(allocations, indent=4)}")
    generate(
        allocations=allocations,
        no_prompt=config.no_prompt,
        workers=config.workers,
        restart=config.restart,
    )
    if not config.validator:
        verify(allocations, allocations)


if __name__ == "__main__":
    main(get_config())