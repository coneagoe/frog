import os
from pathlib import Path


class StorageConfig:
    def __init__(self):
        self.base_path = os.environ.get("stock_data_path", "./data")
        self.encoding = "utf_8_sig"
        self.save_index = False
        self.db_host = os.environ.get("db_host", "localhost")
        self.db_port = int(os.environ.get("db_port", 5432))
        self.db_name = "quant"
        self.db_username = os.environ.get("db_username", "quant")
        self.db_password = os.environ.get("db_password", "quant")

    def get_base_path(self, storage_type: str = "default") -> Path:
        if storage_type == "stock_general_info":
            return Path(os.path.join(self.base_path, "info"))
        elif storage_type == "stock_1d":
            return Path(os.path.join(self.base_path, "1d"))
        elif storage_type == "stock_1w":
            return Path(os.path.join(self.base_path, "1w"))
        elif storage_type == "stock_1M":
            return Path(os.path.join(self.base_path, "1M"))
        else:
            return Path(self.base_path)

    def get_encoding(self) -> str:
        return self.encoding

    def get_save_index(self) -> bool:
        return self.save_index

    def get_db_host(self) -> str:
        return self.db_host

    def get_db_port(self) -> int:
        return self.db_port

    def get_db_name(self) -> str:
        return self.db_name

    def get_db_username(self) -> str:
        return self.db_username

    def get_db_password(self) -> str:
        return self.db_password
