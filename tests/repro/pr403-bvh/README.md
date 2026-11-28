# PR 403 ray-intersection regression results

## CPU reference comparison

With Rust 1.98.1 on x86_64 Linux, all 16 built-in tests in `bvh.rs` passed on each revision. The same independent probe called the public `bvh::intersect` function in both versions.

| Synthetic inputs | Base | PR head |
|---|---|---|
| 16 instance/procedural cases (kinds 6 and 7) | `7f800000 3f800000 00000000 00000000` | `ffffffff ffffffff ffffffff ffffffff` |
| 24 triangle and box controls (kinds 0 through 5) | Expected hits and misses | Identical four output words for every input |

Each instance/procedural kind was tested with zeroed and patterned payloads, central and offset ray origins, and both sort settings. Each triangle and box kind was tested with hit and miss rays and both sort settings. The probe checked triangle hit distances, triangle misses, and box child IDs and misses. The comparison covers the CPU reference. GPU execution, emitted DXIL, the other changes in PR 403, image quality and frame times were outside the test.

## Reproduce the CPU comparison

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

## D3D12 readback on Windows

The same test file was run first against the PR base (`df2daafe`) and then against its head (`a2657986`). It checks the four 32-bit words read back from the shader for instance and procedural nodes (types 6 and 7) against four `0xffffffff` words. The remaining node types continue to use the CPU reference. This protects the test even if the shader and CPU reference later regress together.

| Revision | Four selected D3D12 tests |
| --- | --- |
| Base | All four failed at the first type-6 lane. WARP returned `7f800000 3f800000 00000000 00000000`. Each test stopped on that mismatch. |
| PR head | All four passed, including both types 6 and 7. The tests cover 32- and 64-bit pointers, host buffers and simulated title memory. |

Windows ran the emitted DXIL on Microsoft's WARP software adapter. The hardware adapter did not meet the Shader Model 6.6 requirement on this runner. Image quality and frame rate on a physical RTX card remain open.

The [two-line test-only commit](https://github.com/ANDREANIADS/VIctory-NVIDIA/commit/a86b65eb9c919f9045d19612083edd6083dca38c) is a direct child of the PR head. A [Git patch](https://github.com/ANDREANIADS/VIctory-NVIDIA/commit/a86b65eb9c919f9045d19612083edd6083dca38c.patch) and the [Windows verification job with both logs](https://github.com/ANDREANIADS/VIctory-NVIDIA/actions/runs/46086555430/job/140797366889) are available.

On Windows, from the patched checkout, run:

```powershell
cargo test -p victory-shader --locked --lib emit::intersect_tests::the_ -- --nocapture --test-threads=1
```
