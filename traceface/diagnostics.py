# traceface/diagnostics.py
"""Diagnostics utilities for TraceFace.
Provides functions to check importability of required packages, ONNX Runtime provider availability,
model cache integrity, actual model initialization, and overall pre-flight "doctor" report.
"""

import importlib
import sys
import os
import platform
from pathlib import Path
from typing import Tuple, List


# Helper to format version info safely
def _get_version(module) -> str:
    return getattr(module, "__version__", "unknown")


def check_python_version(min_version: Tuple[int, int] = (3, 10)) -> Tuple[bool, str]:
    v = sys.version_info
    ok = (v.major, v.minor) >= min_version
    msg = f"Python {v.major}.{v.minor}.{v.micro}"
    return ok, msg


def check_import(module_name: str) -> Tuple[bool, str]:
    try:
        mod = importlib.import_module(module_name)
        ver = _get_version(mod)
        return True, f"{module_name} {ver}"
    except ImportError as e:
        return False, f"{module_name} MISSING — {e}"
    except Exception as e:
        return False, f"{module_name} IMPORT ERROR — {e}"


def check_onnx_providers() -> Tuple[bool, str, List[str]]:
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        cpu_ok = "CPUExecutionProvider" in providers
        return cpu_ok, ", ".join(providers), providers
    except ImportError:
        return False, "onnxruntime not installed", []
    except Exception as e:
        return False, f"Failed to query ONNX Runtime: {e}", []


def _default_model_path() -> Path:
    # InsightFace default cache location
    home = Path.home()
    return home / ".insightface" / "models" / "buffalo_l"


def check_model_cache() -> Tuple[bool, str]:
    model_dir = _default_model_path()
    if not model_dir.is_dir():
        return False, (
            f"Model directory not found: {model_dir}\n"
            f"         buffalo_l auto-downloads on first use (~280 MB).\n"
            f"         Run the live pipeline once, or manually download the model."
        )
    # Expect at least one .onnx file
    expected_files = list(model_dir.glob("*.onnx"))
    if not expected_files:
        return False, f"No .onnx model files in {model_dir}"
    for f in expected_files:
        if f.stat().st_size == 0:
            return False, f"Model file appears empty: {f}"
    return True, f"OK ({len(expected_files)} .onnx file(s) in {model_dir})"


def check_model_init(verbose: bool = False) -> Tuple[bool, str]:
    """Actually attempt to initialize InsightFace FaceAnalysis with buffalo_l.

    This catches runtime failures that import-only checks miss:
    - ONNX Runtime session creation failures
    - Model file corruption
    - Provider incompatibilities
    - Version mismatches (e.g. insightface 1.x vs 0.7.x API differences)
    """
    try:
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        return True, "buffalo_l initialized OK"
    except FileNotFoundError as e:
        return False, f"MODEL DOWNLOAD NEEDED — {e}"
    except ImportError as e:
        return False, f"IMPORT FAILURE — {e}"
    except Exception as e:
        msg = f"MODEL INIT FAILURE — {e}"
        if verbose:
            import traceback
            msg += f"\n{traceback.format_exc()}"
        return False, msg


def check_writable_dirs() -> Tuple[bool, str]:
    """Check that key output directories are writable."""
    issues = []
    for dir_name in ["results"]:
        d = Path(dir_name)
        if d.exists() and not os.access(d, os.W_OK):
            issues.append(f"{d} exists but is not writable")
    # Check model cache parent
    model_parent = _default_model_path().parent
    if model_parent.exists() and not os.access(model_parent, os.W_OK):
        issues.append(f"Model cache {model_parent} is not writable")
    if issues:
        return False, "; ".join(issues)
    return True, "OK"


def check_sepolia_rpc() -> Tuple[bool, str]:
    """Check connectivity to a public Sepolia RPC endpoint (read-only)."""
    try:
        from web3 import Web3
    except ImportError:
        return False, "web3 not installed"

    endpoints = [
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://rpc.sepolia.org",
        "https://1rpc.io/sepolia",
    ]
    for ep in endpoints:
        try:
            w3 = Web3(Web3.HTTPProvider(ep, request_kwargs={"timeout": 8}))
            if w3.is_connected():
                chain_id = w3.eth.chain_id
                if chain_id == 11155111:
                    return True, f"Connected ({ep})"
        except Exception:
            continue
    return False, "Cannot reach any Sepolia RPC endpoint"


