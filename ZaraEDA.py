from pathlib import Path
import pandas as pd

base_dir = Path(__file__).resolve().parent

file_path = base_dir / "Point 1 data.csv"

df = pd.read_csv(file_path, low_memory=False)

print(df.columns.tolist())