"""Step 5. Obtain the Kaggle news CSV (azraimohamad/news-article-weekly-updated).

Uses the Kaggle CLI if installed and authenticated; otherwise prints manual steps.
An existing data/news/news_v1.csv is detected and reused.
"""
import shutil
import subprocess

from newsprice.dataprep.paths import DataPaths

DATASET = "azraimohamad/news-article-weekly-updated"


def main() -> None:
    paths = DataPaths.default()
    if paths.legacy_news_csv.exists():
        print(f"Found {paths.legacy_news_csv} ({paths.legacy_news_csv.stat().st_size/1e6:.0f} MB). Nothing to download.")
        return
    paths.raw_news.mkdir(parents=True, exist_ok=True)
    existing = sorted(paths.raw_news.glob("*.csv"))
    if existing:
        print(f"Found {existing[0]}. Nothing to download.")
        return
    if shutil.which("kaggle"):
        r = subprocess.run(["kaggle", "datasets", "download", "-d", DATASET, "-p", str(paths.raw_news), "--unzip"])
        if r.returncode == 0:
            print("Downloaded to", paths.raw_news)
            return
        print("Kaggle CLI failed (check ~/.kaggle/kaggle.json).")
    print(f"Manual: open https://www.kaggle.com/datasets/{DATASET}, click Download, unzip, and put the CSV at {paths.legacy_news_csv}")


if __name__ == "__main__":
    main()
