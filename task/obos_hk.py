import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celery_app import app  # noqa: E402
from common.obos_hk_runner import ObosHkSkip, run_obos_hk_backtest  # noqa: E402


@app.task
def obos_hk():
    import conf

    conf.parse_config()

    try:
        result = run_obos_hk_backtest()
        return "Backtest success." if result.status == "success" else result.status
    except ObosHkSkip as exc:
        message = str(exc)
        if message == "Market is closed today.":
            return message
        return message if message.startswith("Skip:") else f"Skip: {message}"
    except RuntimeError as exc:
        return f"Backtest failed: {str(exc)}"
    except Exception as exc:
        return f"Exception occurred: {str(exc)}"
