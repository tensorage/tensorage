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
import hashlib
import sqlite3
import argparse
import traceback
import threading
import typing
import bittensor as bt
import multiprocessing

# Import this repo.
import allocate
import tensorage
from utils import check_version, is_validator

FAILED_KEY = -1
STEP_TIME = 60
MIN_SIZE_IN_GB = 100


def get_config() -> bt.config:
    """
    Parse params and preparare config object.

    Returns:
        - bittensor.config: Nested config object created from parser arguments.
    """
    # Create parser and add all params.
    parser = argparse.ArgumentParser(description="Configure the miner.")
    parser.add_argument(
        "--db_root_path", default="~/tensorage-db", help="Path to the data database."
    )
    parser.add_argument(
        "--size_in_gb",
        type=float,
        default=MIN_SIZE_IN_GB,
        required=False,
        help="Size of path to fill.",
    )
    parser.add_argument(
        "--seconds_per_reallocate",
        type=int,
        default=600,
        help="The number of seconds between reallocations.",
    )
    parser.add_argument(
        "--workers",
        default=multiprocessing.cpu_count(),
        type=int,
        help="The number of concurrent workers to use for hash generation.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        default=False,
        help="If set, the validator will reallocate its DB entirely.",
    )

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
    config.full_path = os.path.join(
        os.path.expanduser(config.logging.logging_dir),
        config.wallet.name,
        config.wallet.hotkey,
        f"netuid{config.netuid}",
        "miner",
    )
    if not os.path.exists(config.full_path):
        os.makedirs(config.full_path, exist_ok=True)

    return config


