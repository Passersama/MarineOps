"""Prepare the existing approved PNG for Qt and Windows icon containers."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / "assets" / "branding"
original = Image.open(folder / "cargo-track-logo-v1.png").convert("RGBA")
bounds = original.getchannel("A").point(lambda a: 255 if a >= 48 else 0).getbbox()
original.crop(bounds).save(folder / "cargo-track-lockup.png")

# Extract only the approved box/route symbol, excluding the adjacent wordmark.
symbol = original.crop((160, 165, 650, 530))
symbol.paste((0, 0, 0, 0), (440, 120, 490, 365))
icon = Image.new("RGBA", (256, 256))
symbol.thumbnail((232, 232), Image.Resampling.LANCZOS)
icon.alpha_composite(symbol, ((256 - symbol.width) // 2, (256 - symbol.height) // 2))
icon.save(folder / "cargo-track-symbol.png")
icon.save(folder / "cargo-track.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)])
print("Prepared existing logo: transparent lockup, symbol and multi-resolution Windows ICO")
