"""Compare the pinned public CPU references without building the workspace."""
import argparse
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

CASES = {
    "base": ("df2daafeb1b2170931cf7a6eddff6de254841d9c", "3f79f8220195a1c6c406a8708d255e932fa051d1"),
    "pr403": ("a2657986706886c0a27427b5e78d790035201def", "db2012b42ea0d223bb042c6ac37e8d56feade3e9"),
}
MODULE = "crates/victory-shader/src/bvh.rs"


def output(*args):
    return subprocess.check_output(args, text=True)


def measure(label, source_file, rustc, work):
    commit, expected_blob = CASES[label]
    data = source_file.read_bytes()
    digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if digest != expected_blob:
        raise ValueError(f"{label}: expected blob {expected_blob}, got {digest}")
    print(f"\n{label} {commit} | {MODULE} {digest}")
    tests = work / f"{label}-tests"
    library = work / f"lib{label}.rlib"
    probe = work / f"{label}-probe"
    subprocess.run([rustc, "--edition=2024", "--test", source_file, "-o", tests], check=True)
    print(output(tests, "--test-threads=1").strip())
    subprocess.run([rustc, "--edition=2024", "--crate-name", "bvh", "--crate-type=rlib",
                    source_file, "-o", library], check=True)
    subprocess.run([rustc, "--edition=2024", Path(__file__).with_name("probe.rs"), "--extern",
                    f"bvh={library}", "-o", probe], check=True)
    results = {}
    for line in output(probe).splitlines():
        print(line)
        kind, payload, ray, sort, *words = line.split()
        key = (int(kind), payload, ray, sort)
        assert key not in results and len(words) == 4, line
        results[key] = tuple(words)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("pr403", type=Path)
    parser.add_argument("--rustc", default="rustc")
    args = parser.parse_args()
    print(output(args.rustc, "-vV").strip())
    with TemporaryDirectory() as directory:
        work = Path(directory)
        before = measure("base", args.base, args.rustc, work)
        after = measure("pr403", args.pr403, args.rustc, work)
    assert before.keys() == after.keys()
    controls = [key for key in before if key[0] < 6]
    changed = [key for key in before if key[0] >= 6]
    assert len(controls) == 24 and len(changed) == 16
    for key in controls:
        assert before[key] == after[key], (key, before[key], after[key])
    for key in changed:
        assert before[key] == ("7f800000", "3f800000", "00000000", "00000000"), key
        assert after[key] == ("ffffffff",) * 4, key
    print("\n24/24 synthetic controls (kinds 0–5) matched bit for bit.")
    print("16/16 synthetic cases (kinds 6–7) changed from the triangle-miss words to four ffffffff words.")


if __name__ == "__main__":
    main()
