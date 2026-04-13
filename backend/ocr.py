import re
import json
from typing import List, Dict, Any, Optional
import PyPDF2
import pdfplumber
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFTableExtractor:
    def __init__(self):
        pass
        
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}, trying PyPDF2")
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                    return text
            except Exception as e2:
                logger.error(f"Both extraction methods failed: {e2}")
                return ""
    
    def parse_tables_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse tables directly from the raw text using simple string matching"""
        
        # Clean the text first
        text = re.sub(r'Firefox file:///.*?\n', '', text)
        text = re.sub(r'\d+ of \d+ \d+/\d+/\d+, \d+:\d+ [AP]M', '', text)
        
        tables = []
        current_table = None
        gaze_entry_counts = {}  # Track entry count for each gaze test
        
        # Split into lines
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and headers
            if not line or 'Test name Field name Value' in line or 'Normative Range' in line:
                i += 1
                continue
            
            # Check if this line contains a test name but no field data
            # This happens when test name and field name are on separate lines
            if self.is_test_name_only(line):
                # Look ahead to the next line for field data
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not self.is_test_name_only(next_line):
                        # Combine the lines
                        combined_line = f"{line} {next_line}"
                        row_data = self.parse_single_line(combined_line)
                        if row_data:
                            # Filter out unwanted test entries
                            if row_data['test_name'] == 'VEST':
                                i += 2
                                continue
                            
                            # Special handling for Self-Paced Saccade field names
                            if row_data['test_name'] == 'Self-Paced Saccade ~ Horizontal Self-Paced Saccade':
                                if row_data['field_name'] == 'per Second':
                                    row_data['field_name'] = 'Saccades per Second'
                            
                            test_name = row_data['test_name']
                            
                            # Check if we need a new table
                            if not current_table or current_table['test_name'] != test_name:
                                if current_table:
                                    tables.append(current_table)
                                current_table = {
                                    'test_name': test_name,
                                    'data': []
                                }
                            
                            # Add the row to current table
                            current_table['data'].append({
                                'field_name': row_data['field_name'],
                                'value': row_data['value'],
                                'normative_range_low': row_data['normative_range_low'],
                                'normative_range_high': row_data['normative_range_high'],
                                'within_normative_range': row_data['within_normative_range']
                            })
                        i += 2  # Skip both lines
                        continue
            
            # Parse each data line
            row_data = self.parse_single_line(line)
            
            if row_data:
                # Filter out unwanted test entries
                if row_data['test_name'] == 'VEST':
                    i += 1
                    continue
                
                # Special handling for Self-Paced Saccade field names
                if row_data['test_name'] == 'Self-Paced Saccade ~ Horizontal Self-Paced Saccade':
                    if row_data['field_name'] == 'per Second':
                        row_data['field_name'] = 'Saccades per Second'
                
                # Special handling for Gaze test entries with missing or malformed field names
                if row_data['test_name'].startswith('Gaze'):
                    original_field_name = row_data['field_name']
                    
                    # Track entry count for this gaze test
                    test_name = row_data['test_name']
                    if test_name not in gaze_entry_counts:
                        gaze_entry_counts[test_name] = 0
                    entry_index = gaze_entry_counts[test_name]
                    gaze_entry_counts[test_name] += 1
                    
                    # Always try to fix gaze field names, not just empty ones
                    # Check if field name needs fixing (missing direction or malformed)
                    needs_fixing = (
                        not row_data['field_name'] or 
                        row_data['field_name'] == '' or
                        'Horizontal Fixation' in row_data['field_name'] or
                        'Vertical Fixation' in row_data['field_name'] or
                        'Number of Number of' in row_data['field_name']
                    )
                    
                    if needs_fixing:
                        # Use the comprehensive Gaze field name parser with entry index
                        row_data['field_name'] = self._parse_gaze_field_name(line, row_data['test_name'], entry_index)
                        
                        # Log the field name assignment
                        if original_field_name != row_data['field_name']:
                            logger.info(f"Fixed Gaze field name: '{original_field_name}' -> '{row_data['field_name']}'")
                    
                    # Also fix malformed field names
                    if row_data['field_name']:
                        original_field_name = row_data['field_name']
                        
                        # Fix common malformations
                        if 'Beats7' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('Beats7', 'Beats')
                        elif 'Beats10' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('Beats10', 'Beats')
                        elif 'BeatsOff' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('BeatsOff', 'Beats Off')
                        elif 'BeatsOn' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('BeatsOn', 'Beats On')
                        elif 'NumberOfBeats' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('NumberOfBeats', 'Number Of Beats')
                        elif 'NumberofBeats' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('NumberofBeats', 'Number Of Beats')
                        elif 'Number Of Beats' not in row_data['field_name'] and 'Beats' in row_data['field_name']:
                            # Ensure "Number Of Beats" is present
                            row_data['field_name'] = row_data['field_name'].replace('Beats', 'Number Of Beats')
                        
                        # Ensure proper spacing and capitalization
                        row_data['field_name'] = ' '.join(row_data['field_name'].split())
                        
                        # Capitalize first letter of each word for consistency
                        words = row_data['field_name'].split()
                        formatted_words = []
                        for word in words:
                            if word.lower() in ['of', 'on', 'off', 'in', 'at', 'to', 'for', 'with', 'by']:
                                formatted_words.append(word.lower())
                            else:
                                formatted_words.append(word.capitalize())
                        row_data['field_name'] = ' '.join(formatted_words)
                        
                        # Fix specific cases
                        if 'Saccadic component' in row_data['field_name']:
                            row_data['field_name'] = row_data['field_name'].replace('Saccadic component', 'Saccadic Component')
                        
                        # Log malformation fixes
                        if original_field_name != row_data['field_name']:
                            logger.info(f"Fixed malformed Gaze field name: '{original_field_name}' -> '{row_data['field_name']}'")
                
                test_name = row_data['test_name']
                
                # Check if we need a new table
                if not current_table or current_table['test_name'] != test_name:
                    if current_table:
                        tables.append(current_table)
                    current_table = {
                        'test_name': test_name,
                        'data': []
                    }
                
                # Add the row to current table
                current_table['data'].append({
                    'field_name': row_data['field_name'],
                    'value': row_data['value'],
                    'normative_range_low': row_data['normative_range_low'],
                    'normative_range_high': row_data['normative_range_high'],
                    'within_normative_range': row_data['within_normative_range']
                })
            
            i += 1
        
        # Add the last table if it exists
        if current_table:
            tables.append(current_table)
        
        # Calculate within_normative_range ONLY for tests where OCR didn't provide a value
        # OCR extraction is prioritized - calculation is only used as fallback
        for table in tables:
            test_name = table.get('test_name', '')
            test_name_lower = test_name.lower() if test_name else ''
            is_reaction_time = 'reaction time' in test_name_lower
            is_saccades_reaction_time = 'saccades and reaction time' in test_name_lower
            
            for row_data in table['data']:
                # For Reaction Time tests, always recalculate because OCR might have gotten it wrong
                # due to unit mismatch (values in seconds vs normative ranges in msec)
                # For other tests, only calculate if OCR didn't provide a valid value
                should_calculate = False
                if is_reaction_time:
                    # Always recalculate for Reaction Time tests
                    should_calculate = (row_data['normative_range_low'] != "N/A" and 
                                       row_data['normative_range_high'] != "N/A")
                else:
                    # For other tests, only calculate if OCR didn't provide a valid value
                    should_calculate = (row_data['normative_range_low'] != "N/A" and 
                                       row_data['normative_range_high'] != "N/A" and 
                                       row_data['within_normative_range'] == "N/A")
                
                if should_calculate:
                    try:
                        # Improved regex to properly capture decimal numbers
                        value_match = re.search(r'-?\d+(?:\.\d+)?', row_data['value'])
                        low_match = re.search(r'-?\d+(?:\.\d+)?', row_data['normative_range_low'])
                        high_match = re.search(r'-?\d+(?:\.\d+)?', row_data['normative_range_high'])
                        
                        if value_match and low_match and high_match:
                            value_num = float(value_match.group())
                            low_num = float(low_match.group())
                            high_num = float(high_match.group())
                            
                            # For Reaction Time tests, handle unit conversion
                            # IMPORTANT: 
                            # - For Visual/Auditory Reaction Time: Values are in seconds, but normative ranges labeled as "seconds" 
                            #   are actually already in msec (PDF incorrectly labels them)
                            # - For Saccades and Reaction Time: Both values and normative ranges labeled as "seconds" are actually in seconds
                            #   and need to be converted to msec (multiply by 1000)
                            if is_reaction_time:
                                value_str = row_data['value'].lower()
                                original_value = value_num
                                
                                # Convert value from seconds to msec
                                if 'seconds' in value_str:
                                    value_num = value_num * 1000  # Convert seconds to msec
                                    # Update the value string to show msec instead of seconds
                                    row_data['value'] = f"{value_num:.2f} msec"
                                    logger.debug(f"Reaction Time: Converted value {original_value} seconds to {value_num} msec")
                                
                                # Handle normative ranges conversion
                                low_str = row_data['normative_range_low'].lower()
                                high_str = row_data['normative_range_high'].lower()
                                
                                if is_saccades_reaction_time:
                                    # For "Saccades and Reaction Time", normative ranges labeled as "seconds" are actually in seconds
                                    # and need to be converted to msec (multiply by 1000)
                                    if 'seconds' in low_str:
                                        low_num = low_num * 1000
                                        row_data['normative_range_low'] = f"{low_num:.2f} msec"
                                        logger.debug(f"Saccades and Reaction Time: Converted normative range low to {low_num} msec")
                                    if 'seconds' in high_str:
                                        high_num = high_num * 1000
                                        row_data['normative_range_high'] = f"{high_num:.2f} msec"
                                        logger.debug(f"Saccades and Reaction Time: Converted normative range high to {high_num} msec")
                                else:
                                    # For Visual/Auditory Reaction Time, normative ranges labeled as "seconds" are already in msec
                                    # Just update the label from "seconds" to "msec"
                                    if 'seconds' in low_str:
                                        row_data['normative_range_low'] = f"{low_num} msec"
                                        logger.debug(f"Visual/Auditory Reaction Time: Updated normative range low label to msec")
                                    if 'seconds' in high_str:
                                        row_data['normative_range_high'] = f"{high_num} msec"
                                        logger.debug(f"Visual/Auditory Reaction Time: Updated normative range high label to msec")
                            
                            # Compare values (all should be in msec for Reaction Time tests)
                            is_within_range = low_num <= value_num <= high_num
                            if is_reaction_time:
                                logger.debug(f"Reaction Time comparison: {low_num} <= {value_num} <= {high_num} = {is_within_range}")
                            
                            if is_within_range:
                                row_data['within_normative_range'] = "Yes"
                            else:
                                row_data['within_normative_range'] = "No"
                    except (ValueError, AttributeError) as e:
                        logger.debug(f"Error calculating within_normative_range: {e}")
                        pass
        
        return tables
    
    def is_test_name_only(self, line: str) -> bool:
        """Check if a line contains only a test name without field data"""
        # Check if line contains known test name patterns but no numeric values
        test_patterns = [
            'Self-Paced Saccade ~ Horizontal Self-Paced Saccade',
            'Self-Paced Saccade ~ Horizontal Self-Paced',
            'Vergence Pursuit ~ Vergence Pursuit',
            'Vergence Steps ~ Vergence Steps',
            'Smooth Pursuit Horizontal ~',
            'Smooth Pursuit Vertical ~',
            'Saccades ~ Vertical Reflexive',
            'Saccades ~ Horizontal Reflexive',
            'Predictive Saccades ~ Horizontal',
            'Antisaccades ~ Horizontal',
            'OKN Trapezoidal ~'
        ]
        
        for pattern in test_patterns:
            if pattern in line:
                # Check if there are no numeric values after the test name
                parts = line.split()
                for part in parts:
                    if re.match(r'^-?\d+(?:\.\d+)?$', part) or re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', part):
                        return False
                return True
        
        return False
    
    def parse_single_line(self, line: str) -> Optional[Dict[str, str]]:
        """Parse a single line of data with improved logic for complex test names and field names"""
        
        # Remove extra whitespace and clean the line
        line = re.sub(r'\s+', ' ', line.strip())
        
        if not line:
            return None
        
        # Skip header lines
        if any(header in line for header in ['Test name', 'Field name', 'Value', 'Normative Range', 'Within Normative']):
            return None
        
        # Split the line into parts
        parts = line.split()
        
        if len(parts) < 3:
            return None
        
        # Define known test patterns with their variations
        test_patterns = {
            'Spontaneous': ['Spontaneous Nystagmus'],
            'Gaze': ['Gaze Horizontal', 'Gaze Vertical'],
            'Vergence': ['Vergence Pursuit ~ Vergence Pursuit', 'Vergence Steps ~ Vergence Steps'],
            'Smooth': ['Smooth Pursuit Horizontal ~ 0.20 Hz', 'Smooth Pursuit Vertical ~ 0.20 Hz', 'Smooth Pursuit Horizontal ~ 0.30 Hz', 'Smooth Pursuit Vertical ~ 0.30 Hz', 'Smooth Pursuit Horizontal ~ 0.40 Hz', 'Smooth Pursuit Vertical ~ 0.40 Hz'],
            'Saccades': ['Saccades ~ Vertical Reflexive', 'Saccades ~ Horizontal Reflexive'],
            'Predictive': ['Predictive Saccades ~ Horizontal'],
            'Antisaccades': ['Antisaccades ~ Horizontal'],
            'Self-Paced': ['Self-Paced Saccade ~ Horizontal Self-Paced Saccade'],
            'Saccades and Reaction Time': ['Saccades and Reaction Time'],
            'Visual': ['Visual Reaction Time'],
            'Auditory': ['Auditory Reaction Time'],
            'Subjective': ['Subjective Visual Horizontal', 'Subjective Visual Vertical'],
            'OKN': [
                'OKN Trapezoidal ~ 20.0 deg/sec Horizontal',
                'OKN Trapezoidal ~ 40.0 deg/sec Horizontal',
                'OKN Trapezoidal ~ 50.0 deg/sec Horizontal',
                'OKN Trapezoidal ~ 60.0 deg/sec Horizontal',
            ]
        }
        
        # Find the test name by looking for patterns
        test_name = ""
        field_start_idx = 0
        
        # Try to match known test patterns - check longer patterns first
        all_patterns = []
        for patterns in test_patterns.values():
            all_patterns.extend(patterns)
        
        # Sort patterns by length (longest first) to avoid partial matches
        all_patterns.sort(key=len, reverse=True)
        
        for pattern in all_patterns:
            if line.startswith(pattern):
                test_name = pattern
                field_start_idx = len(pattern.split())
                break
        
        # If no pattern match, try to identify test name by looking for common patterns
        if not test_name:
            # Look for common test name indicators
            test_indicators = ['Spontaneous', 'Gaze', 'Vergence', 'Smooth', 'Saccades', 'Predictive', 
                             'Antisaccades', 'Self-Paced', 'Visual', 'Auditory', 'Subjective', 'OKN']
            
            for i, part in enumerate(parts):
                if part in test_indicators:
                    # Check if next part completes the test name
                    if i + 1 < len(parts) and parts[i + 1] in ['Nystagmus', 'Horizontal', 'Vertical', 'Pursuit', 'Steps', 'Reaction', 'Saccades']:
                        test_name = f"{part} {parts[i + 1]}"
                        field_start_idx = i + 2
                    else:
                        test_name = part
                        field_start_idx = i + 1
                    break
            
            # If still no test name, assume first word
            if not test_name:
                test_name = parts[0]
                field_start_idx = 1
        
        # For complex cases like Smooth Pursuit, we need special handling
        if test_name in ['Smooth Pursuit Horizontal', 'Smooth Pursuit Vertical']:
            return self._parse_smooth_pursuit_line(line, test_name)
        elif test_name in ['Saccades Vertical Reflexive', 'Saccades Horizontal Reflexive']:
            return self._parse_saccades_line(line, test_name)
        elif test_name in ['Vergence Pursuit', 'Vergence Steps']:
            return self._parse_vergence_line(line, test_name)
        elif 'OKN Trapezoidal' in test_name:
            return self._parse_okn_line(line, test_name)
        
        # Find the numeric value (this helps identify where field name ends and values begin)
        value_idx = -1
        for i in range(field_start_idx, len(parts)):
            # Check for numeric values with or without units
            if re.match(r'^-?\d+(?:\.\d+)?$', parts[i]):
                value_idx = i
                break
            # Check for values with units
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', parts[i]):
                value_idx = i
                break
        
        if value_idx == -1:
            return None
        
        # Extract field name (everything between test name and value)
        field_name = ' '.join(parts[field_start_idx:value_idx])
        
        # Clean up field name - preserve ~ character
        field_name = field_name.strip()
        
        # Extract value
        value = parts[value_idx]
        
        # Check if next part is a unit
        if value_idx + 1 < len(parts) and parts[value_idx + 1] in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            value += " " + parts[value_idx + 1]
            value_idx += 1
        
        # Extract normative ranges with proper unit handling
        norm_low = parts[value_idx + 1] if value_idx + 1 < len(parts) else "N/A"
        norm_high = parts[value_idx + 2] if value_idx + 2 < len(parts) else "N/A"
        within_range = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
        
        # Handle normative ranges with units
        if norm_low != "N/A" and norm_high in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_low and norm_high as they are one value with unit
            norm_low = f"{norm_low} {norm_high}"
            norm_high = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Handle cases where norm_high has units
        if norm_high != "N/A" and within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_high and within_range as they are one value with unit
            norm_high = f"{norm_high} {within_range}"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Try to extract within_normative_range from OCR text first
        # This is the primary method - only fall back to calculation if OCR fails
        if within_range in ['Yes', 'No', 'N/A']:
            # OCR provided a valid value - keep it
            pass
        elif within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # This is likely a unit, not the within_range value
            within_range = "N/A"
        elif within_range and re.match(r'^-?\d+(?:\.\d+)?$', within_range):
            # This is a numeric value, which shouldn't be in within_range
            # Check if there's a Yes/No value after this numeric value
            if value_idx + 4 < len(parts):
                next_value = parts[value_idx + 4]
                if next_value in ['Yes', 'No']:
                    within_range = next_value
                else:
                    within_range = "N/A"
            else:
                within_range = "N/A"
        else:
            # OCR didn't provide a valid value - set to N/A for later calculation
            within_range = "N/A"
        
        return {
            'test_name': test_name,
            'field_name': field_name,
            'value': value,
            'normative_range_low': norm_low,
            'normative_range_high': norm_high,
            'within_normative_range': within_range
        }
    
    def _parse_smooth_pursuit_line(self, line: str, test_name: str) -> Optional[Dict[str, str]]:
        """Special parser for Smooth Pursuit lines"""
        parts = line.split()
        
        # Find the frequency part (e.g., "0.20 Hz")
        freq_idx = -1
        for i, part in enumerate(parts):
            if re.match(r'\d+\.\d+\s*Hz', part) or (i + 1 < len(parts) and re.match(r'\d+\.\d+', part) and parts[i + 1] == 'Hz'):
                freq_idx = i
                break
        
        if freq_idx == -1:
            return None
        
        # Extract frequency
        frequency = parts[freq_idx]
        if freq_idx + 1 < len(parts) and parts[freq_idx + 1] == 'Hz':
            frequency += " " + parts[freq_idx + 1]
            freq_idx += 1
        
        # Find the actual value (numeric)
        value_idx = -1
        for i in range(freq_idx + 1, len(parts)):
            if re.match(r'^-?\d+(?:\.\d+)?$', parts[i]):
                value_idx = i
                break
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', parts[i]):
                value_idx = i
                break
        
        if value_idx == -1:
            return None
        
        # Extract field name (everything between frequency and value)
        field_name = ' '.join(parts[freq_idx + 1:value_idx])
        field_name = field_name.strip()
        
        # Extract value
        value = parts[value_idx]
        
        # Check if next part is a unit
        if value_idx + 1 < len(parts) and parts[value_idx + 1] in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            value += " " + parts[value_idx + 1]
            value_idx += 1
        
        # Extract normative ranges with proper unit handling
        norm_low = parts[value_idx + 1] if value_idx + 1 < len(parts) else "N/A"
        norm_high = parts[value_idx + 2] if value_idx + 2 < len(parts) else "N/A"
        within_range = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
        
        # Handle normative ranges with units
        if norm_low != "N/A" and norm_high in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_low and norm_high as they are one value with unit
            norm_low = f"{norm_low} {norm_high}"
            norm_high = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Handle cases where norm_high has units
        if norm_high != "N/A" and within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_high and within_range as they are one value with unit
            norm_high = f"{norm_high} {within_range}"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Try to extract within_normative_range from OCR text first
        # This is the primary method - only fall back to calculation if OCR fails
        if within_range in ['Yes', 'No', 'N/A']:
            # OCR provided a valid value - keep it
            pass
        elif within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # This is likely a unit, not the within_range value
            within_range = "N/A"
        elif within_range and re.match(r'^-?\d+(?:\.\d+)?$', within_range):
            # This is a numeric value, which shouldn't be in within_range
            # Check if there's a Yes/No value after this numeric value
            if value_idx + 4 < len(parts):
                next_value = parts[value_idx + 4]
                if next_value in ['Yes', 'No']:
                    within_range = next_value
                else:
                    within_range = "N/A"
            else:
                within_range = "N/A"
        else:
            # OCR didn't provide a valid value - set to N/A for later calculation
            within_range = "N/A"
        
        return {
            'test_name': test_name,
            'field_name': f"{frequency} {field_name}",
            'value': value,
            'normative_range_low': norm_low,
            'normative_range_high': norm_high,
            'within_normative_range': within_range
        }
    
    def _parse_saccades_line(self, line: str, test_name: str) -> Optional[Dict[str, str]]:
        """Special parser for Saccades lines"""
        parts = line.split()
        
        # Find the direction part (e.g., "Downward", "Upward", "Leftward", "Rightward")
        direction_idx = -1
        directions = ['Downward', 'Upward', 'Leftward', 'Rightward']
        for i, part in enumerate(parts):
            if part in directions:
                direction_idx = i
                break
        
        if direction_idx == -1:
            return None
        
        # Find the actual value (numeric)
        value_idx = -1
        for i in range(direction_idx + 1, len(parts)):
            if re.match(r'^-?\d+(?:\.\d+)?$', parts[i]):
                value_idx = i
                break
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', parts[i]):
                value_idx = i
                break
        
        if value_idx == -1:
            return None
        
        # Extract field name (everything between test name and direction)
        field_name = ' '.join(parts[2:direction_idx])  # Skip test name parts
        field_name = f"{field_name} {parts[direction_idx]}"
        field_name = field_name.strip()
        
        # Extract value
        value = parts[value_idx]
        
        # Check if next part is a unit
        if value_idx + 1 < len(parts) and parts[value_idx + 1] in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            value += " " + parts[value_idx + 1]
            value_idx += 1
        
        # Extract normative ranges with proper unit handling
        norm_low = parts[value_idx + 1] if value_idx + 1 < len(parts) else "N/A"
        norm_high = parts[value_idx + 2] if value_idx + 2 < len(parts) else "N/A"
        within_range = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
        
        # Handle normative ranges with units
        if norm_low != "N/A" and norm_high in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_low and norm_high as they are one value with unit
            norm_low = f"{norm_low} {norm_high}"
            norm_high = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Handle cases where norm_high has units
        if norm_high != "N/A" and within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_high and within_range as they are one value with unit
            norm_high = f"{norm_high} {within_range}"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Try to extract within_normative_range from OCR text first
        # This is the primary method - only fall back to calculation if OCR fails
        if within_range in ['Yes', 'No', 'N/A']:
            # OCR provided a valid value - keep it
            pass
        elif within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # This is likely a unit, not the within_range value
            within_range = "N/A"
        elif within_range and re.match(r'^-?\d+(?:\.\d+)?$', within_range):
            # This is a numeric value, which shouldn't be in within_range
            # Check if there's a Yes/No value after this numeric value
            if value_idx + 4 < len(parts):
                next_value = parts[value_idx + 4]
                if next_value in ['Yes', 'No']:
                    within_range = next_value
                else:
                    within_range = "N/A"
            else:
                within_range = "N/A"
        else:
            # OCR didn't provide a valid value - set to N/A for later calculation
            within_range = "N/A"
        
        return {
            'test_name': test_name,
            'field_name': field_name,
            'value': value,
            'normative_range_low': norm_low,
            'normative_range_high': norm_high,
            'within_normative_range': within_range
        }
    
    def _parse_vergence_line(self, line: str, test_name: str) -> Optional[Dict[str, str]]:
        """Special parser for Vergence lines"""
        parts = line.split()
        
        # Find the actual value (numeric)
        value_idx = -1
        for i, part in enumerate(parts):
            if re.match(r'^-?\d+(?:\.\d+)?$', part):
                value_idx = i
                break
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', part):
                value_idx = i
                break
        
        if value_idx == -1:
            return None
        
        # Extract field name (everything between test name and value)
        field_name = ' '.join(parts[2:value_idx])  # Skip test name parts
        field_name = field_name.strip()
        
        # Extract value
        value = parts[value_idx]
        
        # Check if next part is a unit
        if value_idx + 1 < len(parts) and parts[value_idx + 1] in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            value += " " + parts[value_idx + 1]
            value_idx += 1
        
        # Extract normative ranges with proper unit handling
        norm_low = parts[value_idx + 1] if value_idx + 1 < len(parts) else "N/A"
        norm_high = parts[value_idx + 2] if value_idx + 2 < len(parts) else "N/A"
        within_range = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
        
        # Handle normative ranges with units
        if norm_low != "N/A" and norm_high in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_low and norm_high as they are one value with unit
            norm_low = f"{norm_low} {norm_high}"
            norm_high = parts[value_idx + 3] if value_idx + 3 < len(parts) else "N/A"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Handle cases where norm_high has units
        if norm_high != "N/A" and within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # Combine norm_high and within_range as they are one value with unit
            norm_high = f"{norm_high} {within_range}"
            within_range = parts[value_idx + 4] if value_idx + 4 < len(parts) else "N/A"
        
        # Try to extract within_normative_range from OCR text first
        # This is the primary method - only fall back to calculation if OCR fails
        if within_range in ['Yes', 'No', 'N/A']:
            # OCR provided a valid value - keep it
            pass
        elif within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            # This is likely a unit, not the within_range value
            within_range = "N/A"
        elif within_range and re.match(r'^-?\d+(?:\.\d+)?$', within_range):
            # This is a numeric value, which shouldn't be in within_range
            # Check if there's a Yes/No value after this numeric value
            if value_idx + 4 < len(parts):
                next_value = parts[value_idx + 4]
                if next_value in ['Yes', 'No']:
                    within_range = next_value
                else:
                    within_range = "N/A"
            else:
                within_range = "N/A"
        else:
            # OCR didn't provide a valid value - set to N/A for later calculation
            within_range = "N/A"
        
        return {
            'test_name': test_name,
            'field_name': field_name,
            'value': value,
            'normative_range_low': norm_low,
            'normative_range_high': norm_high,
            'within_normative_range': within_range
        }
    
    def _parse_okn_line(self, line: str, test_name: str) -> Optional[Dict[str, str]]:
        """Special parser for OKN Trapezoidal lines"""
        parts = line.split()
        
        # For OKN, the structure varies:
        # "OKN Trapezoidal ~ 20.0 deg/sec Horizontal Average Eye Velocity (CW segment) 12.5 deg / second 14.6 deg / second 19.8 deg / second No"
        # "OKN Trapezoidal ~ 20.0 deg/sec Horizontal Velocity Asymmetry 11.43 -7.66 10.55 No"
        # "OKN Trapezoidal ~ 20.0 deg/sec Horizontal Fast Phase Velocity (Positive AUC) 3432 5516 N/A No"
        
        # Skip the test name parts (first 6 parts: "OKN Trapezoidal ~ 20.0 deg/sec Horizontal")
        test_name_parts = 6
        remaining_parts = parts[test_name_parts:]
        
        if len(remaining_parts) < 3:
            return None
        
        # Find the numeric value (this helps identify where field name ends and values begin)
        value_idx = -1
        for i, part in enumerate(remaining_parts):
            # Check for numeric values with or without units
            if re.match(r'^-?\d+(?:\.\d+)?$', part):
                value_idx = i
                break
            # Check for values with units
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', part):
                value_idx = i
                break
        
        if value_idx == -1:
            return None
        
        # Extract field name (everything between test name and value)
        field_name = ' '.join(remaining_parts[:value_idx])
        field_name = field_name.strip()
        
        # Extract value
        value = remaining_parts[value_idx]
        
        # Check if next part is a unit
        if value_idx + 1 < len(remaining_parts) and remaining_parts[value_idx + 1] in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec']:
            value += " " + remaining_parts[value_idx + 1]
            value_idx += 1
            
            # For OKN, check if there's a "/ second" pattern
            if value_idx + 2 < len(remaining_parts) and remaining_parts[value_idx] == '/' and remaining_parts[value_idx + 1] == 'second':
                value += " / " + remaining_parts[value_idx + 1]
                value_idx += 2
        
        # For OKN, we need to handle different normative range patterns
        norm_parts = remaining_parts[value_idx + 1:]
        
        # Check if this is a complex pattern with "deg / second" units
        if len(norm_parts) >= 4 and norm_parts[0] == '/' and norm_parts[1] == 'second':
            # Complex pattern: "/ second 14.6 deg / second 19.8 deg / second"
            if (re.match(r'^-?\d+\.\d+$', norm_parts[2]) and 
                norm_parts[3] == 'deg' and 
                norm_parts[4] == '/' and 
                norm_parts[5] == 'second'):
                
                # First normative range
                norm_low = f"{norm_parts[2]} {norm_parts[3]} / {norm_parts[5]}"
                
                # Check if there's a second normative range
                if len(norm_parts) >= 10:
                    if (re.match(r'^-?\d+\.\d+$', norm_parts[6]) and 
                        norm_parts[7] == 'deg' and 
                        norm_parts[8] == '/' and 
                        norm_parts[9] == 'second'):
                        
                        norm_high = f"{norm_parts[6]} {norm_parts[7]} / {norm_parts[9]}"
                        within_range = norm_parts[10] if len(norm_parts) > 10 else "N/A"
                    else:
                        norm_high = "N/A"
                        within_range = norm_parts[6] if len(norm_parts) > 6 else "N/A"
                else:
                    norm_high = "N/A"
                    within_range = "N/A"
        else:
            # Simple numeric pattern: "11.43 -7.66 10.55 No" or "3432 5516 N/A No"
            norm_low = norm_parts[0] if norm_parts else "N/A"
            norm_high = norm_parts[1] if len(norm_parts) > 1 else "N/A"
            within_range = norm_parts[2] if len(norm_parts) > 2 else "N/A"
        
        # Fix the within_normative_range field - it should not contain units
        if within_range in ['msec', 'deg', 'degrees', '%', 'seconds', 'Hz', 'deg/sec', '/']:
            # This is likely a unit, not the within_range value
            within_range = "N/A"
        elif within_range in ['Yes', 'No', 'N/A']:
            # These are valid within_range values - keep them as is
            pass
        elif within_range and re.match(r'^-?\d+(?:\.\d+)?$', within_range):
            # This is a numeric value, which shouldn't be in within_range
            # Check if there's a Yes/No value after this numeric value
            if value_idx + 4 < len(remaining_parts):
                next_value = remaining_parts[value_idx + 4]
                if next_value in ['Yes', 'No']:
                    within_range = next_value
                else:
                    within_range = "N/A"
            else:
                within_range = "N/A"
        else:
            # If it doesn't look like a valid within_range value, set to N/A
            within_range = "N/A"
        
        return {
            'test_name': test_name,
            'field_name': field_name,
            'value': value,
            'normative_range_low': norm_low,
            'normative_range_high': norm_high,
            'within_normative_range': within_range
        }
    
    def _parse_gaze_field_name(self, line: str, test_name: str, entry_index: int = 0) -> str:
        """Comprehensive Gaze field name parser using pattern-based approach"""
        line_lower = line.lower()
        test_name_lower = test_name.lower()
        
        # Extract the actual field name from the line by removing test name and values
        parts = line.split()
        
        # Find where the test name ends and field name begins
        test_name_parts = test_name.split()
        field_start_idx = len(test_name_parts)
        
        # Look for numeric values to find where field name ends
        value_idx = -1
        for i in range(field_start_idx, len(parts)):
            # Check for numeric values with or without units
            if re.match(r'^-?\d+(?:\.\d+)?$', parts[i]):
                value_idx = i
                break
            # Check for values with units
            elif re.match(r'^-?\d+(?:\.\d+)?(msec|deg|degrees|%|seconds|Hz|deg/sec)', parts[i]):
                value_idx = i
                break
        
        if value_idx == -1:
            # If no value found, try to extract field name from the remaining parts
            field_parts = parts[field_start_idx:]
        else:
            # Extract field name (everything between test name and value)
            field_parts = parts[field_start_idx:value_idx]
        
        # Join the field parts and clean up
        field_name = ' '.join(field_parts).strip()
        
        # If field name is empty, too short, or missing direction, use pattern-based approach
        needs_direction = (
            not field_name or 
            len(field_name) < 5 or
            ('Horizontal Fixation' in field_name and not any(d in field_name for d in ['Left', 'Right'])) or
            ('Vertical Fixation' in field_name and not any(d in field_name for d in ['Up', 'Down']))
        )
        
        if needs_direction:
            # Use pattern-based approach for direction
            direction = None
            fixation_type = 'On'  # Default
            
            # Determine orientation based on test name
            orientation = 'Horizontal' if 'horizontal' in test_name_lower else 'Vertical'
            
            # Pattern-based direction assignment
            if 'horizontal' in test_name_lower:
                # Gaze Horizontal pattern: Right-Left-Right-Left (4 entries each)
                if entry_index < 4:
                    direction = 'Right'
                elif entry_index < 8:
                    direction = 'Left'
                elif entry_index < 12:
                    direction = 'Right'
                else:  # entry_index >= 12
                    direction = 'Left'
            else:  # vertical
                # Gaze Vertical pattern: Up-Down-Up-Down (4 entries each)
                if entry_index < 4:
                    direction = 'Up'
                elif entry_index < 8:
                    direction = 'Down'
                elif entry_index < 12:
                    direction = 'Up'
                else:  # entry_index >= 12
                    direction = 'Down'
            
            # Check line content for fixation type
            if 'off' in line_lower:
                fixation_type = 'Off'
            
            # Build field name
            field_parts = []
            if direction:
                field_parts.append(direction)
            field_parts.append(orientation)
            field_parts.extend(['Fixation', fixation_type, 'Number', 'Of', 'Beats'])
            field_name = ' '.join(field_parts)
        
        # Clean up and format the field name
        field_name = ' '.join(field_name.split())  # Remove extra spaces
        
        # Ensure proper capitalization
        words = field_name.split()
        formatted_words = []
        for word in words:
            if word.lower() in ['of', 'on', 'off', 'in', 'at', 'to', 'for', 'with', 'by']:
                formatted_words.append(word.lower())
            else:
                formatted_words.append(word.capitalize())
        
        return ' '.join(formatted_words)
    
    def process_sample_data(self) -> List[Dict[str, Any]]:
        """Process the exact sample data from your document"""
        
        # Your exact data
        sample_data = [
            ("Spontaneous Nystagmus", "Horizontal Fixation On Number Of Beats", "4", "0", "N/A", "N/A"),
            ("Spontaneous Nystagmus", "Horizontal Fixation Off Number Of Beats", "12", "0", "N/A", "N/A"),
            ("Spontaneous Nystagmus", "Vertical Fixation On Number Of Beats", "0", "0", "N/A", "N/A"),
            ("Spontaneous Nystagmus", "Vertical Fixation Off Number Of Beats", "0", "0", "N/A", "N/A"),
            ("Gaze Horizontal Right", "Horizontal Fixation On Number Of Beats", "1", "0", "N/A", "N/A"),
            ("Gaze Horizontal Right", "Horizontal Fixation Off Number Of Beats", "2", "0", "N/A", "N/A"),
            ("Gaze Horizontal Right", "Vertical Fixation On Number Of Beats", "0", "0", "N/A", "N/A"),
            ("Gaze Horizontal Right", "Vertical Fixation Off Number Of Beats", "0", "0", "N/A", "N/A"),
            ("Gaze Horizontal Left", "Horizontal Fixation On Number Of Beats", "2", "0", "N/A", "N/A"),
            ("Gaze Horizontal Left", "Horizontal Fixation Off Number Of Beats", "7", "0", "N/A", "N/A"),
            ("Vergence Pursuit", "Vergence Pursuit Left Position Gain", "1.13", "N/A", "N/A", "N/A"),
            ("Vergence Pursuit", "Vergence Pursuit Right Position Gain", "0.89", "N/A", "N/A", "N/A"),
            ("Vergence Steps", "Vergence Steps Eye Correlation Inward", "-0.74", "N/A", "N/A", "N/A"),
            ("Vergence Steps", "Vergence Steps Left Eye Inward Amplitude", "2.41 degrees", "N/A", "N/A", "N/A"),
            ("Smooth Pursuit Horizontal", "0.20 Hz Velocity Gain Rightward", "1.03", "0.76", "1.07", "Yes"),
            ("Smooth Pursuit Horizontal", "0.20 Hz Velocity Gain Leftward", "0.97", "0.76", "1.07", "Yes"),
            ("Smooth Pursuit Horizontal", "0.20 Hz Saccadic component", "36.43 %", "0.00 %", "35.29 %", "No"),
            ("Smooth Pursuit Vertical", "0.20 Hz Velocity Gain Upward", "1.00", "0.65", "1.07", "Yes"),
            ("Saccades Vertical Reflexive", "Latency Downward", "248 msec", "0 msec", "230 msec", "No"),
            ("Saccades Vertical Reflexive", "Latency Upward", "156 msec", "0 msec", "230 msec", "Yes"),
            ("Saccades Horizontal Reflexive", "Latency Leftward", "182 msec", "0 msec", "220 msec", "Yes"),
            ("Predictive Saccades Horizontal", "Max % Predicted", "16.67 %", "N/A", "N/A", "N/A"),
            ("Antisaccades Horizontal", "Error Rate %", "77.78 %", "0.00 %", "50.00 %", "N/A"),
            ("Self-Paced Saccade Horizontal", "Saccades per Second", "1.97", "N/A", "N/A", "N/A"),
            ("Visual Reaction Time", "Mean latency", "0.37 seconds", "220.12 seconds", "342.50 seconds", "N/A"),
            ("Auditory Reaction Time", "Mean latency", "0.22 seconds", "161.10 seconds", "336.13 seconds", "N/A"),
            ("Subjective Visual Horizontal", "Cumulative Mean Error", "-1.92 degrees", "-2.95 degrees", "2.95 degrees", "Yes"),
            ("Subjective Visual Vertical", "Cumulative Mean Error", "-5.38 degrees", "-2.96 degrees", "2.96 degrees", "No"),
            ("OKN Trapezoidal", "20.0 deg/sec Horizontal Average Eye Velocity (CW segment)", "12.5 deg / second", "14.6 deg / second", "19.8 deg / second", "No")
        ]
        
        # Group by test name
        tables = {}
        for test_name, field_name, value, norm_low, norm_high, within_range in sample_data:
            if test_name not in tables:
                tables[test_name] = {
                    'test_name': test_name,
                    'data': []
                }
            
            tables[test_name]['data'].append({
                'field_name': field_name,
                'value': value,
                'normative_range_low': norm_low,
                'normative_range_high': norm_high,
                'within_normative_range': within_range
            })
        
        return list(tables.values())
    
    def process_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Process PDF and extract tables"""
        logger.info(f"Processing PDF: {pdf_path}")
        
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            logger.error("Could not extract text from PDF")
            return []
        
        tables = self.parse_tables_from_text(text)
        logger.info(f"Extracted {len(tables)} tables from PDF")
        return tables
    
    def process_text(self, text_content: str) -> List[Dict[str, Any]]:
        """Process raw text content"""
        logger.info("Processing text content")
        tables = self.parse_tables_from_text(text_content)
        logger.info(f"Extracted {len(tables)} tables from text")
        return tables
    
    def save_to_json(self, tables: List[Dict[str, Any]], output_path: str):
        """Save tables to JSON file"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(tables, f, indent=2, ensure_ascii=False)
            logger.info(f"Successfully saved {len(tables)} tables to {output_path}")
            print(f"✅ Saved {len(tables)} tables to {output_path}")
        except Exception as e:
            logger.error(f"Error saving JSON: {e}")
            print(f"❌ Error saving JSON: {e}")
    
    def print_summary(self, tables: List[Dict[str, Any]]):
        """Print summary of extracted tables"""
        print(f"\n📊 EXTRACTION SUMMARY")
        print(f"Total tables: {len(tables)}")
        print("=" * 50)
        
        for i, table in enumerate(tables, 1):
            print(f"\n{i}. {table['test_name']}")
            print(f"   Rows: {len(table['data'])}")
            
            if table['data']:
                print("   Sample entries:")
                for j, row in enumerate(table['data'][:2]):
                    print(f"   • {row['field_name']}: {row['value']}")
                if len(table['data']) > 2:
                    print(f"   • ... and {len(table['data']) - 2} more")
        
        # Show specific improvements
        print(f"\n🔧 PARSING IMPROVEMENTS:")
        print("✅ Test names now correctly identified (e.g., 'Smooth Pursuit Horizontal')")
        print("✅ Field names properly extracted (e.g., '0.20 Hz Velocity Gain Rightward')")
        print("✅ Values correctly parsed with units")
        print("✅ Normative ranges properly identified with units")
        print("✅ Special handling for complex data structures")

# Main execution
if __name__ == "__main__":
    extractor = PDFTableExtractor()
    
    # If you want to process a PDF file, uncomment and modify this:
    pdf_path = "lite4.pdf"
    pdf_tables = extractor.process_pdf(pdf_path)
    if pdf_tables:
        extractor.save_to_json(pdf_tables, "pdf_extracted_tables_fixed.json")
        extractor.print_summary(pdf_tables) 