def run_doctor(verbose: bool = False) -> int:
    """Run checks and print a compact report. Returns 0 if all required checks pass."""
    failures: List[str] = []
    warnings: List[str] = []

    print("\nTraceFace Doctor — Pre-flight Environment Check")
    print("=" * 66)

    # System info
    print(f"OS:            {platform.platform()}")
    print(f"Architecture:  {platform.machine()}")
    print(f"In virtualenv: {'Yes' if sys.prefix != sys.base_prefix else 'No'}")
    print("-" * 66)

    # Python version
    ok, msg = check_python_version()
    _print_check("Python >= 3.10", ok, msg)
    if not ok:
        failures.append(f"Python version: {msg} (need >= 3.10)")

    # Required imports
    required_packages = [
        ("insightface", True),
        ("onnxruntime", True),
        ("cv2", True),
        ("PIL", True),
        ("numpy", True),
        ("web3", True),
        ("httpx", True),
    ]
    optional_packages = [
        ("PicImageSearch", False),
        ("dotenv", False),
    ]

    for pkg, required in required_packages + optional_packages:
        ok, msg = check_import(pkg)
        _print_check(pkg, ok, msg)
        if not ok:
            if required:
                failures.append(f"{pkg}: {msg}")
            else:
                warnings.append(f"{pkg}: {msg} (optional)")

    # ONNX providers
    print("-" * 66)
    cpu_ok, prov_msg, providers = check_onnx_providers()
    _print_check("ONNX CPU provider", cpu_ok, prov_msg)
    if not cpu_ok:
        failures.append(f"ONNX Runtime: {prov_msg}")

    # Model cache
    cache_ok, cache_msg = check_model_cache()
    _print_check("Model cache", cache_ok, cache_msg)
    if not cache_ok:
        warnings.append("buffalo_l model cache not found (auto-downloads on first use)")

    # Actual model initialization (only if cache exists)
    if cache_ok:
        init_ok, init_msg = check_model_init(verbose=verbose)
        _print_check("Model init", init_ok, init_msg)
        if not init_ok:
            failures.append(f"Model init: {init_msg}")
    else:
        print(f"  {'SKIP':>4}  Model init (no model cache yet)")

    # Writable directories
    write_ok, write_msg = check_writable_dirs()
    _print_check("Writable dirs", write_ok, write_msg)
    if not write_ok:
        warnings.append(f"Directory permissions: {write_msg}")

    # Sepolia RPC
    print("-" * 66)
    rpc_ok, rpc_msg = check_sepolia_rpc()
    _print_check("Sepolia RPC", rpc_ok, rpc_msg)
    if not rpc_ok:
        warnings.append(f"Sepolia RPC: {rpc_msg} (needed for proof-verify)")

    # .env presence (optional for proof mode)
    env_path = Path(".env")
    env_exists = env_path.is_file()
    print(f"  {'FOUND' if env_exists else 'SKIP':>4}  .env file {'(found)' if env_exists else '(not required for proof mode)'}")

    # Summary
    print("=" * 66)
    if failures:
        print(f"\nRESULT: READY = FALSE")
        print(f"\nFailures ({len(failures)}):")
        for f in failures:
            print(f"  ✗ {f}")
        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for w in warnings:
                print(f"  ○ {w}")
        print("\nFix the failures above and re-run: python main.py doctor")
        return 1
    else:
        print(f"\nRESULT: READY = TRUE")
        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for w in warnings:
                print(f"  ○ {w}")
        return 0


def _print_check(label: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    # Handle multi-line detail (indent continuation lines)
    lines = detail.split("\n")
    print(f"  {status:>4}  {label}: {lines[0]}")
    for line in lines[1:]:
        print(f"        {line}")


if __name__ == "__main__":
    sys.exit(run_doctor(verbose="--verbose" in sys.argv))
