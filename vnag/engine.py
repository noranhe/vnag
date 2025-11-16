import json
import inspect
import importlib
from pathlib import Path
from collections.abc import Generator
from uuid import uuid4

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
from .utility import AGENT_DIR


AGENT_CONFIG_DIR: Path = AGENT_DIR.joinpath("agents")
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
        """加载所有Agent类"""
        from . import agents

        for file in agents.__path__:
            for path in Path(file).glob("*.py"):
                if path.name == "__init__.py":
                    continue

                module_name: str = f".{path.stem}"
                module = importlib.import_module(module_name, "vnag.agents")

                for _, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseAgent)
                        and obj is not BaseAgent
                    ):
                        self._agent_classes[obj.__name__] = obj

    def _load_local_tools(self) -> None:
        """加载本地工具"""
        for schema in self._local_manager.list_tools():
            self._local_tools[schema.name] = schema

    def _load_mcp_tools(self) -> None:
        """加载MCP工具"""
        for schema in self._mcp_manager.list_tools():
            self._mcp_tools[schema.name] = schema

    def get_all_tool_schemas(self) -> list[ToolSchema]:
        """获取所有工具的Schema"""
        local_schemas: list[ToolSchema] = list(self._local_tools.values())
        mcp_schemas: list[ToolSchema] = list(self._mcp_tools.values())
        return local_schemas + mcp_schemas

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

    def _prepare_request(
        self,
        messages: list[Message],
        model: str,
        tool_names: list[str] | None,
        temperature: float | None,
        max_tokens: int | None
    ) -> Request:
        """准备 LLM 请求对象"""
        tool_schemas: list[ToolSchema] = []

        # 筛选出需要使用的工具
        if tool_names:
            all_schemas: list[ToolSchema] = self.get_all_tool_schemas()
            for schema in all_schemas:
                if schema.name in tool_names:
                    tool_schemas.append(schema)

        request: Request = Request(
            model=model,
            messages=messages,
            tools_schemas=tool_schemas,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return request

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
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

    def stream(
        self,
        messages: list[Message],
        model: str,
        tool_names: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_iterations: int = 10
    ) -> Generator[Delta, None, None]:
        """
        流式对话接口，通过生成器（Generator）实时返回 AI 的思考和回复。

        函数会处理与大模型的多次交互，直到最终回复完成或者工具调用达到上限。

        Args:
            messages (list[Message]): 当前的对话历史消息列表。
            model (str): 需要使用的语言模型。
            tool_names (list[str] | None): 需要使用的工具名称列表。
            temperature (float | None): 生成文本的温度参数，控制随机性。
            max_tokens (int | None): 单次生成最大票据（Token）数量。
            max_iterations (int): 最大工具调用循环次数，防止无限循环。

        Yields:
            Generator[Delta, None, None]: 一个增量数据（Delta）的生成器。
        """
        # 初始化变量
        working_messages: list[Message] = messages.copy()   # 工作消息列表，复制一份避免影响外部传入的原始列表
        iteration: int = 0                                  # 迭代次数
        response_id: str = ""                               # 响应ID

        # 主循环，该循环负责处理多次工具调用的情况
        while iteration < max_iterations:
            # 迭代次数加1
            iteration += 1

            # 准备请求
            request: Request = self._prepare_request(
                messages=working_messages,
                model=model,
                tool_names=tool_names,
                temperature=temperature,
                max_tokens=max_tokens
            )

            self._tracer.on_llm_start(request)

            # 本轮循环中的数据缓存
            collected_content: str = ""                     # 累积收到的文本内容
            collected_tool_calls: list[ToolCall] = []       # 累积收到的工具调用请求
            finish_reason: FinishReason | None = None       # 累积收到的结束原因

            # 发送请求到AI服务端，并收集响应
            for delta in self.gateway.stream(request):
                # 记录响应ID
                if delta.id and not response_id:
                    response_id = delta.id

                # 累积收到的文本内容
                if delta.content:
                    collected_content += delta.content

                # 累积收到的工具调用请求
                if delta.calls:
                    collected_tool_calls.extend(delta.calls)

                # 记录结束原因
                if delta.finish_reason:
                    finish_reason = delta.finish_reason

                self._tracer.on_llm_delta(delta)

                # 将原始的 Delta 对象直接转发给调用者，实现实时流式效果
                yield delta

            # 流式响应结束后，根据结束原因决定下一步操作
            if finish_reason == FinishReason.STOP:              # 正常结束
                break

            elif (
                finish_reason == FinishReason.TOOL_CALLS and    # 需要调用工具
                collected_tool_calls                            # 且收到了具体的工具调用请求
            ):
                # 将 AI 的回复（包括思考过程和工具调用请求）作为一个消息添加到工作列表中
                assistant_msg: Message = Message(
                    role=Role.ASSISTANT,
                    content=collected_content,
                    tool_calls=collected_tool_calls
                )
                working_messages.append(assistant_msg)

                self._tracer.on_llm_end(assistant_msg)

                # 批量执行所有工具调用
                tool_results: list[ToolResult] = []

                for tool_call in collected_tool_calls:
                    # 在执行前，先通过 yield 发送一个通知，告诉上层应用“正在执行哪个工具”
                    yield Delta(
                        id=response_id or str(uuid4()),
                        content=f"\n\n[执行工具: {tool_call.name}]\n\n"
                    )

                    self._tracer.on_tool_start(tool_call)

                    # 执行单个工具调用，并记录结果
                    result: ToolResult = self._execute_tool(tool_call)
                    tool_results.append(result)

                    self._tracer.on_tool_end(result)

                # 将所有工具的执行结果打包成一个消息，也添加到工作列表中
                user_message: Message = Message(
                    role=Role.USER,
                    tool_results=tool_results
                )
                working_messages.append(user_message)

                # 继续下一次循环
                continue
            else:
                # 其他异常情况，直接退出
                break

        # 如果循环次数达到上限，发送一条警告信息
        if iteration >= max_iterations:
            yield Delta(
                id=response_id or str(uuid4()),
                content="\n[警告: 达到最大工具调用次数限制]\n"
            )
