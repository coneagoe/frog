import re
import subprocess
from pathlib import Path

import storage.model as storage_model

DB_COMMON_PATH = Path(__file__).resolve().parents[2] / "tools" / "db_common.sh"
ETF_QUANT_PIPELINE_TABLES = {"etf_share_size", "index_daily_turnover", "etf_net_flow"}


def _parse_business_tables() -> set[str]:
    content = DB_COMMON_PATH.read_text(encoding="utf-8")
    match = re.search(r"BUSINESS_TABLES=\((.*?)\n\)", content, re.DOTALL)
    assert match is not None, "BUSINESS_TABLES array not found in tools/db_common.sh"

    return {line.strip() for line in match.group(1).splitlines() if line.strip() and not line.lstrip().startswith("#")}


def _parse_business_enum_types() -> set[str]:
    content = DB_COMMON_PATH.read_text(encoding="utf-8")
    match = re.search(r"BUSINESS_ENUM_TYPES=\((.*?)\n\)", content, re.DOTALL)
    assert match is not None, "BUSINESS_ENUM_TYPES array not found in tools/db_common.sh"

    return {line.strip() for line in match.group(1).splitlines() if line.strip() and not line.lstrip().startswith("#")}


def _model_table_names() -> set[str]:
    return {
        value for name, value in vars(storage_model).items() if name.startswith("tb_name_") and isinstance(value, str)
    }


def _business_enum_is_needed(type_name: str, table_name: str) -> bool:
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; business_enum_is_needed "$2" "$3"',
            "bash",
            str(DB_COMMON_PATH),
            type_name,
            table_name,
        ],
        check=False,
    )
    return result.returncode == 0


def test_business_tables_cover_all_storage_models():
    business_tables = _parse_business_tables()
    model_tables = _model_table_names()

    assert business_tables == model_tables


def test_public_storage_model_exposes_pending_settlement_table_name():
    assert storage_model.tb_name_paper_pending_settlement == "paper_pending_settlement"


def test_business_tables_include_etf_share_size():
    assert "etf_share_size" in _parse_business_tables()


def test_business_tables_include_index_daily_turnover():
    assert "index_daily_turnover" in _parse_business_tables()


def test_business_tables_include_etf_net_flow():
    assert "etf_net_flow" in _parse_business_tables()


def test_business_tables_include_paper_order_events():
    assert "paper_order_events" in _parse_business_tables()


def test_business_enum_types_include_paper_order_event_type_and_replay_provenance():
    assert {
        "paper_order_event_type",
        "paper_replay_time_provenance",
    } <= _parse_business_enum_types()


def test_business_enum_is_needed_maps_order_event_and_replay_provenance_types():
    assert _business_enum_is_needed("paper_order_event_type", "paper_order_events")
    for table_name in (
        "paper_cash_ledger",
        "paper_trades",
        "paper_corporate_actions",
        "paper_account_snapshots",
        "paper_order_events",
    ):
        assert _business_enum_is_needed("paper_replay_time_provenance", table_name)
    assert not _business_enum_is_needed("paper_order_event_type", "paper_trades")


def test_business_tables_include_etf_quant_pipeline_tables():
    assert ETF_QUANT_PIPELINE_TABLES <= _parse_business_tables()
