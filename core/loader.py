import pandas as pd


def load_csv(filepath: str) -> pd.DataFrame:
    """Load CSV preserving column names exactly as AppSheet defines them."""
    df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    # Drop fully-empty rows (AppSheet exports sometimes include blank trailing rows)
    df = df[df.apply(lambda r: any(v.strip() for v in r.values), axis=1)]
    df = df.reset_index(drop=True)
    return df
