"""LLM selection and configuration based on config."""

import dspy
from core.config import get_config
from core.llms.openai import create_openai_lm
from core.llms.anthropic import create_anthropic_lm


def get_llm_for_agent(agent_name: str) -> dspy.LM:
    """
    Get DSPy LM instance for a specific agent based on config.
    
    Args:
        agent_name: Name of the agent ('column_canonicalization', 'research', 'spend_classification')
    
    Returns:
        Configured dspy.LM instance
    """
    config = get_config()
    
    # Get provider name for this agent
    provider_attr = f"{agent_name}_llm"
    provider = getattr(config, provider_attr, "openai").lower()
    
    if provider == "openai":
        return create_openai_lm()
    elif provider == "anthropic":
        return create_anthropic_lm()
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. Available: openai, anthropic"
        )
