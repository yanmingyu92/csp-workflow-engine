"""
CSP Skills Shared Utilities

Clinical Trial Statistical Programming skill framework.
Provides base classes, validators, and utilities for regulatory compliance.
"""

from .base_skill import BaseCSPSkill, SkillResult, SkillConfig
from .validators import (
    CDISCTermValidator,
    ISO8601DateValidator,
    DomainValidator,
    VariableValidator,
)
from .io_handlers import (
    XPTHandler,
    CSVHandler,
    SAS7BDATHandler,
    DatasetReader,
    DatasetWriter,
)
from .cdisc_utils import (
    DomainStructureChecker,
    ControlledTerminologyLookup,
    SDTMComplianceChecker,
    ADaMComplianceChecker,
)

__all__ = [
    # Base classes
    "BaseCSPSkill",
    "SkillResult",
    "SkillConfig",
    # Validators
    "CDISCTermValidator",
    "ISO8601DateValidator",
    "DomainValidator",
    "VariableValidator",
    # I/O Handlers
    "XPTHandler",
    "CSVHandler",
    "SAS7BDATHandler",
    "DatasetReader",
    "DatasetWriter",
    # CDISC Utilities
    "DomainStructureChecker",
    "ControlledTerminologyLookup",
    "SDTMComplianceChecker",
    "ADaMComplianceChecker",
]

__version__ = "1.0.0"
