"""
HTML Generation Service
Generates HTML output following the Dart Editor HTML guide format.
Enhanced with support for NPQ and PSQI table formatting.
"""
import base64
import re
import string
from io import BytesIO
from typing import Dict, List, Tuple, Optional
import pandas as pd

from .limbic_service import RESPONSE_PHRASES


def escape_html(text: str) -> str:
    """Escape HTML special characters for security."""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def image_to_base64(img_bytes: BytesIO) -> str:
    """Convert image bytes to base64 data URL for security."""
    img_bytes.seek(0)
    img_data = img_bytes.read()
    img_base64 = base64.b64encode(img_data).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"


def create_html_document(content: str) -> str:
    """
    Create a complete HTML document with proper structure.
    
    Args:
        content: The HTML body content
        
    Returns:
        Complete HTML document string
    """
    # Use string replacement instead of .format() to avoid issues with CSS braces
    html_template = """<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medical Evaluation Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            font-size: 24px;
            font-weight: bold;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        h2 {
            font-size: 20px;
            font-weight: bold;
            margin-top: 18px;
            margin-bottom: 10px;
        }
        h3 {
            font-size: 16px;
            font-weight: bold;
            margin-top: 16px;
            margin-bottom: 8px;
        }
        pre {
            background-color: #f0f0f0;
            padding: 10px;
            border-left: 4px solid #ccc;
            margin: 10px 0;
            font-family: Arial, sans-serif;
            white-space: pre-wrap;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 10px 0;
        }
        th {
            background-color: #e0e0e0;
            font-weight: bold;
            padding: 8px;
            border: 1px solid #ccc;
            text-align: left;
        }
        td {
            padding: 8px;
            border: 1px solid #ccc;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        tr:hover {
            background-color: #f0f0f0;
        }
        ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        li {
            margin: 5px 0;
        }
        .aligned-list {
            list-style-type: none;
            padding-left: 0;
            font-family: Calibri, sans-serif;
            font-size: 10pt;
            white-space: pre;
            line-height: 1.5;
        }
        .aligned-list li {
            margin: 2px 0;
        }
        .aligned-list li::before {
            content: "• ";
            font-size: 10pt;
        }
        .aligned-list-header {
            font-weight: bold;
            margin-bottom: 5px;
        }
        .aligned-list-header::before {
            content: "";
        }
        .no-bullet::before {
            content: "";
        }
        .total-score-item {
            font-weight: bold;
            background-color: #d4edda;
            padding: 2px 0;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 10px 0;
        }
        p {
            margin: 6px 0;
        }
        .page-break {
            page-break-after: always;
        }
        .total-score-row {
            background-color: #d4edda !important;
            font-weight: bold;
        }
    </style>
</head>
<body>
{CONTENT_PLACEHOLDER}
</body>
</html>"""
    # Use replace instead of format to avoid issues with CSS braces
    return html_template.replace("{CONTENT_PLACEHOLDER}", content)


def html_heading(level: int, text: str) -> str:
    """
    Create HTML heading following the guide.
    
    Args:
        level: Heading level (1-3)
        text: Heading text
        
    Returns:
        HTML heading tag
    """
    text = escape_html(str(text))
    return f"<h{level}>{text}</h{level}>"


def html_paragraph(text: str = "", raw_html: bool = False) -> str:
    """
    Create HTML paragraph. Empty paragraph for spacing.
    
    Args:
        text: Paragraph text (empty for spacing)
        raw_html: If True, don't escape HTML tags in text
        
    Returns:
        HTML paragraph tag
    """
    if not text:
        return "<p></p>"
    if not raw_html:
        text = escape_html(str(text))
    return f"<p>{text}</p>"


def html_section_header(text: str) -> str:
    """
    Create section header (gray bar style) using <pre> tag.
    
    Args:
        text: Section header text
        
    Returns:
        HTML pre tag for section header
    """
    text = escape_html(str(text))
    return f"<pre>{text}</pre>"


def html_bold(text: str) -> str:
    """Create bold text using <strong> tag."""
    return f"<strong>{escape_html(str(text))}</strong>"


def html_italic(text: str) -> str:
    """Create italic text using <em> tag."""
    text = escape_html(str(text))
    return f"<em>{text}</em>"


def html_underline(text: str) -> str:
    """Create underlined text using <u> tag."""
    text = escape_html(str(text))
    return f"<u>{text}</u>"


def html_line_break() -> str:
    """Create line break."""
    return "<br/>"


def html_span_with_break(text: str) -> str:
    """
    Create span with break for spacing control.
    Use when spacing between lines is too much.
    
    Args:
        text: Text content
        
    Returns:
        HTML span with break
    """
    text = escape_html(str(text))
    return f"<span>{text}</span><br/>"


