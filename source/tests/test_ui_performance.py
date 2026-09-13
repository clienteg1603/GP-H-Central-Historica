import unittest

import gph_ui_performance as perf


class FakeApp:
    def __init__(self):
        self._page = "search"
        self._callbacks = {}
        self._next_id = 0
        self.colors = {
            "card": "#1", "card2": "#2", "entry": "#3", "text": "#4",
            "muted": "#5", "border": "#6", "selection": "#7", "hover": "#8",
            "accent": "#9", "accent_hover": "#10", "success": "#11",
            "warning": "#12", "danger": "#13",
        }

    def after(self, delay, callback):
        self._next_id += 1
        handle = f"after-{self._next_id}"
        self._callbacks[handle] = (delay, callback)
        return handle

    def after_cancel(self, handle):
        self._callbacks.pop(handle, None)

    def run_all(self):
        callbacks = list(self._callbacks.items())
        self._callbacks.clear()
        for _handle, (_delay, callback) in callbacks:
            callback()


class FakeCentral:
    UI_FONT_FAMILY = "Segoe UI"
    UI_FONT_SEMIBOLD = "Segoe UI Semibold"
    UI_FONT_SIZES = {"body": 10, "secondary": 9}
    UI_TABLE_ROWHEIGHT = 30


class UIPerformanceTests(unittest.TestCase):
    def test_layer_is_performance_only(self):
        self.assertTrue(perf.PERFORMANCE_INFO["performance_only"])
        self.assertFalse(perf.PERFORMANCE_INFO["changes_meta"])
        self.assertFalse(perf.PERFORMANCE_INFO["changes_database"])
        self.assertFalse(perf.PERFORMANCE_INFO["changes_generators"])
        self.assertFalse(perf.PERFORMANCE_INFO["changes_methods"])
        self.assertFalse(perf.PERFORMANCE_INFO["changes_financial"])
        self.assertTrue(perf.PERFORMANCE_INFO["combobox_popup_native"])

    def test_polish_is_deferred_and_coalesced(self):
        app = FakeApp()
        calls = []
        perf.schedule_polish(app, "analysis", lambda: calls.append("first"), expected_pages=("search",))
        perf.schedule_polish(app, "analysis", lambda: calls.append("second"), expected_pages=("search",))
        self.assertEqual(calls, [])
        self.assertEqual(len(app._callbacks), 1)
        self.assertEqual(app._gph_ui_performance["cancelled"], 1)
        app.run_all()
        self.assertEqual(calls, ["second"])
        self.assertIn("analysis", app._gph_ui_performance["polish_ms"])

    def test_stale_page_polish_is_discarded(self):
        app = FakeApp()
        calls = []
        perf.schedule_polish(app, "analysis", lambda: calls.append("ran"), expected_pages=("search",))
        app._page = "methods"
        app.run_all()
        self.assertEqual(calls, [])

    def test_style_cache_reuses_same_theme_and_invalidates_on_change(self):
        app = FakeApp()
        calls = []

        def configure(_app, _central):
            calls.append("configured")

        cached = perf._cached_style_config("analysis", configure)
        cached(app, FakeCentral)
        cached(app, FakeCentral)
        self.assertEqual(calls, ["configured"])
        app.colors["card"] = "#changed"
        cached(app, FakeCentral)
        self.assertEqual(calls, ["configured", "configured"])

    def test_defer_delay_is_small_but_yields_to_tk(self):
        self.assertGreaterEqual(perf.DEFER_MS, 1)
        self.assertLessEqual(perf.DEFER_MS, 10)


if __name__ == "__main__":
    unittest.main()
