"""Settings, Credential Vault, Backup/Restore, and Compliance Gate UI page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.config import HardwareProbe, get_settings
from youtube_studio.domain.policies.compliance_gate import ComplianceReviewGate
from youtube_studio.jobs.retention_runner import RetentionJobRunner
from youtube_studio.security.vault import CredentialVault
from youtube_studio.storage.backup import BackupService


class SettingsPage(QWidget):
    """Unified Settings, Backup/Restore, and Compliance Review Gate page."""

    VAULT_ACCOUNT = "youtube_data_api_key"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vault = CredentialVault()
        self._backup_service = BackupService()
        self._compliance_gate = ComplianceReviewGate()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        heading = QLabel("Settings, Backup & Compliance Hardening")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        # Top row: Environment + Credentials
        top_row = QHBoxLayout()

        env_group = QGroupBox("Environment & Hardware Profile")
        env_form = QFormLayout(env_group)
        self.lbl_data_dir = QLabel("-")
        self.lbl_db_path = QLabel("-")
        self.lbl_profile = QLabel("-")
        self.lbl_hardware = QLabel("-")
        self.lbl_hardware.setWordWrap(True)
        env_form.addRow("Data Directory:", self.lbl_data_dir)
        env_form.addRow("SQLite Database:", self.lbl_db_path)
        env_form.addRow("Configured Profile:", self.lbl_profile)
        env_form.addRow("Detected Hardware:", self.lbl_hardware)
        top_row.addWidget(env_group, stretch=3)

        vault_group = QGroupBox("Credential Vault (OS Keychain / Encrypted Fallback)")
        vault_layout = QVBoxLayout(vault_group)
        self.lbl_vault_status = QLabel("YouTube Data API v3 Key: Checking…")
        vault_layout.addWidget(self.lbl_vault_status)

        self.input_api_key = QLineEdit()
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_api_key.setPlaceholderText("Enter YouTube Data API v3 key…")
        vault_layout.addWidget(self.input_api_key)

        vault_btns = QHBoxLayout()
        btn_save_key = QPushButton("Save Key to Vault")
        btn_save_key.clicked.connect(self._on_save_api_key)
        btn_clear_key = QPushButton("Delete Key")
        btn_clear_key.clicked.connect(self._on_delete_api_key)
        vault_btns.addWidget(btn_save_key)
        vault_btns.addWidget(btn_clear_key)
        vault_layout.addLayout(vault_btns)
        top_row.addWidget(vault_group, stretch=2)

        root.addLayout(top_row)

        # Bottom row: Backup/Restore + Compliance Review Gate
        bottom_row = QHBoxLayout()

        # Backup & Restore panel
        backup_group = QGroupBox("Database & Config Snapshots (Backup / Restore)")
        backup_layout = QVBoxLayout(backup_group)
        self.input_backup_note = QLineEdit()
        self.input_backup_note.setPlaceholderText("Optional snapshot note (e.g. Pre-release v1.0)…")
        backup_layout.addWidget(self.input_backup_note)

        backup_btns = QHBoxLayout()
        btn_create_backup = QPushButton("Create Snapshot Backup")
        btn_create_backup.clicked.connect(self._on_create_backup)
        btn_restore_backup = QPushButton("Restore Selected Snapshot")
        btn_restore_backup.clicked.connect(self._on_restore_backup)
        backup_btns.addWidget(btn_create_backup)
        backup_btns.addWidget(btn_restore_backup)
        backup_layout.addLayout(backup_btns)

        self.list_backups = QListWidget()
        backup_layout.addWidget(self.list_backups)
        bottom_row.addWidget(backup_group, stretch=1)

        # Compliance Review Gate panel
        compliance_group = QGroupBox("Compliance Review Gate & 30-Day API Retention")
        compliance_layout = QVBoxLayout(compliance_group)

        comp_btns = QHBoxLayout()
        btn_audit_manifest = QPushButton("Audit Export Manifest…")
        btn_audit_manifest.clicked.connect(self._on_audit_manifest)
        btn_purge_retention = QPushButton("Purge Expired 30d API Cache")
        btn_purge_retention.clicked.connect(self._on_purge_retention)
        comp_btns.addWidget(btn_audit_manifest)
        comp_btns.addWidget(btn_purge_retention)
        compliance_layout.addLayout(comp_btns)

        self.txt_compliance_report = QTextEdit()
        self.txt_compliance_report.setReadOnly(True)
        self.txt_compliance_report.setPlaceholderText(
            "Select 'Audit Export Manifest…' to run the pre-release Compliance Review Gate "
            "(verifies 100% manual posting control, zero prohibited derived competitor metrics, "
            "30-day YouTube API snapshot freshness, YouTube metadata limits, and rendered media)."
        )
        compliance_layout.addWidget(self.txt_compliance_report)
        bottom_row.addWidget(compliance_group, stretch=1)

        root.addLayout(bottom_row, stretch=1)

    def refresh(self) -> None:
        settings = get_settings()
        self.lbl_data_dir.setText(str(settings.resolved_data_dir()))
        self.lbl_db_path.setText(str(settings.database_path()))
        self.lbl_profile.setText(settings.resource_profile.value)

        try:
            hw = HardwareProbe().probe()
            self.lbl_hardware.setText(
                f"{hw.cpu_cores} cores, {hw.ram_gb:.1f} GB RAM | "
                f"GPU: {hw.gpu_vendor} | Recommended: {hw.recommended_profile.value}"
            )
        except Exception as exc:
            self.lbl_hardware.setText(f"Probe unavailable ({exc})")

        has_key = bool(self._vault.get_secret(self.VAULT_ACCOUNT))
        self.lbl_vault_status.setText(
            "YouTube Data API v3 Key: <b style='color:#2ecc71'>Configured in Vault</b>"
            if has_key
            else "YouTube Data API v3 Key: <span style='color:#e67e22'>Not configured</span>"
        )
        self._refresh_backups_list()

    def _refresh_backups_list(self) -> None:
        self.list_backups.clear()
        for archive_path in self._backup_service.list_backups():
            size_kb = archive_path.stat().st_size / 1024.0 if archive_path.exists() else 0.0
            label = f"{archive_path.name}  ({size_kb:.1f} KB)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(archive_path))
            self.list_backups.addItem(item)

    def _on_save_api_key(self) -> None:
        key = self.input_api_key.text().strip()
        if not key:
            QMessageBox.warning(self, "Empty Key", "Please enter a non-empty API key.")
            return
        self._vault.set_secret(self.VAULT_ACCOUNT, key)
        self.input_api_key.clear()
        self.refresh()
        QMessageBox.information(self, "Saved", "YouTube Data API key stored in Credential Vault.")

    def _on_delete_api_key(self) -> None:
        self._vault.delete_secret(self.VAULT_ACCOUNT)
        self.refresh()
        QMessageBox.information(self, "Removed", "YouTube Data API key removed from Credential Vault.")

    def _on_create_backup(self) -> None:
        try:
            archive, manifest = self._backup_service.create_backup()
            self.input_backup_note.clear()
            self._refresh_backups_list()
            QMessageBox.information(
                self,
                "Backup Created",
                f"Atomic snapshot backup created:\n{archive}\nSHA-256: {manifest.database_sha256[:16]}…",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Backup Failed", str(exc))

    def _on_restore_backup(self) -> None:
        item = self.list_backups.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Select a backup snapshot to restore.")
            return
        archive_path = Path(item.data(Qt.ItemDataRole.UserRole))
        confirm = QMessageBox.question(
            self,
            "Confirm Restore",
            f"Restore database from:\n{archive_path.name}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            manifest = self._backup_service.restore_backup(archive_path)
            self.refresh()
            QMessageBox.information(
                self,
                "Restore Complete",
                f"Restored database snapshot ({manifest.database_sha256[:12]}…).",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))

    def _on_audit_manifest(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Export Package Manifest",
            str(get_settings().resolved_data_dir()),
            "JSON Manifest (*.json)",
        )
        if not file_path:
            return
        report = self._compliance_gate.review_package_manifest(Path(file_path))
        lines = [
            f"Compliance Review Gate: {'PASSED' if report.passed else 'FAILED'}",
            f"Target: {file_path}",
            f"Reviewed at (UTC): {report.checked_at.isoformat()}",
            "-" * 60,
        ]
        for check in report.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"[{status}] {check.name}: {check.details}")
        self.txt_compliance_report.setPlainText("\n".join(lines))

    def _on_purge_retention(self) -> None:
        try:
            runner = RetentionJobRunner()
            purged = runner.run_once()
            self.txt_compliance_report.setPlainText(
                f"30-Day Retention Purge completed.\nPurged expired snapshots: {purged}"
            )
        except Exception as exc:
            self.txt_compliance_report.setPlainText(f"Retention check info: {exc}")
