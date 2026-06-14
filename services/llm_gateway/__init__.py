"""BYO-LLM gateway: the single boundary where provider SDKs and API keys are used.

Business logic and the agent never import a provider directly — they call
LLMGateway.complete(...) with a TaskClass, and routing + key resolution happen here.
Keys are read at call time and NEVER logged or returned.
"""
