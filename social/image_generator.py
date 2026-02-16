"""Instagram card image generator using Pillow."""

from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None


class InstagramCardGenerator:
    """Generate branded image cards for Instagram."""

    # Image dimensions (4:5 portrait ratio for IG)
    WIDTH = 1080
    HEIGHT = 1350

    # Colors
    BG_COLOR = (26, 26, 46)  # Dark blue-gray
    ACCENT_COLOR = (245, 158, 11)  # Amber
    TEXT_COLOR = (255, 255, 255)  # White
    MUTED_COLOR = (160, 160, 160)  # Gray

    def __init__(self, logo_path: Optional[Path] = None):
        """Initialize generator.

        Args:
            logo_path: Path to podcast/brand logo image
        """
        if Image is None:
            raise ImportError("Pillow is required for image generation. Install with: pip install Pillow")

        self.logo_path = logo_path
        self._load_fonts()

    def _load_fonts(self):
        """Load fonts for text rendering."""
        # Try to load system fonts, fall back to default
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",  # macOS Chinese
            "/System/Library/Fonts/STHeiti Light.ttc",  # macOS Chinese alt
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux
            "C:\\Windows\\Fonts\\msjh.ttc",  # Windows Chinese
        ]

        self.font_large = None
        self.font_medium = None
        self.font_small = None

        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    self.font_large = ImageFont.truetype(font_path, 64)
                    self.font_medium = ImageFont.truetype(font_path, 36)
                    self.font_small = ImageFont.truetype(font_path, 28)
                    break
                except Exception:
                    continue

        # Fallback to default font
        if self.font_large is None:
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def generate(self, config: dict, output_path: Path) -> Path:
        """Generate Instagram card image.

        Args:
            config: Image configuration from InstagramFormatter
            output_path: Where to save the PNG

        Returns:
            Path to generated image
        """
        # Create base image
        img = Image.new('RGB', (self.WIDTH, self.HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        y_offset = 80

        # Draw accent bar at top
        draw.rectangle([0, 0, self.WIDTH, 8], fill=self.ACCENT_COLOR)

        # Episode title (large)
        title = config.get("title", "")
        if title:
            draw.text((80, y_offset), title, font=self.font_large, fill=self.ACCENT_COLOR)
            y_offset += 80

        # Podcast name (subtitle)
        subtitle = config.get("subtitle", "")
        if subtitle:
            draw.text((80, y_offset), subtitle, font=self.font_medium, fill=self.MUTED_COLOR)
            y_offset += 60

        # Divider line
        y_offset += 20
        draw.line([(80, y_offset), (self.WIDTH - 80, y_offset)], fill=self.MUTED_COLOR, width=2)
        y_offset += 40

        # One-liner summary
        one_liner = config.get("one_liner", "")
        if one_liner:
            # Word wrap
            wrapped = self._wrap_text(one_liner, 24)
            for line in wrapped[:2]:
                draw.text((80, y_offset), line, font=self.font_medium, fill=self.TEXT_COLOR)
                y_offset += 50
            y_offset += 30

        # Body points
        body_points = config.get("body_points", [])
        if body_points:
            draw.text((80, y_offset), "💡 本集重點", font=self.font_medium, fill=self.ACCENT_COLOR)
            y_offset += 60

            for point in body_points[:3]:
                wrapped = self._wrap_text(f"• {point}", 26)
                for line in wrapped[:2]:
                    draw.text((80, y_offset), line, font=self.font_small, fill=self.TEXT_COLOR)
                    y_offset += 40
                y_offset += 10
            y_offset += 20

        # Tickers section
        tickers = config.get("tickers", [])
        if tickers:
            y_offset += 20
            ticker_text = f"📈 {', '.join(tickers[:6])}"
            draw.text((80, y_offset), ticker_text, font=self.font_small, fill=self.ACCENT_COLOR)
            y_offset += 50

        # Quote section (at bottom)
        quote = config.get("quote", "")
        host = config.get("host", "")
        if quote:
            y_offset = self.HEIGHT - 280
            draw.text((80, y_offset), "💬", font=self.font_medium, fill=self.MUTED_COLOR)
            y_offset += 50

            wrapped = self._wrap_text(f"「{quote}」", 24)
            for line in wrapped[:2]:
                draw.text((100, y_offset), line, font=self.font_medium, fill=self.TEXT_COLOR)
                y_offset += 50

            if host:
                draw.text((100, y_offset + 10), f"— {host}", font=self.font_small, fill=self.MUTED_COLOR)

        # Watermark
        draw.text(
            (self.WIDTH - 200, self.HEIGHT - 50),
            "PodSight 聲見",
            font=self.font_small,
            fill=self.MUTED_COLOR
        )

        # Bottom accent bar
        draw.rectangle([0, self.HEIGHT - 8, self.WIDTH, self.HEIGHT], fill=self.ACCENT_COLOR)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG", quality=95)
        return output_path

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        """Simple text wrapping for Chinese text."""
        lines = []
        current = ""

        for char in text:
            current += char
            if len(current) >= max_chars:
                lines.append(current)
                current = ""

        if current:
            lines.append(current)

        return lines
