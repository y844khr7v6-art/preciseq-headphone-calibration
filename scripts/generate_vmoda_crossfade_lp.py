import csv
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEAS_DIR = ROOT / "measurements" / "2_closed-back"
REPO_DIR = ROOT / "RepositoryFiles"
TARGET_DIR = ROOT / "targets"
TEMP_IN = ROOT / "temp_in_vmoda_lp"
TEMP_OUT = ROOT / "temp_out_vmoda_lp"

SOURCE_NAME = "V-MODA Crossfade LP"
SOURCE = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/measurements/Innerfidelity/data/over-ear/V-MODA%20Crossfade%20LP.csv"

FS_MAP = {"44100": "44", "48000": "48", "96000": "96", "192000": "192"}
EXPECTED = set(FS_MAP.values())

PROFILE_ID = "vmodacrossfadelp"
BRAND = "V-MODA"
MODEL = "Crossfade LP"
TYPE = 2  # closed-back over-ear in PrecisEQ repository format
VERSION = 2  # v2 replaces the earlier reconstructed profile with the raw Innerfidelity measurement


def sanitize(name):
    return re.sub(r"[\W_]+", "", name).lower()


def ensure_measurement_and_zero_target():
    """Mirror the HD 6XX import path: raw measurement CSV -> zero target."""
    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    measurement = MEAS_DIR / f"{SOURCE_NAME}.csv"
    # Always refresh from the canonical raw Innerfidelity CSV so no reconstructed
    # or target-derived data can silently survive in this profile.
    urllib.request.urlretrieve(SOURCE, measurement)

    target = TARGET_DIR / "2_zero.csv"
    with measurement.open(newline="", encoding="utf-8") as src, target.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["frequency", "raw"])
        for row in reader:
            writer.writerow([row["frequency"], "0.00"])

    return measurement, target


def generate_profile(measurement, target):
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)

    input_dir = TEMP_IN / "2_closed-back"
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(measurement, input_dir / f"{SOURCE_NAME}.csv")

    # Same target-neutral convolution workflow as the HD 6XX import. The only
    # required repository-format difference is type/directory = closed-back (2).
    # User-requested FIR frequency resolution is 1 Hz.
    cmd = [
        sys.executable,
        "-m",
        "autoeq",
        "--input-dir",
        str(TEMP_IN),
        "--output-dir",
        str(TEMP_OUT),
        "--target",
        str(target),
        "--fs",
        "44100,48000,96000,192000",
        "--convolution-eq",
        "--phase",
        "minimum",
        "--bit-depth",
        "32",
        "--preamp",
        "-11.8",
        "--f-res",
        "1",
        "--window-size",
        str(1 / 24),
        "--treble-window-size",
        "1.0",
    ]

    print(
        "Generating V-MODA Crossfade LP from the raw Innerfidelity measurement: "
        "1 Hz FIR resolution, 1/24-oct main smoothing, 1-oct treble smoothing"
    )
    subprocess.run(cmd, check=True)

    copied = set()
    expected_name = sanitize(SOURCE_NAME)
    for wav in TEMP_OUT.rglob("*.wav"):
        m = re.match(r"^(.*?)\s+minimum\s+phase\s+(\d+)\s*Hz\.wav$", wav.name, re.I)
        if not m or sanitize(m.group(1)) != expected_name:
            continue
        rate = FS_MAP.get(m.group(2))
        if rate:
            shutil.copy2(wav, REPO_DIR / f"{PROFILE_ID}_{TYPE}_{rate}.wav")
            copied.add(rate)

    if copied != EXPECTED:
        raise RuntimeError(
            f"{SOURCE_NAME}: expected IRs {sorted(EXPECTED)}, generated {sorted(copied)}"
        )


def update_headphone_list():
    path = REPO_DIR / "headphone_list.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries = [e for e in entries if e.get("id") != PROFILE_ID]
    entries.append(
        {
            "id": PROFILE_ID,
            "type": TYPE,
            "brandName": [BRAND],
            "modelName": [MODEL],
            "version": VERSION,
            "noDspOffsetDb": 0.0,
        }
    )
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main():
    measurement, target = ensure_measurement_and_zero_target()
    generate_profile(measurement, target)
    update_headphone_list()

    # Remove the obsolete reconstruction file if it exists from the previous method.
    obsolete = MEAS_DIR / f"{BRAND} {MODEL} (Innerfidelity reconstructed).csv"
    if obsolete.exists():
        obsolete.unlink()

    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    print("Generated raw-measurement V-MODA Crossfade LP PrecisEQ profile successfully.")


if __name__ == "__main__":
    main()
