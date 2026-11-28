#!/usr/bin/env python3
"""Compile the exact PR #60 Rust switch path and CPU-only native tests, independently of D3D12."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
FILE = "crates/victory-gpu/src/host/upq.rs"
OLD = "a5961e6231509babe9d82e3c29822fcfbe2f58a9"
FIX = "457c7986d5c8b490d8b6dc69af2f54e76d829ca0"
BLOBS = {OLD: "e07dbaaa741f1c27937e2db8fd71217a8dfc4843", FIX: "f91b08217b203c13a5b0dddc686651f52df61abf"}
MIB = 1 << 20
MAX = (1 << 64) - 1
CAP = 512 * MIB
TOTALS = (0, 1, MIB-1, MIB, 4*MIB-1, 4*MIB, 4*MIB+1, CAP-1, CAP, CAP+1, MAX)
# The vectors are literal expected masks for TOTALS in order. No parser or
# threshold comparison is reimplemented in this checker.
NO = "00000000000"
ALL = "01111111100"
AT_1 = "00011111100"
AT_4 = "00000111100"
AT_512 = "00000000100"
CASES = [
    (None,None,NO), ("",None,NO), ("  ",None,NO), ("0",None,NO),
    ("1",0,ALL), ("+1",0,ALL), ("4",4*MIB,AT_4), (" +4 ",4*MIB,AT_4),
    ("512",CAP,AT_512), ("513",513*MIB,NO),
    ("-1",None,NO), ("-0",None,NO), ("four",None,NO), ("4.0",None,NO),
    ("17592186044414",18446744073707454464,NO),
    ("17592186044415",18446744073708503040,NO),
    ("17592186044416",None,NO), ("17592186044417",None,NO),
    ("18446744073709551615",None,NO), ("18446744073709551616",None,NO),
]
WRAPPED = {
    "17592186044416": (0, ALL), "17592186044417": (MIB, AT_1),
    "18446744073709551615": (18446744073708503040, NO),
}
PROBE = """
        pub(crate) fn observe() {
            let threshold = threshold().map_or_else(|| "off".to_owned(), |n| n.to_string());
            let bits: String = std::env::args().skip(1)
                .map(|total| if wants(total.parse().unwrap()) { '1' } else { '0' }).collect();
            println!("{threshold} {} {bits}", on());
        }
"""
def git_read(repo, rev):
    data = subprocess.check_output(["git","-C",str(repo),"show",f"{rev}:{FILE}"])
    blob = hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    if blob != BLOBS[rev]:
        raise ValueError(f"{rev}: unexpected git blob {blob}")
    return data.decode()

def production(source):
    return source[source.index("fn threshold()"):source.index("pub(super) struct Slot")]

def native_tests(source):
    at = source.index("#[cfg(test)]\nmod tests")
    gpu = source.index("    fn uploads_preserve_bytes_and_reuse_only_after_drawing()", at)
    return source[at:source.rindex("    #[test]", at, gpu)] + "}\n"

def build(directory, rustc, label, body, tests, flags=()):
    file = directory / f"{label}.rs"
    file.write_text("mod host { pub mod upq { use std::sync::OnceLock;\n" + body + PROBE
                    + tests + "\n} }\n#[cfg(not(test))] fn main() { host::upq::observe(); }\n")
    binary = directory / (label + (".exe" if os.name == "nt" else ""))
    subprocess.run([rustc,"--edition=2024","-A","dead_code",*flags,str(file),"-o",str(binary)],check=True)
    return binary

def run_tests(binary, env, expected_count, failure=()):
    result = subprocess.run([str(binary),"--test-threads=1"],env=env,text=True,capture_output=True)
    text = result.stdout + result.stderr
    if not failure:
        wanted = f"test result: ok. {expected_count} passed; 0 failed"
        good = result.returncode == 0 and wanted in text
    else:
        good = result.returncode != 0 and all(item in text for item in failure) and f"{expected_count-1} passed; 1 failed" in text
    if not good:
        raise RuntimeError(f"{binary.name}: {text}")
    print(f"{binary.name}: {expected_count} passed" if not failure else f"{binary.name}: expected failure: {failure}")

def matrix(binary, env, old):
    for setting, threshold, mask in CASES:
        if old and setting in WRAPPED:
            threshold, mask = WRAPPED[setting]
        child = env.copy()
        if setting is not None:
            child["VICTORY_UPLOAD_QUEUE"] = setting
        measured = subprocess.check_output([str(binary),*map(str,TOTALS)],env=child,text=True).strip()
        expected = f"{'off' if threshold is None else threshold} {'false' if threshold is None else 'true'} {mask}"
        if measured != expected:
            raise ValueError(f"{binary.name}, {setting!r}: expected {expected}, got {measured}")
        print(f"{binary.name} {setting!r}: {measured}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=HERE/"checkout")
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--patch", type=Path, default=HERE/"upq-threshold-regression.patch")
    args = parser.parse_args()
    env = dict(os.environ)
    for name in ("VICTORY_UPLOAD_QUEUE", "VICTORY_TEST_UPLOAD_QUEUE_BYTES"):
        env.pop(name, None)
    old, fixed = (git_read(args.repo, rev) for rev in (OLD,FIX))
    print("parent", OLD, BLOBS[OLD])
    print("head", FIX, BLOBS[FIX])
    print(subprocess.check_output([args.rustc,"--version"],text=True).strip())
    print("mask: one wants(total) bit per byte count", *TOTALS)
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        target = directory / FILE
        target.parent.mkdir(parents=True)
        target.write_bytes(fixed.encode())
        subprocess.run(["git","init","--quiet",str(directory)],check=True)
        for mode in (["--check"],[]):
            subprocess.run(["git","-C",str(directory),"apply",*mode,str(args.patch.resolve())],check=True)
        proposed = target.read_text()
        if fixed.split("#[cfg(test)]",1)[0] != proposed.split("#[cfg(test)]",1)[0]:
            raise RuntimeError("the patch changes production code")
        for name, src, tests, count, failure in [
            ("parent_native",old,old,1,None), ("head_native",fixed,fixed,2,None),
            ("head_tests_on_old_parser",old,fixed,2,None),
            ("regression_on_head",fixed,proposed,2,None),
            ("regression_on_old_parser",old,proposed,2,("host::upq::tests::upload_queue_threshold_reads_the_setting",
                                                       'Some("17592186044416")',"left: Some(0)","right: None")),
        ]:
            binary = build(directory,args.rustc,name,production(src),native_tests(tests),["--test"])
            run_tests(binary,env,count,failure)
        for profile,flags in [("debug",[]),("optimized",["-O"])]:
            for name,source,is_old in [("parent",old,True),("fixed",fixed,False)]:
                binary = build(directory,args.rustc,f"{name}_{profile}",production(source),"",flags)
                matrix(binary,env,is_old)
    print(f"PASS {len(CASES)} settings x {len(TOTALS)} upload sizes x 2 revisions x 2 build profiles; "
          "both revised native CPU tests pass, and the old parser is detected.")

if __name__ == "__main__":
    main()
