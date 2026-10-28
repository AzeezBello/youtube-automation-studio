"""External Nonlinear Video Editor (NLE) Timeline & Clip List Exporter (.fcpxml, .edl, .csv)."""

from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from youtube_studio.domain.models.project import TransitionType
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.jobs.runner import sanitize_output_name


@dataclass(frozen=True)
class NLEExportBundle:
    """Paths of exported timeline exchange files for external video editors."""

    output_dir: Path
    fcpxml_path: Path
    edl_path: Path
    csv_clip_list_path: Path
    json_timeline_path: Path
    clip_count: int
    total_duration_ms: int


class NLEExporterService:
    """Exports a project timeline into FCPXML, CMX 3600 EDL, and CSV/JSON clip lists for external NLE hand-off."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def export_project_timeline(
        self,
        project_id: str,
        output_dir: Path,
        *,
        output_name: Optional[str] = None,
        visual_asset_path: Optional[Path] = None,
    ) -> NLEExportBundle:
        proj_svc = ProjectService(self._session)
        media_svc = MediaLibraryService(self._session)

        project = proj_svc.get_project(project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")

        tracks = proj_svc.list_tracks(project_id)
        chapters = proj_svc.compute_chapters(project_id)
        total_ms = proj_svc.compute_total_duration_ms(project_id)

        stem = sanitize_output_name(output_name or project.name)
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        fcpxml_path = output_dir / f"{stem}_timeline.fcpxml"
        edl_path = output_dir / f"{stem}_timeline.edl"
        csv_path = output_dir / f"{stem}_clip_list.csv"
        json_path = output_dir / f"{stem}_timeline.json"

        clip_rows: list[dict[str, object]] = []
        cursor_ms = 0
        for idx, pt in enumerate(tracks):
            mf = media_svc.get(pt.media_file_id)
            title = (
                str(mf.metadata.get("title") or Path(mf.path).stem)
                if mf
                else f"Track_{idx + 1}"
            )
            file_path = str(Path(mf.path).resolve()) if mf else ""
            src_dur = int(mf.duration_ms or 60_000) if mf else 60_000
            eff_dur = max(500, pt.effective_duration_ms(src_dur))
            start_ms = cursor_ms
            end_ms = start_ms + eff_dur
            tc = pt.transition_config
            overlap = (
                min(max(0, tc.overlap_ms), eff_dur // 2)
                if idx < len(tracks) - 1 and tc.transition_type != TransitionType.NONE
                else 0
            )
            clip_rows.append(
                {
                    "index": idx + 1,
                    "track_id": pt.id,
                    "title": title,
                    "file_path": file_path,
                    "timeline_start_ms": start_ms,
                    "timeline_end_ms": end_ms,
                    "effective_duration_ms": eff_dur,
                    "trim_start_ms": pt.trim_start_ms,
                    "trim_end_ms": pt.trim_end_ms or src_dur,
                    "gain_db": pt.gain_db,
                    "fade_in_ms": pt.fade_in_ms,
                    "fade_out_ms": pt.fade_out_ms,
                    "transition_type": tc.transition_type.value,
                    "overlap_ms": overlap,
                }
            )
            cursor_ms += max(200, eff_dur - overlap)

        eff_total_ms = max(1000, total_ms or cursor_ms)

        # 1. Write CSV Clip List
        with csv_path.open("w", newline="", encoding="utf-8") as cf:
            writer = csv.writer(cf)
            writer.writerow(
                [
                    "Order",
                    "Title",
                    "Timeline Start (MM:SS)",
                    "Duration (s)",
                    "Trim In (ms)",
                    "Trim Out (ms)",
                    "Gain (dB)",
                    "Transition",
                    "Overlap (ms)",
                    "Source File",
                ]
            )
            for row in clip_rows:
                st_s = int(row["timeline_start_ms"]) // 1000
                writer.writerow(
                    [
                        row["index"],
                        row["title"],
                        f"{st_s // 60:02d}:{st_s % 60:02d}",
                        f"{int(row['effective_duration_ms']) / 1000.0:.2f}",
                        row["trim_start_ms"],
                        row["trim_end_ms"],
                        f"{float(row['gain_db']):+.1f}",
                        row["transition_type"],
                        row["overlap_ms"],
                        row["file_path"],
                    ]
                )

        # 2. Write JSON Timeline Exchange File
        json_payload = {
            "project_id": project.id,
            "project_name": project.name,
            "output_name": stem,
            "total_duration_ms": eff_total_ms,
            "visual_asset_path": str(visual_asset_path) if visual_asset_path else None,
            "chapters": [
                {"timestamp": ch.format_timestamp(), "start_ms": ch.start_ms, "title": ch.title}
                for ch in chapters
            ],
            "clips": clip_rows,
        }
        json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

        # 3. Write CMX 3600 EDL (.edl)
        edl_lines = [
            f"TITLE: {stem}",
            "FCM: NON-DROP FRAME",
            "",
        ]
        for row in clip_rows:
            num = f"{int(row['index']):03d}"
            src_in = self._ms_to_smpte(int(row["trim_start_ms"]))
            src_out = self._ms_to_smpte(int(row["trim_end_ms"]))
            rec_in = self._ms_to_smpte(int(row["timeline_start_ms"]))
            rec_out = self._ms_to_smpte(int(row["timeline_end_ms"]))
            edl_lines.append(f"{num}  AX       AA/V  C        {src_in} {src_out} {rec_in} {rec_out}")
            edl_lines.append(f"* FROM CLIP NAME: {row['title']}")
            edl_lines.append(f"* SOURCE FILE: {row['file_path']}")
            edl_lines.append("")
        edl_path.write_text("\n".join(edl_lines), encoding="utf-8")

        # 4. Write Final Cut Pro XML v1.9 (.fcpxml) compatible with major nonlinear editors
        fcpxml_path.write_text(
            self._build_fcpxml(
                project_name=project.name,
                total_ms=eff_total_ms,
                clip_rows=clip_rows,
                visual_asset_path=visual_asset_path,
            ),
            encoding="utf-8",
        )

        return NLEExportBundle(
            output_dir=output_dir,
            fcpxml_path=fcpxml_path,
            edl_path=edl_path,
            csv_clip_list_path=csv_path,
            json_timeline_path=json_path,
            clip_count=len(clip_rows),
            total_duration_ms=eff_total_ms,
        )

    @staticmethod
    def _ms_to_smpte(ms: int, fps: int = 30) -> str:
        total_frames = max(0, int(round((ms / 1000.0) * fps)))
        ff = total_frames % fps
        total_sec = total_frames // fps
        ss = total_sec % 60
        mm = (total_sec // 60) % 60
        hh = total_sec // 3600
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    @staticmethod
    def _build_fcpxml(
        *,
        project_name: str,
        total_ms: int,
        clip_rows: list[dict[str, object]],
        visual_asset_path: Optional[Path] = None,
    ) -> str:
        esc_proj = html.escape(project_name)
        resources_xml: list[str] = [
            '    <format id="r1" name="FFVideoFormat1080p30" frameDuration="100/3000s" width="1920" height="1080"/>'
        ]
        spine_xml: list[str] = []

        if visual_asset_path and visual_asset_path.exists():
            vis_uri = "file://" + quote(str(visual_asset_path.resolve()))
            resources_xml.append(
                f'    <asset id="r_bg" name="{html.escape(visual_asset_path.name)}" src="{vis_uri}" start="0s" duration="{total_ms}/1000s" hasVideo="1"/>'
            )

        for row in clip_rows:
            idx = int(row["index"])
            res_id = f"r_audio_{idx}"
            title = html.escape(str(row["title"]))
            fpath = str(row["file_path"])
            uri = "file://" + quote(fpath) if fpath else ""
            dur_ms = int(row["effective_duration_ms"])
            offset_ms = int(row["timeline_start_ms"])
            trim_in_ms = int(row["trim_start_ms"])
            resources_xml.append(
                f'    <asset id="{res_id}" name="{title}" src="{uri}" start="0s" hasAudio="1" audioSources="1" audioChannels="2"/>'
            )
            spine_xml.append(
                f'            <asset-clip name="{title}" ref="{res_id}" offset="{offset_ms}/1000s" duration="{dur_ms}/1000s" start="{trim_in_ms}/1000s" role="dialogue"/>'
            )

        res_block = "\n".join(resources_xml)
        spine_block = "\n".join(spine_xml)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<!DOCTYPE fcpxml>\n"
            '<fcpxml version="1.9">\n'
            "  <resources>\n"
            f"{res_block}\n"
            "  </resources>\n"
            '  <library>\n'
            f'    <event name="{esc_proj}">\n'
            f'      <project name="{esc_proj}">\n'
            f'        <sequence format="r1" duration="{total_ms}/1000s" tcStart="0s" tcFormat="NDF">\n'
            "          <spine>\n"
            f"{spine_block}\n"
            "          </spine>\n"
            "        </sequence>\n"
            "      </project>\n"
            "    </event>\n"
            "  </library>\n"
            "</fcpxml>\n"
        )