def html_table(headers: List[str], rows: List[List[str]], highlight_rows: Optional[List[int]] = None) -> str:
    """
    Create HTML table following the guide format.
    
    Args:
        headers: List of header column names
        rows: List of rows, each row is a list of cell values
        highlight_rows: Optional list of row indices to highlight (0-based)
        
    Returns:
        HTML table string
    """
    html = "<table>\n"
    
    # Header row
    html += "  <tr>\n"
    for header in headers:
        header_text = escape_html(str(header)) if header else ""
        html += f"    <th>{header_text}</th>\n"
    html += "  </tr>\n"
    
    # Data rows
    for row_idx, row in enumerate(rows):
        # Check if this row should be highlighted
        row_class = ""
        if highlight_rows and row_idx in highlight_rows:
            row_class = ' class="total-score-row"'
        
        html += f"  <tr{row_class}>\n"
        for cell in row:
            cell_text = escape_html(str(cell)) if cell else ""
            html += f"    <td>{cell_text}</td>\n"
        html += "  </tr>\n"
    
    html += "</table>"
    return html


def html_aligned_list(headers: List[str], rows: List[List[str]], highlight_rows: Optional[List[int]] = None, stop_at_total: bool = False) -> str:
    """
    Create aligned bullet-point list with columns aligned at same character position.
    Headers are not bulleted, data rows have bullets.
    Uses Calibri font at 10pt.
    
    Args:
        headers: List of header column names
        rows: List of rows, each row is a list of cell values
        highlight_rows: Optional list of row indices to highlight (0-based)
        stop_at_total: If True, stop adding bullets after a row containing "total score"
        
    Returns:
        HTML string with aligned list
    """
    if not rows:
        return ""
    
    # Determine column widths based on both headers and data
    num_cols = len(headers)
    col_widths = [len(str(h)) for h in headers]
    
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Add some padding
    col_widths = [w + 3 for w in col_widths]
    
    html_parts = []
    html_parts.append('<ul class="aligned-list">')
    
    # Header row (without bullet)
    header_line = ""
    for i, header in enumerate(headers):
        header_line += str(header).ljust(col_widths[i])
    html_parts.append(f'<li class="aligned-list-header">{escape_html(header_line)}</li>')
    
    # Data rows (with bullets, stopping at total score if specified)
    found_total = False
    for row_idx, row in enumerate(rows):
        is_highlighted = highlight_rows and row_idx in highlight_rows
        
        # Check if this row contains "total score"
        if stop_at_total and not found_total:
            domain_lower = row[0].lower() if row else ""
            if 'total score' in domain_lower or domain_lower.endswith('total'):
                found_total = True
        
        # If we've already found total and stop_at_total is True, stop processing rows
        # (The total score row itself should still be included with a bullet)
        if found_total and stop_at_total:
            # Check if this is the total score row (include it) or a row after it (exclude it)
            domain_lower = row[0].lower() if row else ""
            is_total_row = 'total score' in domain_lower or domain_lower.endswith('total')
            if not is_total_row:
                # This is a row after the total score - stop here
                break
        
        row_line = ""
        for i, cell in enumerate(row):
            if i < len(col_widths):
                row_line += str(cell).ljust(col_widths[i])
            else:
                row_line += str(cell)
        
        if is_highlighted:
            html_parts.append(f'<li class="total-score-item">{escape_html(row_line)}</li>')
        else:
            html_parts.append(f'<li>{escape_html(row_line)}</li>')
    
    html_parts.append("</ul>")
    return "\n".join(html_parts)


def html_list_item(text: str, raw_html: bool = False) -> str:
    """
    Create HTML list item.
    
    Args:
        text: List item text
        raw_html: If True, don't escape HTML tags in text
        
    Returns:
        HTML list item
    """
    if not raw_html:
        text = escape_html(str(text))
    return f"<li>{text}</li>"


def html_image(img_bytes: BytesIO, alt_text: str = "Image") -> str:
    """
    Create HTML image tag with base64 encoding.
    
    Args:
        img_bytes: Image bytes
        alt_text: Alt text for accessibility
        
    Returns:
        HTML img tag with base64 data URL
    """
    try:
        img_data_url = image_to_base64(img_bytes)
        alt_text = escape_html(alt_text)
        return f'<img src="{img_data_url}" alt="{alt_text}" />'
    except Exception:
        return html_paragraph(f"[Image: {alt_text}]")


def html_page_break() -> str:
    """Create page break for printing."""
    return '<div class="page-break"></div>'


