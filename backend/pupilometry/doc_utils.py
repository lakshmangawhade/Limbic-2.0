import json
import os
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_UNDERLINE
from collections import defaultdict

def clean_key(key):
    """Clean and normalize keys"""
    # Also handle cases where the key might be None or not a string
    if key is None:
        return ""
    return ' '.join(str(key).replace('\n', ' ').replace('Re-', 'Response').split()).strip()

def add_horizontal_line(doc):
    """Adds a horizontal line to the document."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    run.add_break()
    p = paragraph._p
    pPr = p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'auto')
    pBdr.append(bottom)
    pPr.append(pBdr)

def extract_numeric(value_str):
    """Convert a value string to float if possible, removing common symbols."""
    if value_str is None:
        return None
    try:
        cleaned = str(value_str).replace('%', '').replace(',', '').strip()
        return float(cleaned)
    except ValueError:
        return None

def set_calibri_font(run, size_pt):
    """Set Calibri font and size for a run"""
    run.font.name = 'Calibri'
    run.font.size = Pt(size_pt)
    # Set font for both Latin and East Asian text
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')

def process_json_to_docx(json_path, output_path, groq_api_key=None):
    """
    Process JSON to DOCX with the new JSON structure format.
    
    Args:
        json_path (str): Path to the JSON file
        output_path (str): Path for the output DOCX file
        groq_api_key (str, optional): Groq API key for saccade table formatting (not used in this version)
    """
    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Create Word document
    doc = Document()

    # Add main title "Pupilometry" at the beginning
    title_p = doc.add_paragraph()
    title_r = title_p.add_run("VISUOMOTOR //")
    title_r.bold = True
    set_calibri_font(title_r, 12)
    
    # Add Pupilometry on next line
    title_p2 = doc.add_paragraph()
    title_run = title_p2.add_run("Pupilometry-")
    title_run.bold = True
    set_calibri_font(title_run, 12)
    
    # Add spacing after title
    doc.add_paragraph()
    
    # Collect flagged findings across all sections for summary
    flagged_findings = []

    # Process each table entry
    for entry in data:
        if not isinstance(entry, dict):
            continue
            
        page = entry.get('page', 1)
        table_index = entry.get('table_index', 1)
        table_heading = entry.get('table_heading', f"Table {table_index}")
        table_data = entry.get('table', [])
        
        if not table_data:
            continue
            
        # Skip tables with names "Patient Information" and "Test Information"
        if table_heading in ["Patient Information", "Test Information"]:
            continue
            
        # Write table heading in bold with Calibri 12pt
        if table_heading:
            # Normalize section names so the report always uses the requested test labels.
            heading_alias_map = {
                "Analysis Results": "Analysis",
                "Analysis": "Analysis",
                "Detection Results": "Detection",
                "Detection": "Detection",
                "Constriction Results": "Constrict Result",
                "Constrict Results": "Constrict Result",
                "Constrict Result": "Constrict Result",
                "Dilation Results": "Dialate Results",
                "Dilate Results": "Dialate Results",
                "Dialate Results": "Dialate Results",
                "Other Results": "Other Metrics",
                "Table Data": "Other Metrics",
                "Other Metrics": "Other Metrics",
            }
            normalized_heading = heading_alias_map.get(table_heading, table_heading)
            display_heading = f"{normalized_heading}:"
            p = doc.add_paragraph()
            run = p.add_run(display_heading)
            run.bold = True
            set_calibri_font(run, 12)
        else:
            normalized_heading = table_heading
        
        # Process table data - special handling for Analysis/Detection/Constriction/Dilation/Other, else default rendering
        if normalized_heading == "Analysis":
            from collections import OrderedDict
            normalized_items = OrderedDict()

            def add_item(label, value):
                if not value or str(value).strip() == "":
                    value_text = "N/A"
                else:
                    # Strip any flag marker and keep value
                    v = str(value)
                    v = v.split(" | FLAG")[0]
                    value_text = v.strip()
                # Preserve first occurrence order; overwrite to latest value for same label
                normalized_items[label] = value_text

            import re

            for row in table_data:
                if not isinstance(row, dict) or not row:
                    continue
                if should_skip_header_row(row):
                    continue
                    
                for key, value in row.items():
                    if not key:
                        continue
                    key_str = str(key)
                    # Skip generic Analysis rows
                    if key_str.strip().lower().startswith("analysis"):
                        continue

                    base_name = key_str
                    side_explicit = None

                    if key_str.endswith("_Right_Eye"):
                        base_name = key_str.replace("_Right_Eye", "").strip()
                        side_explicit = "Right"
                    elif key_str.endswith("_Left_Eye"):
                        base_name = key_str.replace("_Left_Eye", "").strip()
                        side_explicit = "Left"
                    elif key_str.endswith("_Additional"):
                        base_name = key_str[: -len("_Additional")].strip()

                    val_str = str(value) if value is not None else ""
                    # Remove flag suffix for parsing
                    val_core = val_str.split(" | FLAG")[0]

                    # Try to extract R/L values from value text
                    r_match = re.search(r"(?i)\bR\s*[:\-]?\s*([^,;\s]+)", val_core)
                    l_match = re.search(r"(?i)\bL\s*[:\-]?\s*([^,;\s]+)", val_core)

                    if side_explicit:
                        label = f"{base_name} {side_explicit}"
                        add_item(label, val_core)
                    elif r_match or l_match:
                        if r_match:
                            add_item(f"{base_name} Right", r_match.group(1))
                        if l_match:
                            add_item(f"{base_name} Left", l_match.group(1))
                    else:
                        # Single value without side
                        add_item(base_name, val_core)

            # Emit as bullet list
            for label, value_text in normalized_items.items():
                p_item = doc.add_paragraph()
                try:
                    p_item.style = 'List Bullet'
                except Exception:
                    # Fallback if style not available
                    pass
                run_label = p_item.add_run(f"{label}: ")
                set_calibri_font(run_label, 10)
                run_val = p_item.add_run(value_text if value_text else "N/A")
                set_calibri_font(run_val, 10)
        elif normalized_heading == "Detection":
            # Render Detection as a bullet list with just the condition names when values are N/A
            import re
            for row in table_data:
                if not isinstance(row, dict) or not row:
                    continue
                if should_skip_header_row(row):
                    continue
                for key, value in row.items():
                    if not key:
                        continue
                    key_str = str(key).strip()
                    # Skip generic Detection rows
                    if key_str.lower().startswith("detection"):
                        continue
                    # Normalize value
                    val_str = "" if value is None else str(value)
                    val_core = val_str.split(" | FLAG")[0].split(" → FLAG")[0].split(" | Flag")[0].split(" → Flag")[0].strip()
                    is_na = (val_core == "" or val_core.upper() in ["N/A", "NA", "NONE"])

                    p_item = doc.add_paragraph()
                    try:
                        p_item.style = 'List Bullet'
                    except Exception:
                        pass

                    if is_na:
                        # Only the condition text
                        run_label = p_item.add_run(key_str)
                        set_calibri_font(run_label, 10)
                    else:
                        # Show as key: value
                        run_label = p_item.add_run(f"{key_str}: ")
                        set_calibri_font(run_label, 10)
                        run_val = p_item.add_run(val_core)
                        set_calibri_font(run_val, 10)
                        # If flag was present, add FLAG marker
                        if ("| Flag" in val_str or "→ Flag" in val_str or "| FLAG" in val_str or "→ FLAG" in val_str):
                            flag_run = p_item.add_run(" | FLAG")
                            flag_run.bold = True
                            set_calibri_font(flag_run, 10)
                            flagged_findings.append((display_heading, key_str, f"{val_core} | FLAG"))
        elif normalized_heading in ["Constrict Result", "Dialate Results", "Other Metrics"]:
            # Group metrics by base name and format with normative ranges
            import re
            from collections import defaultdict
            
            metric_groups = defaultdict(dict)  # {base_name: {right_eye: val, left_eye: val, normative: val}}
            
            for row in table_data:
                if not isinstance(row, dict) or not row:
                    continue
                if should_skip_header_row(row):
                    continue
                
                for key, value in row.items():
                    if not key:
                        continue
                    key_str = str(key).strip()
                    
                    # Determine base name and type
                    base_name = key_str
                    metric_type = None
                    
                    if key_str.endswith("_Right_Eye"):
                        base_name = key_str[:-len("_Right_Eye")].strip()
                        metric_type = "right_eye"
                    elif key_str.endswith("_Left_Eye"):
                        base_name = key_str[:-len("_Left_Eye")].strip()
                        metric_type = "left_eye"
                    elif key_str.endswith("_Normative"):
                        base_name = key_str[:-len("_Normative")].strip()
                        metric_type = "normative"
                    else:
                        continue
                    
                    # Replace underscores with spaces in base_name
                    base_name = base_name.replace("_", " ")
                    
                    # Store value (remove flag markers for storage)
                    val_str = str(value) if value else ""
                    val_clean = val_str.split(" | FLAG")[0].split(" → FLAG")[0].split(" | Flag")[0].split(" → Flag")[0].strip()
                    has_flag = ("| Flag" in val_str or "→ Flag" in val_str or "| FLAG" in val_str or "→ FLAG" in val_str)
                    
                    if metric_type not in metric_groups[base_name]:
                        metric_groups[base_name][metric_type] = {"value": val_clean, "has_flag": has_flag}
                    else:
                        # Update if we get a better value
                        metric_groups[base_name][metric_type] = {"value": val_clean, "has_flag": has_flag}
            
            # Format and render grouped metrics
            def is_value_in_range(value_str, range_str):
                """Check if a value is within a normative range"""
                if not value_str or not range_str:
                    return True  # Can't determine, don't flag
                
                # Extract numeric value
                val_match = re.search(r'([\d.]+)', str(value_str))
                if not val_match:
                    return True
                
                val_num = float(val_match.group(1))
                
                # Extract range (e.g., "0.443 - 1.622" or "3.978 - 11.455")
                range_match = re.search(r'([\d.]+)\s*-\s*([\d.]+)', str(range_str))
                if not range_match:
                    return True  # Can't parse range, don't flag
                
                min_val = float(range_match.group(1))
                max_val = float(range_match.group(2))
                
                return min_val <= val_num <= max_val
            
            # Render each metric group as bullet items
            for base_name in sorted(metric_groups.keys()):
                group = metric_groups[base_name]
                normative = group.get("normative", {}).get("value", "")
                
                # Render Right Eye if present
                if "right_eye" in group:
                    right_data = group["right_eye"]
                    right_val = right_data["value"]
                    right_has_flag = right_data.get("has_flag", False)
                    
                    # Check if value is out of range
                    if normative and right_val and not is_value_in_range(right_val, normative):
                        right_has_flag = True
                    
                    p_item = doc.add_paragraph()
                    try:
                        p_item.style = 'List Bullet'
                    except Exception:
                        pass
                    
                    # Format: Metric Name Right Eye (normative range): value | FLAG
                    if normative:
                        run_text = p_item.add_run(f"{base_name} Right Eye ({normative}): {right_val}")
                    else:
                        run_text = p_item.add_run(f"{base_name} Right Eye: {right_val}")
                    set_calibri_font(run_text, 10)
                    
                    if right_has_flag:
                        flag_run = p_item.add_run(" | FLAG")
                        flag_run.bold = True
                        set_calibri_font(flag_run, 10)
                        flagged_findings.append((display_heading, f"{base_name} Right Eye", f"{right_val} | FLAG"))
                
                # Render Left Eye if present
                if "left_eye" in group:
                    left_data = group["left_eye"]
                    left_val = left_data["value"]
                    left_has_flag = left_data.get("has_flag", False)
                    
                    # Check if value is out of range
                    if normative and left_val and not is_value_in_range(left_val, normative):
                        left_has_flag = True
                    
                    p_item = doc.add_paragraph()
                    try:
                        p_item.style = 'List Bullet'
                    except Exception:
                        pass
                    
                    # Format: Metric Name Left Eye (normative range): value | FLAG
                    if normative:
                        run_text = p_item.add_run(f"{base_name} Left Eye ({normative}): {left_val}")
                    else:
                        run_text = p_item.add_run(f"{base_name} Left Eye: {left_val}")
                    set_calibri_font(run_text, 10)
                    
                    if left_has_flag:
                        flag_run = p_item.add_run(" | FLAG")
                        flag_run.bold = True
                        set_calibri_font(flag_run, 10)
                        flagged_findings.append((display_heading, f"{base_name} Left Eye", f"{left_val} | FLAG"))
        else:
            for row in table_data:
                if isinstance(row, dict) and row:
                    if should_skip_header_row(row):
                        continue
                    for key, value in row.items():
                        if key:  # Process if key exists, even if value is empty or N/A
                            p = doc.add_paragraph()
                            key_run = p.add_run(f"{key}: ")
                            set_calibri_font(key_run, 10)
                            # If value is None, empty, or "N/A", still include it
                            if not value or str(value).strip().upper() in ["N/A", "NA", "NONE", ""]:
                                value_run = p.add_run("N/A")
                                set_calibri_font(value_run, 10)
                            # Check if value contains flag and format it properly
                            elif ("| Flag" in str(value) or "→ Flag" in str(value) or "| FLAG" in str(value) or "→ FLAG" in str(value)):
                                value_text = str(value).split(" | FLAG")[0].split(" → FLAG")[0].split(" | Flag")[0].split(" → Flag")[0]
                                value_run = p.add_run(value_text)
                                set_calibri_font(value_run, 10)
                                flag_run = p.add_run(" | FLAG")
                                flag_run.bold = True
                                set_calibri_font(flag_run, 10)
                                flagged_findings.append((display_heading, str(key), f"{value_text} | FLAG"))
                            else:
                                value_run = p.add_run(str(value))
                                set_calibri_font(value_run, 10)
                # No spacing between rows - removed the extra paragraph
        
    # Append Summary of Flagged Findings at the end
    if flagged_findings:
        summary_p = doc.add_paragraph()
        summary_run = summary_p.add_run("Summary of Flagged Findings:")
        summary_run.bold = True
        set_calibri_font(summary_run, 12)
        for table_name, row_name, val in flagged_findings:
            p_item = doc.add_paragraph()
            try:
                p_item.style = 'List Bullet'
            except Exception:
                pass
            # Split the value to make " | FLAG" bold
            if " | FLAG" in val:
                base_val = val.replace(" | FLAG", "")
                line = f"{table_name.rstrip(':')}: {row_name}: {base_val}"
                r = p_item.add_run(line)
                set_calibri_font(r, 10)
                flag_run = p_item.add_run(" | FLAG")
                flag_run.bold = True
                set_calibri_font(flag_run, 10)
            else:
                line = f"{table_name.rstrip(':')}: {row_name}: {val}"
                r = p_item.add_run(line)
                set_calibri_font(r, 10)

    # Save document
    doc.save(output_path)
    print(f"Document saved to {output_path}")

def should_skip_header_row(row):
    """Determine if a row should be skipped because it contains column headers"""
    if not row:
        return False
    
    # Check if this row contains generic header values
    header_indicators = [
        "metric", "result value", "right eye", "left eye", 
        "normative data", "column", "additional value", "reference range"
    ]
    
    for key, value in row.items():
        key_lower = str(key).lower() if key else ""
        value_lower = str(value).lower() if value else ""
        
        # If both key and value are header indicators, skip this row
        if any(indicator in key_lower for indicator in header_indicators) and \
           any(indicator in value_lower for indicator in header_indicators):
            return True
        
        # Special case: if key is "Metric" and value is "Result Value" or similar
        if "metric" in key_lower and any(indicator in value_lower for indicator in header_indicators):
            return True
    
    return False

# Example usage (commented out to avoid execution during import)
#json_file_path = "data\json_output\ABR19840114_Pupilometry_25.06.24.Report.1_final.json"
#output_docx_path = "data\json_output\ABR19840114_Pupilometry_25.06.24.Report.1.docx"
#groq_api_key = os.getenv("GROQ_API_KEY")
#process_json_to_docx(json_file_path, output_docx_path, groq_api_key)





