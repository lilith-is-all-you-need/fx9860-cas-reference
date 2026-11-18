"""Identify a published CAS launcher and payload from file contents."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]

def identify(directory):
    payload = (directory / "KHICAS.BIN").read_bytes()
    loader = (directory / "KhiMap.g1a").read_bytes()
    if (len(payload) < 512 or payload[:16] != b"KHICAS-MAPPED/1\0" or
            struct.unpack_from(">III", payload, 16) != (1, 0x00300200, len(payload) - 512)):
        raise ValueError("Unexpected payload header or length")
    catalogue = json.loads((ROOT / "evidence/builds.json").read_text("utf-8"))
    pair = {"KHICAS.BIN": payload, "KhiMap.g1a": loader}
    for name, record in catalogue.items():
        if all(hashlib.sha256(data).hexdigest() == record["files"][file]["sha256"]
               for file, data in pair.items()):
            return name
    raise ValueError("Unknown or mixed pair; check both files against evidence/builds.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        print(identify(args.directory))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