def parse_questionnaire_table(section_text: str, test_name: str = "") -> Tuple[Optional[Dict], str]:
    """
    Extract questionnaire table data from raw section text.
    Handles NPQ (3-column), PSQI (2-column), and PCL-5 (2-column) formats.
    
    NPQ Format:
    Domain Score Severity Description
    Attention 300 Severe
    
    PSQI Format:
    Domain Score
    Duration Of Sleep 1
    PSQI Total Score 17
    
    PCL-5 Format:
    Intrusion (Items 1 - 5) 25
    Persistent Avoidance (Items 6 - 7) 10
    Total Score (Items 1 - 20) 89
    
    Args:
        section_text: Raw section text that may contain a table
        test_name: Name of the test (used to detect PSQI, PCL-5)
        
    Returns:
        Tuple of (table_info_dict, remaining_text)
        - table_info_dict: Dict with 'headers', 'rows', 'highlight_rows', 'stop_at_total' or None
        - remaining_text: Section text with table removed
    """
    lines = section_text.split('\n')
    table_start_idx = -1
    table_end_idx = -1
    has_severity_column = False
    table_rows = []
    
    # Check if this is a PSQI test
    is_psqi = "PSQI" in test_name.upper() or "PITTSBURGH" in test_name.upper() or "SLEEP QUALITY" in test_name.upper()
    
    # Check if this is a PCL-5 test
    is_pcl5 = "PCL-5" in test_name.upper() or "PTSD CHECKLIST" in test_name.upper()
    
    # For PCL-5, detect table pattern: "Domain Name (Items X - Y) Score"
    if is_pcl5:
        import re
        # Pattern matches: Domain name (Items X - Y) Score
        # Handles variations: "Items 1 - 5", "Items 1-5", "Items 1- 5", etc.
        pcl5_pattern = r'^([A-Z][^\(]+?)\s*\(Items\s+\d+\s*[-–]\s*\d+\)\s+(\d+)$'
        pcl5_rows = []
        pcl5_start_idx = -1
        pcl5_end_idx = -1
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(pcl5_pattern, stripped)
            if match:
                if pcl5_start_idx == -1:
                    pcl5_start_idx = i
                domain = match.group(1).strip()
                score = match.group(2).strip()
                pcl5_rows.append([domain, score])
                pcl5_end_idx = i + 1  # Update end index
            elif pcl5_rows and stripped:
                # End of table if we have rows and hit a non-matching line
                pcl5_end_idx = i
                break
        
        if pcl5_rows:
            # Found PCL-5 table
            table_rows = pcl5_rows
            table_start_idx = pcl5_start_idx
            table_end_idx = pcl5_end_idx
            has_severity_column = False
        else:
            # No PCL-5 table found, continue with normal parsing
            is_pcl5 = False
    
    # Only continue with normal parsing if we haven't found a PCL-5 table
    if not (is_pcl5 and table_rows):
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Detect table header line
            # For PSQI, always use 2 columns (no severity description)
            if is_psqi and 'Domain' in stripped and 'Score' in stripped:
                table_start_idx = i
                has_severity_column = False
                continue
            
            # Check for NPQ format (3 columns) - only if not PSQI
            elif not is_psqi and ('Domain' in stripped and 'Score' in stripped and 
                ('Severity' in stripped or 'Description' in stripped)):
                table_start_idx = i
                has_severity_column = True
                continue
            
            # Check for PSQI format (2 columns) - fallback for non-PSQI tests
            elif 'Domain' in stripped and 'Score' in stripped and 'Severity' not in stripped:
                table_start_idx = i
                has_severity_column = False
                continue
            
            # If we found the header, start collecting data
            if table_start_idx != -1 and i > table_start_idx:
                # Skip empty lines
                if not stripped:
                    if table_rows:  # End of table if we already have data
                        table_end_idx = i
                        break
                    continue
            
            # For PSQI, check if this line starts with a numbered question (1, 2, 3, etc.)
            # If so, we've reached the end of the table section
            if is_psqi and stripped:
                first_word = stripped.split()[0] if stripped.split() else ""
                # Check if line starts with a number (1-9) followed by a space or text
                # This indicates a numbered question, not a domain/score row
                if first_word.isdigit() and len(first_word) <= 2:
                    if table_rows:  # End of table if we already have data
                        table_end_idx = i
                        break
                    continue
            
            # For PSQI, handle multiple domain/score pairs on a single line
            if is_psqi and not has_severity_column:
                parts = stripped.split()
                # Find all numeric scores in the line
                score_indices = []
                for j, part in enumerate(parts):
                    # Score could be integer or have decimal
                    if part.replace('.', '').isdigit():
                        score_indices.append(j)
                
                # Extract domain/score pairs
                if score_indices:
                    prev_idx = 0
                    for score_idx in score_indices:
                        # Domain is everything from previous score (or start) to current score
                        if prev_idx < score_idx:
                            domain = ' '.join(parts[prev_idx:score_idx])
                            score = parts[score_idx]
                            # Only add if domain is not empty
                            if domain.strip():
                                table_rows.append([domain.strip(), score])
                        prev_idx = score_idx + 1
                    
                    # Check if there's text after the last score (might be another domain/score pair)
                    # But if we've already processed scores, we'll stop here for this line
                else:
                    # No scores found, might be end of table or continuation
                    # Check if this looks like it could be a domain name (has capital letters)
                    # If not, it's probably the end of the table section
                    if table_rows:
                        # If line doesn't look like a domain/score pattern, end table
                        if not any(word[0].isupper() if word else False for word in parts[:3]):
                            table_end_idx = i
                            break
            else:
                # For NPQ or single domain/score per line format
                parts = stripped.split()
                
                if len(parts) >= 2:
                    # Find the score (should be numeric)
                    score_idx = None
                    for j, part in enumerate(parts):
                        # Score could be integer or have decimal
                        if part.replace('.', '').isdigit():
                            score_idx = j
                            break
                    
                    if score_idx is not None:
                        # Everything before score is domain
                        domain = ' '.join(parts[:score_idx])
                        score = parts[score_idx]
                        
                        if has_severity_column:
                            # NPQ format: has severity column
                            severity = ' '.join(parts[score_idx + 1:]) if score_idx + 1 < len(parts) else ''
                            table_rows.append([domain, score, severity])
                        else:
                            # PSQI format: no severity column (single pair per line)
                            table_rows.append([domain, score])
    
    # If no table found, return None
    if not table_rows or table_start_idx == -1:
        return None, section_text
    
    # Determine which rows to highlight (total score rows)
    highlight_rows = []
    for idx, row in enumerate(table_rows):
        domain_lower = row[0].lower()
        if 'total' in domain_lower or 'score' in domain_lower:
            # Check if it's actually a total row (not just a domain containing "score")
            if 'total score' in domain_lower or domain_lower.endswith('total'):
                highlight_rows.append(idx)
    
    # Create headers based on format
    if has_severity_column:
        headers = ["Domain", "Score", "Severity Description"]
    else:
        headers = ["Domain", "Score"]
    
    # Remove table section from original text
    if table_end_idx == -1:
        # Table goes to end or we need to estimate
        table_end_idx = table_start_idx + len(table_rows) + 2  # +2 for header and possible blank
    
    # Reconstruct text without table
    remaining_lines = lines[:table_start_idx] + lines[table_end_idx:]
    remaining_text = '\n'.join(remaining_lines)
    
    table_info = {
        'headers': headers,
        'rows': table_rows,
        'highlight_rows': highlight_rows if highlight_rows else None,
        'stop_at_total': is_psqi  # Only stop at total for PSQI
    }
    
    return table_info, remaining_text


