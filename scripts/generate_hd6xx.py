import csv
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEAS_DIR = ROOT / "measurements" / "1_open-back"
REPO_DIR = ROOT / "RepositoryFiles"
TARGET_DIR = ROOT / "targets"
TEMP_IN = ROOT / "temp_in"
TEMP_OUT = ROOT / "temp_out"
NAME = "Sennheiser HD 6XX"
HP_ID = "sennheiserhd6xx"
SOURCE = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/measurements/oratory1990/data/over-ear/Sennheiser%20HD%206XX.csv"


def main():
    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    measurement = MEAS_DIR / f"{NAME}.csv"
    if not measurement.exists():
        urllib.request.urlretrieve(SOURCE, measurement)

    target = TARGET_DIR / "1_zero.csv"
    with measurement.open(newline="", encoding="utf-8") as src, target.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["frequency", "raw"])
        for row in reader:
            writer.writerow([row["frequency"], "0.00"])

    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    input_dir = TEMP_IN / "1_open-back"
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(measurement, input_dir / measurement.name)

    cmd = [
        sys.executable, "-m", "autoeq",
        "--input-dir", str(TEMP_IN),
        "--output-dir", str(TEMP_OUT),
        "--target", str(target),
        "--fs", "44100,48000,96000,192000",
        "--convolution-eq",
        "--phase", "minimum",
        "--bit-depth", "32",
        "--preamp", "-11.8",
    ]
    subprocess.run(cmd, check=True)

    fs_map = {"44100": "44", "48000": "48", "96000": "96", "192000": "192"}
    copied = set()
    for wav in TEMP_OUT.rglob("*.wav"):
        m = re.match(r"^(.*?)\s+minimum\s+phase\s+(\d+)\s*Hz\.wav$", wav.name, re.I)
        if not m:
            continue
        if re.sub(r"[\W_]+", "", m.group(1)).lower() != HP_ID:
            continue
        rate = fs_map.get(m.group(2))
        if rate:
            shutil.copy2(wav, REPO_DIR / f"{HP_ID}_1_{rate}.wav")
            copied.add(rate)

    expected = {"44", "48", "96", "192"}
    if copied != expected:
        raise RuntimeError(f"Expected IRs {sorted(expected)}, generated {sorted(copied)}")

    headphone_list = [{
        "id": HP_ID,
        "type": 1,
        "brandName": ["Sennheiser"],
        "modelName": ["HD 6XX"],
        "version": 1,
        "noDspOffsetDb": 0.0
    }]
    (REPO_DIR / "headphone_list.json").write_text(json.dumps(headphone_list, indent=2) + "\n", encoding="utf-8")

    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    print("PrecisEQ HD 6XX repository files generated successfully.")


if __name__ == "__main__":
    main()
