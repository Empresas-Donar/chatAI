import pandas as pd


def load_csv(filepath: str) -> pd.DataFrame:
    return pd.read_csv(filepath, dtype=str, keep_default_na=False)
