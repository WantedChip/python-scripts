"""File Share Audit Tool

Scans directories prior to sharing or uploading to identify sensitive data including:
- API Keys / Tokens (AWS, OpenAI, GitHub, generic secrets)
- Environment files (.env) and private logs (.log, .pem, .key)
- Git history (.git) and hidden files
- Usernames exposed in directory paths
- EXIF GPS location metadata in image files
"""

# pylint: disable=too-many-branches,too-many-locals,too-few-public-methods
# pylint: disable=protected-access,missing-function-docstring

import argparse
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Pillow for EXIF parsing
PIL_AVAILABLE = True
try:
    from PIL import ExifTags, Image
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class AuditFinding:
    """Represents a security/privacy finding during audit."""

    filepath: str
    category: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    description: str
    line_number: Optional[int] = None


@dataclass
class AuditReport:
    """Audit execution summary report."""

    target_dir: str
    total_files_scanned: int
    findings: List[AuditFinding] = field(default_factory=list)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "HIGH")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "MEDIUM")

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "LOW")

    def print_summary(self) -> None:
        """Prints formatted terminal audit report summary."""
        print("=" * 60)
        print(f" FILE SHARE AUDIT REPORT for: {self.target_dir}")
        print("=" * 60)
        print(f" Total Files Scanned: {self.total_files_scanned}")
        counts_str = (
            f"HIGH: {self.high_count} | MEDIUM: {self.medium_count} | "
            f"LOW: {self.low_count}"
        )
        print(f" Findings Summary: {counts_str}")
        print("-" * 60)

        if not self.findings:
            print(" [SAFE] No sensitive patterns or privacy issues detected.")
            return

        for idx, finding in enumerate(self.findings, 1):
            line_str = f" (Line {finding.line_number})" if finding.line_number else ""
            hdr = f"{idx}. [{finding.severity}] {finding.category}"
            print(f" {hdr}: {finding.description}")
            print(f"    File: {finding.filepath}{line_str}\n")


