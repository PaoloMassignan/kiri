import os

# Disable chromadb anonymous telemetry — prevents the posthog module from
# being loaded at runtime. posthog is not bundled (not installed in the
# build environment) and kiri does not send usage data.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
