"""Generate deterministic synthetic handoff data. Never used as real data."""

import argparse
from pathlib import Path

from mymarket.fixtures import generate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures"))
    generate(parser.parse_args().output)
    print("FAKE fixtures generated. These are synthetic, not training data.")
