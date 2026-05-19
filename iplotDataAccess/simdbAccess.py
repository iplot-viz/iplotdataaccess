"""SIMDB REST API access — fetch simulation list and per-simulation metadata."""

import getpass
import threading
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

SIMDB_COLUMNS = ["alias", "ip", "b0", "workflow", "date", "description", "uuid", "dashboard_link", "imas_uri", "source"]
EMPTY_DF = pd.DataFrame(columns=SIMDB_COLUMNS)

_thread_local = threading.local()


def _get_session(auth: tuple):
    """Return a per-thread requests.Session, creating/reconfiguring as needed."""
    import requests
    session = getattr(_thread_local, "session", None)
    if session is None or getattr(_thread_local, "session_auth", None) != auth:
        session = requests.Session()
        session.auth = auth
        session.headers.update({"User-Agent": "it_script_basic", "Accept": "application/json"})
        _thread_local.session = session
        _thread_local.session_auth = auth
    return session


def fetch_simulation_metadata(metadata_url_template: str, uuid, auth: tuple) -> dict:
    """Fetch metadata for a single simulation and return a flat {element: value} dict."""
    try:
        uuid_str = uuid.get("hex", "") if isinstance(uuid, dict) else str(uuid)
        url = metadata_url_template.format(uuid=uuid_str)
        session = _get_session(auth)
        resp = session.get(url, timeout=30)
        if not resp.ok:
            logger.debug(f"Metadata fetch failed for {uuid_str}: {resp.status_code}")
            return {}
        if "application/json" not in resp.headers.get("Content-Type", ""):
            return {}
        body = resp.json()
        if isinstance(body, dict):
            imas_uri = ""
            for entry in body.get("inputs", []) + body.get("outputs", []):
                uri = entry.get("uri", "")
                if isinstance(uri, str) and uri.startswith("imas:"):
                    imas_uri = uri
                    break
            items = body.get("metadata", [])
        else:
            imas_uri = ""
            items = body
        if not isinstance(items, list):
            return {}
        result = {e["element"]: e["value"] for e in items if "element" in e and "value" in e}
        result["_imas_uri"] = imas_uri
        return result
    except Exception as e:
        logger.info(f"Metadata fetch exception for {uuid}: {e}")
        return {}


def _decode_array(raw) -> Optional[np.ndarray]:
    """Decode a SIMDB serialised numpy array value."""
    if isinstance(raw, dict) and raw.get("_type") in ("numpy.ndarray", "numpy.float64", "numpy.int64"):
        import base64
        return np.frombuffer(base64.b64decode(raw["bytes"]), dtype=np.dtype(raw["dtype"]))
    if isinstance(raw, (list, tuple)):
        return np.asarray(raw, dtype=float)
    return None


