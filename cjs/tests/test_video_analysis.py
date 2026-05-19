"""Unit tests for Phase 10 video analysis pipeline (mocked dependencies)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cjs.config import Settings
from cjs.pipelines.video_analysis import VideoAnalysisError, analyze_video
from cjs.router.model_router import RouterResult
from cjs.schemas.video_dossier import Scene, VideoVisualAnalysis
from cjs.utils.ffmpeg import FFmpegError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    max_duration_sec: int = 60, max_frames: int = 4, max_file_mb: int = 200
) -> Settings:
    config = Settings()
    config.limits.max_duration_sec = max_duration_sec
    config.limits.max_frames = max_frames
    config.limits.max_file_mb = max_file_mb
    return config


def _make_visual_analysis() -> VideoVisualAnalysis:
    return VideoVisualAnalysis(
        hook_summary="Product shown in first second.",
        scenes=[Scene(order=0, timestamp_sec=0.0, short_text_description="Opening shot")],
        pacing="fast",
        logo_first_appearance_sec=2.0,
        cta_detected=True,
        cta_text="Shop now",
    )


def _mock_router(visual: VideoVisualAnalysis) -> MagicMock:
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content=visual.model_dump_json(),
        tokens_in=100,
        tokens_out=200,
        latency_ms=500.0,
        model="test-model",
    )
    return router


def _make_video(tmp_path: Path, name: str = "ad.mp4", size_bytes: int = 1024) -> Path:
    p = tmp_path / name
    p.write_bytes(b"0" * size_bytes)
    return p


# ---------------------------------------------------------------------------
# _validate_video
# ---------------------------------------------------------------------------


class TestValidateVideo:
    def test_rejects_unsupported_extension(self, tmp_path: Path) -> None:
        video = _make_video(tmp_path, "ad.avi")
        with pytest.raises(VideoAnalysisError, match="Unsupported format"):
            analyze_video(video, tmp_path, MagicMock(), _make_config())

    def test_rejects_oversized_file(self, tmp_path: Path) -> None:
        video = _make_video(tmp_path, "ad.mp4", size_bytes=10 * 1024 * 1024)
        with pytest.raises(VideoAnalysisError, match="exceeds limit"):
            analyze_video(video, tmp_path, MagicMock(), _make_config(max_file_mb=5))

    def test_accepts_valid_extensions(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        config = _make_config()

        for ext in (".mp4", ".mov", ".webm"):
            video = _make_video(tmp_path, f"ad{ext}")
            with (
                patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
                patch("cjs.pipelines.video_analysis.extract_audio"),
                patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
                patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
            ):
                dossier = analyze_video(video, tmp_path, router, config)
            assert dossier.video_path == str(video)


# ---------------------------------------------------------------------------
# Duration check
# ---------------------------------------------------------------------------


class TestDurationCheck:
    def test_rejects_video_exceeding_max_duration(self, tmp_path: Path) -> None:
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=90.0),
            pytest.raises(VideoAnalysisError, match="exceeds limit"),
        ):
            analyze_video(video, tmp_path, MagicMock(), _make_config(max_duration_sec=30))

    def test_skips_duration_check_when_ffprobe_unavailable(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch(
                "cjs.pipelines.video_analysis.get_video_duration_sec",
                side_effect=FFmpegError("ffprobe not found"),
            ),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            dossier = analyze_video(video, tmp_path, router, _make_config())
        assert dossier.duration_sec == 0.0


# ---------------------------------------------------------------------------
# Audio / transcript fallback
# ---------------------------------------------------------------------------


class TestTranscriptFallback:
    def test_returns_empty_transcript_when_audio_extraction_fails(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch(
                "cjs.pipelines.video_analysis.extract_audio",
                side_effect=FFmpegError("ffmpeg not found"),
            ),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            dossier = analyze_video(video, tmp_path, router, _make_config())
        assert dossier.transcript == ""

    def test_transcript_populated_when_whisper_succeeds(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value="Buy now."),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            dossier = analyze_video(video, tmp_path, router, _make_config())
        assert dossier.transcript == "Buy now."


# ---------------------------------------------------------------------------
# analyze_video — full happy path
# ---------------------------------------------------------------------------


class TestAnalyzeVideo:
    def test_returns_dossier_with_all_fields(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=28.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value="Shop now at acme.com"),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            dossier = analyze_video(video, tmp_path, router, _make_config())

        assert dossier.duration_sec == 28.0
        assert dossier.transcript == "Shop now at acme.com"
        assert dossier.hook_summary == visual.hook_summary
        assert dossier.pacing == "fast"
        assert dossier.cta_detected is True
        assert dossier.cta_text == "Shop now"
        assert dossier.logo_first_appearance_sec == 2.0

    def test_writes_dossier_json_to_run_folder(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "spot.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=15.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            analyze_video(video, tmp_path, router, _make_config())

        dossier_path = tmp_path / "dossiers" / "spot_dossier.json"
        assert dossier_path.exists()
        assert "spot" in dossier_path.read_text()

    def test_frames_analyzed_count_matches_extracted_frames(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        fake_frames = [tmp_path / f"frame_{i:04d}.png" for i in range(4)]
        for f in fake_frames:
            f.write_bytes(b"")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=fake_frames),
        ):
            dossier = analyze_video(video, tmp_path, router, _make_config())

        assert dossier.frames_analyzed == 4

    def test_raises_on_invalid_vision_response(self, tmp_path: Path) -> None:
        router = MagicMock()
        router.call_structured.return_value = RouterResult(
            content="not valid json",
            tokens_in=10,
            tokens_out=5,
            latency_ms=100.0,
            model="test",
        )
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
            pytest.raises(VideoAnalysisError, match="Failed to parse vision analysis"),
        ):
            analyze_video(video, tmp_path, router, _make_config())

    def test_passes_frames_to_router_when_available(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        fake_frames = [tmp_path / "frame_0000.png"]
        fake_frames[0].write_bytes(b"")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=fake_frames),
        ):
            analyze_video(video, tmp_path, router, _make_config())

        call_kwargs = router.call_structured.call_args.kwargs
        assert call_kwargs["images"] == fake_frames

    def test_passes_no_images_when_no_frames_extracted(self, tmp_path: Path) -> None:
        visual = _make_visual_analysis()
        router = _mock_router(visual)
        video = _make_video(tmp_path, "ad.mp4")
        with (
            patch("cjs.pipelines.video_analysis.get_video_duration_sec", return_value=10.0),
            patch("cjs.pipelines.video_analysis.extract_audio"),
            patch("cjs.pipelines.video_analysis.transcribe", return_value=""),
            patch("cjs.pipelines.video_analysis.extract_keyframes", return_value=[]),
        ):
            analyze_video(video, tmp_path, router, _make_config())

        call_kwargs = router.call_structured.call_args.kwargs
        assert call_kwargs["images"] is None
