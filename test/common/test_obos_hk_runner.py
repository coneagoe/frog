import pytest
from types import SimpleNamespace
import json
import sys

# The tests now exercise the shared runner contract. Importing the runner
# module is expected to fail for Task 1 (module not implemented yet).
from common.obos_hk_runner import ObosHkSkip, run_obos_hk_backtest


def test_skip_when_redis_not_success():
    """If Redis indicates the upstream download was not successful, the runner must
    raise ObosHkSkip (Airflow skip semantics). Ensure subprocess and email are not called.
    """

    redis_called = False

    def fake_redis_get(key):
        nonlocal redis_called
        # ensure the runner looks up the expected download key exactly
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        redis_called = True
        return json.dumps({"result": "fail"})

    called = {"subprocess": False, "email": False}

    def spy_run_subprocess(cmd, *a, **k):
        # If invoked, mark and return a benign success
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def spy_send_email(subject, body, to=None):
        called["email"] = True

    # Call the real API with injected dependency and a deterministic market-open check
    with pytest.raises(ObosHkSkip):
        run_obos_hk_backtest(redis_get=fake_redis_get, is_market_open=lambda date=None: True, run_subprocess=spy_run_subprocess, send_email=spy_send_email)

    # verify that side-effecting collaborators were not invoked
    assert not called["subprocess"]
    assert not called["email"]
    # and ensure we actually queried Redis
    assert redis_called


def test_missing_redis_result_does_not_skip_by_default():
    """Legacy Celery wrapper behavior should continue when the download marker is absent."""

    redis_called = False
    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        nonlocal redis_called
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        redis_called = True
        return None

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    res = run_obos_hk_backtest(
        redis_get=fake_redis_get,
        is_market_open=lambda date=None: True,
        run_subprocess=fake_run_subprocess,
        send_email=fake_send_email,
    )

    assert res.status == "success"
    assert redis_called
    assert called["subprocess"]
    assert called["email"]


def test_missing_redis_result_skips_when_required():
    """Explicit marker-required mode should skip when the download marker is absent."""

    redis_called = False
    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        nonlocal redis_called
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        redis_called = True
        return None

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    with pytest.raises(ObosHkSkip, match="download result missing"):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=lambda date=None: True,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
            require_download_result=True,
        )

    assert redis_called
    assert not called["subprocess"]
    assert not called["email"]


def test_redis_read_failure_raises_runtimeerror():
    """Redis read errors should hard-fail instead of being treated as Airflow skips."""

    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        raise ConnectionError("redis unavailable")

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    with pytest.raises(RuntimeError, match="failed to read Redis: redis unavailable"):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=lambda date=None: True,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )

    assert not called["subprocess"]
    assert not called["email"]


def test_malformed_redis_payload_raises_runtimeerror():
    """Malformed Redis payloads should hard-fail instead of being treated as skips."""

    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        return "{not-json"

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    with pytest.raises(RuntimeError, match="invalid download result"):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=lambda date=None: True,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )

    assert not called["subprocess"]
    assert not called["email"]


@pytest.mark.parametrize("payload", [[], 123, "success"])
def test_wrong_shape_redis_payload_raises_runtimeerror(payload):
    """Valid JSON payloads must still be objects with a result field."""

    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        return json.dumps(payload)

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    with pytest.raises(RuntimeError, match="invalid download result"):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=lambda date=None: True,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )

    assert not called["subprocess"]
    assert not called["email"]


@pytest.mark.parametrize("payload", [{}, {"date": "2025-04-01"}])
def test_object_payload_without_result_raises_runtimeerror(payload):
    """JSON objects without a usable result field must hard-fail."""

    called = {"subprocess": False, "email": False}

    def fake_redis_get(key):
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY

        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        return json.dumps(payload)

    def fake_run_subprocess(cmd, *a, **k):
        called["subprocess"] = True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_send_email(subject, body, to=None):
        called["email"] = True

    with pytest.raises(RuntimeError, match="invalid download result"):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=lambda date=None: True,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )

    assert not called["subprocess"]
    assert not called["email"]