def main(config: bt.config):
    """
    Main function.

    Args:
        - config (bittensor.config): Nested config object created from parser arguments.
    """
    # Set up logging with the provided configuration and directory.
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info(
        f"Running miner for subnet: {config.netuid} on network: {config.subtensor.chain_endpoint} with config:"
    )

    # The wallet holds the cryptographic key pairs for the miner.
    wallet = bt.wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")

    wallet = bt.wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")

    # The subtensor is our connection to the Bittensor blockchain.
    subtensor = bt.subtensor(config=config)
    bt.logging.info(f"Subtensor: {subtensor}")

    # The metagraph holds the state of the network, letting us know about other miners.
    metagraph = subtensor.metagraph(config.netuid)
    bt.logging.info(f"Metagraph: {metagraph}")

    # Check if hotkey is registered.
    my_subnet_uid = 0
    if wallet.hotkey.ss58_address in metagraph.hotkeys:
        # Each miner gets a unique identity (UID) in the network for differentiation.
        my_subnet_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        bt.logging.info(f"Running miner on uid: {my_subnet_uid}")

    else:
        bt.logging.error(
            f"\nYour miner: {wallet} is not registered to chain connection: {subtensor} \nRun btcli s register and try again."
        )
        exit()

    # Create DBs. Generate the data allocations.
    allocations = {
        a["hotkey"]: a
        for a in allocate.allocate(
            db_root_path=config.db_root_path,
            wallet=wallet,
            size_in_gb=config.size_in_gb,
            metagraph=metagraph,
            restart=config.restart,
        )
    }
    thread_generation = threading.Thread(
        target=allocate.generate,
        args=(list(allocations.values()), True, False, config.workers),
    )
    thread_generation.start()

    # Connect to SQLite databases.
    local_storage = threading.local()

    def close_db_connections():
        """
        Iterate over all connections in local_storage and close them.
        """
        for attr in dir(local_storage):
            if attr.startswith("connection_"):
                connection = getattr(local_storage, attr)
                connection.close()
                bt.logging.info(f"Closed database connection: {attr}")

    def get_db_connection(allocation: dict) -> sqlite3.Connection:
        """
        Check if we have a connection for this DB.

        Args:
            - allocation (dict): A dictionary containing allocation details.

        Returns:
            - sqlite3.Connection: SQLite connection.
        """
        if not hasattr(local_storage, f"connection_{allocation['hotkey']}"):
            bt.logging.info(
                f"Connecting to database under path: {allocation['db_path']}"
            )
            setattr(
                local_storage,
                f"connection_{allocation['hotkey']}",
                sqlite3.connect(allocation["db_path"]),
            )
        return getattr(local_storage, f"connection_{allocation['hotkey']}")

    async def ping(synapse: tensorage.protocol.Ping) -> tensorage.protocol.Ping:
        """
        Answer the call indicating that it's a miner and its version.

        Args:
            - synapse (tensorage.protocol.Ping): Synapse object with ping data.

        Returns:
            - tensorage.protocol.Ping: Synapse object with ping data.
        """
        synapse.data = f"miner-{tensorage.__version__}"
        return synapse

    async def retrieve(
        synapse: tensorage.protocol.Retrieve,
    ) -> tensorage.protocol.Retrieve:
        """
        Listen to a validator's call and respond with the key data requested.

        Args:
            - synapse (tensorage.protocol.Retrieve): Synapse object with retrieve data.

        Returns:
            - tensorage.protocol.Retrieve: Synapse object with retrieve data.
        """
        # blacklist requests from non-validator hotkeys
        is_blacklisted, _ = blacklist(synapse)
        if is_blacklisted:
            return None

        try:
            bt.logging.info(
                f"Got RETRIEVE request for key: {synapse.key} from dendrite: {synapse.dendrite.hotkey}"
            )

            # Connect to SQLite databases
            db = get_db_connection(allocations[synapse.dendrite.hotkey])
            cursor = db.cursor()

            # Fetch data from SQLite databases
            cursor.execute(
                f"SELECT data FROM DB{wallet.hotkey.ss58_address}{synapse.dendrite.hotkey} WHERE id = {synapse.key}"
            )
            data_value = cursor.fetchone()

            # Set data to None if key not found
            if data_value:
                synapse.data = data_value[0]
                bt.logging.success(f"Found data for key {synapse.key}!")

            else:
                synapse.data = None
                bt.logging.error(f"Data not found for key {synapse.key}!")

        except Exception as e:
            bt.logging.debug(f"Error retrieving data from db: {e}")

        return synapse

    async def store(synapse: tensorage.protocol.Store) -> tensorage.protocol.Store:
        """
        Listen to a validator's call and save the data they send.

        Args:
            - synapse (tensorage.protocol.Store): Synapse object with store data.

        Returns:
            - tensorage.protocol.Store: Synapse object with store data.
        """
        is_blacklisted, _ = blacklist(synapse)
        if is_blacklisted:
            return None

        try:
            # Connect to SQLite DB and insert data into SQLite DB.
            db = get_db_connection(allocations[synapse.dendrite.hotkey])
            db.cursor().execute(
                f"UPDATE DB{wallet.hotkey.ss58_address}{synapse.dendrite.hotkey} SET data = {synapse.data}, hash = {hash_data(synapse.data.encode('utf-8'))} WHERE id = {synapse.key}"
            )
            db.commit()

        except Exception as e:
            bt.logging.error(f"Error storing data to db: {e}")

        # Return
        bt.logging.success(f"Stored data for key {synapse.key}!")
        return synapse

    # Blacklisting
    def blacklist(synapse: bt.Synapse) -> typing.Tuple[bool, str]:
        # Ignore requests from un-registered entities.
        if synapse.dendrite.hotkey not in metagraph.hotkeys:
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        if not is_validator(metagraph, synapse.dendrite.hotkey):
            bt.logging.warning(
                f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Non-validator hotkey"

        bt.logging.trace(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, "Hotkey recognized!"

    # The axon handles request processing, allowing miners to listen this process requests.
    axon = bt.axon(config=config, wallet=wallet)
    bt.logging.info(f"Axon {axon}")

    # Attach determiners which functions are called when servicing a request.
    bt.logging.info(f"Attaching functions to axon.")
    axon.attach(ping).attach(retrieve).attach(store)

    # Serve passes the axon information to the network + netuid we are hosting on. This will auto-update if the axon port of external ip have changed.
    bt.logging.info(
        f"Serving axon 'ping','retrieve' and 'store' on network: {config.subtensor.chain_endpoint} with netuid: {config.netuid}"
    )
    axon.serve(netuid=config.netuid, subtensor=subtensor)

    # Start starts the miner's axon, making it active on the network.
    bt.logging.info(f"Starting axon server on port: {config.axon.port}")
    axon.start()

    # The main mining loop.
    step = 0
    bt.logging.info("🚀 Starting miner loop.")
    while True:
        try:
            # Periodically update our knowledge of the network graph.
            metagraph = subtensor.metagraph(config.netuid)
            bt.logging.info(
                f"Step:{step} | "
                f"Block:{metagraph.block.item()} | "
                f"Stake:{metagraph.S[my_subnet_uid]} | "
                f"Rank:{metagraph.R[my_subnet_uid]} | "
                f"Trust:{metagraph.T[my_subnet_uid]} | "
                f"Consensus:{metagraph.C[my_subnet_uid] } | "
                f"Incentive:{metagraph.I[my_subnet_uid]} | "
                f"Emission:{metagraph.E[my_subnet_uid]}"
            )

            # If the allocation is not working and it is time to update it, the allocation process is launched again.
            if (
                not thread_generation.is_alive()
                and step % int(config.seconds_per_reallocate / STEP_TIME) == 0
            ):
                bt.logging.info(f"Reallocating ...")

                # Update allocations if hotkeys change.
                for hotkey in list(set(allocations.keys()) - set(metagraph.hotkeys)):
                    bt.logging.info(f"✨ Found new hotkey. Old hokey: {hotkey}.")

                    # Close DB connection.
                    if hasattr(local_storage, f"connection_{hotkey}"):
                        connection = getattr(local_storage, f"connection_{hotkey}")
                        connection.close()
                        delattr(local_storage, f"connection_{hotkey}")
                        bt.logging.info(
                            f"Closed database connection: connection_{hotkey}"
                        )

                    # Delete old DB file.
                    os.remove(allocations[hotkey]["db_path"])

                allocations = {
                    a["hotkey"]: a
                    for a in allocate.allocate(
                        db_root_path=config.db_root_path,
                        wallet=wallet,
                        size_in_gb=config.size_in_gb,
                        metagraph=metagraph,
                    )
                }
                thread_generation = threading.Thread(
                    target=allocate.generate,
                    args=(list(allocations.values()), True, False, config.workers),
                )
                thread_generation.start()

            step += 1
            time.sleep(STEP_TIME)

        # If we encounter an unexpected error, log it for debugging.
        except RuntimeError as e:
            bt.logging.error(e)
            traceback.print_exc()

        # If someone intentionally stops the miner, it'll safely terminate operations.
        except KeyboardInterrupt:
            axon.stop()
            close_db_connections()  # Close all db connections
            bt.logging.info("Keyboard interrupt detected. Exiting miner.")
            exit()

        # Check version and restart PM2 if it's upgraded.
        check_version()


# The main function parses the configuration and runs the miner.
if __name__ == "__main__":
    # Check version and restart PM2 if it's upgraded.
    check_version()

    # Parse the configuration.
    config = get_config()
    bt.logging.info(config)

    # Run the main function.
    main(config)
