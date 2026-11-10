"""Automated Requirements Traceability Matrix (RTM) Verification (TC-RTM-01 / NFR-15).

Verifies that:
1. Every Functional Requirement (FR-1 to FR-19) from SRS v1.0 has a mapped test case,
   linked issue, pull request, and passed or accepted verification status.
2. Every Security Requirement (SEC-1 to SEC-5) has a mapped test case and passed status.
3. Every Non-Functional Requirement (NFR-1 to NFR-15) has a verified status (P, A, or N).
4. All referenced test files exist on disk.
5. The deviations documentation (docs/PMS_Deviations.md) is present.
"""

import re
from pathlib import Path


def get_repo_root() -> Path:
    # backend/tests/test_rtm.py -> backend/tests -> backend -> repo root
    return Path(__file__).resolve().parent.parent.parent


def test_rtm_completeness_and_traceability():
    """TC-RTM-01: Verify that every SRS requirement is present, traceable, and verified in RTM."""
    repo_root = get_repo_root()
    rtm_path = repo_root / "docs" / "PMS_RTM.md"
    assert rtm_path.exists(), f"RTM document not found at {rtm_path}"

    content = rtm_path.read_text(encoding="utf-8")
    assert len(content) > 1000, "RTM document appears unexpectedly short"

    # Regex building helper to keep line lengths <= 100
    def row_pattern(req_id: str, status_group: str) -> str:
        prefix = rf"\|\s*\*\*{req_id}\*\*\s*\|"
        cols = r"([^|]+)\|" * 7
        suffix = rf"\s*\*\*{status_group}\*\*\s*\|"
        return prefix + cols + suffix

    # 1. Verify all 19 Functional Requirements (all P; FR-18 passed once its backend was added)
    for i in range(1, 20):
        fr_id = f"FR-{i}"
        status_expected = "P"
        pattern = row_pattern(fr_id, status_expected)
        match = re.search(pattern, content)
        assert match is not None, f"FR {fr_id} is missing or has wrong status in RTM"

        issue_col = match.group(4)
        pr_col = match.group(5)
        tc_col = match.group(6)
        test_file_col = match.group(7)

        assert "#" in issue_col, f"{fr_id} missing issue reference"
        assert "#" in pr_col, f"{fr_id} missing PR reference"
        assert "TC-" in tc_col, f"{fr_id} missing test case reference"
        assert len(test_file_col.strip()) > 0, f"{fr_id} missing test implementation path"

    # 2. Verify all 5 Security Requirements (All P)
    for i in range(1, 6):
        sec_id = f"SEC-{i}"
        pattern = row_pattern(sec_id, "P")
        match = re.search(pattern, content)
        assert match is not None, f"Security requirement {sec_id} is missing or not Passed in RTM"

    # 3. Verify all 15 Non-Functional Requirements (P, A, or N)
    for i in range(1, 16):
        nfr_id = f"NFR-{i}"
        pattern = row_pattern(nfr_id, "(?:P|A|N)")
        match = re.search(pattern, content)
        assert match is not None, f"NFR requirement {nfr_id} is missing or not verified in RTM"

    # 4. Verify referenced backend test files exist
    expected_backend_test_files = [
        "test_auth.py",
        "test_access.py",
        "test_lockout.py",
        "test_users.py",
        "test_reset.py",
        "test_2fa.py",
        "test_passwords.py",
        "test_employee_data.py",
        "test_products.py",
        "test_suppliers.py",
        "test_batches.py",
        "test_sales.py",
        "test_stock.py",
        "test_alerts.py",
        "test_notifications.py",
        "test_markdowns.py",
        "test_refrigeration.py",
        "test_device.py",
        "test_offline_sync.py",
        "test_health.py",
        "test_nfr_timing.py",
    ]
    tests_dir = repo_root / "backend" / "tests"
    for filename in expected_backend_test_files:
        path = tests_dir / filename
        assert path.exists(), f"Referenced test file {filename} does not exist at {path}"

    # 5. Verify deviations document exists and covers core deviations
    deviations_path = repo_root / "docs" / "PMS_Deviations.md"
    assert deviations_path.exists(), "Deviations document not found"
    dev_content = deviations_path.read_text(encoding="utf-8")
    assert "Deviation 1" in dev_content
    assert "Attendance" in dev_content
    assert "Supplier" in dev_content
    assert "argon2-cffi" in dev_content

    # 6. Verify test results summary exists
    test_results_path = repo_root / "docs" / "PMS_Test_Results.md"
    assert test_results_path.exists(), "Test results summary document not found"
