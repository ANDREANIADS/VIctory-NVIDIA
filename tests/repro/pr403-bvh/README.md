# PR 403 CPU reference comparison

With Rust 1.98.1 on x86_64 Linux, all 16 built-in tests in `bvh.rs` passed on each revision. The same independent probe called the public `bvh::intersect` function in both versions.

| Synthetic inputs | Base | PR head |
|---|---|---|
| 16 instance/procedural cases (kinds 6 and 7) | `7f800000 3f800000 00000000 00000000` | `ffffffff ffffffff ffffffff ffffffff` |
| 24 triangle and box controls (kinds 0 through 5) | Expected hits and misses | Identical four output words for every input |

Each instance/procedural kind was tested with zeroed and patterned payloads, central and offset ray origins, and both sort settings. Each triangle and box kind was tested with hit and miss rays and both sort settings. The probe checked triangle hit distances, triangle misses, and box child IDs and misses. The comparison covers the CPU reference. GPU execution, emitted DXIL, the other changes in PR 403, image quality and frame times were outside the test.

## Reproduce

Extract this package. Run these commands from its directory in a POSIX shell with Git, Python 3 and Rust 1.98.1 available. Point `repo` to a local checkout of the public repository containing the base and PR commits.

```sh
repo=/path/to/VIctory-NVIDIA
module=crates/victory-shader/src/bvh.rs
git -C "$repo" show "df2daafeb1b2170931cf7a6eddff6de254841d9c:$module" > base.rs
git -C "$repo" show "a2657986706886c0a27427b5e78d790035201def:$module" > pr403.rs
python3 -B verify.py base.rs pr403.rs
```

The verifier checks each source file against its pinned Git blob hash, builds the module's original tests and runs the probe against each reference. For just the built-in suite on one revision, use `rustc --edition=2024 --test pr403.rs -o pr403-tests` and `./pr403-tests --test-threads=1`. The complete recorded comparison is in `results.txt`.

[Base module](https://github.com/trustno1-coder/VIctory-NVIDIA/blob/df2daafeb1b2170931cf7a6eddff6de254841d9c/crates/victory-shader/src/bvh.rs) · [PR module](https://github.com/Kikoarl/VIctory-NVIDIA/blob/a2657986706886c0a27427b5e78d790035201def/crates/victory-shader/src/bvh.rs) · [PR 403](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/403)
