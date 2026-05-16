from __future__ import annotations

from fastapi import FastAPI

from src.audit.log import AuditLog
from src.config.settings import Settings
from src.filter.l1_similarity import L1Filter
from src.filter.l2_symbols import L2Filter
from src.filter.l3_classifier import L3Filter
from src.filter.pipeline import FilterPipeline
from src.indexer.chunker import chunk
from src.indexer.embedder import Embedder
from src.indexer.symbol_extractor import SymbolExtractor
from src.indexer.watcher import Watcher
from src.keys.manager import KeyManager
from src.llm import make_llm_backend
from src.proxy.forwarder import Forwarder
from src.proxy.server import create_app
from src.ratelimit.limiter import RateLimiter
from src.redaction.engine import RedactionEngine
from src.redaction.summary_generator import SummaryGenerator
from src.store.secrets_store import SecretsStore
from src.store.summary_store import SummaryStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore


def create_gateway_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings.load()

    index_dir = settings.workspace / ".kiri" / "index"
    keys_dir = settings.workspace / ".kiri" / "keys"
    secrets_path = settings.workspace / ".kiri" / "secrets"

    # ensure secrets file exists so watcher and secrets store can open it
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    if not secrets_path.exists():
        secrets_path.write_text("", encoding="utf-8")

    vector_store = VectorStore(index_dir=index_dir)
    symbol_store = SymbolStore(index_dir=index_dir)
    summary_store = SummaryStore(index_dir=index_dir)
    secrets_store = SecretsStore(secrets_path=secrets_path, workspace=settings.workspace)

    llm_backend = make_llm_backend(settings)

    embedder = Embedder(settings=settings)
    extractor = SymbolExtractor(backend=llm_backend)

    summary_generator = SummaryGenerator(backend=llm_backend)

    watcher = Watcher(
        secrets_store=secrets_store,
        vector_store=vector_store,
        symbol_store=symbol_store,
        chunker=chunk,
        embedder=embedder,
        extractor=extractor,
        summary_generator=summary_generator,
        summary_store=summary_store,
    )
    watcher.start()

    key_manager = KeyManager(keys_dir=keys_dir)

    l1 = L1Filter(vector_store=vector_store, embedder=embedder)
    l2 = L2Filter(symbol_store=symbol_store)
    l3 = L3Filter(backend=llm_backend)
    pipeline = FilterPipeline(
        settings=settings,
        l1=l1,
        l2=l2,
        l3=l3,
        secrets_store=secrets_store,
    )

    redaction_engine = RedactionEngine(
        summary_store=summary_store,
        symbol_store=symbol_store,
    )

    forwarder = Forwarder(openai_base=settings.openai_upstream_url)

    audit_log = AuditLog(
        log_path=settings.workspace / ".kiri" / "audit.log",
        max_bytes=settings.audit_max_bytes,
        backup_count=settings.audit_backup_count,
    )

    rate_limiter = RateLimiter(rpm=settings.rate_limit_rpm)

    app = create_app(
        key_manager=key_manager,
        pipeline=pipeline,
        forwarder=forwarder,
        redaction_engine=redaction_engine,
        audit_log=audit_log,
        rate_limiter=rate_limiter,
        action=settings.action,
        oauth_passthrough=settings.oauth_passthrough,
    )

    @app.on_event("shutdown")
    async def _shutdown_watcher() -> None:
        watcher.stop()

    return app


