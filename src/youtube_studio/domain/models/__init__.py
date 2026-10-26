"""Domain models – pure Python / Pydantic representations."""

from .ai import ModelCapability, RegisteredModel
from .channel import Channel, ChannelBrandConfig
from .job import Job, JobStatus, JobType
from .media import MediaFile, MediaType
from .project import (
    Asset,
    AssetType,
    ChapterEntry,
    MetadataDraft,
    Project,
    ProjectStatus,
    ProjectTrack,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from .research import ResearchProject, ResearchSource, SavedIdea

__all__ = [
    "Asset",
    "AssetType",
    "Channel",
    "ChannelBrandConfig",
    "ChapterEntry",
    "Job",
    "JobStatus",
    "JobType",
    "MediaFile",
    "MediaType",
    "MetadataDraft",
    "ModelCapability",
    "Project",
    "ProjectStatus",
    "ProjectTrack",
    "ProjectType",
    "RegisteredModel",
    "ResearchProject",
    "ResearchSource",
    "SavedIdea",
    "TransitionConfig",
    "TransitionType",
]
