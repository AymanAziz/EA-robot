# ARM64 dependency availability check

On 2026-11-05, the exact versions below were checked against their official PyPI release JSON metadata. Each has at least one non-yanked Linux AArch64 wheel compatible with CPython 3.12 and Ubuntu 24.04's glibc baseline. Stable-ABI (`abi3`) and Python-independent native (`py3-none`) wheel tags were accepted where applicable. Python `Requires-Python` metadata was also checked.

| Native dependency | Locked version | Compatible wheel present |
|---|---|---|
| LightGBM | 4.7.0 | Yes |
| NumPy | 2.5.4 | Yes |
| pandas | 2.3.3 | Yes |
| SciPy | 1.18.1 | Yes |
| scikit-learn | 1.9.1 | Yes |
| psutil | 7.2.2 | Yes |
| PyArrow | 26.0.1 | Yes |

The generated local manifest is `var/verification/arm64-wheel-manifest.json`. It records the exact [PyPI release JSON](https://docs.pypi.org/api/json/) URLs, wheel filenames, download URLs, SHA-256 digests, Python requirements and upload timestamps. The check read metadata only; it did not download/execute wheels, provision Oracle resources, install on an ARM64 VM or measure resource use. The target is Ubuntu 24.04/AArch64, CPython 3.12 and the [documented glibc 2.39 baseline](https://packages.ubuntu.com/noble/arm64/libc6); it does not establish support for Alpine/musl or an older OS/Python.

LightGBM still needs the system OpenMP runtime (`libgomp1`), installed by `scripts/install_ubuntu.sh`. The cloud AI providers use the existing HTTPS client and require no GPU or local language model. `psutil` is the only added backend dependency for actual host telemetry. Community Cloud's frontend uses a separate lightweight dependency file and does not import the execution/ML modules.

Run the locked installation, imports and tests on the actual Oracle VM. Confirm systemd timers, broker/provider TLS, public Caddy certificates, database permissions and backup restoration there. These remain deployment checks, not conclusions from wheel metadata. Updating the lock requires repeating this availability check.
