import numpy as np
import pandas as pd
import logging

def safe_df_to_records(df):
    """Convert DataFrame to records, ensuring all values are JSON serializable"""
    if df is None or df.empty: return []
    try:
        # Convert DataFrame to records
        records = df.to_dict('records')
        
        # Convert each value to JSON-safe type
        def convert_value(v):
            if v is None:
                return None
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                return None
            if isinstance(v, (np.integer, np.int64, np.int32)):
                return int(v)
            if isinstance(v, (np.floating, np.float64, np.float32)):
                return float(v) if not np.isnan(v) else None
            if isinstance(v, np.bool_):
                return bool(v)
            if isinstance(v, (np.ndarray, list)):
                return [convert_value(x) for x in v]
            if pd.isna(v):
                return None
            return v
        
        clean_records = []
        for record in records:
            clean_record = {}
            for k, v in record.items():
                clean_record[k] = convert_value(v)
            clean_records.append(clean_record)
        
        return clean_records
    except Exception as e:
        logging.error(f"Error converting DataFrame to records: {e}")
        return []
