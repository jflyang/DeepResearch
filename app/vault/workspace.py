"""VaultWorkspace - Vault 根目录校验与基础目录管理。"""

from pathlib import Path

from app.vault.errors import VaultNotFoundError
from app.vault.paths import VaultPaths


class VaultWorkspace:
    """Vault 工作空间，校验并管理基础目录结构。"""

    def __init__(
        self,
        root_path: Path,
        topics_dir: str = "Topics",
        entities_dir: str = "Entities",
        concepts_dir: str = "Concepts",
    ) -> None:
        self.root = root_path
        self.paths = VaultPaths(
            root=root_path,
            topics_dir=topics_dir,
            entities_dir=entities_dir,
            concepts_dir=concepts_dir,
        )

    def validate(self) -> None:
        """校验 Vault 根目录是否存在。"""
        if not self.root.exists():
            raise VaultNotFoundError(
                f"Vault root does not exist: {self.root}",
                path=str(self.root),
            )

    def ensure_base_dirs(self) -> None:
        """创建基础目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.paths.topics.mkdir(parents=True, exist_ok=True)
        self.paths.entities.mkdir(parents=True, exist_ok=True)
        self.paths.concepts.mkdir(parents=True, exist_ok=True)

    @property
    def exists(self) -> bool:
        return self.root.exists()
