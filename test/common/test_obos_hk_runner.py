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
        # ensure the runner looks up the expected download key so we exercise the Redis branch
        assert "download_hk_ggt_history" in str(key)
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


def test_success_email_path():
    """When backtest subprocess succeeds, runner returns a success result and
    sends an email. Dependencies are injected as callables.
    """

    def fake_redis_get(key):
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


def test_subprocess_failure_path():
    """If the backtest subprocess fails, runner should return a failed result
    including the subprocess error and the failure email should include the
    error message.
    """

    def fake_redis_get(key):
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

    with pytest.raises(Exception):
        run_obos_hk_backtest(
            redis_get=fake_redis_get,
            is_market_open=fake_is_market_open,
            run_subprocess=fake_run_subprocess,
            send_email=fake_send_email,
        )

    # ensure failure email payload contains the subprocess stderr and was sent
    assert "some error" in sent.get('body', '')
    # ensure failure email subject indicates failure
    assert "failed" in sent.get('subject', '') or "failed" in sent.get('body', '')

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

