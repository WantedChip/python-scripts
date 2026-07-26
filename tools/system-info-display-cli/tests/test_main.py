import unittest

from main import format_bytes, format_duration, get_system_info, render_dashboard


class TestSystemInfoDisplay(unittest.TestCase):
    """Unit tests for System Info Display CLI."""

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")

    def test_format_duration(self):
        self.assertEqual(format_duration(65), "1m 5s")
        self.assertEqual(format_duration(3665), "1h 1m 5s")
        self.assertEqual(format_duration(90065), "1d 1h 1m 5s")

    def test_get_system_info_structure(self):
        info = get_system_info(top_n_processes=2)
        self.assertIn("system", info)
        self.assertIn("cpu", info)
        self.assertIn("memory", info)
        self.assertIn("disk", info)
        self.assertIn("top_processes", info)

        sys_data = info["system"]
        self.assertIn("os_name", sys_data)
        self.assertIn("hostname", sys_data)

    def test_render_dashboard(self):
        info = get_system_info(top_n_processes=1)
        rendered = render_dashboard(info)
        self.assertIn("SYSTEM INFORMATION DASHBOARD", rendered)
        self.assertIn(info["system"]["hostname"], rendered)


if __name__ == "__main__":
    unittest.main()
