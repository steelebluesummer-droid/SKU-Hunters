# Schema 模块 — 圆桌会议全部输入输出契约
# 证据引用契约：所有 Agent 输出必须绑定 EvidenceRef

from .brief import Brief, BudgetRange, Weights, WeightTemplate
from .evidence import Confidence, EvidenceMixin, EvidenceRef
from .feature import FeatureMatrix, TrendItem
from .gtm import CountryPlan, GTMPlan
from .ip_assessment import IPAssessment, IPCandidate
from .pricing import PricePoint, PricingComparison
from .proposal import ProductProposal, ProposalSet, SourceRef
from .retro import DimensionGap, RetroReport
from .review import ConflictRecord, ConflictType, ReviewIssue, ReviewResult
from .scoring import DimensionScore, OpportunityScore, RiskWarning
from .sentiment import PainPoint, SentimentStat, UserSentiment
from .swot import SWOTAnalysis, SWOTItem
from .testcase import BacktestCase, BacktestSet, Outcome

__all__ = [
    "Brief", "BudgetRange", "Weights", "WeightTemplate",
    "Confidence", "EvidenceMixin", "EvidenceRef",
    "FeatureMatrix", "TrendItem",
    "CountryPlan", "GTMPlan",
    "IPAssessment", "IPCandidate",
    "PricePoint", "PricingComparison",
    "ProductProposal", "ProposalSet", "SourceRef",
    "DimensionGap", "RetroReport",
    "ConflictRecord", "ConflictType", "ReviewIssue", "ReviewResult",
    "DimensionScore", "OpportunityScore", "RiskWarning",
    "PainPoint", "SentimentStat", "UserSentiment",
    "SWOTAnalysis", "SWOTItem",
    "BacktestCase", "BacktestSet", "Outcome",
]
