import re
from pathlib import Path

import storage.model as storage_model

DB_COMMON_PATH = Path(__file__).resolve().parents[2] / "tools" / "db_common.sh"


def _parse_business_tables() -> set[str]:
    content = DB_COMMON_PATH.read_text(encoding="utf-8")
    match = re.search(r"BUSINESS_TABLES=\((.*?)\n\)", content, re.DOTALL)
    assert match is not None, "BUSINESS_TABLES array not found in tools/db_common.sh"

    return {line.strip() for line in match.group(1).splitlines() if line.strip() and not line.lstrip().startswith("#")}


def _model_table_names() -> set[str]:
    return {
        value for name, value in vars(storage_model).items() if name.startswith("tb_name_") and isinstance(value, str)
    }


def test_business_tables_cover_all_storage_models():
    business_tables = _parse_business_tables()
    model_tables = _model_table_names()

    assert business_tables == model_tables
