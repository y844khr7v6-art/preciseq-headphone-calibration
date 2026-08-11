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
MEAS_DIR = ROOT / "measurements" / "0_in-ear"
REPO_DIR = ROOT / "RepositoryFiles"
TARGET_DIR = ROOT / "targets"
TEMP_IN = ROOT / "temp_in_app2"
TEMP_OUT = ROOT / "temp_out_app2"
CACHE_DIR = ROOT / "temp_app2_sources"
FS_MAP = {"44100": "44", "48000": "48", "96000": "96", "192000": "192"}
EXPECTED = set(FS_MAP.values())
AUTOEQ_RAW = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master"
AUTOEQ_TARGET_URL = AUTOEQ_RAW + "/targets/AutoEq%20in-ear.csv"

# These are all currently indexed AirPods Pro 2 measurements in AutoEq that
# expose generated result IRs. Crinacle's raw source files are indexed but not
# redistributed, so we reconstruct a relative FR from AutoEq's published
# correction IR and the exact AutoEq in-ear target. Constant gain is removed at
# 1 kHz before feeding the reconstructed FR back to AutoEq for a zero-target IR.
PROFILES = [
    ("appleairpodspro2anc", "AirPods Pro 2 ANC", "crinacle/711 in-ear/Apple AirPods Pro 2 (ANC mode)", "Apple AirPods Pro 2 (ANC mode)"),
    ("appleairpodspro2anc51db", "AirPods Pro 2 ANC 51 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (51dB + ANC)", "Apple AirPods Pro 2 (51dB + ANC)"),
    ("appleairpodspro2anc56db", "AirPods Pro 2 ANC 56 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (56dB + ANC)", "Apple AirPods Pro 2 (56dB + ANC)"),
    ("appleairpodspro2anc60db", "AirPods Pro 2 ANC 60 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (60dB + ANC)", "Apple AirPods Pro 2 (60dB + ANC)"),
    ("appleairpodspro2anc65db", "AirPods Pro 2 ANC 65 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (65dB + ANC)", "Apple AirPods Pro 2 (65dB + ANC)"),
    ("appleairpodspro2anc69db", "AirPods Pro 2 ANC 69 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (69dB + ANC)", "Apple AirPods Pro 2 (69dB + ANC)"),
    ("appleairpodspro2anc73db", "AirPods Pro 2 ANC 73 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (73dB + ANC)", "Apple AirPods Pro 2 (73dB + ANC)"),
    ("appleairpodspro2anc77db", "AirPods Pro 2 ANC 77 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (77dB + ANC)", "Apple AirPods Pro 2 (77dB + ANC)"),
    ("appleairpodspro2anc81db", "AirPods Pro 2 ANC 81 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (81dB + ANC)", "Apple AirPods Pro 2 (81dB + ANC)"),
    ("appleairpodspro2anc84db", "AirPods Pro 2 ANC 84 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (84dB + ANC)", "Apple AirPods Pro 2 (84dB + ANC)"),
    ("appleairpodspro2anc88db", "AirPods Pro 2 ANC 88 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (88dB + ANC)", "Apple AirPods Pro 2 (88dB + ANC)"),
    ("appleairpodspro2anc91db", "AirPods Pro 2 ANC 91 dB", "crinacle/711 in-ear/Apple AirPods Pro 2 (91dB + ANC)", "Apple AirPods Pro 2 (91dB + ANC)"),
    ("appleairpodspro2passive", "AirPods Pro 2 Passive", "crinacle/711 in-ear/Apple AirPods Pro 2 (passive mode)", "Apple AirPods Pro 2 (passive mode)"),
    ("appleairpodspro2transparency", "AirPods Pro 2 Transparency", "crinacle/711 in-ear/Apple AirPods Pro 2 (transparency mode)", "Apple AirPods Pro 2 (transparency mode)"),
    ("appleairpodspro2filk", "AirPods Pro 2 — Filk", "Filk/in-ear/Apple Airpods Pro 2", "Apple Airpods Pro 2"),
    ("appleairpodspro2harpo", "AirPods Pro 2 — Harpo", "Harpo/in-ear/Apple Airpods Pro 2", "Apple Airpods Pro 2"),
    ("appleairpodspro2hypethesonics", "AirPods Pro 2 — HypetheSonics RA0045", "HypetheSonics/GRAS RA0045 in-ear/Apple Airpods Pro 2", "Apple Airpods Pro 2"),
]


def download(url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "preciseq-headphone-calibration"})
    with urllib.request.urlopen(req, timeout=60) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f)


