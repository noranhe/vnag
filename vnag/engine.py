import json
import inspect
import importlib
import traceback
from pathlib import Path
from typing import Any
from collections.abc import Generator
from glob import glob
from types import ModuleType

from .gateway import BaseGateway
from .object import (
    Message,
    Request,
    Delta,
    Response,
    Usage,
    ToolCall,
    ToolResult,
    ToolSchema,
    Session
)
from .constant import Role, FinishReason
from .mcp import McpManager
from .local import LocalManager
from .tracer import LogTracer
from .agent import AgentConfig, BaseAgent
from .utility import WORKING_DIR


AGENT_CONFIG_DIR: Path = WORKING_DIR.joinpath("agents")
AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class AgentEngine:
    """
    Agent 引擎：负责Agent类的发现和注册，并提供Agent实例创建的工厂方法。
    """

    def __init__(self, gateway: BaseGateway) -> None:
        """构造函数"""
        self.gateway: BaseGateway = gateway

        self._tracer: LogTracer = LogTracer()

        self._local_manager: LocalManager = LocalManager()
        self._mcp_manager: McpManager = McpManager()

        self._local_tools: dict[str, ToolSchema] = {}
        self._mcp_tools: dict[str, ToolSchema] = {}

        self._agent_classes: dict[str, type[BaseAgent]] = {}

    def init(self) -> None:
        """初始化引擎"""
        self._load_local_tools()
        self._load_mcp_tools()
        self._load_agent_classes()

    def _load_agent_classes(self) -> None:
        """加载所有智能体类"""
        path_1: Path = Path(__file__).parent.joinpath("agents")
        self._load_agent_classes_from_folder(path_1, "vnag.agents")

        path_2: Path = Path.cwd().joinpath("agents")
        self._load_agent_classes_from_folder(path_2, "agents")

    def _load_agent_classes_from_folder(self, folder_path: Path, module_name: str) -> None:
        """从文件夹加载智能体类"""
        pathname: str = str(folder_path.joinpath("*.py"))

        for filepath in glob(pathname):
            filename: str = Path(filepath).stem
            name: str = f"{module_name}.{filename}"
            self._load_agent_classes_from_module(name)

    def _load_agent_classes_from_module(self, module_name: str) -> None:
        """从模块加载智能体类"""
        try:
            module: ModuleType = importlib.import_module(module_name)

            for name in dir(module):
                value: Any = getattr(module, name)
                if isinstance(value, type) and issubclass(value, BaseAgent):
                    self._agent_classes[value.__name__] = value
        except Exception:
            msg: str = f"Agent class [{module_name}] load failed: {traceback.format_exc()}"
            print(msg)

    def _load_local_tools(self) -> None:
        """加载本地工具"""
        for schema in self._local_manager.list_tools():
            self._local_tools[schema.name] = schema

    def _load_mcp_tools(self) -> None:
        """加载MCP工具"""
        for schema in self._mcp_manager.list_tools():
            self._mcp_tools[schema.name] = schema

    def get_tool_schemas(self, tool_names: list[str] | None = None) -> list[ToolSchema]:
        """获取所有工具的Schema"""
        local_schemas: list[ToolSchema] = list(self._local_tools.values())
        mcp_schemas: list[ToolSchema] = list(self._mcp_tools.values())
        all_schemas: list[ToolSchema] = local_schemas + mcp_schemas

        if tool_names:
            tool_schemas: list[ToolSchema] = []
            for schema in all_schemas:
                if schema.name in tool_names:
                    tool_schemas.append(schema)
            return tool_schemas
        else:
            return all_schemas

    def list_models(self) -> list[str]:
        """查询可用模型列表"""
        return self.gateway.list_models()

    def load_agent_configs(self) -> dict[str, AgentConfig]:
        """从JSON文件加载所有Agent配置模板。"""
        configs: dict[str, AgentConfig] = {}

        for file_path in AGENT_CONFIG_DIR.glob("*.json"):
            with open(file_path, encoding="UTF-8") as f:
                data: dict = json.load(f)
                config: AgentConfig = AgentConfig.model_validate(data)
                configs[config.id] = config

        return configs

    def save_agent_config(self, config: AgentConfig) -> None:
        """保存一个Agent配置模板到JSON。"""
        data: dict[str, AgentConfig] = config.model_dump()

        file_path = AGENT_CONFIG_DIR.joinpath(f"{config.id}.json")

        with open(file_path, "w", encoding="UTF-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def delete_agent_config(self, agent_id: str) -> None:
        """删除一个Agent配置模板。"""
        file_path = AGENT_CONFIG_DIR.joinpath(f"{agent_id}.json")

        if file_path.exists():
            file_path.unlink()

    def create_agent_instance(self, config: AgentConfig, session: Session) -> BaseAgent:
        """【核心工厂方法】根据配置和会话，创建一个全新的Agent实例。"""
        agent_class = self._agent_classes.get(config.agent_type)

        if not agent_class:
            raise ValueError(f"Agent class {config.agent_type} not found.")

        return agent_class(self, config, session)

    def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """执行单个工具并返回结果"""
        if tool_call.name in self._local_tools:
            result_content: str = self._local_manager.execute_tool(
                tool_call.name,
                tool_call.arguments
            )
        elif tool_call.name in self._mcp_tools:
            result_content = self._mcp_manager.execute_tool(
                tool_call.name,
                tool_call.arguments
            )
        else:
            result_content = ""

        return ToolResult(
            id=tool_call.id,
            name=tool_call.name,
            content=result_content,
            is_error=bool(result_content)
        )

    def stream(self, request: Request) -> Generator[Delta, None, None]:
        """
        流式对话接口，通过生成器（Generator）实时返回 AI 的思考和回复。

        Args:
            request (Request): 请求对象。

        Yields:
            Generator[Delta, None, None]: 一个增量数据（Delta）的生成器。
        """
        return self.gateway.stream(request)
