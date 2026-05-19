from typing import Literal

from pydantic import BaseModel, Field


class Scene(BaseModel):
    order: int = Field(
        ...,
        description="Zero-based index of the scene within the ad (0 = first scene).",
    )
    timestamp_sec: float = Field(
        ...,
        description="Timestamp in seconds where this scene starts in the video.",
    )
    short_text_description: str = Field(
        ...,
        max_length=150,
        description="Short description of what happens in this scene.",
    )
    frame_image_paths: list[str] = Field(
        default_factory=list,
        description="Paths to representative frame images for this scene.",
    )


class VideoVisualAnalysis(BaseModel):
    """Structured output from Claude Vision analysis of video keyframes."""

    hook_summary: str = Field(
        description="What happens in the first 3 seconds — the hook that opens the ad.",
    )
    scenes: list[Scene] = Field(
        default_factory=list,
        description="Ordered scene breakdown of the ad.",
    )
    pacing: Literal["fast", "medium", "slow"] = Field(
        description="Overall pacing assessment of the ad.",
    )
    logo_first_appearance_sec: float | None = Field(
        default=None,
        description="Estimated time when the brand logo first appears. None if not detected.",
    )
    cta_detected: bool = Field(
        default=False,
        description="Whether a call-to-action was detected.",
    )
    cta_text: str | None = Field(
        default=None,
        description="The CTA text if detected (e.g. 'Shop now', 'Learn more'). None if not detected.",
    )


class VideoDossier(BaseModel):
    video_path: str = Field(
        ...,
        description="Filesystem path of the analyzed video.",
    )
    duration_sec: float = Field(
        ...,
        description="Duration of the video in seconds.",
    )
    transcript: str = Field(
        ...,
        description="Full transcript of the video's spoken and on-screen text.",
    )
    hook_summary: str | None = Field(
        default=None,
        description="Short summary of the hook or core idea of the video.",
    )
    scenes: list[Scene] = Field(
        default_factory=list,
        description="Ordered list of scenes that describe the structure of the video.",
    )
    pacing: str | None = Field(
        default=None,
        description="Overall pacing of the ad: fast, medium, or slow.",
    )
    logo_first_appearance_sec: float | None = Field(
        default=None,
        description="Time in seconds when the brand logo first appears. None if not detected.",
    )
    cta_detected: bool = Field(
        default=False,
        description="Whether a call-to-action was detected.",
    )
    cta_text: str | None = Field(
        default=None,
        description="The CTA text if detected. None if not detected.",
    )
    frames_analyzed: int = Field(
        default=0,
        description="Number of keyframes extracted and analyzed.",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata about the video (e.g. aspect_ratio, language, frames_dir).",
    )
