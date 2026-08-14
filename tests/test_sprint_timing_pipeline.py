from __future__ import annotations

from base64 import b64decode, b64encode
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from PIL import Image, ImageDraw

import race_github as github
import race_import as race
import race_import_ui as ui
import race_workbook as workbook


MAIN_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = PROJECT_ROOT / ".codex-tmp"
TAB_BOXES = {
    "WEEKEND": (12, 18, 112, 42),
    "SR": (124, 18, 224, 42),
    "R": (236, 18, 336, 42),
}
TAB_TEXT = {
    "WEEKEND": "RESULTS (WEEKEND)",
    "SR": "RESULTS (SPRINT)",
    "R": "RESULTS (RACE)",
}


def token(
    text: str,
    confidence: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    source: str,
) -> race.OcrToken:
    return race.OcrToken(text, confidence, x_min, y_min, x_max, y_max, source)


def sprint_detail_fixture(source: str) -> tuple[bytes, list[race.OcrToken]]:
    """Build a selected Sprint tab plus a detailed BEST/TIME result grid."""
    image = Image.new("RGB", (1050, 300), (24, 31, 47))
    draw = ImageDraw.Draw(image)
    tokens: list[race.OcrToken] = []
    for kind, box in TAB_BOXES.items():
        draw.rectangle(box, fill=(176, 25, 48) if kind == "SR" else (65, 70, 88))
        draw.line((box[0] + 8, 27, box[2] - 8, 27), fill=(235, 235, 238), width=2)
        draw.line((box[0] + 8, 34, box[2] - 18, 34), fill=(235, 235, 238), width=2)
        tokens.append(
            token(
                TAB_TEXT[kind],
                0.99,
                box[0] + 4,
                box[1] + 4,
                box[2] - 4,
                box[3] - 4,
                source,
            )
        )

    tokens.extend(
        [
            token("FORMULA 1 BRITISH GRAND PRIX - SPRINT", 0.99, 300, 135, 650, 155, source),
            token("POS.DRIVER", 0.99, 500, 180, 575, 190, source),
            token("TEAM", 0.99, 674, 180, 705, 190, source),
            token("GRID", 0.99, 793, 180, 820, 190, source),
            token("STOEPEEST", 0.92, 826, 180, 886, 190, source),
            token("TIME", 0.99, 912, 180, 940, 190, source),
            token("PTS.", 0.99, 995, 180, 1018, 190, source),
            token("1", 0.99, 505, 198, 515, 208, source),
            token("Alice", 0.99, 560, 198, 630, 208, source),
            token("Red", 0.99, 680, 198, 740, 208, source),
            token("1:32.888", 0.99, 850, 198, 910, 208, source),
            token("26:40.317", 0.99, 912, 198, 970, 208, source),
            token("2", 0.99, 505, 216, 515, 226, source),
            token("Bob", 0.99, 560, 216, 630, 226, source),
            token("Blue", 0.99, 680, 216, 740, 226, source),
            token("1:33.456", 0.99, 850, 216, 910, 226, source),
            token("+1.250", 0.99, 912, 216, 970, 226, source),
        ]
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), tokens


