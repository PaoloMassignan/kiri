import os

# Disable chromadb anonymous telemetry so posthog is never loaded at runtime.
# chromadb 0.x reads ANONYMIZED_TELEMETRY; 1.x reads CHROMA_ANONYMIZED_TELEMETRY.
# Set both to be safe.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "false")