class FileShareAuditor:
    """Audits directory trees for sensitive API keys, hidden configs, etc."""

    gh_pat = r"\b(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})\b"
    sec_pat = (
        r"(?i)\b(api_key|secret_key|private_key|auth_token)\s*[:=]\s*"
        r"['\"]([a-zA-Z0-9_\-]{16,})['\"]"
    )

    API_KEY_PATTERNS = [
        ("AWS Access Key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "HIGH"),
        ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9]{32,}\b"), "HIGH"),
        ("GitHub Token", re.compile(gh_pat), "HIGH"),
        ("Generic Secret", re.compile(sec_pat), "HIGH"),
    ]

    SENSITIVE_EXTENSIONS = {".env", ".pem", ".key", ".p12", ".pfx", ".id_rsa"}
    SENSITIVE_FILENAME_PATTERNS = {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
    }

    def __init__(self, username: Optional[str] = None) -> None:
        """Initialize auditor.

        Args:
            username: Target username to flag in paths.
        """
        env_user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        self.username = username or env_user

    def audit_directory(self, target_dir: str) -> AuditReport:
        """Scans directory recursively and generates audit findings.

        Args:
            target_dir: Directory path to audit.

        Returns:
            AuditReport object containing list of findings.
        """
        target_dir = os.path.abspath(target_dir)
        report = AuditReport(target_dir=target_dir, total_files_scanned=0)

        for root, dirs, files in os.walk(target_dir):
            # Check directory names for hidden/git folders
            for d in dirs:
                dir_path = os.path.join(root, d)
                if d == ".git":
                    report.findings.append(
                        AuditFinding(
                            filepath=dir_path,
                            category="Git History",
                            severity="MEDIUM",
                            description="Exposed .git repository directory found.",
                        )
                    )
                elif d.startswith("."):
                    report.findings.append(
                        AuditFinding(
                            filepath=dir_path,
                            category="Hidden Directory",
                            severity="LOW",
                            description=f"Hidden directory detected: '{d}'",
                        )
                    )

            for f in files:
                filepath = os.path.join(root, f)
                report.total_files_scanned += 1

                # Check path username
                self._check_path_username(filepath, report)

                # Check hidden / sensitive filenames
                self._check_filename_rules(filepath, f, report)

                # Check EXIF data if image
                if f.lower().endswith((".jpg", ".jpeg", ".tiff", ".png")):
                    self._check_exif_gps(filepath, report)

                # Scan text contents for secrets
                self._check_text_content(filepath, report)

        return report

    def _check_path_username(self, filepath: str, report: AuditReport) -> None:
        """Flags presence of local system username in file paths."""
        if self.username and self.username.lower() in filepath.lower():
            report.findings.append(
                AuditFinding(
                    filepath=filepath,
                    category="Username Exposure",
                    severity="LOW",
                    description=(
                        f"File path contains user account name '{self.username}'"
                    ),
                )
            )

    def _check_filename_rules(
        self, filepath: str, filename: str, report: AuditReport
    ) -> None:
        """Checks filename against sensitive file rules."""
        ext = os.path.splitext(filename)[1].lower()
        is_sens = (
            filename.lower() in self.SENSITIVE_FILENAME_PATTERNS
            or ext in self.SENSITIVE_EXTENSIONS
        )
        if is_sens:
            report.findings.append(
                AuditFinding(
                    filepath=filepath,
                    category="Sensitive File",
                    severity="HIGH",
                    description=f"Sensitive file type detected: {filename}",
                )
            )
        elif filename.endswith(".log"):
            report.findings.append(
                AuditFinding(
                    filepath=filepath,
                    category="Private Log",
                    severity="MEDIUM",
                    description="Log file detected with potential runtime data.",
                )
            )
        elif filename.startswith(".") and filename not in {".gitignore"}:
            report.findings.append(
                AuditFinding(
                    filepath=filepath,
                    category="Hidden File",
                    severity="LOW",
                    description=f"Hidden file detected: {filename}",
                )
            )

    def _check_exif_gps(self, filepath: str, report: AuditReport) -> None:
        """Parses image EXIF data for GPS location coordinates."""
        if not PIL_AVAILABLE:
            return
        try:
            with Image.open(filepath) as img:
                exif_data = img._getexif()  # type: ignore[attr-defined]
                if exif_data:
                    for tag_id in exif_data:
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag_name == "GPSInfo":
                            report.findings.append(
                                AuditFinding(
                                    filepath=filepath,
                                    category="EXIF GPS Data",
                                    severity="HIGH",
                                    description="Image contains embedded GPS metadata.",
                                )
                            )
                            break
        except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
            pass

    def _check_text_content(self, filepath: str, report: AuditReport) -> None:
        """Scans plain text files line-by-line for secret keys and credentials."""
        # Skip large binary files
        if os.path.getsize(filepath) > 5 * 1024 * 1024:
            return

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f, 1):
                    for pattern_name, regex, severity in self.API_KEY_PATTERNS:
                        if regex.search(line):
                            report.findings.append(
                                AuditFinding(
                                    filepath=filepath,
                                    category="API Key / Credential",
                                    severity=severity,
                                    description=f"Potential {pattern_name} detected",
                                    line_number=line_idx,
                                )
                            )
        except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
            pass


def main() -> None:
    """CLI entry point for file share audit."""
    parser = argparse.ArgumentParser(
        description="Audit directory before uploading/sharing."
    )
    parser.add_argument("directory", type=str, help="Target directory to audit")
    parser.add_argument(
        "--username", type=str, help="Explicit username to flag in file paths"
    )

    args = parser.parse_args()

    auditor = FileShareAuditor(username=args.username)
    report = auditor.audit_directory(args.directory)
    report.print_summary()


if __name__ == "__main__":
    main()