def test_success_email_path():
    """When backtest subprocess succeeds, runner returns a success result and
    sends an email. Dependencies are injected as callables.
    """

    redis_called = False

    def fake_redis_get(key):
        nonlocal redis_called
        # exact Redis key contract
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        redis_called = True
        return json.dumps({"result": "success"})

    def fake_is_market_open(date=None):
        return True

    captured = {}
    counts = {"subprocess": 0, "email": 0}

    def fake_run_subprocess(cmd, *a, **k):
        # capture the invoked command, count invocation, and emulate successful subprocess
        captured['cmd'] = cmd
        counts["subprocess"] += 1
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    sent = {}

    def fake_send_email(subject, body, to=None):
        sent['subject'] = subject
        sent['body'] = body
        counts["email"] += 1

    res = run_obos_hk_backtest(
        redis_get=fake_redis_get,
        is_market_open=fake_is_market_open,
        run_subprocess=fake_run_subprocess,
        send_email=fake_send_email,
    )

    assert res.status == "success"
    assert "obos_hk" in res.email_subject
    assert "OK" in res.email_body
    # ensure our fake email sender was used
    assert "obos_hk" in sent.get('subject', '')
    # validate actual email payload
    assert "OK" in sent.get('body', '')

    # validate the subprocess argv structure
    cmd = captured.get('cmd')
    assert cmd is not None, "subprocess was not invoked"
    assert isinstance(cmd, (list, tuple)), f"expected argv list, got {type(cmd)}"
    # lock argv[0] and argv[1]
    assert cmd[0] == sys.executable
    assert cmd[1] == "backtest/obos_hk_9.py"
    # ensure options -s, -e, -f appear in order with paired values
    def _find_opt(argv, opt):
        try:
            return argv.index(opt)
        except ValueError:
            return -1
    i_s = _find_opt(cmd, "-s")
    i_e = _find_opt(cmd, "-e")
    i_f = _find_opt(cmd, "-f")
    assert i_s != -1 and i_e != -1 and i_f != -1
    assert i_s < i_e < i_f
    for idx in (i_s, i_e, i_f):
        assert idx + 1 < len(cmd)
        assert cmd[idx + 1], "option value missing"

    # enforce exactly one subprocess invocation and exactly one email sent
    assert counts["subprocess"] == 1, f"expected 1 subprocess call, got {counts['subprocess']}"
    assert counts["email"] == 1, f"expected 1 email sent, got {counts['email']}"
    # ensure we actually queried Redis
    assert redis_called


def test_subprocess_failure_path():
    """If the backtest subprocess fails, the runner must send a failure email
    containing the subprocess error and then raise a RuntimeError carrying the subprocess stderr.
    """

    redis_called = False

    def fake_redis_get(key):
        nonlocal redis_called
        # exact Redis key contract
        from common.const import REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        assert str(key) == REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
        redis_called = True
        return json.dumps({"result": "success"})

    def fake_is_market_open(date=None):
        return True

    captured = {}
    counts = {"subprocess": 0, "email": 0}

    def fake_run_subprocess(cmd, *a, **k):
        # capture the invoked command, count invocation, and emulate failing subprocess
        captured['cmd'] = cmd
        counts["subprocess"] += 1
        return SimpleNamespace(returncode=1, stdout="", stderr="some error")

    sent = {}

    def fake_send_email(subject, body, to=None):
        sent['subject'] = subject
        sent['body'] = body
        counts["email"] += 1

    with pytest.raises(RuntimeError) as exc:
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=fake_is_market_open,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )
    # the RuntimeError should carry the subprocess stderr
    assert "some error" in str(exc.value)

    # ensure failure email payload contains the subprocess stderr and was sent
    assert "some error" in sent.get('body', '')

    # validate the subprocess argv structure
    cmd = captured.get('cmd')
    assert cmd is not None, "subprocess was not invoked"
    assert isinstance(cmd, (list, tuple)), f"expected argv list, got {type(cmd)}"
    # lock argv[0] and argv[1]
    assert cmd[0] == sys.executable
    assert cmd[1] == "backtest/obos_hk_9.py"
    # ensure options -s, -e, -f appear in order with paired values
    def _find_opt(argv, opt):
        try:
            return argv.index(opt)
        except ValueError:
            return -1
    i_s = _find_opt(cmd, "-s")
    i_e = _find_opt(cmd, "-e")
    i_f = _find_opt(cmd, "-f")
    assert i_s != -1 and i_e != -1 and i_f != -1
    assert i_s < i_e < i_f
    for idx in (i_s, i_e, i_f):
        assert idx + 1 < len(cmd)
        assert cmd[idx + 1], "option value missing"

    # enforce exactly one subprocess invocation and exactly one email sent
    assert counts["subprocess"] == 1, f"expected 1 subprocess call, got {counts['subprocess']}"
    assert counts["email"] == 1, f"expected 1 email sent, got {counts['email']}"
    # ensure we actually queried Redis
    assert redis_called
