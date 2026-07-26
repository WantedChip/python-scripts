import unittest

from main import SwallowTracer


class TestSwallowTrace(unittest.TestCase):

    def test_tracer_catches_suppressed_exception(self):
        tracer = SwallowTracer()

        def dummy_swallower():
            try:
                _ = 1 / 0
            except ZeroDivisionError:
                return None

        tracer.start()
        dummy_swallower()
        tracer.stop()

        summary = tracer.get_summary()
        self.assertGreater(summary.total_raised, 0)
        self.assertGreater(len(summary.suppressed_records), 0)

        record = summary.suppressed_records[0]
        self.assertEqual(record.exception_event.exc_type, "ZeroDivisionError")
        self.assertTrue(record.is_fallback_return)

    def test_tracer_ignores_unhandled_exception(self):
        tracer = SwallowTracer()

        def normal_func():
            return 42

        tracer.start()
        normal_func()
        tracer.stop()

        summary = tracer.get_summary()
        self.assertEqual(summary.total_raised, 0)
        self.assertEqual(len(summary.suppressed_records), 0)


if __name__ == "__main__":
    unittest.main()
