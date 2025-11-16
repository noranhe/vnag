import json
from pathlib import Path
from uuid import uuid4
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from collections.abc import Generator

from pydantic import BaseModel, Field

from .object import Session, Delta, Response
from .utility import AGENT_DIR

if TYPE_CHECKING:
    from .engine import AgentEngine


SESSION_DIR: Path = AGENT_DIR.joinpath("session")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class AgentConfig(BaseModel):
    """
    Agent实例的配置数据模型（对应策略的JSON配置）。
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str                                   # 实例名称，如“市场研究员”
    agent_type: str                             # 对应的Agent类名，如“ChatAgent”
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """
    Agent模板类（对应CtaTemplate）。
    """

    def __init__(self, engine: "AgentEngine", config: AgentConfig, session: Session):
        """构造函数"""
        self.engine: AgentEngine = engine
        self.config: AgentConfig = config
        self.session: Session = session

    def save_session(self) -> None:
        """将会话状态保存到文件。"""
        self.session.agent_id = self.config.id
        data: dict = self.session.model_dump()
        file_path: Path = SESSION_DIR.joinpath(f"{self.session.id}.json")

        with open(file_path, mode="w+", encoding="UTF-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

    def delete_session(self) -> None:
        """从文件系统删除会话文件。"""
        file_path: Path = SESSION_DIR.joinpath(f"{self.session.id}.json")
        if file_path.exists():
            file_path.unlink()

    @abstractmethod
    def stream(self, prompt: str) -> Generator[Delta, None, None]:
        """
        所有Agent子类必须实现的流式执行接口。
        """
        pass

    @abstractmethod
    def invoke(self, prompt: str) -> Response:
        """
        所有Agent子类必须实现的阻塞式执行接口。
        """
        pass
