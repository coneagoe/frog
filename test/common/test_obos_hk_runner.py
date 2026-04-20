import pytest
from types import SimpleNamespace
import json

# The tests now exercise the shared runner contract. Importing the runner
# module is expected to fail for Task 1 (module not implemented yet).
from common.obos_hk_runner import ObosHkSkip, run_obos_hk_backtest


def test_skip_when_redis_not_success():
    """If Redis indicates the upstream download was not successful, the runner must
    raise ObosHkSkip (Airflow skip semantics).
    """

    def fake_redis_get(key):
        # return a non-success sentinel
        return json.dumps({"result": "fail"})

    # Call the real API with injected dependency
    with pytest.raises(ObosHkSkip):
        run_obos_hk_backtest(redis_get=fake_redis_get)


def test_success_email_path():
    """When backtest subprocess succeeds, runner returns a success result and
    sends an email. Dependencies are injected as callables.
    """

    def fake_redis_get(key):
        return json.dumps({"result": "success"})

    def fake_is_market_open(date=None):
        return True

    def fake_run_subprocess(cmd, *a, **k):
        # emulate successful subprocess
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    sent = {}

    def fake_send_email(subject, body, to=None):
        sent['subject'] = subject
        sent['body'] = body

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


def test_subprocess_failure_path():
    """If the backtest subprocess fails, runner should return a failed result
    including the subprocess error and the failure email should include the
    error message.
    """

    def fake_redis_get(key):
        return json.dumps({"result": "success"})

    def fake_is_market_open(date=None):
        return True

    def fake_run_subprocess(cmd, *a, **k):
        # emulate failing subprocess
        return SimpleNamespace(returncode=1, stdout="", stderr="some error")

    sent = {}

    def fake_send_email(subject, body, to=None):
        sent['subject'] = subject
        sent['body'] = body

    res = run_obos_hk_backtest(
        redis_get=fake_redis_get,
        is_market_open=fake_is_market_open,
        run_subprocess=fake_run_subprocess,
        send_email=fake_send_email,
    )

    assert res.status == "failed"
    assert "some error" in res.error
    assert "some error" in res.email_body
    # ensure failure email payload contains the subprocess stderr
    assert "some error" in sent.get('body', '')
    # ensure failure email subject indicates failure
    assert "failed" in sent.get('subject', '') or "failed" in sent.get('body', '')
