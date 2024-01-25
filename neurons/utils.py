import os
import tensorage
import bittensor as bt
import subprocess

current_version = tensorage.__version__

def check_version():
    latest_version = get_version()
    print(f"Current version: {current_version}")
    print(f"Latest version: {latest_version}")

    if current_version != latest_version and latest_version != None:
        print("Updating to the latest version...")
        current_version = latest_version
        subprocess.run(["git", "reset", "--hard"])
        subprocess.run(["git", "pull"])
        subprocess.run(["pip", "install", "-e", "."])
        os._exit(0)

# Get tensorage version from git repo
def get_version(line_number: int = 31):
    url = "https://api.github.com/repos/tensorage/tensorage/contents/tensorage/__init__.py"
    response = requests.get(url)
    if not response.ok:
        bt.logging.error("Github api call failed")
        return None

    content = response.json()['content']
    decoded_content = base64.b64decode(content).decode('utf-8')
    lines = decoded_content.split('\n')
    if line_number > len(lines):
        raise Exception("Line number exceeds file length")

    version_line = lines[line_number - 1]
    version_match = re.search(r'__version__ = "(.*?)"', version_line)
    if not version_match:
        raise Exception("Version information not found in the specified line")

    return version_match.group(1)

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