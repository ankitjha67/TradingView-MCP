import json
from litellm import completion

def generate_analysis(api_key: str, provider: str, model: str, base_url: str, state: dict) -> str:
    """
    Generates trading analysis using LiteLLM to support any model provider.
    """
    if not model:
        return "Error: No model selected."
        
    prompt = f"""
    You are an expert trading AI. Analyze the current market state and provide a concise, actionable analysis.
    
    Current State:
    Symbol: {state.get('tv_symbol')} ({state.get('tv_interval')})
    Exchange: {state.get('tv_exchange')}
    
    Indicators:
    {json.dumps(state.get('indicators'), indent=2)}
    
    System Recommendation: {state.get('recommendation')}
    Bias Reason: {state.get('bias_reason')}
    
    Please provide:
    1. A quick summary of the technical picture.
    2. Any hidden risks or bullish/bearish divergences you notice from the numbers.
    3. A clear final verdict (Buy, Sell, or Hold).
    """

    # Model string formatting for litellm (e.g. "ollama/llama3" or "openai/gpt-4o")
    if provider.lower() == "ollama":
        model_name = f"ollama/{model}"
    elif provider.lower() == "anthropic":
        model_name = f"anthropic/{model}"
    elif provider.lower() == "openai":
        model_name = f"openai/{model}"
    elif provider.lower() == "groq":
        model_name = f"groq/{model}"
    else:
        model_name = model # fallback

    try:
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
            
        response = completion(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        return f"Error connecting to AI Provider ({provider}): {str(e)}\n\nPlease check your API Key and Model name."
