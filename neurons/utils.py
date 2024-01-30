import os
import tensorage
import bittensor as bt
import subprocess
import requests
import base64
import re

def check_version():
    latest_version = get_version_with_raw()
    current_version = tensorage.__version__

    bt.logging.info(f"Current version: {current_version}")
    bt.logging.info(f"Latest version: {latest_version}")

    if tensorage.version_to_num(current_version) < tensorage.version_to_num(latest_version) and latest_version != None:
        bt.logging.info("Updating to the latest version...")
        current_version = latest_version
        subprocess.run(["git", "reset", "--hard"])
        subprocess.run(["git", "pull"])
        subprocess.run(["pip", "install", "-r", "requirements.txt"])
        subprocess.run(["pip", "install", "-e", "."])
        subprocess.run(["neurons/generate_db/cargo", "build", "--release"])
        os._exit(0)

# Get tensorage version from git repo
def get_version_with_api(line_number: int = 30):
    url = "https://api.github.com/repos/tensorage/tensorage/contents/tensorage/__init__.py"
    response = requests.get(url, timeout=10)
    if not response.ok:
        return None

    content = response.json()['content']
    decoded_content = base64.b64decode(content).decode('utf-8')
    lines = decoded_content.split('\n')
    if line_number > len(lines):
        raise Exception("Line number exceeds file length")

    version_line = lines[line_number - 11]
    version_match = re.search(r'__version__ = "(.*?)"', version_line)
    if not version_match:
        raise Exception("Version information not found in the specified line")

    return version_match.group(1)

def get_version_with_raw(line_number: int = 20):
    # The raw content URL of the file on GitHub
    raw_url = 'https://raw.githubusercontent.com/tensorage/tensorage/main/tensorage/__init__.py'

    # Send an HTTP GET request to the raw content URL
    response = requests.get(raw_url)

    # Check if the request was successful
    if response.status_code == 200:
        content = response.text.split('\n')  # Split the content by new line
        if len(content) >= line_number:
            
            version_match = re.search(r'__version__ = "(.*?)"', content[line_number - 1])
            version_line = content[line_number - 1]

            if not version_match:
                raise Exception("Version information not found in the specified line")
            return version_match.group(1)
        else:
            bt.logging.error(f"The file has only {len(content)} lines.")
    else:
        bt.logging.error(f"Failed to fetch file content. Status code: {response.status_code}")

def validate_min_max_range(value, min_value, max_value):
    """
    Purpose:
        Make sure if value is in range of min_value and max_value.
    """
    min_value = min(min_value, max_value)
    max_value = max(min_value, max_value)

    if value < min_value:
        value = min_value
    elif value > max_value:
        value = max_value
    
    return value
# end def