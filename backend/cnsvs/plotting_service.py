"""
Plotting Service for Longitudinal Data
Handles extraction and visualization of longitudinal cognitive domain scores.
"""
import pdfplumber
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from io import BytesIO
from typing import Optional


def extract_longitudinal_table(pdf_path: str) -> Optional[pd.DataFrame]:
    """
    Extract longitudinal table from PDF.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        DataFrame with longitudinal data or None
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table and table[0] and any("Longitudinal View" in str(cell) for cell in table[0]):
                    # Find the header row index
                    header_idx = None
                    for i, row in enumerate(table):
                        if row and any("Longitudinal View" in str(cell) for cell in row):
                            header_idx = i
                            break
                    if header_idx is not None:
                        columns = table[header_idx]
                        data = table[header_idx+1:]
                        df = pd.DataFrame(data, columns=columns)
                        df = df.set_index(df.columns[0])
                        df = df.dropna(axis=1, how='all').dropna(axis=0, how='all')
                        df = df.apply(pd.to_numeric, errors='coerce')
                        return df
    return None


def plot_longitudinal_table(df: pd.DataFrame) -> BytesIO:
    """
    Create longitudinal plot from DataFrame.
    
    Args:
        df: DataFrame with longitudinal data
        
    Returns:
        BytesIO object containing the plot image
    """
    df_t = df.transpose()  # Rows: dates, Columns: domains
    plt.figure(figsize=(12, 7))
    x = [str(domain) for domain in df_t.columns]
    
    for date, row in df_t.iterrows():
        y = row.values
        # Skip if all values are NaN
        if pd.isna(y).all():
            continue
        colors = []
        for val in y:
            if pd.isna(val):
                colors.append('gray')
            elif val < 70:
                colors.append('red')
            elif val < 90:
                colors.append('orange')
            else:
                colors.append('green')
        plt.plot(x, y, marker='o', label=str(date))
        plt.scatter(x, y, c=colors, s=60, edgecolors='black')
    
    plt.xlabel('Domain')
    plt.ylabel('Score')
    plt.title('Longitudinal Cognitive Domain Scores (by Date)')
    plt.xticks(rotation=45, ha='right')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
    plt.tight_layout()
    
    img_bytes = BytesIO()
    plt.savefig(img_bytes, format='png')
    plt.close()
    img_bytes.seek(0)
    
    # Additional plots for every pair of consecutive dates
    def format_date_label(date):
        if hasattr(date, 'strftime'):
            return date.strftime('%Y-%m-%d %H:%M:%S')
        return str(date)
    
    date_list = [format_date_label(d) for d in df_t.index]
    n_dates = len(date_list)
    pair_plot_bytes = []
    pair_plot_labels = []
    
    if n_dates > 1:
        for i in range(n_dates):
            date1 = date_list[i]
            date2 = date_list[(i+1)%n_dates]  # wrap around
            y1 = df_t.iloc[i].values
            y2 = df_t.iloc[(i+1)%n_dates].values
            # Skip if both are all NaN
            if pd.isna(y1).all() and pd.isna(y2).all():
                continue
            plt.figure(figsize=(12, 7))
            plt.plot(x, y1, marker='o', label=date1)
            plt.plot(x, y2, marker='o', label=date2)
            plt.xlabel('Domain')
            plt.ylabel('Score')
            plt.title(f'Cognitive Domain Scores: {date1} vs {date2}')
            plt.xticks(rotation=45, ha='right')
            plt.legend()
            plt.tight_layout()
            pair_img_bytes = BytesIO()
            plt.savefig(pair_img_bytes, format='png')
            plt.close()
            pair_img_bytes.seek(0)
            pair_plot_bytes.append(pair_img_bytes)
            pair_plot_labels.append(f'Cognitive Domain Scores: {date1} vs {date2}')
    
    # Attach pair plots to main image bytes
    img_bytes.pair_plot_bytes = pair_plot_bytes
    img_bytes.pair_plot_labels = pair_plot_labels
    
    return img_bytes