def create_limbic_html_section(
    identified_tests: List[Dict[str, str]],
    test_sections: Dict[str, str],
    test_patterns: Dict
) -> str:
    """
    Create HTML section for limbic tests.
    Follows the same logic as DOCX generation for consistency.
    Now includes aligned bullet-point formatting for NPQ, PSQI, and similar questionnaires.
    
    Args:
        identified_tests: List of identified tests
        test_sections: Dictionary of test sections
        test_patterns: Test patterns dictionary
        
    Returns:
        HTML string for limbic section
    """
    html_parts = []
    
    # Main heading
    html_parts.append(html_heading(1, "SCALES //"))
    html_parts.append(html_paragraph())
    
    if not test_sections:
        html_parts.append(html_paragraph("No test sections were extracted."))
    else:
        for test_id, section in test_sections.items():
            # Test name as heading
            test_info = test_patterns.get(test_id, {})
            test_name = test_info.get("name", test_id)
            html_parts.append(html_heading(2, test_name))
            html_parts.append(html_paragraph())
            
            # Check if this test has a table format (NPQ, PSQI, PCL-5, or similar questionnaire)
            test_name_upper = test_name.upper()
            is_table_format = (
                "NPQ" in test_name_upper or 
                "PSQI" in test_name_upper or 
                "PCL-5" in test_name_upper or
                "PTSD CHECKLIST" in test_name_upper or
                "QUESTIONNAIRE" in test_name_upper or
                "PITTSBURGH" in test_name_upper or
                "SLEEP QUALITY" in test_name_upper
            )
            
            # Check if this is a PSQI test
            is_psqi = "PSQI" in test_name_upper or "PITTSBURGH" in test_name_upper or "SLEEP QUALITY" in test_name_upper
            
            if is_table_format:
                table_info, remaining_text = parse_questionnaire_table(section, test_name)
                
                if table_info:
                    # Create aligned bullet-point list instead of table
                    html_parts.append(html_aligned_list(
                        table_info['headers'], 
                        table_info['rows'],
                        table_info.get('highlight_rows'),
                        table_info.get('stop_at_total', False)
                    ))
                    html_parts.append(html_paragraph())
                    
                    # Continue with remaining text
                    section = remaining_text
            
            # Preprocess lines to join wrapped lines (same logic as DOCX)
            merged_lines = []
            buffer = ""
            lines = section.split('\n')
            
            # For PSQI, preprocess lines to split alphabetic sub-questions (a., b., c., etc.)
            if is_psqi:
                preprocessed_lines = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        preprocessed_lines.append("")
                        continue
                    
                    # Find all positions where pattern " [a-z]. " appears (space + lowercase letter + period + space)
                    # This pattern indicates the start of a new alphabetic sub-question
                    pattern = r' ([a-z]\.) '
                    matches = list(re.finditer(pattern, line))
                    
                    if matches:
                        # Split the line at each match position
                        split_lines = []
                        last_end = 0
                        
                        for match in matches:
                            # Add text before this match (could be main question or previous sub-question)
                            before_text = line[last_end:match.start()].strip()
                            if before_text:
                                split_lines.append(before_text)
                            
                            # Update pointer to start from the letter (skip the leading space)
                            last_end = match.start() + 1  # +1 to skip the space before the letter
                        
                        # Add the last sub-question (from last match to end of line)
                        if last_end < len(line):
                            last_text = line[last_end:].strip()
                            if last_text:
                                split_lines.append(last_text)
                        
                        # Add all split lines
                        preprocessed_lines.extend(split_lines)
                    else:
                        # No sub-questions found, keep line as is
                        preprocessed_lines.append(line)
                
                lines = preprocessed_lines
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                
                # For PSQI, check if line starts with a number (questions 1-5)
                is_psqi_question = False
                if is_psqi and parts and parts[0].isdigit() and len(parts[0]) <= 2:
                    is_psqi_question = True
                
                is_new_bullet = (
                    len(parts) > 4 and
                    parts[0].isdigit() and
                    parts[1].isdigit() and
                    parts[2] == '-'
                )
                is_heading = line.startswith('**')
                is_score_line = (
                    "score" in line.lower() or "severity" in line.lower()
                    or (len(parts) == 1 and parts[0].isdigit())
                    or (len(parts) == 2 and parts[1].isdigit() and "score" in parts[0].lower())
                    or ("score" in line.lower() and len(parts) <= 4)
                )
                is_footnote = (
                    line.lower().startswith("developed by") or
                    line.lower().startswith("no permission required") or
                    line.lower().startswith("psychiatry research") or
                    line.lower().startswith("used with permission") or
                    line.lower().startswith("reference") or
                    line.lower().startswith("references")
                )
                
                # Check if line is a list item (a., b., c., etc.)
                is_list_item = bool(re.match(r'^[a-z]\.\s+', line))
                
                if is_new_bullet or is_heading or is_score_line or is_footnote or is_psqi_question or is_list_item or not buffer:
                    if buffer:
                        merged_lines.append(buffer)
                        buffer = ""
                    buffer = line
                else:
                    prev_parts = buffer.split()
                    prev_is_bullet = (
                        len(prev_parts) > 4 and
                        prev_parts[0].isdigit() and
                        prev_parts[1].isdigit() and
                        prev_parts[2] == '-'
                    )
                    # Check if previous line was a PSQI question
                    prev_is_psqi_question = False
                    if is_psqi and prev_parts and prev_parts[0].isdigit() and len(prev_parts[0]) <= 2:
                        prev_is_psqi_question = True
                    
                    # Check if previous line was a list item
                    prev_is_list_item = bool(re.match(r'^[a-z]\.\s+', buffer))
                    
                    if prev_is_bullet and not (parts and parts[0].isdigit()) and not is_heading and not is_score_line and not is_footnote:
                        buffer += " " + line
                    elif prev_is_psqi_question and not is_psqi_question and not is_heading and not is_score_line and not is_footnote and not is_list_item:
                        # Continuation of PSQI question
                        buffer += " " + line
                    elif prev_is_list_item and not is_list_item and not is_heading and not is_score_line and not is_footnote:
                        # Continuation of list item
                        buffer += " " + line
                    else:
                        merged_lines.append(buffer)
                        buffer = line
            if buffer:
                merged_lines.append(buffer)
            
            # Process merged lines
            in_list = False
            for line in merged_lines:
                # Check if line contains "Interpretation of Total Score" and bold it
                # But only if it's not already bolded (not inside <strong> tags or marked with **)
                line_has_bold = False
                if re.search(r'Interpretation\s+of\s+Total\s+Score', line, re.IGNORECASE):
                    # Check if the phrase is already inside <strong> tags
                    # Pattern: <strong>...Interpretation of Total Score...</strong>
                    already_bolded_pattern = r'<strong>.*?Interpretation\s+of\s+Total\s+Score.*?</strong>'
                    already_bolded = re.search(already_bolded_pattern, line, re.IGNORECASE | re.DOTALL)
                    
                    # Also check if line starts with ** (will be bolded as heading)
                    starts_with_bold_marker = line.strip().startswith('**')
                    
                    if not already_bolded and not starts_with_bold_marker:
                        # Bold the phrase "Interpretation of Total Score"
                        bolded_line = re.sub(
                            r'(Interpretation\s+of\s+Total\s+Score)',
                            lambda m: html_bold(m.group(1)),
                            line,
                            flags=re.IGNORECASE
                        )
                        line = bolded_line
                        line_has_bold = True
                    else:
                        # Already bolded, but might contain HTML, so set flag
                        if '<strong>' in line.lower() or starts_with_bold_marker:
                            line_has_bold = True
                
                if line.startswith('**'):
                    if in_list:
                        html_parts.append("</ul>")
                        in_list = False
                    subheading_text = line.strip('*')
                    # Use raw_html=True when passing html_bold() output
                    html_parts.append(html_paragraph(html_bold(subheading_text), raw_html=True))
                else:
                    parts = line.split()
                    
                    # For PSQI, check if this is a numbered question (1-5 or a-z)
                    if is_psqi and parts:
                        # Check for main questions (1, 2, 3, 4, 5)
                        if parts[0].isdigit() and len(parts[0]) <= 2:
                            if in_list:
                                html_parts.append("</ul>")
                                in_list = False
                            # Just output as paragraph - the question with its answer
                            html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                            continue
                        # Check for sub-questions (a., b., c., etc.)
                        elif len(parts[0]) >= 2 and parts[0][0].isalpha() and parts[0][1] == '.':
                            if in_list:
                                html_parts.append("</ul>")
                                in_list = False
                            # Output as paragraph
                            html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                            continue
                    
                    # Check for bullet pattern: digit digit - ...
                    if (
                        len(parts) > 4 and
                        parts[0].isdigit() and
                        parts[1].isdigit() and
                        parts[2] == '-'
                    ):
                        if not in_list:
                            html_parts.append("<ul>")
                            in_list = True
                        score = parts[1]
                        dash_index = line.find('-')
                        after_dash = line[dash_index+1:].strip()
                        response = ""
                        question = after_dash
                        for phrase in RESPONSE_PHRASES:
                            if after_dash.startswith(phrase):
                                response = phrase
                                question = after_dash[len(phrase):].strip()
                                break
                        bullet = f"{question}: {score} - {response}"
                        html_parts.append(html_list_item(bullet))
                    # Check for other bullet patterns
                    elif len(parts) > 3 and parts[0][0].isdigit():
                        score_idx = None
                        for i, part in enumerate(parts):
                            if part.isdigit() and i != 0:
                                score_idx = i
                                break
                        if score_idx is not None and score_idx + 2 <= len(parts):
                            if parts[score_idx + 1] == '-':
                                if not in_list:
                                    html_parts.append("<ul>")
                                    in_list = True
                                question = ' '.join(parts[:score_idx])
                                question = question.lstrip('0123456789').strip()
                                score = parts[score_idx]
                                response = ' '.join(parts[score_idx + 2:])
                                bullet = f"{question}: {score} - {response}"
                                html_parts.append(html_list_item(bullet))
                            else:
                                if in_list:
                                    html_parts.append("</ul>")
                                    in_list = False
                                html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                        else:
                            if in_list:
                                html_parts.append("</ul>")
                                in_list = False
                            html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                    elif len(parts) > 3 and (parts[0][0].isalpha() and (parts[0].endswith('.') or parts[0].endswith(')'))):
                        double_space_index = line.find('  ')
                        if double_space_index != -1:
                            if not in_list:
                                html_parts.append("<ul>")
                                in_list = True
                            left = line[:double_space_index].strip()
                            right = line[double_space_index:].strip()
                            right_parts = right.split(' - ', 1)
                            if len(right_parts) == 2:
                                score = right_parts[0].strip()
                                response = right_parts[1].strip()
                                question = left[2:].strip().lstrip(string.punctuation + " ").rstrip(string.punctuation + " ")
                                bullet = f"{question}: {score} - {response}"
                                html_parts.append(html_list_item(bullet))
                            else:
                                if in_list:
                                    html_parts.append("</ul>")
                                    in_list = False
                                html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                        else:
                            if in_list:
                                html_parts.append("</ul>")
                                in_list = False
                            html_parts.append(html_paragraph(line, raw_html=line_has_bold))
                    elif line.startswith('•'):
                        if not in_list:
                            html_parts.append("<ul>")
                            in_list = True
                        content = line[1:].strip()
                        if ':' in content:
                            idx = content.rfind(':')
                            question = content[:idx].strip()
                            rest = content[idx+1:].strip()
                            bullet = f"{question}: {rest}"
                            html_parts.append(html_list_item(bullet))
                        else:
                            html_parts.append(html_list_item(content))
                    else:
                        if in_list:
                            html_parts.append("</ul>")
                            in_list = False
                        html_parts.append(html_paragraph(line, raw_html=line_has_bold))
            
            # Close any open list
            if in_list:
                html_parts.append("</ul>")
            
            # Page break between tests (except last)
            if test_id != list(test_sections.keys())[-1]:
                html_parts.append(html_page_break())
    
    return "\n".join(html_parts)


