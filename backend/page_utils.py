import json
import pdfplumber

def load_extracted_pages(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(entry["page"] for entry in data)


def get_total_pages(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)