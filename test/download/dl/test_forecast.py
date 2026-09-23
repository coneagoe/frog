from unittest.mock import ANY, MagicMock

import pandas as pd
import pytest

from download.dl import downloader_tushare


def test_download_forecast_normalizes_supported_a_share_records(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    pro = MagicMock()
    pro.forecast.return_value = pd.DataFrame(
        {
            "ts_code": ["600001.SH", "000001.SZ", "430001.BJ", "600002.XX", "malformed"],
            "ann_date": ["20250101", "20250102", "20250103", "20250104", "20250105"],
            "end_date": ["20241231", "20241231", "20241231", "20241231", "20241231"],
            "type": ["预增", "预增", "预增", "预增", "预增"],
            "p_change_min": [50.0, 70.0, 100.0, 120.0, 130.0],
            "p_change_max": [60.0, 80.0, 110.0, 130.0, 140.0],
        }
    )
    monkeypatch.setattr(downloader_tushare, "_create_pro_client", lambda: pro)

    result = downloader_tushare.download_forecast(ann_date="20250101")

    assert result["股票代码"].tolist() == ["600001", "000001", "430001"]
    assert result["预告类型"].tolist() == ["预增", "预增", "预增"]
    assert result.attrs["source_rows"] == 5
    pro.forecast.assert_called_once_with(ann_date="20250101", fields=ANY)


def test_download_forecast_preserves_source_count_without_a_share_records(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    pro = MagicMock()
    pro.forecast.return_value = pd.DataFrame(
        {
            "ts_code": ["600001.XX"],
            "ann_date": ["20250101"],
            "end_date": ["20241231"],
            "type": ["预增"],
            "p_change_min": [100.0],
            "p_change_max": [110.0],
        }
    )
    monkeypatch.setattr(downloader_tushare, "_create_pro_client", lambda: pro)

    result = downloader_tushare.download_forecast(ann_date="20250101")

    assert result.empty
    assert result.attrs["source_rows"] == 1


@pytest.mark.parametrize("provider_code", ["100000.SH", "600001.SZ", "600001.BJ"])
def test_download_forecast_rejects_invalid_codes_with_valid_looking_suffixes(monkeypatch, provider_code):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    pro = MagicMock()
    pro.forecast.return_value = pd.DataFrame(
        {
            "ts_code": [provider_code],
            "ann_date": ["20250101"],
            "end_date": ["20241231"],
            "type": ["预增"],
            "p_change_min": [100.0],
            "p_change_max": [110.0],
        }
    )
    monkeypatch.setattr(downloader_tushare, "_create_pro_client", lambda: pro)

    result = downloader_tushare.download_forecast(ann_date="20250101")

    assert result.empty
    assert result.attrs["source_rows"] == 1