class SimDBClient:
    """Fetches the full simulation list (with metadata) from the SIMDB REST API."""

    KEYRING_SERVICE = "iplotDataAccess_simdb"

    def __init__(self, config: dict):
        self.config = config

    # Credential helpers
    def _resolve_credentials(self) -> Optional[Tuple[str, str]]:
        """Return (username, password) or None if the user cancels."""
        username = self.config.get("simdb_user", getpass.getuser()) or getpass.getuser()
        password = self.config.get("simdb_password", "")

        # 1. Try keyring
        if not password:
            try:
                import keyring
                stored = keyring.get_password(self.KEYRING_SERVICE, username)
                if stored:
                    logger.info("Loaded SIMDB credentials from keyring")
                    password = stored
            except Exception as e:
                logger.debug(f"Keyring not available: {e}")

        # 2. Prompt user
        if not password:
            try:
                from PySide6.QtWidgets import QInputDialog, QLineEdit, QApplication
                from PySide6.QtCore import Qt
                app = QApplication.instance()
                if app is not None:
                    username, ok = QInputDialog.getText(
                        None, "SIMDB Login", "Username:", text=username,
                        flags=Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint,
                    )
                    if not ok or not username:
                        logger.warning("SIMDB login cancelled by user")
                        return None
                    password, ok = QInputDialog.getText(
                        None, "SIMDB Login", f"Password for {username}:",
                        QLineEdit.EchoMode.Password,
                        flags=Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint,
                    )
                    if not ok or not password:
                        logger.warning("SIMDB login cancelled by user")
                        return None
                else:
                    import getpass as _gp
                    entered = input(f"SIMDB Username [{username}]: ").strip()
                    if entered:
                        username = entered
                    password = _gp.getpass(f"SIMDB Password for {username}: ")
            except Exception as e:
                logger.warning(f"Could not prompt for credentials: {e}")
                return None

        return username, password

    def _save_credentials(self, username: str, password: str):
        if self.config.get("simdb_password"):
            return  # already in config, no need to persist
        try:
            import keyring
            keyring.set_password(self.KEYRING_SERVICE, username, password)
            logger.debug("SIMDB credentials saved to keyring")
        except Exception as e:
            logger.debug(f"Could not save to keyring: {e}")

    def _clear_credentials(self, username: str):
        try:
            import keyring
            keyring.delete_password(self.KEYRING_SERVICE, username)
        except Exception:
            pass

    # HTTP helpers
    def _do_get(self, url: str, auth: tuple, page: Optional[int] = None):
        import requests
        headers = {"User-Agent": "it_script_basic", "Accept": "application/json"}
        if page is not None:
            headers["simdb-page"] = str(page)
        return requests.get(url, auth=auth, headers=headers, timeout=60)

    # Main fetch
    def fetch_pulses(self) -> pd.DataFrame:
        """Fetch and return the full simulation list as a DataFrame."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        simdb_url = self.config.get("simdb_url", "https://simdb.iter.org/scenarios/api/v1.2/simulations")
        simdb_metadata_url = self.config.get(
            "simdb_metadata_url",
            "https://simdb.iter.org/scenarios/api/v1.2/simulation/{uuid}",
        )

        creds = self._resolve_credentials()
        if creds is None:
            return EMPTY_DF.copy()
        username, password = creds
        auth = (username, password)

        # Page 1: validate credentials + get total count
        try:
            response = self._do_get(simdb_url, auth)
        except Exception as e:
            if "SSL" in type(e).__name__ or "CERTIFICATE" in str(e).upper():
                logger.error(
                    "SIMDB TLS certificate verification failed. "
                    "set the REQUESTS_CA_BUNDLE environment variable to the ITER CA bundle path\n"
                )
            else:
                logger.exception(f"SIMDB connection error: {e}")
            return EMPTY_DF.copy()

        if response.status_code in (401, 403):
            logger.warning(f"SIMDB authentication failed ({response.status_code}). Clearing stored credentials.")
            self._clear_credentials(username)
            return EMPTY_DF.copy()
        if not response.ok:
            logger.error(f"SIMDB request failed: {response.status_code} {response.reason}")
            return EMPTY_DF.copy()
        if "application/json" not in response.headers.get("Content-Type", ""):
            logger.error(f"SIMDB returned non-JSON response (content-type: {response.headers.get('Content-Type')})")
            logger.error(f"Response body (first 500 chars): {response.text[:500]}")
            return EMPTY_DF.copy()

        data = response.json()
        items = list(data.get("results", []))
        total = data.get("count", len(items))
        page_size = len(items) or 100
        num_pages = (total + page_size - 1) // page_size
        logger.info(f"Total simulations: {total}, pages: {num_pages}")

        # Remaining pages in parallel
        if num_pages > 1:
            def _fetch_page(page):
                try:
                    r = self._do_get(simdb_url, auth, page=page)
                    if r.ok and "application/json" in r.headers.get("Content-Type", ""):
                        return r.json().get("results", [])
                    logger.warning(f"Page {page} failed: {r.status_code}")
                except Exception as e:
                    logger.warning(f"Page {page} error: {e}")
                return []

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(_fetch_page, p): p for p in range(2, num_pages + 1)}
                for future in as_completed(futures):
                    items.extend(future.result())

        logger.info(f"Fetched {len(items)} records out of {total} total")

        # Metadata in parallel
        uuid_list = [item.get("uuid", "") for item in items]
        meta_results: dict = {}
        logger.info(f"Fetching metadata for {len(uuid_list)} simulations...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {
                executor.submit(fetch_simulation_metadata, simdb_metadata_url, uuid, auth): idx
                for idx, uuid in enumerate(uuid_list) if uuid
            }
            done = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                meta_results[idx] = future.result()
                done += 1
                if done % 100 == 0:
                    logger.info(f"Metadata fetched: {done}/{len(uuid_list)}")

        logger.info(f"Metadata fetch complete: {len(meta_results)} results")

        # Build records
        records = []
        for idx, item in enumerate(items):
            meta = meta_results.get(idx, {})

            ip_arr = _decode_array(meta.get("global_quantities.ip.value", ""))
            ip_val = f"{ip_arr.flat[np.argmax(np.abs(ip_arr))]:.3f}" if ip_arr is not None and ip_arr.size > 0 else ""

            b0_arr = _decode_array(meta.get("global_quantities.b0.value", ""))
            b0_val = (
                f"{b0_arr.min() if np.sign(b0_arr).min() < 0 else b0_arr.max():.3f}"
                if b0_arr is not None and b0_arr.size > 0 else ""
            )

            uuid_raw = item.get("uuid", {})
            uuid_hex = uuid_raw.get("hex", "") if isinstance(uuid_raw, dict) else str(uuid_raw)
            dashboard_link = f"https://simdb.iter.org/dashboard/uuid/{uuid_hex}" if uuid_hex else ""

            records.append({
                "uuid": uuid_hex,
                "dashboard_link": dashboard_link,
                "alias": item.get("alias", ""),
                "ip": ip_val,
                "b0": b0_val,
                "workflow": meta.get("code.name", ""),
                "date": meta.get("ids_properties.creation_date", "") or str(item.get("datetime", ""))[:19],
                "imas_uri": meta.get("_imas_uri", ""),
                "description": meta.get("ids_properties.comment", ""),
            })

        if records:
            self._save_credentials(username, password)

        return pd.DataFrame(records) if records else EMPTY_DF.copy()
