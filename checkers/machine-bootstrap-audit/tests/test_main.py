"""Unit tests for machine-bootstrap-audit tool."""

import tempfile
import unittest
from pathlib import Path

from main import audit_script_file, generate_audit_report


class TestMachineBootstrapAudit(unittest.TestCase):
    """Test suite for machine-bootstrap-audit functionality."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_audit_shell_script(self) -> None:
        script = self.root / "setup.sh"
        content = (
            "#!/bin/bash\n"
            "sudo apt-get update\n"
            "read -p 'Enter username: ' user_name\n"
            "docker run hello-world\n"
            "cp myfile /home/dev/target\n"
        )
        script.write_text(content, encoding="utf-8")

        findings = audit_script_file(script)
        categories = [f.category for f in findings]

        self.assertIn("Privilege Escalation", categories)
        self.assertIn("Interactive Prompt", categories)
        self.assertIn("Unchecked Binary Dependency", categories)
        self.assertIn("Hardcoded Path", categories)

    def test_audit_clean_script(self) -> None:
        script = self.root / "clean.sh"
        content = (
            "#!/bin/bash\n"
            "if command -v docker >/dev/null 2>&1; then\n"
            "    echo 'Docker is installed'\n"
            "fi\n"
        )
        script.write_text(content, encoding="utf-8")

        findings = audit_script_file(script)
        self.assertEqual(len(findings), 0)

    def test_generate_report(self) -> None:
        script = self.root / "setup.py"
        script.write_text("input('Confirm?')\n", encoding="utf-8")
        findings = audit_script_file(script)
        report = generate_audit_report(script, findings)
        self.assertIn("Interactive Prompt", report)


if __name__ == "__main__":
    unittest.main()
