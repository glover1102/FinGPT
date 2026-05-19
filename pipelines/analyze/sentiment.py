from typing import Dict, Any, Tuple

def analyze_sentiment(raw_output: Dict[str, Any]) -> Tuple[str, float]:
    """
    Extracts sentiment and confidence from the raw model output.
    Returns (sentiment: str, confidence: float).
    """
    # Expected keys from FinGPT adapter JSON schema
    sentiment = raw_output.get("sentiment", "Neutral")
    # Clean up the format
    sentiment = str(sentiment).strip().capitalize()
    
    confidence = raw_output.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (ValueError, TypeError):
        confidence = 0.5
        
    return sentiment, confidence
