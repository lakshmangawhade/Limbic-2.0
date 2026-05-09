"""
Text Formatter Service using LangChain with Groq (Llama models)
Intelligently formats text to ensure proper line breaks and formatting.
"""
import os
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging

logger = logging.getLogger(__name__)


class TextFormatter:
    """Text formatter using LangChain with Groq Llama models."""
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "llama-3.3-70b-versatile"):
        """
        Initialize the text formatter.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model_name: Llama model name to use (default: llama-3.1-70b-versatile)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not found. LLM formatting will be disabled.")
            self.llm = None
            return
        
        try:
            self.llm = ChatGroq(
                groq_api_key=self.api_key,
                model_name=model_name,
                temperature=0.1,  # Low temperature for consistent formatting
                max_tokens=4096
            )
            logger.info(f"✅ TextFormatter initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq LLM: {str(e)}")
            self.llm = None
    
    def format_text(self, text: str) -> str:
        """
        Format text using LLM to ensure ONLY a small, fixed set of formatting rules:
        1. "Interpretation of Total Score:" must be on a single line
        2. "The NeuroPsych" (and similar) must start on a new line
        3. NPQ domain rows are aligned as plain-text columns (Domain, Score, Severity Description)
        4. Inline alphabetic sub-question list items (a., b., c., etc.) are moved to their own lines
        
        Args:
            text: Raw text to format
            
        Returns:
            Formatted text with only these specific corrections applied
        """
        if not self.llm or not text:
            return text
        
        try:
            # Create prompt template - STRICTLY focused on only the rules below
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a text formatting expert. Your task is to apply ONLY a very small, fixed set of formatting corrections to medical/psychological test report text.

STRICT FORMATTING RULES (ONLY THESE THREE – DO NOTHING ELSE):

────────────────────────────────
RULE 1
"Interpretation of Total Score:" MUST be on a SINGLE line.
- If split across lines, merge into:
  "Interpretation of Total Score:"
- Do NOT modify surrounding text

────────────────────────────────
RULE 2
Text starting with "The NeuroPsych" / "The Neuropsych" MUST have:
- "The" and "Neuropsych" on the SAME line
- Merge only if they are split across lines
- Do NOT change anything else

────────────────────────────────
RULE 3 (NPQ DOMAIN COLUMN ALIGNMENT – PLAIN TEXT ONLY)

When you detect a block related to:
"NeuroPsych Questionnaire (NPQ)"

And it contains inline or poorly formatted domain data,
you MUST reformat ONLY that section into a clean, aligned, plain-text layout.

FORMAT REQUIREMENTS (VERY IMPORTANT):
- Output MUST be plain text (NOT Markdown)
- DO NOT use pipes "|", bullets, or tables
- Use SPACES ONLY for alignment
- Columns MUST align vertically across all rows

COLUMNS (EXACTLY THREE):
1. Domain
2. Score
3. Severity Description

HEADER FORMAT (single line):
Domain              Score   Severity Description

ROW FORMAT RULES:
- Each domain on its own line
- Domain column left-aligned
- Score column numeric and aligned vertically
- Severity Description stays together as ONE column
- Domain names may be multi-word
- Severity text may vary (e.g., Severe, Moderate, Mild, Not a problem)
- Description may be empty — do NOT invent text

SPACING RULE:
- Ensure that all rows start each column at the same character position
- Use additional spaces as needed for longer domain names

DO NOT:
- Use "|" characters
- Convert to Markdown
- Change values
- Reorder rows
- Modify any text outside the NPQ section

────────────────────────────────
CRITICAL INSTRUCTIONS:
- Apply ONLY these three rules
- Do NOT change spacing, punctuation, or wording elsewhere
- Do NOT summarize or explain
- Return ONLY the corrected text
"""),
                ("human", "Apply ONLY the rules above to this text. Do not change anything else:\n\n{text}")
            ])
            
            # Create chain
            chain = prompt | self.llm | StrOutputParser()
            
            # Format the text
            formatted = chain.invoke({"text": text})
            
            logger.info("✅ Text formatted successfully using LLM (strict mode: 2 rules only)")
            return formatted.strip()
            
        except Exception as e:
            logger.error(f"Error formatting text with LLM: {str(e)}")
            # Return original text if LLM fails
            return text
    
    def format_section(self, section: str) -> str:
        """
        Format a specific section of text.
        
        Args:
            section: Text section to format
            
        Returns:
            Formatted section
        """
        return self.format_text(section)


# Global formatter instance
_formatter_instance: Optional[TextFormatter] = None


def get_formatter() -> TextFormatter:
    """
    Get or create the global formatter instance.
    
    Returns:
        TextFormatter instance
    """
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = TextFormatter()
    return _formatter_instance


def format_text_with_llm(text: str) -> str:
    """
    Convenience function to format text using LLM.
    
    Args:
        text: Text to format
        
    Returns:
        Formatted text
    """
    formatter = get_formatter()
    return formatter.format_text(text)

