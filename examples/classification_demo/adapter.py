import time


SYSTEM_PROMPT = (
    "You classify movie review snippets. Respond with exactly one word: "
    "either 'positive' or 'negative'. No punctuation, no extra words."
)


def run_model(model_client, input_record: dict) -> dict:
    start = time.perf_counter()
    response = model_client.complete(
        prompt=f"{SYSTEM_PROMPT}\n\nReview: {input_record['review_text']}\nSentiment:",
        max_tokens=8,
    )
    label = response.text.strip().lower().strip(".,!?\"'")
    if label not in {"positive", "negative"}:
        label = "negative" if "neg" in label else "positive" if "pos" in label else label

    return {
        "output": {"sentiment": label},
        "usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        },
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "raw_response": response.raw,
    }
