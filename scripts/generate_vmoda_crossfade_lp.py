import csv
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
MEAS_DIR = ROOT / "measurements" / "2_closed-back"
REPO_DIR = ROOT / "RepositoryFiles"
TARGET_DIR = ROOT / "targets"
TEMP_IN = ROOT / "temp_in_vmoda_lp"
TEMP_OUT = ROOT / "temp_out_vmoda_lp"
CACHE_DIR = ROOT / "temp_vmoda_lp_sources"
FS_MAP = {"44100": "44", "48000": "48", "96000": "96", "192000": "192"}
EXPECTED = set(FS_MAP.values())

PROFILE_ID = "vmodacrossfadelp"
BRAND = "V-MODA"
MODEL = "Crossfade LP"
TYPE = 2  # closed-back over-ear in PrecisEQ repository format

AUTOEQ_RAW = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master"
RESULT_DIR = "Innerfidelity/over-ear/V-MODA Crossfade LP"
RESULT_NAME = "V-MODA Crossfade LP"
TARGET_NAME = "HMS II.3 Harman over-ear 2018 without bass.csv"
TARGET_URL = AUTOEQ_RAW + "/targets/" + urllib.parse.quote(TARGET_NAME)


def download(url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "preciseq-headphone-calibration"})
    with urllib.request.urlopen(req, timeout=60) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f)


def lowshelf_db(freq, fs=48000.0, fc=105.0, gain=6.0, q=0.7):
    # RBJ low-shelf response, matching AutoEq's standard 6 dB over-ear bass shelf.
    A = 10 ** (gain / 40.0)
    w0 = 2.0 * np.pi * fc / fs
    alpha = np.sin(w0) / (2.0 * q)
    two_sqrt_A_alpha = 2.0 * np.sqrt(A) * alpha
    c = np.cos(w0)
    b0 = A * ((A + 1) - (A - 1) * c + two_sqrt_A_alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * c)
    b2 = A * ((A + 1) - (A - 1) * c - two_sqrt_A_alpha)
    a0 = (A + 1) + (A - 1) * c + two_sqrt_A_alpha
    a1 = -2 * ((A - 1) + (A + 1) * c)
    a2 = (A + 1) + (A - 1) * c - two_sqrt_A_alpha
    w = 2.0 * np.pi * freq / fs
    z = np.exp(-1j * w)
    h = (b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)
    return 20.0 * np.log10(np.maximum(np.abs(h), 1e-12))


def load_result_target():
    path = CACHE_DIR / TARGET_NAME
    if not path.exists():
        download(TARGET_URL, path)
    f, g = [], []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            f.append(float(row["frequency"]))
            g.append(float(row["raw"]))
    f = np.asarray(f)
    g = np.asarray(g)
    # Current AutoEq recommendation for Innerfidelity over-ear is the HMS II.3
    # Harman over-ear baseline with the standard 6 dB / 105 Hz / Q 0.7 bass shelf.
    g = g + lowshelf_db(f)
    return f, g


def result_ir_url():
    rel = f"results/{RESULT_DIR}/{RESULT_NAME} minimum phase 48000Hz.wav"
    return AUTOEQ_RAW + "/" + urllib.parse.quote(rel, safe="/")


def reconstruct_measurement(target_f, target_db):
    src_wav = CACHE_DIR / "vmoda_crossfade_lp_autoeq_48k.wav"
    if not src_wav.exists():
        download(result_ir_url(), src_wav)

    x, fs = sf.read(src_wav, dtype="float64", always_2d=False)
    if x.ndim > 1:
        x = x[:, 0]
    if fs != 48000:
        raise RuntimeError(f"Expected 48 kHz AutoEq IR, got {fs}")

    nfft = max(131072, 1 << int(np.ceil(np.log2(max(len(x), 2)))))
    H = np.fft.rfft(x, n=nfft)
    hf = np.fft.rfftfreq(nfft, 1.0 / fs)
    hdb = 20.0 * np.log10(np.maximum(np.abs(H), 1e-12))

    # Published AutoEq correction ~= result target - measured response + constant preamp.
    # Reconstruct the relative stock FR and remove the unknown constant at 1 kHz.
    corr_db = np.interp(target_f, hf, hdb)
    raw = target_db - corr_db
    raw -= np.interp(1000.0, target_f, raw)

    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    out = MEAS_DIR / f"{BRAND} {MODEL} (Innerfidelity reconstructed).csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frequency", "raw"])
        for f, db in zip(target_f, raw):
            if 20.0 <= f <= 20000.0:
                w.writerow([f"{f:.2f}", f"{db:.5f}"])
    return out


def make_zero_target(reference_csv):
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / "2_zero.csv"
    with reference_csv.open(newline="", encoding="utf-8") as src, target.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["frequency", "raw"])
        for row in reader:
            writer.writerow([row["frequency"], "0.00"])
    return target


def sanitize(name):
    return re.sub(r"[\W_]+", "", name).lower()


def generate_ir(measurement, target):
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    input_dir = TEMP_IN / "2_closed-back"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_name = f"{BRAND} {MODEL}.csv"
    shutil.copy2(measurement, input_dir / input_name)

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
        "--f-res", "2",
        "--window-size", str(1 / 24),
        "--treble-window-size", "1.0",
    ]
    print(f"Generating {BRAND} {MODEL}")
    subprocess.run(cmd, check=True)

    copied = set()
    expected_name = sanitize(f"{BRAND} {MODEL}")
    for wav in TEMP_OUT.rglob("*.wav"):
        m = re.match(r"^(.*?)\s+minimum\s+phase\s+(\d+)\s*Hz\.wav$", wav.name, re.I)
        if not m or sanitize(m.group(1)) != expected_name:
            continue
        rate = FS_MAP.get(m.group(2))
        if rate:
            REPO_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav, REPO_DIR / f"{PROFILE_ID}_{TYPE}_{rate}.wav")
            copied.add(rate)
    if copied != EXPECTED:
        raise RuntimeError(f"Expected IRs {sorted(EXPECTED)}, generated {sorted(copied)}")


def update_headphone_list():
    path = REPO_DIR / "headphone_list.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries = [e for e in entries if e.get("id") != PROFILE_ID]
    entries.append({
        "id": PROFILE_ID,
        "type": TYPE,
        "brandName": [BRAND],
        "modelName": [MODEL],
        "version": 1,
        "noDspOffsetDb": 0.0,
    })
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target_f, target_db = load_result_target()
    measurement = reconstruct_measurement(target_f, target_db)
    zero = make_zero_target(measurement)
    generate_ir(measurement, zero)
    update_headphone_list()
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
    print(f"Generated {BRAND} {MODEL} PrecisEQ profile.")


if __name__ == "__main__":
    main()
