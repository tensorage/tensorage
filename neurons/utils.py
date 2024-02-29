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
import re
import requests
import subprocess
import bittensor as bt

# Import this repository.
import tensorage


def version_str_to_num(version: str) -> int:
    """
    Convert version number as string to number (1.2.0 => 120).
    Multiply the first version number by one hundred, the second by ten, and the last by one. Finally add them all.

    Args:
        - version (str): The version number as string.

    Returns:
        - int: Version number as int.
    """
    version_split = version.split(".")
    return (100 * int(version_split[0])) + (10 * int(version_split[1])) + int(version_split[2])


def check_version():
    """
    Check current version of the module on GitHub. If it is greater than the local version, download and update the module.
    """
    latest_version = get_latest_version()
    current_version = tensorage.__version__

    # If version in GitHub is greater, update module.
    if version_str_to_num(current_version) < version_str_to_num(latest_version) and latest_version is not None:
        bt.logging.info("Updating to the latest version...")
        subprocess.run(["git", "reset", "--hard"], cwd=os.getcwd())
        subprocess.run(["git", "pull"], cwd=os.getcwd())
        subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=os.getcwd())
        subprocess.run(["pip", "install", "-e", "."], cwd=os.getcwd())
        subprocess.run(["cargo", "build", "--release"], cwd=os.path.join(os.getcwd(), "neurons/generate_db"))
        exit(0)


def get_latest_version() -> str:
    """
    Retrieve latest version number from GitHub repository..

    Returns:
        - str: Version number as string (X.X.X).
    """

    # The raw content URL of the file on GitHub.
    url = 'https://raw.githubusercontent.com/tensorage/tensorage/main/tensorage/__init__.py'

    # Send an HTTP GET request to the raw content URL.
    response = requests.get(url)

    # Check if the request was successful.
    if response.status_code == 200:
        version_match = re.search(r'__version__ = "(.*?)"', response.text)

        if not version_match:
            raise Exception("Version information not found in the specified line")

        return version_match.group(1)

    else:
        bt.logging.error(f"Failed to fetch file content. Status code: {response.status_code}")
