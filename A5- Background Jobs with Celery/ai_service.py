"""
AI Service for PDF and text analysis using OpenAI and LangChain.
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PDFAnalysisResult(BaseModel):
    """Schema for PDF analysis output."""
    summary: str = Field(..., description="Executive summary of the document")
    key_points: List[str] = Field(..., description="Main points (5-8 items)")
    pages_analyzed: int = Field(..., description="Number of pages processed")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Analysis confidence")
    full_analysis: Optional[Dict[str, Any]] = Field(None, description="Detailed analysis")


class TextAnalysisResult(BaseModel):
    """Schema for text analysis output."""
    summary: str = Field(..., description="Summary of the text")
    category: str = Field(..., description="Document category")
    sentiment: str = Field(..., description="Overall sentiment")
    key_points: List[str] = Field(..., description="Main points")
    confidence: float = Field(..., ge=0.0, le=1.0)


def extract_pdf_text(file_path: str, max_pages: Optional[int] = None) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        max_pages: Maximum pages to extract (None = all)
    
    Returns:
        Extracted text content
    
    Raises:
        ValueError: If PDF is invalid or unreadable
    """
    try:
        import pdfplumber
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        text_content = []
        page_count = 0
        
        with pdfplumber.open(file_path) as pdf:
            pages_to_process = min(
                len(pdf.pages),
                max_pages or len(pdf.pages)
            )
            
            for i, page in enumerate(pdf.pages[:pages_to_process]):
                try:
                    text = page.extract_text()
                    if text:
                        text_content.append(f"--- Page {i+1} ---\n{text}")
                        page_count += 1
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {i+1}: {e}")
                    continue
        
        if not text_content:
            raise ValueError("No text could be extracted from PDF")
        
        result = "\n\n".join(text_content)
        logger.info(f"Extracted text from {page_count} pages")
        return result
    
    except ImportError:
        raise ImportError("pdfplumber is required for PDF extraction")
    except Exception as e:
        logger.exception(f"Error extracting PDF text: {e}")
        raise ValueError(f"Failed to extract PDF text: {str(e)}")


def analyze_pdf_content(
    text_content: str,
    analysis_type: str = "summary",
) -> Dict[str, Any]:
    """
    Analyze PDF text content using OpenAI.
    
    Args:
        text_content: Text extracted from PDF
        analysis_type: Type of analysis ('summary', 'detailed', 'keywords')
    
    Returns:
        Analysis results
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        api_key=api_key,
        temperature=0.7,
        timeout=25,  # Leave margin under 30s task timeout
    )
    
    # Truncate if too long
    if len(text_content) > 12000:
        text_content = text_content[:12000] + "\n[... truncated ...]"
    
    if analysis_type == "summary":
        prompt = PromptTemplate(
            template="""Analyze the following document and provide a concise summary with key points.

Document:
{text_content}

Provide your analysis as valid JSON with these fields:
- summary: 2-3 sentence executive summary
- key_points: array of 5-8 main points
- pages_analyzed: estimated number of pages
- confidence: your confidence level (0.0-1.0)
- full_analysis: null (for summary type)

Return ONLY valid JSON, no other text.""",
            input_variables=["text_content"],
        )
    
    elif analysis_type == "detailed":
        prompt = PromptTemplate(
            template="""Provide a detailed analysis of this document including structure, topics, and findings.

Document:
{text_content}

Return valid JSON with:
- summary: comprehensive overview
- key_points: array of detailed points (up to 10)
- pages_analyzed: estimated pages
- confidence: your confidence (0.0-1.0)
- full_analysis: object with structure, topics, findings""",
            input_variables=["text_content"],
        )
    
    else:  # keywords
        prompt = PromptTemplate(
            template="""Extract and analyze keywords, topics, and themes from this document.

Document:
{text_content}

Return valid JSON with:
- summary: keyword summary
- key_points: array of main topics/keywords
- pages_analyzed: estimated pages
- confidence: confidence level
- full_analysis: object with keywords, frequencies, themes""",
            input_variables=["text_content"],
        )
    
    try:
        # Format prompt
        formatted_prompt = prompt.format(text_content=text_content)
        
        # Call LLM
        response = llm.invoke(formatted_prompt)
        content = response.content
        
        # Parse JSON
        try:
            # Find JSON in response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                result = json.loads(json_str)
                
                # Validate required fields
                required = ["summary", "key_points", "pages_analyzed", "confidence"]
                for field in required:
                    if field not in result:
                        result[field] = None
                
                return result
            else:
                raise ValueError("No JSON found in response")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            # Return fallback
            return {
                "summary": content[:200],
                "key_points": [],
                "pages_analyzed": 0,
                "confidence": 0.0,
                "full_analysis": None,
            }
    
    except Exception as e:
        logger.exception(f"Error analyzing PDF content: {e}")
        raise


def analyze_text_content(text_content: str) -> Dict[str, Any]:
    """
    Analyze text content using OpenAI.
    
    Simpler version than PDF analysis.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        api_key=api_key,
        temperature=0.7,
        timeout=25,
    )
    
    prompt = PromptTemplate(
        template="""Analyze this text and provide insights.

Text:
{text_content}

Return valid JSON with:
- summary: 1-2 sentence summary
- category: text category (document, email, article, etc.)
- sentiment: sentiment (positive, negative, neutral)
- key_points: array of 3-5 key points
- confidence: your confidence (0.0-1.0)""",
        input_variables=["text_content"],
    )
    
    try:
        formatted_prompt = prompt.format(text_content=text_content)
        response = llm.invoke(formatted_prompt)
        content = response.content
        
        # Parse JSON
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        
        if json_start != -1 and json_end > json_start:
            json_str = content[json_start:json_end]
            return json.loads(json_str)
        else:
            raise ValueError("No JSON in response")
    
    except Exception as e:
        logger.exception(f"Error analyzing text: {e}")
        raise
