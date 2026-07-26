import tempfile
import unittest
from pathlib import Path

from main import CommandProfiler


class TestDirtyGenerator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_profile_command_creates_file(self):
        cmd = (
            f'python -c "open(\'{self.root_dir / "out.tmp"}\', \'w\').write(\'test\')"'
        )

        profiler = CommandProfiler(self.root_dir)
        report = profiler.profile_command(cmd)

        self.assertTrue(report.is_dirty)
        self.assertIn("out.tmp", report.created_files)

    def test_baseline_recording_and_validation(self):
        baseline_file = self.root_dir / "baseline.json"
        log_path = self.root_dir / "build.log"
        cmd = f"python -c \"open('{log_path}', 'w').write('done')\""

        profiler = CommandProfiler(self.root_dir, baseline_path=baseline_file)
        report1 = profiler.profile_command(cmd, record_as_baseline=True)

        self.assertEqual(len(report1.violations), 0)
        self.assertTrue(baseline_file.exists())

        # Second run should match baseline and have 0 violations
        report2 = profiler.profile_command(cmd)
        self.assertEqual(len(report2.violations), 0)


if __name__ == "__main__":
    unittest.main()
