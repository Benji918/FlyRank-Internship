"""
AI Analysis Service - Integrates LLM with retry logic, timeouts, and validation.
"""
import asyncio
import json
import os
from typing import Optional
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)


class TaskAnalysis(BaseModel):
    """Schema for AI analysis output - ensures structured responses."""
    task_type: str = Field(
        ..., 
        description="Type of task (e.g., 'review', 'write', 'analyze', 'plan', 'implement')"
    )
    category: str = Field(
        ..., 
        description="Business category (e.g., 'finance', 'engineering', 'marketing', 'admin')"
    )
    priority: str = Field(
        ..., 
        description="Priority level: 'low', 'medium', or 'high'"
    )
    estimated_time_minutes: int = Field(
        ..., 
        ge=5, 
        le=480, 
        description="Estimated time to complete in minutes (5-480)"
    )
    key_points: list[str] = Field(
        ..., 
        description="2-4 key points or steps for this task"
    )
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Confidence level of analysis (0.0-1.0)"
    )


class AIAnalysisService:
    """
    Service for analyzing tasks using OpenAI LLM with robust error handling.
    
    Features:
    - Automatic retries with exponential backoff (3 attempts)
    - 30-second timeout per request
    - Schema validation for all responses
    - Structured output using Pydantic models
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ):
        """Initialize AI service with configuration."""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")
        
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        
        self.llm = ChatOpenAI(
            model=model,
            api_key=self.api_key,
            temperature=0.7,
            timeout=timeout_seconds,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def analyze_task(self, task_description: str) -> TaskAnalysis:
        """
        Analyze a task description using OpenAI LLM.
        
        Args:
            task_description: The task to analyze
            
        Returns:
            TaskAnalysis: Structured analysis with validation
            
        Raises:
            ValueError: If task_description is empty or too long
            TimeoutError: If request exceeds timeout
            RetryError: If all retry attempts fail
        """
        # Input validation
        if not task_description or not task_description.strip():
            raise ValueError("Task description cannot be empty")
        
        if len(task_description) > 5000:
            raise ValueError("Task description too long (max 5000 characters)")
        
        # Parser for structured output
        parser = PydanticOutputParser(pydantic_object=TaskAnalysis)
        format_instructions = parser.get_format_instructions()
        
        prompt = PromptTemplate(
            template="""Analyze the following task and provide a structured breakdown.
Be concise but informative. Return valid JSON.

Task: {task_description}

{format_instructions}

Provide your analysis as a JSON object with these exact fields:
- task_type: one of 'review', 'write', 'analyze', 'plan', 'implement', 'other'
- category: business category like 'finance', 'engineering', 'marketing', 'admin', 'sales', 'operations'
- priority: 'low', 'medium', or 'high' based on task importance
- estimated_time_minutes: realistic time estimate (5-480 minutes)
- key_points: list of 2-4 key points or action items
- confidence: how confident you are in this analysis (0.0-1.0)

Return ONLY valid JSON, no additional text.""",
            input_variables=["task_description"],
            partial_variables={"format_instructions": format_instructions},
        )
        
        try:
            # Run with asyncio timeout wrapper
            response = await asyncio.wait_for(
                self._call_llm(prompt, task_description),
                timeout=self.timeout_seconds,
            )
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"AI analysis request timed out after {self.timeout_seconds} seconds"
            )
    
    async def _call_llm(self, prompt: PromptTemplate, task_description: str) -> TaskAnalysis:
        """Call LLM and parse response."""
        parser = PydanticOutputParser(pydantic_object=TaskAnalysis)
        
        # Format the prompt
        formatted_prompt = prompt.format(task_description=task_description)
        
        # Call LLM
        response = await asyncio.to_thread(
            lambda: self.llm.invoke(formatted_prompt)
        )
        
        # Extract content
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON from response
        try:
            # Try to find JSON in the response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                analysis_dict = json.loads(json_str)
                return TaskAnalysis(**analysis_dict)
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse AI response: {e}")
    
    def health_check(self) -> dict:
        """Check if AI service is configured correctly."""
        return {
            "status": "ok",
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "api_key_configured": bool(self.api_key),
        }


# Global service instance
_service: Optional[AIAnalysisService] = None


def get_ai_service() -> AIAnalysisService:
    """Get or create AI service singleton."""
    global _service
    if _service is None:
        _service = AIAnalysisService()
    return _service


def init_ai_service(api_key: Optional[str] = None) -> AIAnalysisService:
    """Initialize AI service with optional custom API key."""
    global _service
    _service = AIAnalysisService(api_key=api_key)
    return _service