def load_target():
    target_path = CACHE_DIR / "AutoEq in-ear.csv"
    if not target_path.exists():
        download(AUTOEQ_TARGET_URL, target_path)
    f, g = [], []
    with target_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            f.append(float(row["frequency"]))
            g.append(float(row["raw"]))
    return np.asarray(f), np.asarray(g)


def result_ir_url(result_dir, result_name):
    rel = f"results/{result_dir}/{result_name} minimum phase 48000Hz.wav"
    return AUTOEQ_RAW + "/" + urllib.parse.quote(rel, safe="/")


def reconstruct_measurement(profile_id, result_dir, result_name, target_f, target_db):
    src_wav = CACHE_DIR / f"{profile_id}_autoeq_48k.wav"
    if not src_wav.exists():
        download(result_ir_url(result_dir, result_name), src_wav)

    x, fs = sf.read(src_wav, dtype="float64", always_2d=False)
    if x.ndim > 1:
        x = x[:, 0]
    if fs != 48000:
        raise RuntimeError(f"{profile_id}: expected 48 kHz AutoEq IR, got {fs}")

    nfft = max(131072, 1 << int(np.ceil(np.log2(max(len(x), 2)))))
    H = np.fft.rfft(x, n=nfft)
    hf = np.fft.rfftfreq(nfft, 1.0 / fs)
    hdb = 20.0 * np.log10(np.maximum(np.abs(H), 1e-12))

    # Correction ~= target - measurement (+ constant preamp). Therefore
    # measurement ~= target - correction. We only need relative FR, so anchor
    # it to 0 dB at 1 kHz to remove AutoEq's convolution preamp constant.
    corr_db = np.interp(target_f, hf, hdb)
    raw = target_db - corr_db
    raw -= np.interp(1000.0, target_f, raw)

    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    out = MEAS_DIR / f"Apple {profile_id}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frequency", "raw"])
        for f, db in zip(target_f, raw):
            if 20.0 <= f <= 20000.0:
                w.writerow([f"{f:.2f}", f"{db:.5f}"])
    return out


def make_zero_target(reference_csv):
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / "0_zero.csv"
    with reference_csv.open(newline="", encoding="utf-8") as src, target.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["frequency", "raw"])
        for row in reader:
            writer.writerow([row["frequency"], "0.00"])
    return target


def sanitize(name):
    return re.sub(r"[\W_]+", "", name).lower()


def generate_ir(profile_id, model, measurement, target):
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    input_dir = TEMP_IN / "0_in-ear"
    input_dir.mkdir(parents=True, exist_ok=True)

    input_name = f"Apple {model}.csv"
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
    print(f"Generating {model}")
    subprocess.run(cmd, check=True)

    copied = set()
    expected_name = sanitize("Apple " + model)
    for wav in TEMP_OUT.rglob("*.wav"):
        m = re.match(r"^(.*?)\s+minimum\s+phase\s+(\d+)\s*Hz\.wav$", wav.name, re.I)
        if not m or sanitize(m.group(1)) != expected_name:
            continue
        rate = FS_MAP.get(m.group(2))
        if rate:
            REPO_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav, REPO_DIR / f"{profile_id}_0_{rate}.wav")
            copied.add(rate)
    if copied != EXPECTED:
        raise RuntimeError(f"{model}: expected IRs {sorted(EXPECTED)}, generated {sorted(copied)}")


def update_headphone_list():
    path = REPO_DIR / "headphone_list.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries = [e for e in entries if not str(e.get("id", "")).startswith("appleairpodspro2")]
    for profile_id, model, _, _ in PROFILES:
        entries.append({
            "id": profile_id,
            "type": 0,
            "brandName": ["Apple"],
            "modelName": [model],
            "version": 1,
            "noDspOffsetDb": 0.0,
        })
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target_f, target_db = load_target()
    measurements = []
    for profile_id, model, result_dir, result_name in PROFILES:
        measurement = reconstruct_measurement(profile_id, result_dir, result_name, target_f, target_db)
        measurements.append((profile_id, model, measurement))

    zero = make_zero_target(measurements[0][2])
    for profile_id, model, measurement in measurements:
        generate_ir(profile_id, model, measurement, zero)

    update_headphone_list()
    shutil.rmtree(TEMP_IN, ignore_errors=True)
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
    print(f"Generated {len(PROFILES)} AirPods Pro 2 PrecisEQ profiles.")


if __name__ == "__main__":
    main()
