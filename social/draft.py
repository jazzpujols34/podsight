"""Draft storage model for social posts."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class PlatformDraft:
    """Draft for a single platform."""
    status: str = "pending"  # pending, published, failed, skipped
    content_file: str = ""
    image_file: Optional[str] = None
    published_at: Optional[str] = None
    post_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None
    url: Optional[str] = None


@dataclass
class SocialDraft:
    """Complete draft for all platforms."""
    episode_id: str
    podcast: str
    created_at: str = ""
    summary_hash: str = ""
    status: str = "pending"  # pending, partial, published, failed
    platforms: dict[str, PlatformDraft] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        # Initialize platforms
        for platform in ["twitter", "threads", "line", "instagram"]:
            if platform not in self.platforms:
                self.platforms[platform] = PlatformDraft(content_file=f"{platform}.json")

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        data = asdict(self)
        # Convert PlatformDraft objects
        data["platforms"] = {k: asdict(v) for k, v in self.platforms.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SocialDraft":
        """Create from dict."""
        platforms = {}
        for k, v in data.get("platforms", {}).items():
            platforms[k] = PlatformDraft(**v)
        data["platforms"] = platforms
        return cls(**data)

    def save(self, draft_dir: Path):
        """Save draft to directory."""
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_file = draft_dir / "draft.json"
        with open(draft_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, draft_dir: Path) -> Optional["SocialDraft"]:
        """Load draft from directory."""
        draft_file = draft_dir / "draft.json"
        if not draft_file.exists():
            return None
        with open(draft_file, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def update_status(self):
        """Update overall status based on platform statuses."""
        statuses = [p.status for p in self.platforms.values()]
        if all(s == "published" for s in statuses):
            self.status = "published"
        elif all(s in ("published", "skipped") for s in statuses):
            self.status = "published"
        elif any(s == "published" for s in statuses):
            self.status = "partial"
        elif any(s == "failed" for s in statuses):
            self.status = "failed"
        else:
            self.status = "pending"


class DraftManager:
    """Manage social drafts for a podcast."""

    def __init__(self, data_dir: Path):
        """Initialize with podcast data directory."""
        self.drafts_dir = data_dir / "social_drafts"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def get_draft_dir(self, episode_id: str) -> Path:
        """Get directory for episode's drafts."""
        return self.drafts_dir / episode_id

    def get_draft(self, episode_id: str) -> Optional[SocialDraft]:
        """Get draft for an episode."""
        return SocialDraft.load(self.get_draft_dir(episode_id))

    def save_draft(self, draft: SocialDraft):
        """Save a draft."""
        draft.save(self.get_draft_dir(draft.episode_id))

    def list_drafts(self, status: Optional[str] = None) -> list[SocialDraft]:
        """List all drafts, optionally filtered by status."""
        drafts = []
        for episode_dir in sorted(self.drafts_dir.iterdir(), reverse=True):
            if episode_dir.is_dir():
                draft = SocialDraft.load(episode_dir)
                if draft:
                    if status is None or draft.status == status:
                        drafts.append(draft)
        return drafts

    def save_platform_content(self, episode_id: str, platform: str, content: dict):
        """Save platform-specific content."""
        draft_dir = self.get_draft_dir(episode_id)
        draft_dir.mkdir(parents=True, exist_ok=True)
        content_file = draft_dir / f"{platform}.json"
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)

    def get_platform_content(self, episode_id: str, platform: str) -> Optional[dict]:
        """Load platform-specific content."""
        content_file = self.get_draft_dir(episode_id) / f"{platform}.json"
        if not content_file.exists():
            return None
        with open(content_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete_draft(self, episode_id: str):
        """Delete a draft and all its files."""
        import shutil
        draft_dir = self.get_draft_dir(episode_id)
        if draft_dir.exists():
            shutil.rmtree(draft_dir)
