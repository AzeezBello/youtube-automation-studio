"""Research Workspace UI page – keyword discovery, topic clustering, watchlist, ideas & hand-off."""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
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

from youtube_studio.domain.models.project import ProjectType
from youtube_studio.domain.services import ChannelService, ResearchService
from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService
from youtube_studio.jobs import RetentionJobRunner
from youtube_studio.mcp.channel_sync import ChannelSyncService, ConnectedChannelProfile
from youtube_studio.mcp.client import MCPClientHub
from youtube_studio.research import (
    QuotaTracker,
    ResearchResult,
    StubResearchProvider,
    TopicClusterer,
    YouTubeDataAPIProvider,
)
from youtube_studio.security import CredentialVault
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


class ResearchPage(QWidget):
    """Interactive research workspace with provenance tracking, clustering, watchlist, and production hand-off."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vault = CredentialVault()
        self._quota = QuotaTracker()
        self._stub_provider = StubResearchProvider()
        self._yt_provider = YouTubeDataAPIProvider(vault=self._vault, quota_tracker=self._quota)
        self._clusterer = TopicClusterer()
        self._mcp_hub = MCPClientHub(vault=self._vault)

        self._channel_ids: list[str] = []
        self._research_project_ids: list[str] = []
        self._idea_ids: list[str] = []
        self._current_results: list[tuple[str, ResearchResult]] = []

        self._build_ui()
        if self._mcp_hub.is_account_connected("vidiq-seo"):
            self.provider_combo.setCurrentIndex(2)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QLabel("Research Workspace — Topic Clustering & Idea Pipeline")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        subtitle = QLabel(
            "Discover audience topics, group results with TF-IDF cosine clustering, monitor public watchlists, "
            "and hand off saved ideas directly into production projects."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # Top selector row: Channel + Research Project + Retention Cleanup
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setToolTip("Select the active YouTube channel profile for research.")
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        top_row.addWidget(self.channel_combo, stretch=1)

        top_row.addWidget(QLabel("Research Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Select a research project to store notes, watchlists, and saved ideas.")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_row.addWidget(self.project_combo, stretch=1)

        new_proj_btn = QPushButton("+ Research Project")
        new_proj_btn.setObjectName("PrimaryButton")
        new_proj_btn.setToolTip("Create a new research project container for the selected channel.")
        new_proj_btn.clicked.connect(self._on_new_research_project)
        top_row.addWidget(new_proj_btn)

        self.sync_vidiq_btn = QPushButton("📈 Sync Channel && Ideas from vidIQ")
        self.sync_vidiq_btn.setObjectName("AccentButton")
        self.sync_vidiq_btn.setToolTip(
            "Pull your connected YouTube channel metadata, recent video scores, and rising keyword ideas via vidIQ MCP."
        )
        self.sync_vidiq_btn.clicked.connect(self._on_sync_from_vidiq)
        top_row.addWidget(self.sync_vidiq_btn)

        purge_btn = QPushButton("Purge Expired API Data (≤30d)")
        purge_btn.setToolTip(
            "Immediately remove any cached YouTube Data API v3 records older than 30 days."
        )
        purge_btn.clicked.connect(self._on_purge_expired)
        top_row.addWidget(purge_btn)

        root.addLayout(top_row)

        # 🔗 YouTube Link -> Research Brief & 1-Click Auto-Pilot Bar
        url_group = QGroupBox("🔗 YouTube Video URL → Research Brief, Chapters & 1-Click Project")
        url_row = QHBoxLayout(url_group)
        url_row.setContentsMargins(12, 8, 12, 8)
        url_row.setSpacing(8)
        url_row.addWidget(QLabel("Video URL:"))
        self.url_import_input = QLineEdit()
        self.url_import_input.setPlaceholderText(
            "Paste YouTube Video URL or ID (e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ)…"
        )
        self.url_import_input.setToolTip(
            "Paste any YouTube video URL to fetch public metadata (title, description, chapters, tags) "
            "and save it as a structured Research Brief + Idea."
        )
        url_row.addWidget(self.url_import_input, stretch=1)

        self.import_url_btn = QPushButton("📥 Import from Video URL → Brief && Idea")
        self.import_url_btn.setObjectName("AccentButton")
        self.import_url_btn.setToolTip(
            "Fetch public video title, description, and 00:00 chapters and save as a Research Project Brief & Idea."
        )
        self.import_url_btn.clicked.connect(self._on_import_from_video_url)
        url_row.addWidget(self.import_url_btn)

        self.autopilot_url_btn = QPushButton("🚀 1-Click Project from URL (Auto-Pilot)")
        self.autopilot_url_btn.setObjectName("PrimaryButton")
        self.autopilot_url_btn.setToolTip(
            "Import the YouTube URL into a Research Brief and immediately build a complete Production Project "
            "(tracks, silence trim, harmonic sort, scored SEO title, script & thumbnail) in 1 click!"
        )
        self.autopilot_url_btn.clicked.connect(self._on_autopilot_from_url)
        url_row.addWidget(self.autopilot_url_btn)
        root.addWidget(url_group)

        # Main split: Left = Search + Topic Clustering, Right = Notes + Watchlist + Ideas
        body = QHBoxLayout()

        # Left column
        left_col = QVBoxLayout()
        search_row = QHBoxLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(
            [
                "Stub Provider (Offline)",
                "YouTube Data API v3",
                "vidIQ MCP (Keyword Score, Velocity & Channel Intelligence)",
            ]
        )
        self.provider_combo.setToolTip(
            "Choose between the Offline Stub Provider, YouTube Data API v3, "
            "or your connected vidIQ MCP session for keyword score & channel intelligence."
        )
        search_row.addWidget(self.provider_combo)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter keyword or topic query (e.g. roots reggae dub mix)…")
        self.query_input.setToolTip("Enter a niche keyword, genre, or mood to search and cluster.")
        search_row.addWidget(self.query_input, stretch=1)

        search_btn = QPushButton("Search && Cluster")
        search_btn.setObjectName("PrimaryButton")
        search_btn.setToolTip("Fetch public video metadata and automatically group results into topic clusters.")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)

        left_col.addLayout(search_row)

        self.quota_label = QLabel()
        self.quota_label.setStyleSheet("color: #94a3b8;")
        self.quota_label.setToolTip("Tracks daily YouTube Data API v3 quota usage (10,000 unit daily budget).")
        left_col.addWidget(self.quota_label)

        # Empty State Guide (visible before first search)
        self.empty_state = EmptyStateWidget(
            title="Start Discovering Topics & Niche Clusters",
            description=(
                "No search results are displayed yet. Run a keyword search above to cluster topics "
                "and turn high-potential themes into production briefs."
            ),
            tips=[
                "<b>Offline or Live API:</b> Test workflows offline with the Stub Provider or switch to YouTube Data API v3.",
                "<b>Automatic Clustering:</b> Results are grouped into topical clusters using local TF-IDF cosine similarity.",
                "<b>One-Click Hand-Off:</b> Save any search result as an Idea and hand it off directly into a Production Project.",
            ],
            action_label="Run Sample Search ('deep dubstep mix')",
            action_tooltip="Populate a sample keyword search and cluster results immediately.",
            on_action=self._on_run_sample_search,
            secondary_label="+ Create Research Project",
            secondary_tooltip="Create a new research project for the current channel.",
            on_secondary=self._on_new_research_project,
        )
        left_col.addWidget(self.empty_state)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setToolTip(
            "Clustered search results showing topic group, title, channel, provenance provider, and 30-day retention expiry."
        )
        self.results_table.setHorizontalHeaderLabels(
            ["Topic Cluster", "Title", "Channel", "Provider", "Retention", "Expires"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_col.addWidget(self.results_table, stretch=1)

        save_from_result_btn = QPushButton("Save Selected Result as Idea…")
        save_from_result_btn.setObjectName("AccentButton")
        save_from_result_btn.setToolTip(
            "Save the highlighted search result row into your Saved Ideas list with full source provenance."
        )
        save_from_result_btn.clicked.connect(self._on_save_result_as_idea)
        left_col.addWidget(save_from_result_btn)

        body.addLayout(left_col, stretch=3)

        # Right column: Brief Notes + Competitor Watchlist + Saved Ideas -> Production Hand-Off
        right_col = QVBoxLayout()

        # 1. Research Brief & Notes
        brief_group = QGroupBox("Research Brief & Notes")
        brief_layout = QVBoxLayout(brief_group)
        self.brief_edit = QPlainTextEdit()
        self.brief_edit.setPlaceholderText("Document research themes, audience notes, and production angles…")
        self.brief_edit.setToolTip("Freeform notes saved with the active research project.")
        brief_layout.addWidget(self.brief_edit)
        save_brief_btn = QPushButton("Save Brief Notes")
        save_brief_btn.setToolTip("Persist your research brief notes to the local SQLite database.")
        save_brief_btn.clicked.connect(self._on_save_brief)
        brief_layout.addWidget(save_brief_btn)
        right_col.addWidget(brief_group, stretch=1)

        # 2. Competitor Watchlist (Public metadata only)
        watch_group = QGroupBox("Competitor Watchlist (Public Metadata · ≤30d TTL)")
        watch_layout = QVBoxLayout(watch_group)
        self.watchlist_table = QTableWidget(0, 3)
        self.watchlist_table.setAlternatingRowColors(True)
        self.watchlist_table.setToolTip("Public channels tracked for inspiration (subject to 30-day API cache TTL).")
        self.watchlist_table.setHorizontalHeaderLabels(["Channel Title", "ID / Handle", "Expires At"])
        self.watchlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.watchlist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        watch_layout.addWidget(self.watchlist_table)
        add_watch_btn = QPushButton("+ Add Public Channel to Watchlist")
        add_watch_btn.setToolTip("Add a public YouTube channel handle or ID to your research watchlist.")
        add_watch_btn.clicked.connect(self._on_add_watchlist)
        watch_layout.addWidget(add_watch_btn)
        right_col.addWidget(watch_group, stretch=1)

        # 3. Saved Ideas & Production Hand-Off
        ideas_group = QGroupBox("Saved Ideas → Production Hand-Off")
        ideas_layout = QVBoxLayout(ideas_group)
        self.ideas_table = QTableWidget(0, 3)
        self.ideas_table.setAlternatingRowColors(True)
        self.ideas_table.setToolTip("Saved video concepts ready to be converted into Production Projects.")
        self.ideas_table.setHorizontalHeaderLabels(["Idea Title", "Status", "Rationale"])
        self.ideas_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ideas_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ideas_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ideas_layout.addWidget(self.ideas_table)

        idea_btns = QHBoxLayout()
        new_idea_btn = QPushButton("+ New Idea")
        new_idea_btn.setToolTip("Manually create a new video idea for this research project.")
        new_idea_btn.clicked.connect(self._on_new_idea)
        idea_btns.addWidget(new_idea_btn)

        handoff_btn = QPushButton("Hand Off to Production →")
        handoff_btn.setObjectName("PrimaryButton")
        handoff_btn.setToolTip(
            "Create a new Production Project and initial Metadata Draft from the selected idea."
        )
        handoff_btn.clicked.connect(self._on_handoff_to_production)
        idea_btns.addWidget(handoff_btn)

        self.autopilot_idea_btn = QPushButton("🚀 1-Click Project from Idea")
        self.autopilot_idea_btn.setObjectName("AccentButton")
        self.autopilot_idea_btn.setToolTip(
            "Convert the selected research idea into a fully populated, harmonic-sorted Production Project with SEO & Artwork in 1 click."
        )
        self.autopilot_idea_btn.clicked.connect(self._on_autopilot_from_idea)
        idea_btns.addWidget(self.autopilot_idea_btn)

        ideas_layout.addLayout(idea_btns)
        right_col.addWidget(ideas_group, stretch=1)

        body.addLayout(right_col, stretch=2)
        root.addLayout(body, stretch=1)

    def _on_run_sample_search(self) -> None:
        self.query_input.setText("deep dubstep harmonic bass mix")
        self._on_search()

    def refresh(self) -> None:
        self._update_quota_label()
        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
        except Exception:
            return

        synced_prof = ChannelSyncService.get_synced_profile()
        prev_ch = self.current_channel_id()
        if not prev_ch and synced_prof and synced_prof.studio_channel_id:
            prev_ch = synced_prof.studio_channel_id

        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self._channel_ids = []
        for ch in channels:
            self.channel_combo.addItem(ch.name)
            self._channel_ids.append(ch.id)
        if prev_ch in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(prev_ch))
        self.channel_combo.blockSignals(False)
        self._reload_research_projects()

        # If vidIQ is connected and results table is empty, automatically load channel intelligence
        if not self._current_results and synced_prof and self._mcp_hub.is_account_connected("vidiq-seo"):
            default_kw = synced_prof.top_keywords[0] if synced_prof.top_keywords else f"{synced_prof.title} mix"
            if not self.query_input.text().strip():
                self.query_input.setText(default_kw)
            vidiq_res = ChannelSyncService.generate_vidiq_research_results(
                default_kw, channel_profile=synced_prof
            )
            clusters = self._clusterer.cluster(vidiq_res)
            self._populate_results_table(clusters)

        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(len(self._current_results) == 0)

    def current_channel_id(self) -> Optional[str]:
        idx = self.channel_combo.currentIndex()
        if 0 <= idx < len(self._channel_ids):
            return self._channel_ids[idx]
        return None

    def current_research_project_id(self) -> Optional[str]:
        idx = self.project_combo.currentIndex()
        if 0 <= idx < len(self._research_project_ids):
            return self._research_project_ids[idx]
        return None

    def _update_quota_label(self) -> None:
        synced_prof = ChannelSyncService.get_synced_profile()
        if self._mcp_hub.is_account_connected("vidiq-seo"):
            ch_badge = (
                f"{synced_prof.title} ({synced_prof.handle}) · Optimization {synced_prof.vidiq_optimization_score}/100"
                if synced_prof
                else "Account Connected"
            )
            self.quota_label.setText(
                f"🟢 vidIQ MCP Active ({ch_badge})  |  "
                f"YouTube API Quota: {self._quota.used_units} / {self._quota.daily_budget} units"
            )
        else:
            self.quota_label.setText(
                f"YouTube API Daily Quota: {self._quota.used_units} / {self._quota.daily_budget} units used "
                f"({self._quota.remaining_units} remaining)"
            )

    def _on_sync_from_vidiq(self) -> None:
        synced_prof = ChannelSyncService.get_synced_profile()
        default_text = synced_prof.handle if synced_prof and synced_prof.handle else ""
        ch_query, ok = QInputDialog.getText(
            self,
            "Sync Channel & Ideas from vidIQ",
            "Enter your YouTube @Handle, Channel URL, or Channel Name\n"
            "(Pulls live channel metadata, recent videos, keywords, and high-score ideas into Research):",
            text=default_text,
        )
        if not ok or not ch_query.strip():
            return
        try:
            profile = ChannelSyncService.sync_channel_to_studio(ch_query.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Channel Sync Failed", str(exc))
            return
        self.provider_combo.setCurrentIndex(2)
        self.refresh()
        if profile.studio_channel_id in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(profile.studio_channel_id))
        if profile.research_project_id and profile.research_project_id in self._research_project_ids:
            self.project_combo.setCurrentIndex(self._research_project_ids.index(profile.research_project_id))

        seed_kw = profile.top_keywords[0] if profile.top_keywords else f"{profile.title} mix"
        self.query_input.setText(seed_kw)
        self._on_search()
        QMessageBox.information(
            self,
            "vidIQ Channel & Research Synced",
            f"✅ Synced Channel: {profile.title} ({profile.handle})\n"
            f"• vidIQ Optimization Score: {profile.vidiq_optimization_score}/100\n"
            f"• Videos Audited: {len(profile.recent_videos)}\n"
            f"• Saved Ideas Added: {len(profile.recommended_ideas)} high-opportunity concepts ready for Production Hand-Off!",
        )

    def _on_channel_changed(self, _index: int) -> None:
        self._reload_research_projects()

    def _reload_research_projects(self) -> None:
        channel_id = self.current_channel_id()
        prev_rp = self.current_research_project_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self._research_project_ids = []
        if channel_id:
            with session_scope() as session:
                projects = ResearchService(session).list_research_projects(channel_id=channel_id)
            for rp in projects:
                self.project_combo.addItem(rp.name)
                self._research_project_ids.append(rp.id)
            if prev_rp in self._research_project_ids:
                self.project_combo.setCurrentIndex(self._research_project_ids.index(prev_rp))
        self.project_combo.blockSignals(False)
        self._reload_project_details()

    def _on_project_changed(self, _index: int) -> None:
        self._reload_project_details()

    def _reload_project_details(self) -> None:
        rp_id = self.current_research_project_id()
        channel_id = self.current_channel_id()
        self.brief_edit.setPlainText("")
        self.watchlist_table.setRowCount(0)
        self.ideas_table.setRowCount(0)
        self._idea_ids = []

        with session_scope() as session:
            svc = ResearchService(session)
            if rp_id:
                rp = svc.get_research_project(rp_id)
                if rp and rp.brief:
                    self.brief_edit.setPlainText(rp.brief)
            watchlist = svc.list_watchlist(research_project_id=rp_id)
            ideas = svc.list_ideas(channel_id=channel_id, research_project_id=rp_id)

        self.watchlist_table.setRowCount(len(watchlist))
        for idx, w in enumerate(watchlist):
            exp_str = w.expires_at.strftime("%Y-%m-%d") if w.expires_at else "—"
            self.watchlist_table.setItem(idx, 0, QTableWidgetItem(w.title))
            self.watchlist_table.setItem(
                idx, 1, QTableWidgetItem(w.custom_url or w.channel_external_id)
            )
            self.watchlist_table.setItem(idx, 2, QTableWidgetItem(exp_str))

        self.ideas_table.setRowCount(len(ideas))
        for idx, idea in enumerate(ideas):
            self._idea_ids.append(idea.id)
            self.ideas_table.setItem(idx, 0, QTableWidgetItem(idea.title))
            self.ideas_table.setItem(idx, 1, QTableWidgetItem(idea.status))
            self.ideas_table.setItem(idx, 2, QTableWidgetItem(idea.rationale or ""))

    def _on_new_research_project(self) -> None:
        channel_id = self.current_channel_id()
        if not channel_id:
            QMessageBox.warning(self, "Research Project", "Please create or select a channel first.")
            return
        name, ok = QInputDialog.getText(self, "New Research Project", "Research project name:")
        if not ok or not name.strip():
            return
        with session_scope() as session:
            ResearchService(session).create_research_project(name.strip(), channel_id=channel_id)
        self._reload_research_projects()

    def _on_save_brief(self) -> None:
        rp_id = self.current_research_project_id()
        if not rp_id:
            QMessageBox.warning(self, "Save Brief", "Please create or select a research project first.")
            return
        with session_scope() as session:
            ResearchService(session).update_research_project(
                rp_id,
                brief=self.brief_edit.toPlainText().strip(),
            )
        QMessageBox.information(self, "Saved", "Research brief notes updated.")

    def _on_search(self) -> None:
        query = self.query_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Search", "Please enter a search query.")
            return
        prov_idx = self.provider_combo.currentIndex()
        rp_id = self.current_research_project_id()

        try:
            if prov_idx == 2:
                synced_prof = ChannelSyncService.get_synced_profile()
                vidiq_results = ChannelSyncService.generate_vidiq_research_results(
                    query, channel_profile=synced_prof, max_results=8
                )
                stub_results = self._stub_provider.search(query, max_results=7)
                results = [*vidiq_results, *stub_results]
            elif prov_idx == 1:
                results = self._yt_provider.search(query, max_results=15)
            else:
                results = self._stub_provider.search(query, max_results=15)

            clusters = self._clusterer.cluster(results)
            with session_scope() as session:
                svc = ResearchService(session)
                for r in results:
                    svc.record_source(r, research_project_id=rp_id)
        except Exception as exc:
            QMessageBox.critical(self, "Search Failed", str(exc))
            return

        self._update_quota_label()
        self._populate_results_table(clusters)

    def _populate_results_table(self, clusters: list[object]) -> None:
        self._current_results = []
        for cluster in clusters:
            c_label = getattr(cluster, "label", "Cluster")
            for r in getattr(cluster, "results", []):
                self._current_results.append((c_label, r))

        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(len(self._current_results) == 0)

        self.results_table.setRowCount(len(self._current_results))
        for row_idx, (cluster_label, r) in enumerate(self._current_results):
            exp = r.expires_at()
            exp_str = exp.strftime("%Y-%m-%d") if exp else "—"
            self.results_table.setItem(row_idx, 0, QTableWidgetItem(cluster_label))
            self.results_table.setItem(
                row_idx, 1, QTableWidgetItem(str(r.payload.get("title", "")))
            )
            self.results_table.setItem(
                row_idx, 2, QTableWidgetItem(str(r.payload.get("channel_title", "")))
            )
            self.results_table.setItem(row_idx, 3, QTableWidgetItem(r.provider))
            self.results_table.setItem(row_idx, 4, QTableWidgetItem(r.retention_class.value))
            self.results_table.setItem(row_idx, 5, QTableWidgetItem(exp_str))

    def _on_save_result_as_idea(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self._current_results):
            QMessageBox.warning(self, "Save Idea", "Select a search result row first.")
            return
        cluster_label, res = self._current_results[row]
        default_title = str(res.payload.get("title", "New Video Idea"))
        title, ok = QInputDialog.getText(
            self, "Save Idea", "Idea title:", text=default_title
        )
        if not ok or not title.strip():
            return
        rationale, ok_r = QInputDialog.getText(
            self,
            "Idea Rationale",
            "Why this topic works:",
            text=f"Cluster: {cluster_label} | Source: {res.external_reference or res.provider}",
        )
        if not ok_r:
            return
        with session_scope() as session:
            ResearchService(session).save_idea(
                title.strip(),
                channel_id=self.current_channel_id(),
                research_project_id=self.current_research_project_id(),
                rationale=rationale.strip(),
                evidence=[
                    {
                        "provider": res.provider,
                        "external_reference": res.external_reference,
                        "cluster": cluster_label,
                    }
                ],
            )
        self._reload_project_details()

    def _on_add_watchlist(self) -> None:
        ch_ext_id, ok = QInputDialog.getText(
            self, "Add Watchlist Channel", "YouTube Channel ID or handle:"
        )
        if not ok or not ch_ext_id.strip():
            return
        title, ok_t = QInputDialog.getText(
            self, "Add Watchlist Channel", "Public Channel Title:"
        )
        if not ok_t or not title.strip():
            return
        with session_scope() as session:
            ResearchService(session).add_to_watchlist(
                ch_ext_id.strip(),
                title.strip(),
                research_project_id=self.current_research_project_id(),
            )
        self._reload_project_details()

    def _on_new_idea(self) -> None:
        title, ok = QInputDialog.getText(self, "New Idea", "Idea title:")
        if not ok or not title.strip():
            return
        rationale, ok_r = QInputDialog.getText(self, "New Idea", "Rationale / angle:")
        if not ok_r:
            return
        with session_scope() as session:
            ResearchService(session).save_idea(
                title.strip(),
                channel_id=self.current_channel_id(),
                research_project_id=self.current_research_project_id(),
                rationale=rationale.strip(),
            )
        self._reload_project_details()

    def _on_handoff_to_production(self) -> None:
        row = self.ideas_table.currentRow()
        if row < 0 or row >= len(self._idea_ids):
            QMessageBox.warning(self, "Hand Off", "Please select a saved idea first.")
            return
        channel_id = self.current_channel_id()
        if not channel_id:
            QMessageBox.warning(self, "Hand Off", "Please select a target channel first.")
            return
        idea_id = self._idea_ids[row]
        types = [t.value for t in ProjectType]
        chosen, ok = QInputDialog.getItem(
            self, "Hand Off to Production", "Select production project type:", types, 1, False
        )
        if not ok:
            return

        try:
            with session_scope() as session:
                prod_project, draft = ResearchService(session).handoff_idea_to_production(
                    idea_id,
                    channel_id=channel_id,
                    project_type=ProjectType(chosen),
                )
            self._reload_project_details()
            QMessageBox.information(
                self,
                "Hand-Off Complete",
                f"Created Production Project '{prod_project.name}' ({prod_project.id})\n"
                f"with initial Metadata Draft v{draft.version} and tags: {', '.join(draft.tags)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Hand-Off Failed", str(exc))

    def _on_import_from_video_url(self) -> None:
        url = self.url_import_input.text().strip()
        if not url:
            QMessageBox.warning(
                self,
                "Import from Video URL",
                "Paste a YouTube video URL or video ID first.",
            )
            return
        try:
            with session_scope() as session:
                ch_id = self.current_channel_id()
                if not ch_id:
                    ch_id, _, _ = ExpressAutopilotService(session).ensure_active_channel()
                r_proj, source, idea = ResearchService(session).import_from_video_url(
                    url,
                    channel_id=ch_id,
                    research_project_id=self.current_research_project_id(),
                    yt_provider=self._yt_provider,
                )
            self._update_quota_label()
            self.refresh()
            if r_proj.id in self._research_project_ids:
                self.project_combo.setCurrentIndex(self._research_project_ids.index(r_proj.id))
                self._reload_project_details()
            chapters = source.payload.get("chapters") or []
            QMessageBox.information(
                self,
                "YouTube Video Imported to Research Brief",
                f"Imported Video Brief:\n  {idea.title}\n\n"
                f"Research Project: {r_proj.name}\n"
                f"Extracted Chapters: {len(chapters)}\n"
                f"Saved Idea: '{idea.title}' (ready for Production Hand-Off or 1-Click Auto-Pilot)",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import from Video URL Failed", str(exc))

    def _on_autopilot_from_url(self) -> None:
        url = self.url_import_input.text().strip()
        if not url:
            QMessageBox.warning(
                self,
                "1-Click Project from URL",
                "Paste a YouTube video URL or video ID first.",
            )
            return
        try:
            with session_scope() as session:
                ap = ExpressAutopilotService(session)
                res = ap.run_from_video_url(
                    url,
                    channel_id=self.current_channel_id(),
                    research_project_id=self.current_research_project_id(),
                    render_video=False,
                )
            self.refresh()
            win = self.window()
            pages = getattr(win, "pages", None)
            if isinstance(pages, dict):
                for key in ("production", "artwork", "dashboard"):
                    p = pages.get(key)
                    if p is not None and hasattr(p, "refresh"):
                        try:
                            p.refresh()
                        except Exception:
                            pass
            QMessageBox.information(
                self,
                "🚀 1-Click Project from Research URL Complete!",
                f"Created Production Project from YouTube URL:\n  '{res.project_name}' ({res.track_count} tracks)\n\n"
                f"Highest-Scoring SEO Title:\n  {res.seo_title}\n"
                f"  [{res.title_score_summary}]\n\n"
                f"Thumbnail & NLE XML Prepared:\n  {res.output_dir}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "1-Click Project from URL Failed", str(exc))

    def _on_autopilot_from_idea(self) -> None:
        row = self.ideas_table.currentRow()
        if row < 0 or row >= len(self._idea_ids):
            QMessageBox.warning(self, "1-Click Project from Idea", "Select a saved idea first.")
            return
        idea_id = self._idea_ids[row]
        try:
            with session_scope() as session:
                ap = ExpressAutopilotService(session)
                ch_id, _, _ = ap.ensure_active_channel(self.current_channel_id())
                prod_proj, _ = ResearchService(session).handoff_idea_to_production(
                    idea_id,
                    channel_id=ch_id,
                )
                res = ap.run_autopilot(
                    channel_id=ch_id,
                    project_id=prod_proj.id,
                    project_name=prod_proj.name,
                    output_name=prod_proj.name,
                    render_video=False,
                )
            self._reload_project_details()
            QMessageBox.information(
                self,
                "🚀 1-Click Project from Idea Ready!",
                f"Built Production Project '{res.project_name}' ({res.track_count} tracks)!\n\n"
                f"Highest-Scoring SEO Title:\n  {res.seo_title}\n"
                f"  [{res.title_score_summary}]\n\n"
                f"Switch to the Production or Artwork tab to review or render.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "1-Click Project from Idea Failed", str(exc))

    def _on_purge_expired(self) -> None:
        try:
            with session_scope() as session:
                _, purged_count = RetentionJobRunner(session).run_cleanup()
            self._reload_project_details()
            QMessageBox.information(
                self,
                "Retention Cleanup",
                f"Purged {purged_count} expired research source record(s) per 30-day API retention policy.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Retention Cleanup Failed", str(exc))
