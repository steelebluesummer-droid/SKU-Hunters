# Schema 模块 — 圆桌会议全部输入输出契约
# 证据引用契约：所有 Agent 输出必须绑定 EvidenceRef

from .brief import Brief, BudgetRange, Weights, WeightTemplate
from .challenge import ChallengeRecord, ChallengeStance
from .evidence import Confidence, EvidenceMixin, EvidenceRef
from .feature import FeatureMatrix, TrendItem
from .gtm import CountryPlan, GTMPlan
from .ip_assessment import IPAssessment, IPCandidate
from .pricing import PricePoint, PricingComparison
from .proposal import ProductProposal, ProposalSet, SourceRef
from .recommendation import Decision, ProjectRecommendation
from .retro import DimensionGap, RetroReport
from .review import ConflictRecord, ConflictType, ReviewIssue, ReviewResult
from .scoring import DimensionScore, OpportunityScore, RiskWarning
from .sentiment import PainPoint, SentimentStat, UserSentiment
from .swot import SWOTAnalysis, SWOTItem
from .testcase import BacktestCase, BacktestSet, Outcome

__all__ = [
    "BacktestCase",
    "BacktestSet",
    "Brief",
    "BudgetRange",
    "ChallengeRecord",
    "ChallengeStance",
    "Confidence",
    "ConflictRecord",
    "ConflictType",
    "CountryPlan",
    "Decision",
    "DimensionGap",
    "DimensionScore",
    "EvidenceMixin",
    "EvidenceRef",
    "FeatureMatrix",
    "GTMPlan",
    "IPAssessment",
    "IPCandidate",
    "OpportunityScore",
    "Outcome",
    "PainPoint",
    "PricePoint",
    "PricingComparison",
    "ProductProposal",
    "ProjectRecommendation",
    "ProposalSet",
    "RetroReport",
    "ReviewIssue",
    "ReviewResult",
    "RiskWarning",
    "SWOTAnalysis",
    "SWOTItem",
    "SentimentStat",
    "SourceRef",
    "TrendItem",
    "UserSentiment",
    "WeightTemplate",
    "Weights",
]
