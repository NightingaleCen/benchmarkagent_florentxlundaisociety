def evaluate(model_output: dict, expected: dict, judge=None) -> dict:
    got = model_output.get("sentiment")
    want = expected.get("sentiment")
    score = 1 if got == want else 0
    return {
        "score": score,
        "reason": f"expected={want!r}, got={got!r}",
    }
