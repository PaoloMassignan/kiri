"""Add OS001-OS012 real open-source-style cases to smart-coding dataset."""
import json
from pathlib import Path

path = Path(__file__).parent / "smart-coding" / "coding_dataset.json"
cases = json.loads(path.read_text(encoding="utf-8"))

OS_CASES = [
  {
    "id": "OS001", "language": "python", "scenario": "refactor",
    "developer_prompt": "Refactor the following code:\n\nfrom sqlalchemy.orm import Session\nfrom decimal import Decimal\nfrom typing import Optional\nfrom .models import ChargeRecord\n\nclass VaultLedgerService:\n    def __init__(self, db: Session):\n        self._db = db\n\n    def post_charge(self, account_id: str, amount: Decimal, currency: str = \"USD\") -> ChargeRecord:\n        if amount <= Decimal(\"0\"):\n            raise ValueError(\"charge amount must be positive\")\n        record = ChargeRecord(\n            account_id=account_id,\n            amount=amount,\n            currency=currency,\n            status=\"pending\",\n        )\n        self._db.add(record)\n        self._db.flush()\n        return record\n\n    def settle(self, charge_id: int) -> Optional[ChargeRecord]:\n        record = self._db.query(ChargeRecord).filter_by(id=charge_id).first()\n        if record:\n            record.status = \"settled\"\n        return record\n",
    "registered_symbols": [
      {"text": "VaultLedgerService", "label": "CLASS_NAME"},
      {"text": "ChargeRecord",       "label": "INTERNAL_MODEL"},
      {"text": "post_charge",        "label": "FUNCTION_NAME"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can advise on SQLAlchemy session patterns and method decomposition without seeing proprietary financial logic.",
    "source_note": "SQLAlchemy service layer pattern common in fintech backends; resembles Stripe internal ledger abstractions."
  },
  {
    "id": "OS002", "language": "python", "scenario": "debug",
    "developer_prompt": "Help me debug this code:\n\nimport apache_beam as beam\nfrom apache_beam.transforms.window import FixedWindows\nfrom .transforms import NormalizationStage, AnomalyScorer\n\nclass IngestionPipeline:\n    def __init__(self, config: dict):\n        self.window_size = config.get(\"window_seconds\", 300)\n        self.threshold = config.get(\"anomaly_threshold\", 0.85)\n\n    def build(self, pipeline: beam.Pipeline):\n        return (\n            pipeline\n            | \"ReadKafka\" >> beam.io.ReadFromKafka(\n                consumer_config={\"bootstrap.servers\": \"kafka:9092\"},\n                topics=[\"raw-events\"],\n            )\n            | \"Window\" >> beam.WindowInto(FixedWindows(self.window_size))\n            | \"Normalize\" >> beam.ParDo(NormalizationStage())\n            | \"Score\" >> beam.ParDo(AnomalyScorer(threshold=self.threshold))\n            | \"WriteBQ\" >> beam.io.WriteToBigQuery(\"project:dataset.anomalies\")\n        )\n",
    "registered_symbols": [
      {"text": "IngestionPipeline",  "label": "CLASS_NAME"},
      {"text": "NormalizationStage", "label": "INTERNAL_TRANSFORM"},
      {"text": "AnomalyScorer",      "label": "INTERNAL_TRANSFORM"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can explain Beam windowing and Kafka consumer configuration without exposing proprietary transform logic.",
    "source_note": "Apache Beam streaming pipeline; mirrors beam-examples GitHub patterns."
  },
  {
    "id": "OS003", "language": "python", "scenario": "optimize",
    "developer_prompt": "Optimize the following code:\n\nimport torch\nfrom torch import nn\nfrom .backbone import FeatureExtractorV3\nfrom .heads import RiskScoringHead\n\nclass UnderwritingModel(nn.Module):\n    def __init__(self, embedding_dim: int = 256, dropout: float = 0.3):\n        super().__init__()\n        self.backbone = FeatureExtractorV3(out_dim=embedding_dim)\n        self.head = RiskScoringHead(in_dim=embedding_dim)\n        self.dropout = nn.Dropout(dropout)\n\n    def forward(self, x: torch.Tensor) -> torch.Tensor:\n        features = self.backbone(x)\n        features = self.dropout(features)\n        return self.head(features)\n\n    def predict_risk(self, x: torch.Tensor) -> dict:\n        self.eval()\n        with torch.no_grad():\n            logits = self.forward(x)\n            probs = torch.sigmoid(logits)\n        return {\"risk_score\": probs.item(), \"label\": \"high\" if probs > 0.7 else \"low\"}\n",
    "registered_symbols": [
      {"text": "UnderwritingModel",  "label": "CLASS_NAME"},
      {"text": "FeatureExtractorV3", "label": "INTERNAL_MODULE"},
      {"text": "RiskScoringHead",    "label": "INTERNAL_MODULE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can recommend PyTorch inference optimizations without learning proprietary risk-scoring logic.",
    "source_note": "PyTorch nn.Module head/backbone split; idiomatic torchvision architecture in ML fintech."
  },
  {
    "id": "OS004", "language": "python", "scenario": "explain",
    "developer_prompt": "Explain what this code does:\n\nfrom dataclasses import dataclass, field\nfrom typing import List\nfrom enum import Enum\n\nclass ConsentScope(Enum):\n    ANALYTICS = \"analytics\"\n    MARKETING = \"marketing\"\n    ESSENTIAL = \"essential\"\n\n@dataclass\nclass PatientConsentRecord:\n    patient_id: str\n    granted_scopes: List[ConsentScope] = field(default_factory=list)\n    revoked_scopes: List[ConsentScope] = field(default_factory=list)\n\n    def grant(self, scope: ConsentScope) -> None:\n        if scope in self.revoked_scopes:\n            self.revoked_scopes.remove(scope)\n        if scope not in self.granted_scopes:\n            self.granted_scopes.append(scope)\n\n    def revoke(self, scope: ConsentScope) -> None:\n        if scope in self.granted_scopes:\n            self.granted_scopes.remove(scope)\n        if scope not in self.revoked_scopes:\n            self.revoked_scopes.append(scope)\n\n    def is_active(self, scope: ConsentScope) -> bool:\n        return scope in self.granted_scopes\n",
    "registered_symbols": [
      {"text": "PatientConsentRecord", "label": "CLASS_NAME"},
      {"text": "ConsentScope",         "label": "INTERNAL_ENUM"},
      {"text": "patient_id",           "label": "PHI_FIELD"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can explain consent state-machine patterns without seeing patient identifiers or proprietary scope taxonomy.",
    "source_note": "Healthcare consent modeled after FHIR Consent resource; dataclass pattern common in health-tech backends."
  },
  {
    "id": "OS005", "language": "typescript", "scenario": "refactor",
    "developer_prompt": "Refactor the following code:\n\nimport { Injectable } from '@nestjs/common';\nimport { InjectRepository } from '@nestjs/typeorm';\nimport { Repository } from 'typeorm';\nimport { OAuthSession } from './entities/oauth-session.entity';\nimport { TokenCryptoBridge } from './crypto/token-crypto-bridge';\n\n@Injectable()\nexport class SessionBrokerService {\n  constructor(\n    @InjectRepository(OAuthSession)\n    private readonly sessions: Repository<OAuthSession>,\n    private readonly crypto: TokenCryptoBridge,\n  ) {}\n\n  async createSession(userId: string, scopes: string[]): Promise<string> {\n    const rawToken = this.crypto.generateOpaque(32);\n    const session = this.sessions.create({\n      userId,\n      tokenHash: await this.crypto.hash(rawToken),\n      scopes,\n      expiresAt: new Date(Date.now() + 3_600_000),\n    });\n    await this.sessions.save(session);\n    return rawToken;\n  }\n\n  async validate(rawToken: string): Promise<OAuthSession | null> {\n    const hash = await this.crypto.hash(rawToken);\n    return this.sessions.findOne({ where: { tokenHash: hash, revoked: false } }) ?? null;\n  }\n}\n",
    "registered_symbols": [
      {"text": "SessionBrokerService", "label": "CLASS_NAME"},
      {"text": "TokenCryptoBridge",   "label": "INTERNAL_SERVICE"},
      {"text": "OAuthSession",        "label": "INTERNAL_ENTITY"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can advise on NestJS DI and TypeORM repository patterns without seeing proprietary session entity structure.",
    "source_note": "NestJS + TypeORM OAuth token management; mirrors nestjs/jwt and Passport.js strategies."
  },
  {
    "id": "OS006", "language": "typescript", "scenario": "debug",
    "developer_prompt": "Help me debug this code:\n\nimport { SQSEvent, SQSRecord } from 'aws-lambda';\nimport { ShipmentManifestParser } from './parsers/shipment-manifest-parser';\nimport { WarehouseRouterClient } from './clients/warehouse-router-client';\nimport { logger } from './observability';\n\nexport async function handler(event: SQSEvent): Promise<void> {\n  const parser = new ShipmentManifestParser();\n  const router = new WarehouseRouterClient();\n  await Promise.all(\n    event.Records.map(async (rec: SQSRecord) => {\n      try {\n        const manifest = parser.parse(rec.body);\n        const route = await router.resolveRoute(manifest.originCode, manifest.destinationCode);\n        logger.info({ manifestId: manifest.id, route }, 'routed shipment');\n      } catch (err) {\n        logger.error({ messageId: rec.messageId, err }, 'failed to route shipment');\n        throw err;\n      }\n    }),\n  );\n}\n",
    "registered_symbols": [
      {"text": "ShipmentManifestParser", "label": "INTERNAL_CLASS"},
      {"text": "WarehouseRouterClient",  "label": "INTERNAL_SERVICE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can diagnose SQS Lambda error-handling without seeing proprietary manifest parsing or routing logic.",
    "source_note": "AWS Lambda SQS consumer from aws-samples/serverless-patterns; pino logger object style."
  },
  {
    "id": "OS007", "language": "java", "scenario": "optimize",
    "developer_prompt": "Optimize the following code:\n\n@Service\n@RequiredArgsConstructor\npublic class ClaimsAdjudicationEngine {\n\n    private final ClaimRepository claimRepo;\n    private final PolicyEligibilityChecker eligibilityChecker;\n    private final BenefitCalculatorV2 benefitCalculator;\n\n    @Transactional\n    public AdjudicationResult adjudicate(String claimId) {\n        Claim claim = claimRepo.findById(claimId)\n            .orElseThrow(() -> new ClaimNotFoundException(claimId));\n        if (!eligibilityChecker.isEligible(claim.getMemberId(), claim.getServiceDate())) {\n            return AdjudicationResult.denied(claimId, \"member not eligible\");\n        }\n        BigDecimal benefit = benefitCalculator.compute(claim);\n        claim.setStatus(ClaimStatus.APPROVED);\n        claim.setPaidAmount(benefit);\n        claimRepo.save(claim);\n        return AdjudicationResult.approved(claimId, benefit);\n    }\n}\n",
    "registered_symbols": [
      {"text": "ClaimsAdjudicationEngine",  "label": "CLASS_NAME"},
      {"text": "BenefitCalculatorV2",       "label": "INTERNAL_SERVICE"},
      {"text": "PolicyEligibilityChecker",  "label": "INTERNAL_SERVICE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can recommend Spring @Transactional optimizations without seeing proprietary adjudication business rules.",
    "source_note": "Spring Boot service with Lombok; mirrors spring-petclinic and healthcare claim processing microservices."
  },
  {
    "id": "OS008", "language": "java", "scenario": "refactor",
    "developer_prompt": "Refactor the following code:\n\n@RestController\n@RequestMapping(\"/api/v2/orders\")\npublic class FulfillmentOrderController {\n\n    private final FulfillmentOrchestrator orchestrator;\n    private final OrderDtoMapper mapper;\n\n    public FulfillmentOrderController(FulfillmentOrchestrator orchestrator, OrderDtoMapper mapper) {\n        this.orchestrator = orchestrator;\n        this.mapper = mapper;\n    }\n\n    @PostMapping\n    public ResponseEntity<OrderResponseDto> create(@Valid @RequestBody CreateOrderRequest req) {\n        FulfillmentOrder order = orchestrator.initiate(mapper.toDomain(req));\n        return ResponseEntity.status(HttpStatus.CREATED).body(mapper.toDto(order));\n    }\n\n    @PatchMapping(\"/{orderId}/cancel\")\n    public ResponseEntity<Void> cancel(@PathVariable String orderId) {\n        orchestrator.cancel(orderId);\n        return ResponseEntity.noContent().build();\n    }\n}\n",
    "registered_symbols": [
      {"text": "FulfillmentOrchestrator", "label": "INTERNAL_SERVICE"},
      {"text": "FulfillmentOrder",        "label": "INTERNAL_MODEL"},
      {"text": "OrderDtoMapper",          "label": "INTERNAL_CLASS"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can advise on Spring REST controller design and DTO mapping without seeing proprietary fulfillment domain models.",
    "source_note": "Spring Boot REST controller with MapStruct-style mapper; logistics SaaS pattern."
  },
  {
    "id": "OS009", "language": "go", "scenario": "debug",
    "developer_prompt": "Help me debug this code:\n\npackage dispatch\n\nimport (\n\t\"context\"\n\t\"fmt\"\n\t\"github.com/acme/platform/internal/routeengine\"\n)\n\ntype DriverAssignmentService struct {\n\trouter *routeengine.GeoProximityRouter\n\tstore  AssignmentStore\n}\n\nfunc (s *DriverAssignmentService) Assign(ctx context.Context, req AssignRequest) (*Assignment, error) {\n\tcandidates, err := s.store.AvailableDrivers(ctx, req.ZoneID)\n\tif err != nil {\n\t\treturn nil, fmt.Errorf(\"fetch drivers: %w\", err)\n\t}\n\tif len(candidates) == 0 {\n\t\treturn nil, ErrNoDriversAvailable\n\t}\n\tbest, err := s.router.NearestDriver(ctx, req.PickupCoords, candidates)\n\tif err != nil {\n\t\treturn nil, fmt.Errorf(\"routing: %w\", err)\n\t}\n\treturn s.store.CreateAssignment(ctx, best.DriverID, req.OrderID)\n}\n",
    "registered_symbols": [
      {"text": "DriverAssignmentService", "label": "CLASS_NAME"},
      {"text": "GeoProximityRouter",     "label": "INTERNAL_SERVICE"},
      {"text": "AssignmentStore",        "label": "INTERNAL_INTERFACE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can help debug Go error wrapping and context propagation without seeing proprietary geospatial routing algorithms.",
    "source_note": "Idiomatic Go struct with interface DI; mirrors uber-go/fx examples and ride-dispatch microservices."
  },
  {
    "id": "OS010", "language": "go", "scenario": "explain",
    "developer_prompt": "Explain what this code does:\n\npackage pipeline\n\nimport (\n\t\"sync\"\n\t\"github.com/acme/platform/internal/featurestore\"\n)\n\ntype FeatureEnrichmentWorker struct {\n\tpool        *featurestore.RedisFeaturePool\n\tconcurrency int\n}\n\nfunc (w *FeatureEnrichmentWorker) Enrich(records []RawEvent) ([]EnrichedEvent, error) {\n\tsem := make(chan struct{}, w.concurrency)\n\tresults := make([]EnrichedEvent, len(records))\n\tvar mu sync.Mutex\n\tvar wg sync.WaitGroup\n\tvar firstErr error\n\n\tfor i, rec := range records {\n\t\twg.Add(1)\n\t\tsem <- struct{}{}\n\t\tgo func(idx int, r RawEvent) {\n\t\t\tdefer wg.Done()\n\t\t\tdefer func() { <-sem }()\n\t\t\tfeats, err := w.pool.Lookup(r.EntityID)\n\t\t\tif err != nil {\n\t\t\t\tmu.Lock()\n\t\t\t\tif firstErr == nil { firstErr = err }\n\t\t\t\tmu.Unlock()\n\t\t\t\treturn\n\t\t\t}\n\t\t\tresults[idx] = EnrichedEvent{Raw: r, Features: feats}\n\t\t}(i, rec)\n\t}\n\twg.Wait()\n\treturn results, firstErr\n}\n",
    "registered_symbols": [
      {"text": "FeatureEnrichmentWorker", "label": "CLASS_NAME"},
      {"text": "RedisFeaturePool",       "label": "INTERNAL_SERVICE"},
      {"text": "EnrichedEvent",          "label": "INTERNAL_TYPE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can explain Go semaphore-based concurrency patterns without seeing proprietary feature engineering logic.",
    "source_note": "Worker-pool with semaphore; Go wiki bounded-parallelism pattern; Feast/Redis online store lookup."
  },
  {
    "id": "OS011", "language": "csharp", "scenario": "refactor",
    "developer_prompt": "Refactor the following code:\n\nusing MediatR;\nusing System.Threading;\nusing System.Threading.Tasks;\n\npublic class IssueRefundCommandHandler : IRequestHandler<IssueRefundCommand, RefundResult>\n{\n    private readonly IPaymentGatewayAdapter _gateway;\n    private readonly IRefundAuditWriter _auditWriter;\n\n    public IssueRefundCommandHandler(IPaymentGatewayAdapter gateway, IRefundAuditWriter auditWriter)\n    {\n        _gateway = gateway;\n        _auditWriter = auditWriter;\n    }\n\n    public async Task<RefundResult> Handle(IssueRefundCommand command, CancellationToken ct)\n    {\n        var result = await _gateway.ProcessRefundAsync(command.TransactionId, command.Amount, ct);\n        await _auditWriter.RecordAsync(new RefundAuditEntry\n        {\n            TransactionId = command.TransactionId,\n            Amount        = command.Amount,\n            Outcome       = result.Status,\n            Timestamp     = DateTimeOffset.UtcNow,\n        }, ct);\n        return result;\n    }\n}\n",
    "registered_symbols": [
      {"text": "IssueRefundCommandHandler", "label": "CLASS_NAME"},
      {"text": "IPaymentGatewayAdapter",    "label": "INTERNAL_INTERFACE"},
      {"text": "IRefundAuditWriter",        "label": "INTERNAL_INTERFACE"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can advise on MediatR CQRS patterns without seeing proprietary payment gateway adapter or audit schema.",
    "source_note": "MediatR IRequestHandler from jbogard/MediatR; .NET fintech microservice CQRS pattern."
  },
  {
    "id": "OS012", "language": "ruby", "scenario": "debug",
    "developer_prompt": "Help me debug this code:\n\nclass SubscriptionRenewalJob < ApplicationJob\n  queue_as :billing\n  retry_on Stripe::RateLimitError, wait: 5.seconds, attempts: 3\n\n  def perform(subscription_id)\n    subscription = MembershipLedger.find!(subscription_id)\n    return if subscription.cancelled?\n\n    result = BillingCycleProcessor.call(\n      account_id:         subscription.account_id,\n      plan:               subscription.plan_code,\n      amount_cents:       subscription.next_billing_amount_cents\n    )\n\n    if result.success?\n      subscription.update!(status: :active, next_billed_at: result.next_cycle_date)\n      SubscriptionRenewedEvent.publish(subscription)\n    else\n      subscription.update!(status: :past_due)\n      RenewalFailureMailer.notify(subscription).deliver_later\n    end\n  end\nend\n",
    "registered_symbols": [
      {"text": "MembershipLedger",        "label": "INTERNAL_MODEL"},
      {"text": "BillingCycleProcessor",   "label": "INTERNAL_SERVICE"},
      {"text": "SubscriptionRenewedEvent","label": "INTERNAL_EVENT"}
    ],
    "expected_action": "REDACT",
    "expected_utility": "LLM can debug ActiveJob retry semantics and Stripe error handling without seeing proprietary subscription billing logic.",
    "source_note": "Rails ActiveJob + Stripe retry; Interactor gem .call convention; real SaaS billing pattern."
  },
]

existing_ids = {c["id"] for c in cases}
added = sum(1 for c in OS_CASES if c["id"] not in existing_ids)
for c in OS_CASES:
    if c["id"] not in existing_ids:
        cases.append(c)

path.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Added {added} OS cases. Total: {len(cases)}")
