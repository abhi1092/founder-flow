## Output Format

You MUST respond with a single JSON object — no markdown fences, no commentary before or after, no explanatory text. Your entire response must be valid JSON that can be parsed by `json.loads()`.

If you cannot fully analyze a dimension, provide your best assessment with a lower confidence score rather than omitting the field. Every field in the schema is required.

Confidence scoring guidelines:
- 0-20: Speculation with no supporting evidence
- 21-40: Weak signals, limited data, mostly inference
- 41-60: Mixed evidence, some data points but significant gaps
- 61-80: Solid evidence from multiple sources, minor gaps remain
- 81-100: Strong evidence, multiple corroborating sources, high certainty
