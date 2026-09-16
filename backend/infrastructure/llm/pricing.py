# Point-in-time token costs (USD per 1M tokens)
# Must be updated manually, do not fetch at runtime.
PRICING = {
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60
    },
    "text-embedding-3-small": {
        "input": 0.02,
        "output": 0.00
    },
    "llama3": {
        "input": 0.00,
        "output": 0.00
    },
    "nomic-embed-text": {
        "input": 0.00,
        "output": 0.00
    },
    "stub": {
        "input": 0.00,
        "output": 0.00
    }
}

def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = PRICING.get(model, {"input": 0.0, "output": 0.0})
    input_cost = (prompt_tokens / 1_000_000.0) * rates["input"]
    output_cost = (completion_tokens / 1_000_000.0) * rates["output"]
    return input_cost + output_cost
