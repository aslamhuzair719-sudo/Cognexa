import subprocess
import json
import os

EXIFTOOL = r"C:\Tools\exiftool.exe"


def get_metadata(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return None

    result = subprocess.run(
        [EXIFTOOL, "-json", file_path],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("ExifTool Error:")
        print(result.stderr)
        return None

    return json.loads(result.stdout)[0]


def test_metadata():
    file_path = r"C:\Users\syedh\Desktop\Request-1\payslips\1.png"

    metadata = get_metadata(file_path)

    if metadata is None:
        return

    print(json.dumps(metadata, indent=4))


if __name__ == "__main__":
    test_metadata()