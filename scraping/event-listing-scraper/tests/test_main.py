import unittest

from main import (
    Event,
    export_ics,
    export_json,
    export_markdown,
    filter_events,
    parse_ical,
    parse_json_ld,
)


class TestEventListingScraper(unittest.TestCase):

    def setUp(self):
        self.sample_json_ld = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@type": "Event",
            "name": "Tech Conference 2026",
            "startDate": "2026-09-15T09:00:00",
            "endDate": "2026-09-16T17:00:00",
            "location": {
                "@type": "Place",
                "name": "Convention Center"
            },
            "category": "Technology",
            "description": "Annual tech summit"
        }
        </script>
        </head>
        </html>
        """

        self.sample_ical = """
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Python Workshop
DTSTART:20261001T100000Z
DTEND:20261001T120000Z
LOCATION:Online / Zoom
CATEGORIES:Education
DESCRIPTION:Hands-on Python coding session
END:VEVENT
END:VCALENDAR
        """

    def test_parse_json_ld(self):
        events = parse_json_ld(self.sample_json_ld)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Tech Conference 2026")
        self.assertEqual(events[0].location, "Convention Center")
        self.assertEqual(events[0].category, "Technology")

    def test_parse_ical(self):
        events = parse_ical(self.sample_ical)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Python Workshop")
        self.assertEqual(events[0].location, "Online / Zoom")

    def test_filter_events(self):
        e1 = Event("E1", "2026-05-01", location="New York", category="Music")
        e2 = Event("E2", "2026-06-01", location="Boston", category="Tech")
        events = [e1, e2]

        filtered_date = filter_events(events, start_date="2026-05-15")
        self.assertEqual(len(filtered_date), 1)
        self.assertEqual(filtered_date[0].title, "E2")

        filtered_cat = filter_events(events, category="music")
        self.assertEqual(len(filtered_cat), 1)
        self.assertEqual(filtered_cat[0].title, "E1")

    def test_exports(self):
        e = Event("Test", "2026-08-01", location="Room A")
        md = export_markdown([e])
        self.assertIn("# Event Listings", md)
        self.assertIn("Test", md)

        ics = export_ics([e])
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("SUMMARY:Test", ics)

        json_out = export_json([e])
        self.assertIn('"title": "Test"', json_out)


if __name__ == "__main__":
    unittest.main()
