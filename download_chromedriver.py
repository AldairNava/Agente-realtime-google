import urllib.request
import json
import zipfile
import os
import shutil

url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
print("Fetching Chrome versions...")
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode('utf-8'))

target_version = "136.0.7103"
found_url = None

for v in data['versions']:
    if target_version in v['version']:
        downloads = v.get('downloads', {}).get('chromedriver', [])
        for d in downloads:
            if d['platform'] == 'win64':
                found_url = d['url']
                print(f"Found match: {v['version']} -> {found_url}")
                break
        if found_url:
            break

if found_url:
    print(f"Downloading from {found_url}...")
    zip_path = "chromedriver_win64.zip"
    urllib.request.urlretrieve(found_url, zip_path)
    print("Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall("temp_driver")
    
    # Locate the chromedriver.exe inside the extracted folder
    for root, dirs, files in os.walk("temp_driver"):
        for file in files:
            if file == "chromedriver.exe":
                src = os.path.join(root, file)
                # Overwrite the existing one in the root folder
                dest = os.path.join(os.getcwd(), "chromedriver.exe")
                shutil.copy2(src, dest)
                print(f"Success! Chromedriver 136 saved to {dest}")
    
    # Cleanup
    os.remove(zip_path)
    shutil.rmtree("temp_driver")
else:
    print("Could not find chromedriver for version 136.0.7103")
