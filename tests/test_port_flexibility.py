import socket

import ss_dcl.app as flask_app


def test_find_free_port_returns_a_port():
    port = flask_app._find_free_port(9000)
    assert isinstance(port, int)
    assert 9000 <= port < 9100


def test_find_free_port_skips_occupied():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        occupied_port = s.getsockname()[1]
        port = flask_app._find_free_port(occupied_port)
        assert port != occupied_port
        assert port > occupied_port
    finally:
        s.close()


def test_find_free_port_raises_when_all_occupied():
    sockets = []
    try:
        for port in range(19876, 19876 + 10):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            sockets.append(s)
        try:
            flask_app._find_free_port(19876, max_tries=10)
            raise AssertionError("Should have raised")
        except RuntimeError as e:
            assert "No free port" in str(e)
    finally:
        for s in sockets:
            s.close()


def test_selected_port_is_int():
    assert isinstance(flask_app.SELECTED_PORT, int)
    assert flask_app.SELECTED_PORT >= 0