def create_cognitive_html_section(
    upper_table_df: Optional[pd.DataFrame],
    cognitive_test_data: Dict,
    standard_scores: List[Tuple[str, str]],
    test_standard_scores: Dict,
    CANONICAL_TESTS: List[str],
    flagged_findings: Optional[List[Dict]] = None
) -> str:
    """
    Create HTML section for cognitive data.
    
    Args:
        upper_table_df: DataFrame with domain scores
        cognitive_test_data: Dictionary of cognitive test data
        standard_scores: List of standard score tuples
        test_standard_scores: Dictionary of test standard scores
        CANONICAL_TESTS: List of canonical test names
        flagged_findings: Optional list to collect flagged findings (mutated in place)
        
    Returns:
        HTML string for cognitive section
    """
    if flagged_findings is None:
        flagged_findings = []
    
    html_parts = []
    
    # COGNITIVE // heading
    html_parts.append(html_heading(1, "COGNITIVE //"))
    html_parts.append(html_paragraph())
    
    # Cognitive Domain Scores header
    # Use raw_html=True when passing html_bold() output
    html_parts.append(html_paragraph(
        html_bold("Cognitive Domain Scores (Flagged where Percentile < 30) -"),
        raw_html=True
    ))
    
    # Domain scores as list items
    if upper_table_df is not None:
        html_parts.append("<ul>")
        for _, row in upper_table_df.iterrows():
            domain = row.get('Domain Scores', '')
            std = row.get('Standard Score') if 'Standard Score' in row else row.get('Score', '')
            perc = row.get('Percentile', '')
            
            try:
                std_float = float(str(std).replace('-', '').strip())
                perc_float = float(str(perc).replace('-', '').strip())
                is_flagged = perc_float < 30  # Flag if Percentile < 30
                flag_text = " | FLAG" if is_flagged else ""
            except:
                is_flagged = False
                flag_text = ""
            
            if is_flagged:
                # Collect flagged finding
                flagged_findings.append({
                    "type": "Domain Score",
                    "name": domain,
                    "standard_score": str(std),
                    "percentile": str(perc),
                    "category": "Cognitive Domain"
                })
                # Build text with HTML and use raw_html=True
                text = f"{escape_html(domain)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                html_parts.append(html_list_item(text, raw_html=True))
            else:
                text = f"{domain}: Standard Score: {std} | Percentile: {perc}"
                html_parts.append(html_list_item(text))
        html_parts.append("</ul>")
    
    html_parts.append(html_paragraph())
    
    # Define test groups
    SPECIFIC_TESTS = [
        "Verbal Memory Test (VBM)",
        "Visual Memory Test (VSM)",
        "Finger Tapping Test (FTT)",
        "Symbol Digit Coding (SDC)",
        "Stroop Test (ST)",
        "Shifting Attention Test (SAT)",
        "Continuous Performance Test (CPT)",
        "Perception Of Emotions Test (POET)",
        "Positive Emotions",
        "Negative Emotions",
        "Reasoning Test (RT)",
    ]
    
    FOUR_PART_TESTS = [
        "Part 1",
        "Part 2",
        "Part 3",
        "Part 4",
    ]

    # Specific Test Scores header
    html_parts.append(html_paragraph(
        html_bold("Specific Test Scores (Flagged where Percentile < 30):"),
        raw_html=True
    ))
    
    # Render Specific Test Scores
    for test_name in SPECIFIC_TESTS:
        if test_standard_scores.get(test_name):
            html_parts.append(html_paragraph())
            html_parts.append(html_paragraph(html_bold(f"{test_name}:"), raw_html=True))
            
            test_dict = test_standard_scores[test_name]
            # Main metrics
            if "__main__" in test_dict and test_dict["__main__"]:
                html_parts.append("<ul>")
                for metric, std, perc in test_dict["__main__"]:
                    try:
                        perc_float = float(str(perc).replace('-', '').strip())
                        is_flagged = perc_float < 30
                    except:
                        is_flagged = False
                    
                    if is_flagged:
                        flagged_findings.append({
                            "type": "Test Score",
                            "test": test_name,
                            "metric": metric,
                            "standard_score": str(std),
                            "percentile": str(perc),
                            "category": "Cognitive Test"
                        })
                        text = f"{escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                        html_parts.append(html_list_item(text, raw_html=True))
                    else:
                        text = f"{metric}: Standard Score: {std} | Percentile: {perc}"
                        html_parts.append(html_list_item(text))
                html_parts.append("</ul>")
            
            # Subheadings (like Positive Emotions if it appears under POET)
            for subheading in test_dict:
                if subheading == "__main__":
                    continue
                metrics = test_dict[subheading]
                if metrics:
                    html_parts.append(html_paragraph(html_bold(subheading), raw_html=True))
                    html_parts.append("<ul>")
                    for metric, std, perc in metrics:
                        try:
                            perc_float = float(str(perc).replace('-', '').strip())
                            is_flagged = perc_float < 30
                        except:
                            is_flagged = False
                        
                        if is_flagged:
                            flagged_findings.append({
                                "type": "Test Score",
                                "test": test_name,
                                "subheading": subheading,
                                "metric": metric,
                                "standard_score": str(std),
                                "percentile": str(perc),
                                "category": "Cognitive Test"
                            })
                            text = f"{escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                            html_parts.append(html_list_item(text, raw_html=True))
                        else:
                            text = f"{metric}: Standard Score: {std} | Percentile: {perc}"
                            html_parts.append(html_list_item(text))
                    html_parts.append("</ul>")

    html_parts.append(html_paragraph())
    
    # Four Part Continuous Performance Test header
    html_parts.append(html_paragraph(
        html_bold("Four Part Continuous Performance Test:"),
        raw_html=True
    ))
    
    # Render Four Part Continuous Performance Test parts
    for test_name in FOUR_PART_TESTS:
        if test_standard_scores.get(test_name):
            html_parts.append(html_paragraph())
            html_parts.append(html_paragraph(html_bold(f"{test_name}:"), raw_html=True))
            
            test_dict = test_standard_scores[test_name]
            if "__main__" in test_dict and test_dict["__main__"]:
                html_parts.append("<ul>")
                for metric, std, perc in test_dict["__main__"]:
                    try:
                        perc_float = float(str(perc).replace('-', '').strip())
                        is_flagged = perc_float < 30
                    except:
                        is_flagged = False
                    
                    if is_flagged:
                        flagged_findings.append({
                            "type": "Test Score",
                            "test": test_name,
                            "metric": metric,
                            "standard_score": str(std),
                            "percentile": str(perc),
                            "category": "Cognitive Test"
                        })
                        text = f"{escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                        html_parts.append(html_list_item(text, raw_html=True))
                    else:
                        text = f"{metric}: Standard Score: {std} | Percentile: {perc}"
                        html_parts.append(html_list_item(text))
                html_parts.append("</ul>")
            
            # Subheadings for parts if any
            for subheading in test_dict:
                if subheading == "__main__":
                    continue
                metrics = test_dict[subheading]
                if metrics:
                    html_parts.append(html_paragraph(html_bold(subheading), raw_html=True))
                    html_parts.append("<ul>")
                    for metric, std, perc in metrics:
                        try:
                            perc_float = float(str(perc).replace('-', '').strip())
                            is_flagged = perc_float < 30
                        except:
                            is_flagged = False
                        
                        if is_flagged:
                            flagged_findings.append({
                                "type": "Test Score",
                                "test": test_name,
                                "subheading": subheading,
                                "metric": metric,
                                "standard_score": str(std),
                                "percentile": str(perc),
                                "category": "Cognitive Test"
                            })
                            text = f"{escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                            html_parts.append(html_list_item(text, raw_html=True))
                        else:
                            text = f"{metric}: Standard Score: {std} | Percentile: {perc}"
                            html_parts.append(html_list_item(text))
                    html_parts.append("</ul>")
    
    return "\n".join(html_parts)


