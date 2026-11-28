# VIctory-NVIDIA review results

## Clippy and shader tests · [PR #665](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/665)

On the parent `8fc22547`, Clippy reproduced the workspace warnings. On this PR’s head `0a368d63`, the default and all-features Clippy checks both exited 0 with Rust 1.98.1 and `-D warnings`. I ran Clippy from Linux targeting `x86_64-pc-windows-msvc`, with `blake3/pure` for the cross-build. The native Linux `victory-shader` library suite passed 207 tests, with 2 ignored. The Windows loader test in the PR is outside this run.

From the PR head, with the Windows MSVC target and dependencies installed, run the three commands below.

```sh
cargo clippy --workspace --all-targets --locked --offline --target x86_64-pc-windows-msvc --features blake3/pure --keep-going -- -D warnings
cargo clippy --workspace --all-targets --all-features --locked --offline --target x86_64-pc-windows-msvc --features blake3/pure --keep-going -- -D warnings
cargo test --lib --locked --offline -p victory-shader
```

## DLSS diagnostic · [PR #558](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/558)

I rechecked the cache fix on `cd02cc3a` with a 1920×1080 output and a synthetic SDK response reporting a 960×540 optimum and 1920×1080 maximum. With a 1280×720 scene, the success message labels 1920×1080 as optimal. The attached diagnostic change prints `optimal Some([960, 540]), offered Some([1920, 1080])`. Reversing the input order produced the same selection and the second frame reused the six cached queries. Both revisions selected DLAA when all modes reported identical sizes. The standard profile selected Quality at 1280×720 and Performance at 960×540. These observations cover the selection and message from CPU callbacks. Driver acceptance and rendered output remain unverified. [Diagnostic patch](https://github.com/ANDREANIADS/VIctory-NVIDIA/commit/31edc0e52c87ff4947615da4f9d44f0883d85f6c)

The probe compiles the checkout’s `record()` and the success-message expression used by `victory upscaler-check --device`. Each revision passed six sequences covering 11 inputs, 36 simulated settings queries, and nine simulated evaluations. The range-disabled control rejected 1280×720 with the reduced-optimum fixture. The full Windows CLI was outside this run. [Baseline output](dlss/before.txt) · [Patched output](dlss/after.txt)

## Upload threshold · [PR #60](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/60)

I added a regression test for the real `VICTORY_UPLOAD_QUEUE` parser on top of `cf9a417b`. At `17592186044416` MiB, the previous parser returned `Some(0)`, which let a one-byte upload through. The new test caught it on the parent `ef87380a`. Both CPU tests passed on this PR head with the added cases. The existing tests also passed when paired with the old parser. The separate routing check covered 20 settings and 11 upload sizes on two revisions, in debug and optimized builds, for 880 decisions. This exercised CPU configuration and routing. The test did not submit a D3D12 transfer. [Test-only patch](https://github.com/ANDREANIADS/VIctory-NVIDIA/commit/7d5f83c6706a4eb15e3861700bbaafd2243a1781) · [Routing and test output](upload/results.txt)

## Synthetic node readbacks · [PR #403](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/403)

I added a two-line regression check on top of `a265798` that expects `[u32::MAX; 4]` directly for instance and procedural nodes (kinds 6 and 7), independently of the CPU reference. With the same test file on both revisions, all four D3D12 readback tests failed on `df2daaf` at the first kind-6 case and passed on this PR head using Windows WARP. The runner had no SM 6.6 hardware adapter. The results cover the synthetic node readbacks. [Two-line test](https://github.com/ANDREANIADS/VIctory-NVIDIA/commit/a86b65eb9c919f9045d19612083edd6083dca38c) · [Before/after Windows job](https://github.com/ANDREANIADS/VIctory-NVIDIA/actions/runs/46086555430/job/140797366889)

## Reproduce the CPU checks

Run these commands from the directory containing this report in a Git clone of VIctory-NVIDIA. They fetch the two patch branches from the fork. Python 3, Git and rustc with Rust 2024 edition support are required. The recorded runs used rustc 1.98.1.

```sh
git fetch https://github.com/ANDREANIADS/VIctory-NVIDIA.git refs/heads/review/pr-558-dlss-reported-sizes refs/heads/review/pr-60-upload-threshold-test
repo=$(git rev-parse --show-toplevel)
python3 -B dlss/run.py --repo "$repo" --rev cd02cc3a17f47a04bae6ba5b0dfe20e26bd116d9 --original
python3 -B dlss/run.py --repo "$repo" --rev 31edc0e52c87ff4947615da4f9d44f0883d85f6c
python3 -B upload/verify_current.py --repo "$repo"
```

If a specific check would help move one of these PRs forward, please point us to the issue or PR, the revision, and the behavior you want to verify. We’re available to help reproduce it and share the result.
