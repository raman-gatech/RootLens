"""RootLens FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from opentelemetry import metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from rootlens.anomaly.repository import AnomalyRepository
from rootlens.anomaly.service import AnomalyAnalysisService
from rootlens.api.anomalies import router as anomaly_router
from rootlens.api.evaluations import router as evaluation_router
from rootlens.api.health import router as health_router
from rootlens.api.incidents import router as incident_router
from rootlens.api.remediation import router as remediation_router
from rootlens.api.security import router as security_router
from rootlens.api.topology import router as topology_router
from rootlens.api.ui import _UI_DIR
from rootlens.api.ui import router as ui_router
from rootlens.config import Settings, get_settings
from rootlens.db.session import Database
from rootlens.evaluation.repository import EvaluationRepository
from rootlens.investigation.agents import InvestigationRunner
from rootlens.investigation.causal import CausalRanker
from rootlens.investigation.memory import IncidentMemory, IncidentMemoryRepository
from rootlens.investigation.provider import (
    DeterministicHypothesisProvider,
    HypothesisProvider,
    OpenAIResponsesProvider,
)
from rootlens.investigation.repository import InvestigationRepository
from rootlens.investigation.service import InvestigationService
from rootlens.investigation.tools import EvidenceToolbox
from rootlens.investigation.verifier import EvidenceVerifier
from rootlens.observability import configure_telemetry
from rootlens.remediation.executor import (
    DisabledRemediationExecutor,
    KubectlPodRestartExecutor,
    RemediationExecutor,
)
from rootlens.remediation.policy import RemediationPolicy
from rootlens.remediation.repository import RemediationRepository
from rootlens.remediation.service import RemediationService
from rootlens.security import ApiSecurityMiddleware, CredentialStore
from rootlens.telemetry import TelemetryGateway
from rootlens.topology.repository import ServiceGraphRepository
from rootlens.topology.service import ServiceTopologyService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_telemetry(resolved_settings)
    database = Database(
        resolved_settings.database_url,
        pool_size=resolved_settings.database_pool_size,
        max_overflow=resolved_settings.database_max_overflow,
        pool_timeout=resolved_settings.database_pool_timeout_seconds,
    )
    telemetry_gateway = TelemetryGateway.from_settings(resolved_settings)
    topology_service = ServiceTopologyService(
        gateway=telemetry_gateway,
        repository=ServiceGraphRepository(database),
        default_trace_limit=resolved_settings.topology_trace_limit,
    )
    anomaly_service = AnomalyAnalysisService(
        prometheus=telemetry_gateway.prometheus,
        repository=AnomalyRepository(database),
    )
    hypothesis_provider: HypothesisProvider
    if resolved_settings.agent_provider == "openai" and resolved_settings.openai_api_key:
        hypothesis_provider = OpenAIResponsesProvider(
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.openai_model,
        )
    else:
        hypothesis_provider = DeterministicHypothesisProvider()
    incident_memory = IncidentMemory(IncidentMemoryRepository(database))
    investigation_runner = InvestigationRunner(
        toolbox=EvidenceToolbox(
            gateway=telemetry_gateway,
            anomaly_service=anomaly_service,
            topology_service=topology_service,
            namespace=resolved_settings.kubernetes_namespace,
            log_limit=resolved_settings.investigation_log_limit,
        ),
        provider=hypothesis_provider,
        ranker=CausalRanker(),
        verifier=EvidenceVerifier(),
        memory=incident_memory,
    )
    investigation_service = InvestigationService(
        repository=InvestigationRepository(database),
        runner=investigation_runner,
        memory=incident_memory,
    )
    remediation_executor: RemediationExecutor
    if resolved_settings.remediation_execution_enabled:
        remediation_executor = KubectlPodRestartExecutor(
            kubectl_path=resolved_settings.remediation_kubectl_path,
            context=resolved_settings.remediation_kubernetes_context,
        )
    else:
        remediation_executor = DisabledRemediationExecutor()
    remediation_service = RemediationService(
        repository=RemediationRepository(database),
        investigations=investigation_service,
        gateway=telemetry_gateway,
        policy=RemediationPolicy(
            allowed_namespaces=resolved_settings.remediation_allowed_namespaces
        ),
        executor=remediation_executor,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.gather(database.close(), telemetry_gateway.aclose())

    app = FastAPI(
        title="RootLens API",
        version=resolved_settings.service_version,
        lifespan=lifespan,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
    )
    app.state.database = database
    app.state.settings = resolved_settings
    app.state.telemetry_gateway = telemetry_gateway
    app.state.topology_service = topology_service
    app.state.anomaly_service = anomaly_service
    app.state.investigation_service = investigation_service
    app.state.remediation_service = remediation_service
    app.state.evaluation_repository = EvaluationRepository(database)
    app.include_router(health_router)
    app.include_router(security_router)
    app.include_router(topology_router)
    app.include_router(anomaly_router)
    app.include_router(incident_router)
    app.include_router(remediation_router)
    app.include_router(evaluation_router)
    app.include_router(ui_router)
    app.mount("/dashboard/assets", StaticFiles(directory=_UI_DIR), name="dashboard-assets")
    credential_store = (
        CredentialStore.from_file(resolved_settings.auth_credentials_file)
        if resolved_settings.auth_enabled and resolved_settings.auth_credentials_file
        else None
    )
    app.add_middleware(
        ApiSecurityMiddleware,
        enabled=resolved_settings.auth_enabled,
        store=credential_store,
        hsts_enabled=resolved_settings.environment in {"staging", "production"},
    )
    if resolved_settings.trusted_hosts != ("*",):
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(resolved_settings.trusted_hosts),
        )

    meter = metrics.get_meter("rootlens.api")
    startup_counter = meter.create_counter(
        "rootlens.api.startups",
        description="Number of RootLens API process starts",
    )
    startup_counter.add(1)

    if resolved_settings.telemetry_enabled:
        FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
