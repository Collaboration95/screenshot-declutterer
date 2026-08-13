"""Logging config + request correlation tests (audit #85)."""

import logging
import logging.handlers

import ss_dcl.logging_config as logging_config
from ss_dcl.logging_config import RequestIdFilter, configure_logging


def _find_file_handler():
    handlers = logging.getLogger().handlers
    return next(
        (h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)),
        None,
    )


def test_access_log_record_shape(client, caplog):
    c, _ = client
    with caplog.at_level(logging.INFO, logger="ss_dcl.app"):
        r = c.get("/api/health")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    records = [rec for rec in caplog.records if "ACCESS" in rec.getMessage()]
    assert len(records) == 1
    rec = records[0]
    assert "GET" in rec.getMessage()
    assert "/api/health" in rec.getMessage()
    assert "200" in rec.getMessage()
    assert rec.request_id == r.headers["X-Request-ID"]
    assert rec.request_id != "-"


def test_request_ids_unique_per_request(client):
    c, _ = client
    r1 = c.get("/api/health")
    r2 = c.get("/api/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_configure_logging_creates_file_handler(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("SS_DCL_LOG_FILE", str(log_file))
    configure_logging(force=True)
    handler = _find_file_handler()
    assert handler is not None
    assert handler.baseFilename == str(log_file)
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 3


def test_configure_logging_writes_records(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("SS_DCL_LOG_FILE", str(log_file))
    configure_logging(force=True)
    logging.getLogger("ss_dcl.app").info("hello-logging-test")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text()
    assert "hello-logging-test" in content
    assert "[" in content  # formatted with request_id placeholder


def test_request_id_filter_defaults_to_dash():
    record = logging.LogRecord("ss_dcl.test", logging.INFO, __file__, 1, "msg", None, None)
    assert RequestIdFilter().filter(record) is True
    assert getattr(record, "request_id", None) == "-"


def test_new_request_id_is_12_hex_chars():
    rid = logging_config.new_request_id()
    assert len(rid) == 12
    assert all(ch in "0123456789abcdef" for ch in rid)


def test_security_headers_still_set_after_middleware(client):
    c, _ = client
    r = c.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
