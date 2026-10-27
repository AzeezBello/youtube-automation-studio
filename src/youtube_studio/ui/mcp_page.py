"""MCP Hub UI page – manage MCP server connections, inspect tools/resources/prompts, and execute live MCP calls."""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.mcp.client import MCPClientHub
from youtube_studio.mcp.oauth import MCPOAuthSession
from youtube_studio.mcp.protocol import MCPToolDefinition
from youtube_studio.mcp.server import StudioMCPServer
from youtube_studio.ui.components import EmptyStateWidget


class MCPHubPage(QWidget):
    """Interactive Bidirectional MCP Hub for Studio MCP Server & External MCP Client connections."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._hub = MCPClientHub()
        self._hub.seed_preconfigured_servers()
        self._server_ids: list[str] = []
        self._current_tools: list[MCPToolDefinition] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QLabel("MCP Hub — Model Context Protocol Server & Client Bridge")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        subtitle = QLabel(
            "Expose YouTube Automation Studio to AI agents via the built-in Studio MCP Server, "
            "or connect external stdio / HTTP MCP servers to extend research and production."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # Empty State Guide (shown when no external accounts are linked yet)
        self.empty_state = EmptyStateWidget(
            title="Preconfigured MCP Connectors Ready — Connect via Browser Login (No API Keys Needed)",
            description=(
                "We've preconfigured 9 creator MCP connectors (including vidIQ, TubeBuddy, YouTube Data API v3, "
                "Suno/Udio, ElevenLabs, Replicate Flux, Brave Search, Google Drive & Discord) using their official "
                "MCP Connection URLs. Select any connector below and click '🌐 Login & Connect in Browser' to sign in."
            ),
            tips=[
                "<b>Connection URL + Browser Login:</b> No API keys required — select any connector (or paste a custom MCP URL) and click '🌐 Login & Connect in Browser' to authenticate in your browser.",
                "<b>Studio as MCP Server:</b> Click 'Copy Host Config (JSON)' to add `youtube-studio-mcp` to Claude Desktop, Cursor, or Antigravity.",
                "<b>Live Tool Inspector:</b> Select any connector and click '▶ Execute MCP Tool' on the right to run its tools immediately.",
            ],
            action_label="🌐 Login & Connect Selected in Browser",
            action_tooltip="Open your browser to sign in and authorize the selected MCP Connection URL (no API key needed).",
            on_action=self._on_connect_account,
            secondary_label="Copy Host Config (JSON)",
            secondary_tooltip="Copy the mcpServers JSON configuration snippet to your clipboard.",
            on_secondary=self._on_copy_host_config,
        )
        root.addWidget(self.empty_state)

        body = QHBoxLayout()

        # Left column: Registered & Preconfigured MCP Servers + Browser OAuth Redirect
        left_col = QVBoxLayout()
        srv_group = QGroupBox("Preconfigured & Custom MCP Connectors (Connection URL + Browser Redirect)")
        srv_layout = QVBoxLayout(srv_group)

        # Connection URL bar
        url_row = QHBoxLayout()
        lbl_url = QLabel("Connection URL:")
        lbl_url.setStyleSheet("font-weight: 600;")
        url_row.addWidget(lbl_url)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "https://mcp.vidiq.com/sse — Select a connector below or paste any MCP Connection URL…"
        )
        self.url_input.setToolTip(
            "MCP Server Connection URL (SSE / Streamable HTTP). Clicking 'Login & Connect in Browser' redirects to your browser to sign in."
        )
        url_row.addWidget(self.url_input, stretch=1)
        srv_layout.addLayout(url_row)

        srv_btns_top = QHBoxLayout()
        self.btn_connect_account = QPushButton("🌐 Login && Connect in Browser")
        self.btn_connect_account.setObjectName("PrimaryButton")
        self.btn_connect_account.setToolTip(
            "Use the MCP Connection URL above and redirect to your browser to log in and authorize (no API keys required)."
        )
        self.btn_connect_account.clicked.connect(self._on_connect_account)
        srv_btns_top.addWidget(self.btn_connect_account, stretch=2)

        self.btn_disconnect_account = QPushButton("Disconnect")
        self.btn_disconnect_account.setToolTip("Disconnect the browser OAuth session for the selected MCP connector.")
        self.btn_disconnect_account.clicked.connect(self._on_disconnect_account)
        srv_btns_top.addWidget(self.btn_disconnect_account)

        self.btn_ping_server = QPushButton("Ping / Test")
        self.btn_ping_server.setToolTip("Test connection and list capabilities for the selected MCP server.")
        self.btn_ping_server.clicked.connect(self._on_ping_selected)
        srv_btns_top.addWidget(self.btn_ping_server)
        srv_layout.addLayout(srv_btns_top)

        srv_btns_bottom = QHBoxLayout()
        self.btn_add_server = QPushButton("+ Add Custom MCP URL…")
        self.btn_add_server.setToolTip("Add a custom remote MCP Connection URL or local stdio server.")
        self.btn_add_server.clicked.connect(self._on_add_external_server)
        srv_btns_bottom.addWidget(self.btn_add_server)

        self.btn_copy_config = QPushButton("Copy Studio Host Config (JSON)")
        self.btn_copy_config.setObjectName("AccentButton")
        self.btn_copy_config.setToolTip(
            "Copy the mcpServers JSON configuration snippet so external AI hosts can launch youtube-studio-mcp."
        )
        self.btn_copy_config.clicked.connect(self._on_copy_host_config)
        srv_btns_bottom.addWidget(self.btn_copy_config)

        srv_layout.addLayout(srv_btns_bottom)

        self.servers_table = QTableWidget(0, 4)
        self.servers_table.setAlternatingRowColors(True)
        self.servers_table.setToolTip(
            "Preconfigured & custom MCP connectors. Select any row to populate its MCP Connection URL and log in via browser."
        )
        self.servers_table.setHorizontalHeaderLabels(
            ["MCP Connector", "Category", "Connection Status", "MCP Connection URL"]
        )
        self.servers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.servers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.servers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.servers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.servers_table.itemSelectionChanged.connect(self._on_server_selected)
        srv_layout.addWidget(self.servers_table, stretch=1)

        left_col.addWidget(srv_group, stretch=1)
        body.addLayout(left_col, stretch=5)

        # Right column: Interactive Tool, Resource & Prompt Inspector
        right_col = QVBoxLayout()
        insp_group = QGroupBox("Interactive MCP Tool, Resource & Prompt Inspector")
        insp_layout = QVBoxLayout(insp_group)

        form = QFormLayout()
        self.tool_combo = QComboBox()
        self.tool_combo.setToolTip("Select an MCP tool exposed by the active server to inspect and execute.")
        self.tool_combo.currentIndexChanged.connect(self._on_tool_changed)
        form.addRow("MCP Tool:", self.tool_combo)

        self.lbl_tool_desc = QLabel("-")
        self.lbl_tool_desc.setWordWrap(True)
        self.lbl_tool_desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        form.addRow("Description:", self.lbl_tool_desc)

        self.resource_combo = QComboBox()
        self.resource_combo.setToolTip("Select an MCP resource URI (e.g. studio://channels) to read.")
        form.addRow("MCP Resource:", self.resource_combo)

        self.prompt_combo = QComboBox()
        self.prompt_combo.setToolTip("Select an MCP prompt template to preview.")
        form.addRow("MCP Prompt:", self.prompt_combo)
        insp_layout.addLayout(form)

        insp_layout.addWidget(QLabel("Tool Arguments (JSON):"))
        self.args_edit = QPlainTextEdit()
        self.args_edit.setMaximumHeight(110)
        self.args_edit.setToolTip("JSON object passed as 'arguments' when calling tools/call.")
        insp_layout.addWidget(self.args_edit)

        exec_row = QHBoxLayout()
        self.btn_exec_tool = QPushButton("▶ Execute MCP Tool")
        self.btn_exec_tool.setObjectName("PrimaryButton")
        self.btn_exec_tool.setToolTip("Invoke tools/call on the selected MCP server with the JSON arguments above.")
        self.btn_exec_tool.clicked.connect(self._on_execute_tool)
        exec_row.addWidget(self.btn_exec_tool)

        self.btn_read_resource = QPushButton("Read Resource")
        self.btn_read_resource.setToolTip("Invoke resources/read for the selected resource URI.")
        self.btn_read_resource.clicked.connect(self._on_read_resource)
        exec_row.addWidget(self.btn_read_resource)

        self.btn_get_prompt = QPushButton("Preview Prompt")
        self.btn_get_prompt.setToolTip("Invoke prompts/get for the selected prompt template.")
        self.btn_get_prompt.clicked.connect(self._on_preview_prompt)
        exec_row.addWidget(self.btn_get_prompt)

        insp_layout.addLayout(exec_row)

        insp_layout.addWidget(QLabel("MCP JSON-RPC Response Output:"))
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setToolTip("Live response payload returned by the MCP server.")
        insp_layout.addWidget(self.output_edit, stretch=1)

        right_col.addWidget(insp_group, stretch=1)
        body.addLayout(right_col, stretch=5)

        root.addLayout(body, stretch=1)

    def refresh(self) -> None:
        servers = self._hub.list_servers()
        self._server_ids = [s.id for s in servers]
        any_external_connected = any(
            s.account_connected for s in servers if s.id != MCPClientHub.BUILTIN_SERVER_ID
        )
        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(not any_external_connected)

        self.servers_table.setRowCount(len(servers))
        for idx, srv in enumerate(servers):
            oauth_sess = self._hub.get_oauth_session(srv.id)
            if srv.transport == "builtin":
                category = "Built-in Studio"
                status = "🟢 Online (10 Tools)"
                endpoint = "studio://local/mcp (Built-in Server)"
            elif srv.transport == "preset":
                category = srv.category or "Preconfigured"
                if oauth_sess is not None:
                    status = f"🟢 Connected ({oauth_sess.account_label or 'Browser Login'})"
                elif srv.account_connected:
                    status = "🟢 Connected (Browser Login)"
                else:
                    status = "🟡 Click 'Login & Connect in Browser'"
                endpoint = srv.url or "https://mcp.server/sse"
            else:
                category = f"Custom ({srv.transport})"
                if oauth_sess is not None or srv.account_connected:
                    status = "🟢 Connected (Browser Login)"
                else:
                    status = "🟡 Click 'Login & Connect'" if srv.transport == "http" else ("Enabled" if srv.enabled else "Disabled")
                endpoint = srv.url if srv.transport == "http" else f"{srv.command or ''} {' '.join(srv.args)}".strip()

            self.servers_table.setItem(idx, 0, QTableWidgetItem(srv.name))
            self.servers_table.setItem(idx, 1, QTableWidgetItem(category))
            self.servers_table.setItem(idx, 2, QTableWidgetItem(status))
            self.servers_table.setItem(idx, 3, QTableWidgetItem(endpoint))

        if servers and self.servers_table.currentRow() < 0:
            self.servers_table.selectRow(0)
        else:
            self._on_server_selected()

    def _on_connect_account(self) -> None:
        sid = self.current_server_id()
        if not sid:
            return
        if sid == MCPClientHub.BUILTIN_SERVER_ID:
            # If the user clicks the connect button while row 0 (Built-in) is selected,
            # default to vidIQ ('vidiq-seo') so they can connect vidIQ immediately via browser!
            sid = "vidiq-seo"
            if sid in self._server_ids:
                self.servers_table.selectRow(self._server_ids.index(sid))

        cfg = self._hub.get_server(sid)
        if cfg is None:
            return

        custom_url = self.url_input.text().strip() if hasattr(self, "url_input") else ""
        conn_url = custom_url or cfg.url or f"https://mcp.{sid}.com/sse"

        authorize_url = self._hub.start_browser_oauth_login(
            sid,
            connection_url=conn_url,
            on_connected=lambda sess: QTimer.singleShot(0, lambda: self._on_oauth_completed(sess)),
            open_browser=True,
        )
        self.output_edit.setPlainText(
            f"🌐 Opening browser to log in & authorize '{cfg.name}'…\n\n"
            f"• MCP Connection URL: {conn_url}\n"
            f"• Browser Sign-In Redirect: {authorize_url}\n\n"
            "Waiting for you to click 'Authorize & Connect to Studio' in your browser (no API keys required)…"
        )

    def _on_oauth_completed(self, session: MCPOAuthSession) -> None:
        self.refresh()
        cfg = self._hub.get_server(session.server_id)
        name = cfg.name if cfg else session.server_id
        self.output_edit.setPlainText(
            f"✅ Browser Login & MCP Connection Complete for '{name}'!\n\n"
            f"• Connected Account: {session.account_label}\n"
            f"• MCP Connection URL: {session.connection_url}\n\n"
            "No API key was required. You can now execute live MCP tools on the right!"
        )

    def _on_disconnect_account(self) -> None:
        sid = self.current_server_id()
        if not sid or sid == MCPClientHub.BUILTIN_SERVER_ID:
            return
        cfg = self._hub.get_server(sid)
        self._hub.disconnect_account(sid)
        self.refresh()
        self.output_edit.setPlainText(
            f"🔌 Disconnected browser session for '{cfg.name if cfg else sid}'."
        )

    def current_server_id(self) -> Optional[str]:
        row = self.servers_table.currentRow()
        if 0 <= row < len(self._server_ids):
            return self._server_ids[row]
        return self._server_ids[0] if self._server_ids else None

    def _on_server_selected(self) -> None:
        sid = self.current_server_id()
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        self.resource_combo.clear()
        self.prompt_combo.clear()
        self._current_tools = []
        if not sid:
            self.tool_combo.blockSignals(False)
            return

        cfg = self._hub.get_server(sid)
        if cfg is not None and hasattr(self, "url_input"):
            if cfg.transport == "builtin":
                self.url_input.setText("https://mcp.vidiq.com/sse")
            else:
                self.url_input.setText(cfg.url or "")

        try:
            self._current_tools = self._hub.list_tools(sid)
            for t in self._current_tools:
                self.tool_combo.addItem(t.name)
            for r in self._hub.list_resources(sid):
                self.resource_combo.addItem(r.uri)
            for p in self._hub.list_prompts(sid):
                self.prompt_combo.addItem(p.name)
        except Exception as exc:
            self.output_edit.setPlainText(f"Could not query server '{sid}': {exc}")

        self.tool_combo.blockSignals(False)
        self._on_tool_changed(self.tool_combo.currentIndex())

    def _on_tool_changed(self, index: int) -> None:
        if 0 <= index < len(self._current_tools):
            tool = self._current_tools[index]
            self.lbl_tool_desc.setText(tool.description)
            self.args_edit.setPlainText(json.dumps(tool.sample_arguments, indent=2))
        else:
            self.lbl_tool_desc.setText("-")
            self.args_edit.setPlainText("{}")

    def _on_execute_tool(self) -> None:
        sid = self.current_server_id()
        t_name = self.tool_combo.currentText().strip()
        if not sid or not t_name:
            return
        raw_args = self.args_edit.toPlainText().strip() or "{}"
        try:
            parsed_args = json.loads(raw_args)
            if not isinstance(parsed_args, dict):
                raise ValueError("Tool arguments must be a JSON object")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid JSON", f"Arguments must be valid JSON:\n{exc}")
            return

        res = self._hub.call_tool(sid, t_name, parsed_args)
        header = "ERROR" if res.is_error else "OK"
        self.output_edit.setPlainText(f"[{header}] tools/call -> {t_name}\n\n{res.text}")

    def _on_read_resource(self) -> None:
        sid = self.current_server_id()
        uri = self.resource_combo.currentText().strip()
        if not sid or not uri:
            return
        res = self._hub.read_resource(sid, uri)
        self.output_edit.setPlainText(f"[RESOURCE] {uri}\n\n{res.text}")

    def _on_preview_prompt(self) -> None:
        sid = self.current_server_id()
        p_name = self.prompt_combo.currentText().strip()
        if not sid or not p_name:
            return
        res = self._hub.get_prompt(sid, p_name, {})
        self.output_edit.setPlainText(f"[PROMPT] {p_name}\n\n{res.text}")

    def _on_copy_host_config(self) -> None:
        cfg_json = StudioMCPServer.get_host_config_json()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(cfg_json)
        self.output_edit.setPlainText(
            "// Copied to clipboard! Paste into claude_desktop_config.json or mcp_config.json:\n"
            + cfg_json
        )

    def _on_ping_selected(self) -> None:
        sid = self.current_server_id()
        if not sid:
            return
        ok, msg = self._hub.ping_server(sid)
        row = self.servers_table.currentRow()
        if row >= 0:
            self.servers_table.setItem(row, 2, QTableWidgetItem(msg))
        self.output_edit.setPlainText(f"Ping '{sid}': {'ONLINE' if ok else 'OFFLINE'} — {msg}")

    def _on_add_external_server(self) -> None:
        name, ok = QInputDialog.getText(self, "Add MCP Connection", "MCP Server display name:")
        if not ok or not name.strip():
            return
        url, ok_u = QInputDialog.getText(
            self,
            "MCP Connection URL",
            "Enter MCP Connection URL (e.g. https://mcp.vidiq.com/sse):\n"
            "(After adding, click '🌐 Login & Connect in Browser' to authenticate.)",
        )
        if not ok_u or not url.strip():
            return
        cfg = self._hub.register_server(name.strip(), transport="http", url=url.strip())
        self.refresh()
        if cfg.id in self._server_ids:
            self.servers_table.selectRow(self._server_ids.index(cfg.id))

    def _on_remove_selected(self) -> None:
        sid = self.current_server_id()
        if not sid:
            return
        if sid == MCPClientHub.BUILTIN_SERVER_ID:
            QMessageBox.information(
                self,
                "Built-in Server",
                "The built-in Studio MCP Server is always available and cannot be removed.",
            )
            return
        self._hub.remove_server(sid)
        self.refresh()
