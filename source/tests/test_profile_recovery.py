import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gph_profile_recovery as recovery


CODE_RE = re.compile(r"^GPH-[A-Z0-9]{4}-[A-Z0-9]{4}$")


def fake_central(root: Path):
    data = root / "local" / "dados"
    data.mkdir(parents=True, exist_ok=True)

    def normalize(value):
        raw = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
        if raw.startswith("GPH"):
            raw = raw[3:]
        if len(raw) == 8:
            return f"GPH-{raw[:4]}-{raw[4:]}"
        return str(value or "").strip().upper()

    ns = SimpleNamespace()
    ns.DATA_DIR = data
    ns.ROOT = root / "install"
    ns.ROOT.mkdir(parents=True, exist_ok=True)
    ns.ACCOUNT_PROFILE_PATH = data / "account_profile.json"
    ns.normalize_profile_code = normalize
    ns.valid_profile_code = lambda value: bool(CODE_RE.fullmatch(normalize(value)))
    ns.default_device_name = lambda: "PC-TESTE"
    ns.load_account_profile = lambda: None
    ns.save_account_profile = lambda data: data
    return ns


class ProfileRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(
            os.environ,
            {
                "USERPROFILE": str(self.root / "user"),
                "LOCALAPPDATA": str(self.root / "local"),
                "APPDATA": str(self.root / "roaming"),
                "OneDrive": "",
                "OneDriveCommercial": "",
                "OneDriveConsumer": "",
                "Dropbox": "",
            },
            clear=False,
        )
        self.env.start()
        self.central = fake_central(self.root)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_salva_codigo_de_json_truncado(self):
        path = Path(self.central.ACCOUNT_PROFILE_PATH)
        path.write_text('{"profile_name":"Giovane","profile_code":"GPH-ABCD-2345"', encoding="utf-8")
        profile, source = recovery.recover_profile(self.central)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["profile_code"], "GPH-ABCD-2345")
        self.assertEqual(profile["profile_name"], "Giovane")
        self.assertIn("account_profile.json", source)

    def test_recupera_perfil_de_pasta_portatil_antiga(self):
        old = self.central.ROOT / "dados"
        old.mkdir(parents=True, exist_ok=True)
        (old / "account_profile.json").write_text(json.dumps({
            "profile_name": "Meu perfil",
            "profile_code": "GPH-QWER-6789",
            "remember_login": True,
            "device_id": "device-antigo",
            "device_name": "PC-TESTE",
        }), encoding="utf-8")
        profile, _ = recovery.recover_profile(self.central)
        self.assertEqual(profile["profile_code"], "GPH-QWER-6789")
        self.assertEqual(profile["device_id"], "device-antigo")

    def test_nao_escolhe_entre_dois_codigos_ambiguos(self):
        p1 = self.central.DATA_DIR / "logs" / "um.log"
        p2 = self.central.DATA_DIR / "exportacoes" / "dois.txt"
        p1.parent.mkdir(parents=True, exist_ok=True)
        p2.parent.mkdir(parents=True, exist_ok=True)
        p1.write_text("GPH-AAAA-2222", encoding="utf-8")
        p2.write_text("GPH-BBBB-3333", encoding="utf-8")
        profile, source = recovery.recover_profile(self.central)
        self.assertIsNone(profile)
        self.assertIsNone(source)

    def test_patch_grava_atomico_e_backup(self):
        original = {
            "profile_name": "Giovane",
            "profile_code": "GPH-ZZZZ-8888",
            "remember_login": True,
            "device_id": "dev",
            "device_name": "PC-TESTE",
        }
        self.central.load_account_profile = lambda: dict(original)
        recovery.install_profile_recovery(self.central)
        loaded = self.central.load_account_profile()
        self.assertEqual(loaded["profile_code"], original["profile_code"])
        main = json.loads(Path(self.central.ACCOUNT_PROFILE_PATH).read_text(encoding="utf-8"))
        backup = json.loads((Path(self.central.ACCOUNT_PROFILE_PATH).parent / recovery.PROFILE_BACKUP_NAME).read_text(encoding="utf-8"))
        self.assertEqual(main["profile_code"], original["profile_code"])
        self.assertEqual(backup["profile_code"], original["profile_code"])

    def test_remember_false_continua_false(self):
        original = {
            "profile_name": "Perfil",
            "profile_code": "GPH-CCCC-4444",
            "remember_login": False,
        }
        self.central.load_account_profile = lambda: dict(original)
        recovery.install_profile_recovery(self.central)
        loaded = self.central.load_account_profile()
        self.assertFalse(loaded["remember_login"])


if __name__ == "__main__":
    unittest.main()
