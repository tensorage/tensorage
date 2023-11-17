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
import bittensor as bt

# Custom modules
import copy
import hashlib
import sqlite3
import secrets
from tqdm import tqdm

# import this repo
import storage
import allocate

LIMIT_LOOP_COUNT = 3 # Maximum loop_count for every loop
CHUNK_STORE_COUNT = 1 # Number of chunks to store
CHUNK_SIZE = 1 << 22    # 1 MB
MIN_N_CHUNKS = 1 << 8  # the minimum number of chunks a miner should provide at least is 1GB (CHUNK_SIZE * MIN_N_CHUNKS)
TB_NAME = "saved_data"

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

    # Return the parsed config.
    return config

# Create a database to store the given file
def create_database_for_file(db_name):
    db_base_path = f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/data"
    if not os.path.exists(db_base_path):
        os.makedirs(db_base_path, exist_ok=True)

    conn = sqlite3.connect(f"{db_base_path}/{db_name}.db")
    cursor = conn.cursor()
    
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {TB_NAME} (chunk_id INTEGER PRIMARY KEY, miner_hotkey TEXT, miner_key INTEGER)")
    conn.close()

# Save the chunk(index : chunk_number) to db_name
def save_chunk_location(db_name, chunk_number, store_resp_list):
    conn = sqlite3.connect(f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/data/{db_name}.db")
    cursor = conn.cursor()

    for store_resp in store_resp_list:
        cursor.execute(f"INSERT INTO {TB_NAME} (chunk_id, miner_hotkey, miner_key) VALUES (?, ?, ?)", (chunk_number, store_resp['hotkey'], store_resp['key']))
    conn.commit()
    conn.close()

# Update the hash value of miner table
def update_miner_hash(validator_hotkey, store_resp_list):
    for store_resp in store_resp_list:
        miner_hotkey = store_resp['hotkey']
        db_path = f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/DB-{miner_hotkey}-{validator_hotkey}"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        update_request = f"UPDATE DB{miner_hotkey}{validator_hotkey} SET hash = ? where id = ?"
        cursor.execute(update_request, (store_resp['hash'], store_resp['key']))
        conn.commit()
        conn.close()

# Hash the given data
def hash_data(data):
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.digest()

# Generate random hash string
def generate_random_hash_str():
    random_bytes = secrets.token_bytes(32)  # 32 bytes for SHA-256
    hashed = hashlib.sha256(random_bytes).hexdigest()
    return str(hashed)

# Retrieve the file
def retrieve_file(metagraph, dendrite, validator_hotkey, db_name, output_filename):
    db_path = f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/data/{db_name}.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM {TB_NAME}")
    rows = cursor.fetchall()

    chunk_size = max(rows, key=lambda obj: obj[0])[0] + 1
    
    hotkey_axon_dict = {}
    for axon in metagraph.axons:
        hotkey_axon_dict[axon.hotkey] = axon

    with open(output_filename, 'wb') as output_file:
        for id in range(chunk_size):
            cursor.execute(f"SELECT * FROM {TB_NAME} where chunk_id = {id}")
            rows = cursor.fetchall()
            hotkey_list = [row[1] for row in rows]
            key_list = {row[1]:row[2] for row in rows}
            axons_list = [hotkey_axon_dict[hotkey] for hotkey in hotkey_list]

            miner_hotkey = axons_list[0].hotkey
            db = sqlite3.connect( f"{config.db_root_path}/{config.wallet.name}/{config.wallet.hotkey}/DB-{miner_hotkey}-{validator_hotkey}")
            validation_hash = (
                db.cursor()
                .execute(
                    f"SELECT hash FROM DB{miner_hotkey}{validator_hotkey} WHERE id=?", (key_list[miner_hotkey],)
                )
                .fetchone()[0]
            )
            db.close()
            
            chunk_data = ''
            loop_count = 0
            while not chunk_data and loop_count < LIMIT_LOOP_COUNT:
                loop_count = loop_count + 1
                retrieve_response = dendrite.query(
                    axons_list,
                    storage.protocol.Retrieve(key_list = key_list),
                    deserialize=True,
                )
                for index, retrieve_resp in enumerate(retrieve_response):
                    if retrieve_resp and hash_data(retrieve_resp.encode('utf-8')) == validation_hash:
                        chunk_data = retrieve_resp
                        break
            if not chunk_data:
                return {"status":False, "error_msg":f"Chunk_{id} is missing!"}
            else:
                hex_representation = chunk_data.split("'")[1]
                clean_hex_representation = ''.join(c for c in hex_representation if c in '0123456789abcdefABCDEF')
                # Convert the cleaned hexadecimal representation back to bytes
                chunk_data = bytes.fromhex(clean_hex_representation)
                output_file.write(chunk_data)
    conn.close()
    return {"status":True, "file_path":output_filename}

#Store the provided file
def store_file(metagraph, dendrite, validator_hotkey, file_path, chunk_size):
    db_name = generate_random_hash_str()
    create_database_for_file(db_name)
    #Number of miners
    axon_count = len(metagraph.axons)
    with open(file_path, 'rb') as infile:
        chunk_number = 0
        while True:
            chunk = infile.read(chunk_size)
            if not chunk:
                break  # reached end of file
            hex_representation = ''.join([f'\\x{byte:02x}' for byte in chunk])

            # Construct the desired string
            chunk = f"b'{hex_representation}'"
            store_resp_list = []
            index_list = []
            loop_count = 0
            while len(store_resp_list) < CHUNK_STORE_COUNT and loop_count < LIMIT_LOOP_COUNT:
                loop_count = loop_count + 1
                #Generate list of miners who will receive chunk, count: CHUNK_STORE_COUNT
                store_count = min(CHUNK_STORE_COUNT * 2, axon_count - len(index_list))
                for i in range(store_count):
                    while True:
                        chunk_i = random.randint(0, axon_count - 1)
                        if chunk_i in index_list:
                            continue
                        index_list.append(chunk_i)
                        break
                
                #Transfer the chunk to selected miners
                axons_list = []
                for index in index_list:
                    axons_list.append(metagraph.axons[index])

                store_response = dendrite.query(
                    axons_list,
                    storage.protocol.Store(data = chunk),
                    deserialize=True,
                )
                
                for index, key in enumerate(store_response):
                    if key != -1: #Miner saved the chunk
                        store_resp_list.append({"key": key, "hotkey": axons_list[index].hotkey, "hash": hash_data(chunk.encode('utf-8'))})

            if not store_resp_list:
                return {"status": False, "error_msg" : "NOT ENOUGH SPACE"}
            
            #Save the key to db
            save_chunk_location(db_name, chunk_number, store_resp_list)
            
            #Update the hash value of the key that miner responded
            update_miner_hash(validator_hotkey, store_resp_list)

            chunk_number += 1
    return {"status": True, "db_name":db_name}

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

    #Experiment store and retrieve
    file_path = "/root/tensorage/node-v20.9.0-x64.msi"
    store_result = store_file(metagraph, dendrite, wallet.hotkey.ss58_address, file_path, CHUNK_SIZE)

    if store_result['status'] == True:
        db_name = store_result['db_name']
        output_filename = "output"
        retrieve_result = retrieve_file(metagraph, dendrite, wallet.hotkey.ss58_address, db_name, output_filename)
        if retrieve_result['status'] == True:
            bt.logging.info(f"File successfully retrieved into : {retrieve_result['file_path']}")
        else:
            bt.logging.info(f"Retrieving failed with err : {retrieve_result['error_msg']}")
    else:
        bt.logging.info(f"Storing failed with err : {store_result['error_msg']}")

# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    # Parse the configuration.
    config = get_config()
    # Run the main function.
    main(config)