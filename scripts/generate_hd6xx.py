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
SOURCE_NAME = "Sennheiser HD 6XX"
SOURCE = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/measurements/oratory1990/data/over-ear/Sennheiser%20HD%206XX.csv"
FS_MAP = {"44100": "44", "48000": "48", "96000": "96", "192000": "192"}
EXPECTED = set(FS_MAP.values())

PROFILES = [
    {
        "name": "Sennheiser HD 6XX",
        "id": "sennheiserhd6xx",
        "model": "HD 6XX",
        "extra_args": [],
        "note": "Reference / generator-default smoothing"
    },
    {
        "name": "Sennheiser HD 6XX Hi-Res 2Hz",
        "id": "sennheiserhd6xxhires2hz",
        "model": "HD 6XX Hi-Res 2Hz",
        "extra_args": [
            "--f-res", "2",
            "--window-size", str(1 / 24),
            "--treble-window-size", "1.0",
        ],
        "note": "Experimental: 2 Hz FIR resolution, 1/24-oct main smoothing, 1-oct treble smoothing"
    },
    {
        "name": "Sennheiser HD 6XX Extreme 1Hz",
        "id": "sennheiserhd6xxextreme1hz",
        "model": "HD 6XX Extreme 1Hz",
        "extra_args": [
            "--f-res", "1",
            "--window-size", str(1 / 24),
            "--treble-window-size", "0.5",
        ],
        "note": "Experimental: 1 Hz FIR resolution, 1/24-oct main smoothing, 1/2-oct treble smoothing"
    },
    {
        "name": "Sennheiser HD 6XX Hybrid 1Hz",
        "id": "sennheiserhd6xxhybrid1hz",
        "model": "HD 6XX Hybrid 1Hz",
        "extra_args": [
            "--f-res", "1",
            "--window-size", str(1 / 24),
            "--treble-window-size", "1.0",
        ],
        "note": "Experimental hybrid: Extreme 1 Hz frequency sampling with Hi-Res 1-oct treble smoothing"
    },
]


def sanitize(name):
    return re.sub(r"[\W_]+", "", name).lower()


def ensure_measurement_and_zero_target():
    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    measurement = MEAS_DIR / f"{SOURCE_NAME}.csv"
    if not measurement.exists():
        urllib.request.urlretrieve(SOURCE, measurement)

    target = TARGET_DIR / "1_zero.csv"
    with measurement.open(newline="", encoding="utf-8") as src, target.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["frequency", "raw"])
        for row in reader:
            writer.writerow([row["frequency"], "0.00"])
    return measurement, target


def generate_profile(profile, measurement, target):
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    input_dir = TEMP_IN / "1_open-back"
    input_dir.mkdir(parents=True, exist_ok=True)

    profile_measurement = input_dir / f"{profile['name']}.csv"
    shutil.copy2(measurement, profile_measurement)

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
        *profile["extra_args"],
    ]
    print(f"Generating {profile['name']}: {profile['note']}")
    subprocess.run(cmd, check=True)

    copied = set()
    for wav in TEMP_OUT.rglob("*.wav"):
        m = re.match(r"^(.*?)\s+minimum\s+phase\s+(\d+)\s*Hz\.wav$", wav.name, re.I)
        if not m or sanitize(m.group(1)) != profile["id"]:
            continue
        rate = FS_MAP.get(m.group(2))
        if rate:
            shutil.copy2(wav, REPO_DIR / f"{profile['id']}_1_{rate}.wav")
            copied.add(rate)

    if copied != EXPECTED:
        raise RuntimeError(f"{profile['name']}: expected IRs {sorted(EXPECTED)}, generated {sorted(copied)}")


def main():
    measurement, target = ensure_measurement_and_zero_target()

    for profile in PROFILES:
        generate_profile(profile, measurement, target)

    headphone_list = []
    for profile in PROFILES:
        headphone_list.append({
            "id": profile["id"],
            "type": 1,
            "brandName": ["Sennheiser"],
            "modelName": [profile["model"]],
            "version": 1,
            "noDspOffsetDb": 0.0
        })

    (REPO_DIR / "headphone_list.json").write_text(
        json.dumps(headphone_list, indent=2) + "\n", encoding="utf-8"
    )

    (REPO_DIR / "EXPERIMENTS.md").write_text(
        "# HD 6XX calibration experiments\n\n"
        "All profiles use the same stock Sennheiser HD 6XX measurement from oratory1990 and the same target-neutral PrecisEQ zero target.\n\n"
        "- HD 6XX: reference profile, AutoEq generator defaults.\n"
        "- HD 6XX Hi-Res 2Hz: 2 Hz FIR resolution, 1/24-oct main smoothing, 1-oct treble smoothing.\n"
        "- HD 6XX Extreme 1Hz: 1 Hz FIR resolution, 1/24-oct main smoothing, 1/2-oct treble smoothing.\n"
        "- HD 6XX Hybrid 1Hz: 1 Hz FIR resolution and 1/24-oct main smoothing from Extreme, but the gentler 1-oct treble smoothing from Hi-Res. Designed to test the preferred Extreme low/mid behavior with the preferred Hi-Res top end.\n\n"
        "We tested 1/48-oct main smoothing, but the oratory1990 source sampling is not dense enough for AutoEq's Savitzky-Golay smoother at that window size. 1/24 octave is therefore the practical source-resolution floor for this measurement in AutoEq 4.1.2.\n\n"
        "The listening target remains a separate PrecisEQ in-app stage.\n",
        encoding="utf-8"
    )

    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    print("PrecisEQ HD 6XX reference + experimental repository files generated successfully.")


if __name__ == "__main__":
    main()
