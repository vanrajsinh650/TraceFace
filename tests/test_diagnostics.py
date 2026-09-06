"""Tests for TraceFace pre-flight diagnostics module."""
import unittest
from traceface.diagnostics import (
    check_python_version,
    check_import,
    check_onnx_providers,
    check_model_cache,
    check_writable_dirs,
    run_doctor,
)


class TestDiagnostics(unittest.TestCase):
    """Verify diagnostic functions execute safely and return expected structures."""

    def test_check_python_version(self):
        ok, msg = check_python_version(min_version=(3, 10))
        self.assertIsInstance(ok, bool)
        self.assertIn("Python", msg)

    def test_check_import_existing(self):
        ok, msg = check_import("sys")
        self.assertTrue(ok)
        self.assertIn("sys", msg)

    def test_check_import_nonexistent(self):
        ok, msg = check_import("non_existent_module_xyz_123")
        self.assertFalse(ok)
        self.assertIn("MISSING", msg)

    def test_check_onnx_providers(self):
        cpu_ok, prov_msg, providers = check_onnx_providers()
        self.assertIsInstance(cpu_ok, bool)
        self.assertIsInstance(prov_msg, str)
        self.assertIsInstance(providers, list)

    def test_check_model_cache(self):
        ok, msg = check_model_cache()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)

    def test_check_writable_dirs(self):
        ok, msg = check_writable_dirs()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)

    def test_run_doctor_returns_int(self):
        code = run_doctor(verbose=False)
        self.assertIn(code, (0, 1))


if __name__ == "__main__":
    unittest.main()
