#!/usr/bin/env python3
"""Compile the checkout's record() and the check_run() success-message expression on the CPU."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "cd02cc3a17f47a04bae6ba5b0dfe20e26bd116d9"
SMALL, LARGE, FULL = "960x540", "1280x720", "1920x1080"
# Each expectation gives current scene, selected mode, raw optimum and calculated offer.
S = (SMALL, "DLAA", SMALL, SMALL)
L = (LARGE, "DLAA", SMALL, FULL)
X = (LARGE, "none", "-", "-")
CASES = [
    ("override, increasing", "equal", "performance", "1", [S, L]),
    ("override, decreasing", "equal", "quality", "1", [L, S]),
    ("range off, increasing", "equal", "performance", "0", [S, X]),
    ("range off, decreasing", "equal", "quality", "0", [X, S]),
    ("standard", "normal", "quality", "1", [(LARGE, "quality", LARGE, LARGE), (SMALL, "performance", SMALL, SMALL)]),
    ("standard, range off", "normal", "quality", "0", [(LARGE, "quality", LARGE, LARGE)]),
]


def item(text, prefix):
    start = text.index("\n" + prefix) + 1
    return text[start:text.index("\n}", start) + 2]


def debug_size(size):
    return f"Some([{', '.join(size.split('x'))}])"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="local VIctory-NVIDIA checkout")
    parser.add_argument("--rev", help="read files from this Git revision (default: working tree)")
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--original", action="store_true", help="verify the author's original diagnostic")
    args = parser.parse_args()

    def source(path):
        if args.rev:
            return subprocess.check_output(["git", "-C", str(args.repo), "show", f"{args.rev}:{path}"], text=True)
        return (args.repo / path).read_text(encoding="utf-8")

    src = "crates/victory-gpu/src/streamline"
    top = source(src + ".rs")
    types = [item(top, x) for x in ("pub struct Asked {", "impl Asked {", "struct Plan {")]
    types += ["#[derive(Default)]\n" + item(top, x) for x in ("struct Functions {", "struct Calls {")]
    record = item(top, "fn record(")
    types += [item(top, "static CALLS:") + ");", item(top, "fn calls()"), item(top, "fn frame_token("),
              item(top, "struct Recorded {"), record]
    for name in ("DEFAULT_DIR", "COLOUR", "DEPTH", "MOTION", "EXPOSURE", "REACTIVE", "OUTPUT",
                 "VIEWPORT_DLSS", "T_UPSCALE", "T_UPSCALE_LOCK"):
        types.append(re.search(r"^(?:pub )?const " + name + r":.*$", top, re.M)[0])

    # Render exactly the format! expression and sizes closure used by check_run's success arm.
    check = item(top, "fn check_run(")
    start = check.index("let sizes = || -> String {")
    closure = check[start:check.index("\n        };", start) + len("\n        };")]
    prefix = "(Ok(r), Ok(())) if round == 0 => lines.push("
    start = check.index(prefix) + len(prefix)
    end = check.index(")),\n", start)
    types.append("fn check_line(r: &Recorded, render: [u32; 2], output: [u32; 2]) -> String {\n"
                 + closure + "\n" + check[start:end + 1] + "\n}")
    types.append("fn recorded_offer(_r: &Recorded) -> Option<[u32; 2]> { "
                 + ("None" if args.original else "_r.offered") + " }")

    # The tracing implementation is stubbed. Check the production field bindings at source level.
    prod = item(top, "fn evaluate(")
    assert "optimal = ?recorded.optimal," in prod
    assert ("offered = ?recorded.offered," in prod) == (not args.original)
    if args.rev == BASE:
        assert args.original
        assert hashlib.sha1(f"blob {len(top.encode())}\0".encode() + top.encode()).hexdigest() == "4aa7acdfbe85c8602b60d447c8c68021c01a5381"
    print("source", args.rev or "working tree", "original" if args.original else "corrected")
    print("record-sha256", hashlib.sha256(record.encode()).hexdigest())
    print(subprocess.check_output([args.rustc, "--version"], text=True).strip())
    count = evaluations = requests = 0
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for name in ("plan.rs", "abi.rs"):
            (work / name).write_text(source(src + "/" + name), encoding="utf-8")
        generated = work / "probe.rs"
        generated.write_text("#![allow(dead_code)]\n" + (HERE / "fixture.rs").read_text(encoding="utf-8")
                             + "\n" + "\n\n".join(types), encoding="utf-8")
        binary = work / ("probe.exe" if os.name == "nt" else "probe")
        subprocess.run([args.rustc, "--edition=2024", str(generated), "-o", str(binary)], check=True)
        for label, profile, asked, flag, frames in CASES:
            env = {k: v for k, v in os.environ.items() if not k.startswith("VICTORY_")}
            env.update(VICTORY_DLSS="1", VICTORY_DLSS_MODE=asked, VICTORY_MENU_CONSOLE="series-s", VICTORY_DLSS_RANGE=flag)
            command = [str(binary), profile, *(row[0] for row in frames)]
            lines = subprocess.check_output(command, env=env, text=True).splitlines()
            assert len(lines) == len(frames)
            for i, (line, (scene, mode, optimum, offer)) in enumerate(zip(lines, frames)):
                fields = line.split("\t")
                expected_optimum = offer if args.original else optimum
                expected_offer = "-" if args.original else offer
                assert fields[:6] == [scene, mode, expected_optimum, expected_offer,
                                      "6" if i == 0 else "0", "0" if mode == "none" else "1"], (label, fields)
                if mode != "none":
                    pair = f"optimal {debug_size(expected_optimum)}"
                    if not args.original:
                        pair += f", offered {debug_size(expected_offer)}"
                    assert f"as {mode} ({pair});" in fields[6], (label, fields[6])
                    assert "render sizes for [1920, 1080]: DLAA Some(" in fields[6], fields[6]
                print(f"{label}: {scene}; mode={mode}; optimal={fields[2]}; offered={fields[3]}; new_queries={fields[4]}; "
                      + (f"CLI fields=({pair})" if mode != "none" else "rejected before evaluation"))
                count += 1
                requests += int(fields[4])
                evaluations += int(fields[5])
    print(f"PASS {len(CASES)} independent sequences, {count} frames, {requests} settings queries, "
          f"{evaluations} simulated evaluations and formatted messages. No D3D12 or SDK execution.")


if __name__ == "__main__":
    main()