def create_flagged_findings_summary(flagged_findings: List[Dict]) -> str:
    """
    Create HTML section summarizing all flagged findings.
    
    Args:
        flagged_findings: List of dictionaries containing flagged finding details
        
    Returns:
        HTML string for flagged findings summary section
    """
    html_parts = []
    
    if not flagged_findings:
        return ""  # Return empty string if no flagged findings
    
    # Add page break before summary
    html_parts.append(html_page_break())
    
    # Main heading
    html_parts.append(html_heading(1, "Summary of Flagged Findings"))
    html_parts.append(html_paragraph())
    
    # Group findings by category
    domain_findings = [f for f in flagged_findings if f.get("category") == "Cognitive Domain"]
    test_findings = [f for f in flagged_findings if f.get("category") == "Cognitive Test"]
    
    # Domain Scores section
    if domain_findings:
        html_parts.append(html_paragraph(
            html_bold("Cognitive Domain Scores:"),
            raw_html=True
        ))
        html_parts.append("<ul>")
        for finding in domain_findings:
            name = finding.get("name", "Unknown")
            std = finding.get("standard_score", "N/A")
            perc = finding.get("percentile", "N/A")
            text = f"{escape_html(name)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
            html_parts.append(html_list_item(text, raw_html=True))
        html_parts.append("</ul>")
        html_parts.append(html_paragraph())
    
    # Test Scores section
    if test_findings:
        html_parts.append(html_paragraph(
            html_bold("Specific Test Scores:"),
            raw_html=True
        ))
        html_parts.append("<ul>")
        
        # Group by test name
        tests_dict = {}
        for finding in test_findings:
            test_name = finding.get("test", "Unknown Test")
            if test_name not in tests_dict:
                tests_dict[test_name] = []
            tests_dict[test_name].append(finding)
        
        for test_name, findings in tests_dict.items():
            html_parts.append(html_list_item(
                html_bold(f"{escape_html(test_name)}:"),
                raw_html=True
            ))
            html_parts.append("<ul>")
            for finding in findings:
                metric = finding.get("metric", "Unknown")
                subheading = finding.get("subheading", "")
                std = finding.get("standard_score", "N/A")
                perc = finding.get("percentile", "N/A")
                
                if subheading:
                    text = f"{escape_html(subheading)} - {escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                else:
                    text = f"{escape_html(metric)}: Standard Score: {escape_html(str(std))} | Percentile: {escape_html(str(perc))} | {html_bold('FLAG')}"
                html_parts.append(html_list_item(text, raw_html=True))
            html_parts.append("</ul>")
        
        html_parts.append("</ul>")
    
    return "\n".join(html_parts)


def create_longitudinal_html_section(
    img_bytes: BytesIO,
    pair_plot_bytes: List[BytesIO],
    pair_plot_labels: List[str]
) -> str:
    """
    Create HTML section for longitudinal plots.
    
    Args:
        img_bytes: Main plot image bytes
        pair_plot_bytes: List of pairwise plot image bytes
        pair_plot_labels: List of labels for pairwise plots
        
    Returns:
        HTML string for longitudinal section
    """
    html_parts = []
    
    html_parts.append(html_page_break())
    html_parts.append(html_image(img_bytes, "Longitudinal Cognitive Domain Scores (Line Plot)"))
    html_parts.append(html_paragraph("Longitudinal Cognitive Domain Scores (Line Plot)"))
    
    # Add pairwise plots
    if pair_plot_bytes:
        for i, pair_img in enumerate(pair_plot_bytes):
            html_parts.append(html_page_break())
            if pair_plot_labels and i < len(pair_plot_labels):
                html_parts.append(html_paragraph(pair_plot_labels[i]))
            html_parts.append(html_image(pair_img, pair_plot_labels[i] if pair_plot_labels and i < len(pair_plot_labels) else "Pairwise Plot"))
    
    return "\n".join(html_parts)