"""OpenAI LLM provider implementation."""

import os
import dspy
from core.config import get_config


def create_openai_lm() -> dspy.LM:
    """
    Create DSPy LM instance for OpenAI or OpenRouter.
    
    Returns:
        Configured dspy.LM instance for OpenAI/OpenRouter
    """
    config = get_config()
    
    # Determine model name - if using OpenRouter, use openrouter/ prefix
    model = config.openai.model
    api_key = config.openai.api_key
    
    # Auto-detect OpenRouter keys (they start with "sk-or-")
    is_openrouter = api_key and api_key.startswith("sk-or-")
    
    # If OpenRouter key detected, configure for OpenRouter
    if is_openrouter:
        # Set environment variable for LiteLLM to use OpenRouter
        os.environ["OPENROUTER_API_KEY"] = api_key
        
        # Use OpenRouter model format if not already in that format
        if not model.startswith("openrouter/"):
            # Map common OpenAI models to OpenRouter format
            model_mapping = {
                "gpt-4o": "openrouter/openai/gpt-4o",
                "gpt-4": "openrouter/openai/gpt-4",
                "gpt-3.5-turbo": "openrouter/openai/gpt-3.5-turbo",
            }
            model = model_mapping.get(model, f"openrouter/openai/{model}")
    
    lm_kwargs = {
        "model": model,
        "api_key": api_key,
        "temperature": config.openai.temperature,
    }
    
    if config.openai.max_tokens:
        lm_kwargs["max_tokens"] = config.openai.max_tokens
    
    # Set base URL if explicitly configured
    if config.openai.base_url:
        lm_kwargs["api_base"] = config.openai.base_url
    
    return dspy.LM(**lm_kwargs)
