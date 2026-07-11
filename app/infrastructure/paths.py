from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
SALESDATA_CSV: Final[Path] = DATA_DIR / "salesdata.csv"
POSTS_DIR: Final[Path] = DATA_DIR / "posts"
ASSISTED_GALLERY_DIR: Final[Path] = DATA_DIR / "assisted_gallery"
LOGO_JPG: Final[Path] = DATA_DIR / "logo" / "logo.jpg"
WARM_UP_POSTS_IMG_DIR: Final[Path] = DATA_DIR / "warm_up_posts_img"
WEEKLY_POSTS_IMG_DIR: Final[Path] = DATA_DIR / "weekly_posts_img"
