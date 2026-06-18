"""LLM connectivity check (provider-agnostic: Gemini / Azure / Anthropic).

Validates that your .env credentials work BEFORE running the whole graph.
Resolves the planner slot exactly like the agent does, makes one tiny call,
and prints the result.

    python check_llm.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend-ai")

from app.agents.test_case_creation_langgraph.settings import settings  # noqa: E402
from app.agents.test_case_creation_langgraph.tools.shared import (  # noqa: E402
    build_llm,
    using_stub,
)


def main() -> None:
    slot = settings.llm_planner
    print(f"provider      : {slot.provider}")
    print(f"model/deploy  : {slot.model}")
    if slot.provider == "azure_openai":
        print(f"endpoint      : {slot.endpoint}")
    print(f"offline_stub  : {slot.offline_stub}")

    if using_stub(slot):
        print("\n[!] Still in OFFLINE STUB mode. To go live, in .env set:")
        print("    LLM_OFFLINE_STUB=false")
        print(f"    and a non-empty API key for provider '{slot.provider}'")
        print("    (e.g. GOOGLE_API_KEY for Gemini).")
        return

    print("\nCalling the model with a 1-line prompt...")
    llm = build_llm(slot)
    from langchain_core.messages import HumanMessage

    try:
        resp = llm.invoke([HumanMessage(content="Reply with exactly: OK")])
    except Exception as exc:
        msg = str(exc)
        if "CERTIFICATE_VERIFY" in msg or "SSL" in msg:
            print("\n[X] TLS certificate verification failed — this is your corporate")
            print("    network doing TLS inspection, not an agent bug. Fix:")
            print("      pip install truststore")
            print("    then re-run. (build_llm() auto-uses the OS trust store, which")
            print("    already trusts your corporate root CA.)")
            print("\n    If it still fails, ask IT for the corporate root CA .pem and set:")
            print("      $env:SSL_CERT_FILE = 'C:\\path\\to\\corp-root-ca.pem'")
        elif "API_KEY" in msg.upper() or "API key" in msg or "PERMISSION" in msg.upper():
            print(f"\n[X] Auth/permission error from the provider:\n    {msg[:300]}")
            print("    Check GOOGLE_API_KEY and that the model is enabled for it.")
        else:
            print(f"\n[X] Call failed:\n    {msg[:400]}")
        return
    text = resp.content if hasattr(resp, "content") else str(resp)
    print(f"model replied : {text!r}")
    print("\n[OK] Live connection works. You can now run: python demo.py")


if __name__ == "__main__":
    main()
