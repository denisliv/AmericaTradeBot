from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
SALESDATA_CSV: Final[Path] = DATA_DIR / "salesdata.csv"
POSTS_DIR: Final[Path] = DATA_DIR / "posts"
ASSISTED_GALLERY_DIR: Final[Path] = DATA_DIR / "assisted_gallery"
