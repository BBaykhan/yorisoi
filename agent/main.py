"""AgentCore Runtime entrypoint. Copy this whole agent/ folder into app/<AgentName>/."""
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from yorisoi_agent import handle_request

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context=None):
    session_id = getattr(context, "session_id", None) or "default"
    return handle_request(payload, session_id)


if __name__ == "__main__":
    app.run()
