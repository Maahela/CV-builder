"""Config and profile load/save. API key kept in OS keyring."""
import json
import os

import keyring

from .constants import (CONFIG_FILE, DEFAULT_OUTPUT, KEYRING_SERVICE,
                        KEYRING_USER, PROFILE_FILE)


def _get_api_key_from_keyring():
    """Read the API key from the OS keyring. Returns '' on any failure."""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:
        return ""


def _set_api_key_in_keyring(key):
    """Store (or delete if empty) the API key in the OS keyring."""
    try:
        if key:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                pass
    except Exception:
        pass


def load_config():
    """Return config dict. API key comes from OS keyring; if a legacy
    plaintext key is found in config.json it is migrated to the keyring
    and scrubbed from disk."""
    cfg = {"api_key": "", "output_folder": DEFAULT_OUTPUT}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                disk = json.load(f)
            cfg["output_folder"] = disk.get("output_folder") or DEFAULT_OUTPUT
            cfg["theme"] = disk.get("theme", "dark")
            legacy_key = (disk.get("api_key") or "").strip()
            if legacy_key:
                _set_api_key_in_keyring(legacy_key)
                try:
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump({"output_folder": cfg["output_folder"]},
                                  f, indent=2)
                except Exception:
                    pass
        except Exception:
            pass
    cfg["api_key"] = _get_api_key_from_keyring()
    return cfg


def save_config(cfg):
    """Persist non-secret config to disk; persist API key to OS keyring."""
    _set_api_key_in_keyring((cfg.get("api_key") or "").strip())
    on_disk = {"output_folder": cfg.get("output_folder") or DEFAULT_OUTPUT,
               "theme": cfg.get("theme", "dark")}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(on_disk, f, indent=2)


def load_profile():
    """Return master profile dict, or None if missing/corrupt."""
    if not os.path.exists(PROFILE_FILE):
        return None
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_profile(profile):
    """Persist master profile to JSON."""
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
