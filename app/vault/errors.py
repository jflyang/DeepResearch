"""Vault 子系统异常。"""


class VaultError(Exception):
    """Vault 操作基础异常。"""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        super().__init__(message)


class VaultNotFoundError(VaultError):
    """Vault 根目录不存在。"""


class VaultWriteError(VaultError):
    """文件写入失败。"""


class VaultFileExistsError(VaultError):
    """文件已存在且 overwrite=False。"""