def build_temporary_workbook(path: Path) -> None:
    columns = [
        "Game",
        "Season",
        "League Name",
        "Round",
        "Type",
        "GP Name",
        "Driver",
        "Team",
        "Finish Pos",
        "Points",
        "Time",
        "Fastest Lap",
    ]
    standings = pd.DataFrame(
        [
            ["F1 26", "2026-T01", "Sprint League", 1, "R", "Australian GP", "Alice", "Red", 1, 25, "80:00.000", "1:30.000"],
            ["F1 26", "2026-T01", "Sprint League", 1, "R", "Australian GP", "Bob", "Blue", 2, 18, "+1.000", "1:31.000"],
            ["F1 26", "2026-T01", "Sprint League", 1, "SR", "Australian GP", "Alice", "Red", 1, 8, "25:00.000", "1:30.500"],
            ["F1 26", "2026-T01", "Sprint League", 1, "SR", "Australian GP", "Bob", "Blue", 2, 7, "+0.800", "1:31.500"],
        ],
        columns=columns,
    )
    calendar = pd.DataFrame(
        [
            [
                "Sprint League",
                2,
                "2026-08-15",
                "British Grand Prix",
                "Silverstone",
                "Upcoming",
                "18:00",
            ]
        ],
        columns=[
            "League Name",
            "Round",
            "Date",
            "GP Name",
            "Circuit",
            "Status",
            "Time (Lisbon)",
        ],
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        standings.to_excel(writer, sheet_name="Leagues", index=False)
        calendar.to_excel(writer, sheet_name="Calendar", index=False)

    # The production writer deliberately requires the Leagues pivot source.
    # An orphaned synthetic definition is sufficient for this isolated OOXML
    # transaction test; pandas and Excel readers ignore it safely.
    pivot_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cacheSource type="worksheet"><worksheetSource ref="A1:L5" sheet="Leagues"/>'
        '</cacheSource></pivotCacheDefinition>'
    ).encode("utf-8")
    with ZipFile(path, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr(workbook._PIVOT_SOURCE_PART, pivot_xml)


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(content)}\0".encode("ascii") + content,
        usedforsecurity=False,
    ).hexdigest()


class RecordingGitHubTransport:
    """Serve one synthetic workbook and retain any attempted publication."""

    def __init__(self, workbook_bytes: bytes) -> None:
        self.workbook_bytes = workbook_bytes
        self.calls: list[str] = []
        self.published_bytes: bytes | None = None

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> github.HttpResponse:
        del url, headers, timeout
        self.calls.append(method)
        if method == "POST":
            return github.HttpResponse(
                201,
                json.dumps(
                    {"token": "fixture-installation-token", "expires_at": "2026-08-15T00:00:00Z"}
                ).encode("utf-8"),
            )
        if method == "GET":
            return github.HttpResponse(
                200,
                json.dumps(
                    {
                        "type": "file",
                        "encoding": "base64",
                        "content": b64encode(self.workbook_bytes).decode("ascii"),
                        "sha": git_blob_sha(self.workbook_bytes),
                    }
                ).encode("utf-8"),
            )
        if method == "PUT":
            if body is None:
                raise AssertionError("Publication request had no body")
            payload = json.loads(body)
            self.published_bytes = b64decode(payload["content"])
            updated_sha = git_blob_sha(self.published_bytes)
            return github.HttpResponse(
                200,
                json.dumps(
                    {
                        "content": {"sha": updated_sha},
                        "commit": {
                            "sha": "c" * 40,
                            "html_url": "https://example.invalid/commit/sprint-fixture",
                        },
                    }
                ).encode("utf-8"),
            )
        raise AssertionError(f"Unexpected method: {method}")


class SprintTimingPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TEMP_ROOT.mkdir(exist_ok=True)
        hosted_temporary_directory = mock.patch.object(
            github,
            "TemporaryDirectory",
            side_effect=lambda **kwargs: TemporaryDirectory(
                dir=TEST_TEMP_ROOT,
                **kwargs,
            ),
        )
        hosted_temporary_directory.start()
        self.addCleanup(hosted_temporary_directory.stop)
        self.roster = [
            race.DriverEntry("Alice", "Red"),
            race.DriverEntry("Bob", "Blue"),
        ]
        self.scoring = {1: 8.0, 2: 7.0}
        first_image, first_tokens = sprint_detail_fixture("Screenshot 1")
        second_image, second_tokens = sprint_detail_fixture("Screenshot 2")
        self.uploads = [first_image, second_image]
        self.token_sets = [first_tokens, second_tokens]

    def reviewed_sprint_rows(self) -> list[dict]:
        with mock.patch(
            "race_import_ui.race_ocr.extract_tokens",
            side_effect=self.token_sets,
        ):
            review_rows, _ = ui._draft_from_ocr(
                self.uploads,
                self.roster,
                require_timing_detail=True,
                expected_event_type="SR",
                expected_gp="British Grand Prix",
            )
        reviewed = [
            {
                "Position": row["Position"],
                "Driver": row["Driver"],
                "Time": row["Time"],
                "Fastest Lap": row["Fastest Lap"],
                "Timing Expected": True,
            }
            for row in review_rows
        ]
        validation = race.validate_review_rows(reviewed, self.roster, self.scoring)
        self.assertTrue(validation.is_valid, (validation.blockers, review_rows))
        return validation.rows

    def config(self) -> github.GitHubAppConfig:
        return github.GitHubAppConfig(
            app_id="123",
            installation_id=456,
            private_key="-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----",
            owner="fixture-owner",
            repository="fixture-repository",
            branch="main",
            workbook_path="F1_Standings.xlsx",
        )

    def metadata(self) -> workbook.RaceMetadata:
        return workbook.RaceMetadata(
            game="F1 26",
            season="2026-T01",
            league="Sprint League",
            round_number=2,
            event_type="SR",
            gp_name="British Grand Prix",
        )

    @mock.patch("race_github._create_app_jwt", return_value="fixture-jwt")
    def test_selected_sprint_detail_flows_to_hosted_safe_k_l_write(self, _: mock.Mock) -> None:
        rows = self.reviewed_sprint_rows()
        self.assertEqual(rows[0]["Time"], "26:40.317")
        self.assertEqual(rows[0]["Fastest Lap"], "1:32.888")
        self.assertEqual(rows[1]["Time"], "+1.250")
        self.assertEqual(rows[1]["Fastest Lap"], "1:33.456")

        with TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary_directory:
            fixture_path = Path(temporary_directory) / "sprint-fixture.xlsx"
            build_temporary_workbook(fixture_path)
            original = fixture_path.read_bytes()
            transport = RecordingGitHubTransport(original)

            result = github.publish_race_import(
                self.config(),
                metadata=self.metadata(),
                rows=rows,
                scoring_profile=self.scoring,
                expected_blob_sha=git_blob_sha(original),
                approved=True,
                commit_message="Import British Grand Prix Sprint",
                transport=transport,
            )

        self.assertEqual(transport.calls, ["POST", "GET", "PUT"])
        self.assertIsNotNone(transport.published_bytes)
        self.assertFalse(result.calendar_updated)
        assert transport.published_bytes is not None
        with ZipFile(io.BytesIO(transport.published_bytes)) as archive:
            leagues_part = workbook._sheet_paths(archive)["Leagues"]
            worksheet = ET.fromstring(archive.read(leagues_part))
        cells = {
            cell.attrib["r"]: cell
            for cell in worksheet.findall(".//m:sheetData/m:row/m:c", MAIN_NS)
        }

        expected = [
            ("SR", "26:40.317", "1:32.888"),
            ("SR", "+1.250", "1:33.456"),
        ]
        for offset, (event_type, result_time, fastest_lap) in enumerate(expected):
            excel_row = result.first_excel_row + offset
            for column, value in (("E", event_type), ("K", result_time), ("L", fastest_lap)):
                cell = cells[f"{column}{excel_row}"]
                self.assertEqual(cell.attrib.get("t"), "inlineStr")
                self.assertIsNone(cell.find("m:f", MAIN_NS))
                actual = "".join(node.text or "" for node in cell.findall(".//m:t", MAIN_NS))
                self.assertEqual(actual, value)

    @mock.patch("race_github._create_app_jwt", return_value="fixture-jwt")
    def test_hosted_sprint_publication_blocks_missing_fastest_lap_before_put(self, _: mock.Mock) -> None:
        rows = [dict(row) for row in self.reviewed_sprint_rows()]
        rows[1]["Fastest Lap"] = ""

        with TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary_directory:
            fixture_path = Path(temporary_directory) / "sprint-fixture.xlsx"
            build_temporary_workbook(fixture_path)
            original = fixture_path.read_bytes()
            transport = RecordingGitHubTransport(original)

            with self.assertRaisesRegex(
                workbook.WorkbookUpdateError,
                "canonical Fastest Lap",
            ):
                github.publish_race_import(
                    self.config(),
                    metadata=self.metadata(),
                    rows=rows,
                    scoring_profile=self.scoring,
                    expected_blob_sha=git_blob_sha(original),
                    approved=True,
                    transport=transport,
                )

        self.assertEqual(transport.calls, ["POST", "GET"])
        self.assertIsNone(transport.published_bytes)


if __name__ == "__main__":
    unittest.main()
