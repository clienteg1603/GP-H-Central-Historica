import unittest

import gph_ui_windowed as windowed


class FakeGrid:
    def __init__(self):
        self.rows = {}

    def grid_rowconfigure(self, row, **kwargs):
        self.rows[row] = kwargs


class FakeAppInstance:
    def __init__(self):
        self.home_grid = FakeGrid()
        self.home_calls = 0
        self.maximize_calls = 0


class FakeAppClass:
    def _maximize_main_window(self):
        self.maximize_calls += 1

    def show_home(self):
        self.home_calls += 1
        return "home-ok"


class FakeCentral:
    App = FakeAppClass


class WindowedLayoutTests(unittest.TestCase):
    def setUp(self):
        # O instalador é idempotente; cada teste recebe uma classe nova para
        # validar o contrato sem depender da ordem da suíte.
        class App:
            def __init__(self):
                self.home_grid = FakeGrid()
                self.home_calls = 0
                self.maximize_calls = 0

            def _maximize_main_window(self):
                self.maximize_calls += 1

            def show_home(self):
                self.home_calls += 1
                return "home-ok"

        class Central:
            pass

        Central.App = App
        self.central = Central

    def test_layer_is_visual_only(self):
        info = windowed.WINDOWED_LAYOUT_INFO
        self.assertTrue(info["visual_only"])
        self.assertFalse(info["changes_meta"])
        self.assertFalse(info["changes_database"])
        self.assertFalse(info["changes_generators"])
        self.assertFalse(info["changes_methods"])
        self.assertFalse(info["changes_financial"])
        self.assertFalse(info["changes_results"])
        self.assertFalse(info["forces_maximized_startup"])

    def test_home_rows_can_shrink_in_normal_window(self):
        app = FakeAppInstance()
        self.assertTrue(windowed.compact_home_for_windowed(app))
        self.assertEqual(set(app.home_grid.rows), set(range(5)))
        for row in range(5):
            cfg = app.home_grid.rows[row]
            self.assertEqual(cfg["minsize"], windowed.HOME_ANIMAL_ROW_MINSIZE)
            self.assertEqual(cfg["weight"], 1)
            self.assertEqual(cfg["uniform"], "animalrows")
        self.assertLess(windowed.HOME_ANIMAL_ROW_MINSIZE, 88)

    def test_installer_removes_forced_maximize_and_keeps_home(self):
        windowed.install_windowed_layout(self.central)
        app = self.central.App()

        # O callback legado continua podendo ser agendado, porém agora é no-op.
        app._maximize_main_window()
        self.assertEqual(app.maximize_calls, 0)

        result = app.show_home()
        self.assertEqual(result, "home-ok")
        self.assertEqual(app.home_calls, 1)
        self.assertEqual(len(app.home_grid.rows), 5)

    def test_installer_is_idempotent(self):
        first = windowed.install_windowed_layout(self.central)
        wrapped = self.central.App.show_home
        second = windowed.install_windowed_layout(self.central)
        self.assertIs(self.central.App.show_home, wrapped)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
