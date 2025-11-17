from pathlib import Path
import json

from ..engine import AgentEngine
from ..utility import WORKING_DIR
from ..object import Session
from ..agent import Profile, TaskAgent
from .. import __version__
from .widget import AgentWidget, ToolDialog, ModelDialog, ProfileDialog
from .qt import QtWidgets, QtGui, QtCore


SESSION_DIR = WORKING_DIR.joinpath("session")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class MainWindow(QtWidgets.QMainWindow):
    """主窗口"""

    def __init__(self, engine: AgentEngine) -> None:
        """构造函数"""
        super().__init__()

        self.engine: AgentEngine = engine

        self.agent_profiles: dict[str, Profile] = {}

        self.agent_widgets: dict[str, AgentWidget] = {}

        self.current_id: str = ""

        self.models: list[str] = self.engine.list_models()

        self.init_ui()
        self.load_data()

    def init_ui(self) -> None:
        """初始化UI"""
        self.setWindowTitle(f"VeighNa Agent - {__version__} - [ {WORKING_DIR} ]")

        self.init_menu()
        self.init_widgets()

        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.statusBar().addWidget(self.status_label, 1)

    def init_widgets(self) -> None:
        """初始化中央控件"""
        # 左侧会话相关
        self.new_button: QtWidgets.QPushButton = QtWidgets.QPushButton("新建会话")
        self.new_button.setFixedHeight(50)
        self.new_button.clicked.connect(self.new_agent_widget)

        self.session_list: QtWidgets.QListWidget = QtWidgets.QListWidget()

        # 设置自定义样式表
        stylesheet: str = """
            QListWidget::item {
                padding-top: 10px;
                padding-bottom: 10px;
                padding-left: 10px;
                border-radius: 12px;
            }
            QListWidget::item:hover {
                background-color: rgba(42, 92, 142, 0.3);
                color: white;
            }
            QListWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
        """
        self.session_list.setStyleSheet(stylesheet)

        self.session_list.itemClicked.connect(self.on_item_clicked)
        self.session_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self.on_menu_requested)
        self.session_list.installEventFilter(self)

        left_vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        left_vbox.addWidget(self.session_list)
        left_vbox.addWidget(self.new_button)

        left_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        left_widget.setLayout(left_vbox)
        left_widget.setFixedWidth(300)

        # 右侧聊天相关
        self.stacked_widget: QtWidgets.QStackedWidget = QtWidgets.QStackedWidget()

        # 主布局
        main_hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        main_hbox.addWidget(left_widget)
        main_hbox.addWidget(self.stacked_widget)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(main_hbox)
        self.setCentralWidget(central_widget)

    def init_menu(self) -> None:
        """初始化菜单"""
        menu_bar: QtWidgets.QMenuBar = self.menuBar()

        sys_menu: QtWidgets.QMenu = menu_bar.addMenu("系统")
        sys_menu.addAction("退出", self.close)

        function_menu: QtWidgets.QMenu = menu_bar.addMenu("功能")
        function_menu.addAction("新建会话", self.new_agent_widget)
        function_menu.addAction("管理智能体", self.show_profile_dialog)
        function_menu.addAction("查看工具", self.show_tool_dialog)
        function_menu.addAction("查看模型", self.show_model_dialog)

        help_menu: QtWidgets.QMenu = menu_bar.addMenu("帮助")
        help_menu.addAction("官网", self.open_website)
        help_menu.addAction("关于", self.show_about)

    def show_profile_dialog(self) -> None:
        """显示智能体管理界面"""
        dialog: ProfileDialog = ProfileDialog(self.engine, self)
        dialog.exec()

        # 重新加载智能体配置
        self.agent_profiles = self.engine.load_agent_profiles()

    def show_tool_dialog(self) -> None:
        """显示工具"""
        dialog: ToolDialog = ToolDialog(self.engine, self)
        dialog.exec()

    def show_model_dialog(self) -> None:
        """显示模型"""
        dialog: ModelDialog = ModelDialog(self.engine, self)
        dialog.exec()

    def load_data(self) -> None:
        """加载智能体配置和所有会话"""
        self.agent_profiles = self.engine.load_agent_profiles()

        # 如果没有任何Agent配置，则创建一个默认的
        if not self.agent_profiles:
            default_config: Profile = Profile(
                name="通用聊天助手",
                system_prompt="你是一个乐于助人的人工智能助手。"
            )
            self.engine.save_agent_profile(default_config)
            self.agent_profiles[default_config.id] = default_config

        self.load_agent_widgets()

    def load_agent_widgets(self) -> None:
        """加载所有会话"""
        agents: list[TaskAgent] = self.engine.get_all_agents()
        agents.sort(key=lambda a: a.id, reverse=True)

        for agent in agents:
            self.add_agent_widget(agent)

        if not self.agent_widgets:
            self.new_agent_widget()
        else:
            self.current_id = agents[0].id
            self.switch_agent_widget(self.current_id)

        self.update_agent_list()

    def update_agent_list(self) -> None:
        """更新会话列表UI"""
        self.session_list.clear()

        sorted_widgets = sorted(
            self.agent_widgets.values(),
            key=lambda w: w.agent.id,
            reverse=True
        )

        for widget in sorted_widgets:
            agent: TaskAgent = widget.agent
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(agent.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, agent.id)
            self.session_list.addItem(item)

            if agent.id == self.current_id:
                self.session_list.setCurrentItem(item)

    def new_agent_widget(self) -> None:
        """创建新会话"""
        # 如果没有Agent配置则返回
        if not self.agent_profiles:
            QtWidgets.QMessageBox.warning(self, "创建失败", "请先在“功能”->“管理智能体”中创建一个智能体配置。")
            return

        # 让用户选择一个Agent配置
        agent_names: list[str] = [config.name for config in self.agent_profiles.values()]
        name, ok = QtWidgets.QInputDialog.getItem(
            self,
            "选择智能体",
            "请选择要用于新会话的智能体：",
            agent_names,
            0,
            False
        )
        if not (ok and name):
            return

        selected_config: Profile | None = None
        for config in self.agent_profiles.values():
            if config.name == name:
                selected_config = config
                break

        if not selected_config:
            return

        # 创建新Session和Agent实例
        agent: TaskAgent = self.engine.create_agent(selected_config)

        self.add_agent_widget(agent)
        self.update_agent_list()
        self.switch_agent_widget(agent.id)

    def add_agent_widget(self, agent: TaskAgent) -> None:
        """添加会话窗口"""
        widget: AgentWidget = AgentWidget(self.engine, agent, self.models)
        self.stacked_widget.addWidget(widget)
        self.agent_widgets[agent.id] = widget

    def switch_agent_widget(self, session_id: str) -> None:
        """根据ID切换会话"""
        self.current_id = session_id

        widget: AgentWidget = self.agent_widgets[session_id]
        self.stacked_widget.setCurrentWidget(widget)
        self.update_agent_list()

    def rename_agent_widget(self, session_id: str) -> None:
        """重命名会话"""
        widget: AgentWidget | None = self.agent_widgets.get(session_id)
        if not widget:
            return

        agent: TaskAgent = widget.agent
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "重命名会话",
            "请输入新的会话名称：",
            text=agent.name
        )

        if ok and text:
            widget.agent.rename(text)
            self.update_agent_list()

    def delete_agent_widget(self, session_id: str) -> None:
        """删除会话"""
        reply: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.question(
            self,
            "删除会话",
            "确定要删除该会话吗？此操作不可恢复。",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 移除对应的控件
            widget: AgentWidget = self.agent_widgets.pop(session_id, None)
            if widget:
                # 从文件系统删除
                self.engine.delete_agent(session_id)

                self.stacked_widget.removeWidget(widget)
                widget.deleteLater()

            # 如果删除的是当前会话，则切换到另一个会话
            if self.current_id == session_id:
                if self.agent_widgets:
                    self.current_id = next(iter(self.agent_widgets.keys()))
                    self.switch_agent_widget(self.current_id)
                else:
                    self.new_agent_widget()

            self.update_agent_list()

    def show_about(self) -> None:
        """显示关于"""
        QtWidgets.QMessageBox.information(
            self,
            "关于",
            (
                "VeighNa Agent\n"
                "\n"
                f"版本号：{__version__}\n"
                "\n"
                f"运行目录：{WORKING_DIR}"
            ),
            QtWidgets.QMessageBox.StandardButton.Ok
        )

    def open_website(self) -> None:
        """打开官网"""
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://www.github.com/vnpy/vnag"))

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """事件过滤器"""
        if obj is self.session_list and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Delete:
                item: QtWidgets.QListWidgetItem = self.session_list.currentItem()
                if item:
                    self.delete_agent_widget(item.data(QtCore.Qt.ItemDataRole.UserRole))
                    return True

        return super().eventFilter(obj, event)

    def on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """处理列表项点击事件"""
        session_id: str = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.switch_agent_widget(session_id)

    def on_menu_requested(self, pos: QtCore.QPoint) -> None:
        """显示会话的右键菜单"""
        item: QtWidgets.QListWidgetItem | None = self.session_list.itemAt(pos)
        if not item:
            return

        session_id: str = item.data(QtCore.Qt.ItemDataRole.UserRole)

        menu: QtWidgets.QMenu = QtWidgets.QMenu(self)

        rename_action: QtGui.QAction = menu.addAction("重命名")
        rename_action.triggered.connect(lambda: self.rename_agent_widget(session_id))

        delete_action: QtGui.QAction = menu.addAction("删除")
        delete_action.triggered.connect(lambda: self.delete_agent_widget(session_id))

        menu.exec(self.session_list.mapToGlobal(pos))
