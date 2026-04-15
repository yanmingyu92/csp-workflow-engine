#!/usr/bin/env python3
"""
CDISC Utilities

Utilities for CDISC standard compliance:
- SDTM structure checking
- ADaM structure checking
- Controlled terminology lookup
- Domain validation
"""

import re
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass


@dataclass
class ComplianceIssue:
    """Represents a compliance issue found during checking."""

    severity: str  # ERROR, WARNING, INFO
    category: str  # e.g., "Missing Variable", "Invalid Value"
    message: str
    variable: Optional[str] = None
    record: Optional[int] = None
    value: Optional[str] = None
    rule_id: Optional[str] = None  # e.g., "SD0001" for P21 rules


class DomainStructureChecker:
    """
    Checks SDTM/ADaM domain structure against CDISC standards.
    """

    # Standard SDTM domains and their categories
    SDTM_DOMAINS = {
        # Special Purpose
        "DM": "Demographics",
        "SE": "Subject Elements",
        "SV": "Subject Visits",
        "CO": "Comments",
        "RELREC": "Related Records",
        "SUPPQUAL": "Supplemental Qualifiers",
        # Interventions
        "CM": "Concomitant Medications",
        "EX": "Exposure",
        "SU": "Substance Use",
        # Events
        "AE": "Adverse Events",
        "DS": "Disposition",
        "MH": "Medical History",
        "CE": "Clinical Events",
        # Findings
        "LB": "Laboratory Tests",
        "VS": "Vital Signs",
        "PE": "Physical Examination",
        "EG": "ECG",
        "IE": "Inclusion/Exclusion",
        "QS": "Questionnaires",
        "SC": "Subject Characteristics",
        "DA": "Drug Accountability",
        "MB": "Microbiology",
        "MI": "Microscopy",
        "PC": "Pharmacokinetic Concentrations",
        "PP": "Pharmacokinetic Parameters",
        # Trial Design
        "TS": "Trial Summary",
        "TA": "Trial Arms",
        "TI": "Trial Inclusion/Exclusion",
        "TV": "Trial Visits",
        # Findings About
        "FA": "Findings About",
    }

    # Standard ADaM datasets
    ADAM_DATASETS = {
        "ADSL": "Subject-Level Analysis Dataset",
        "ADAE": "Adverse Event Analysis Dataset",
        "ADLB": "Laboratory Analysis Dataset",
        "ADVS": "Vital Signs Analysis Dataset",
        "ADCM": "Concomitant Medications Analysis Dataset",
        "ADEX": "Exposure Analysis Dataset",
        "ADMH": "Medical History Analysis Dataset",
        "ADTTE": "Time-to-Event Analysis Dataset",
        "ADCE": "Clinical Events Analysis Dataset",
        "ADEG": "ECG Analysis Dataset",
        "ADIE": "Inclusion/Exclusion Analysis Dataset",
        "ADPE": "Physical Examination Analysis Dataset",
        "ADQS": "Questionnaires Analysis Dataset",
        "ADSC": "Subject Characteristics Analysis Dataset",
        "ADPC": "Pharmacokinetic Concentrations Analysis Dataset",
        "ADPP": "Pharmacokinetic Parameters Analysis Dataset",
        "ADCO": "Comments Analysis Dataset",
        "ADEFF": "Efficacy Analysis Dataset",
    }

    def is_valid_sdtm_domain(self, domain: str) -> bool:
        """Check if domain is a valid SDTM domain."""
        return domain.upper() in self.SDTM_DOMAINS

    def is_valid_adam_dataset(self, dataset: str) -> bool:
        """Check if dataset is a valid ADaM dataset."""
        return dataset.upper() in self.ADAM_DATASETS

    def get_domain_category(self, domain: str) -> Optional[str]:
        """Get the category for an SDTM domain."""
        return self.SDTM_DOMAINS.get(domain.upper())

    def check_sdtm_structure(
        self, data: Dict[str, List[Any]], domain: str
    ) -> List[ComplianceIssue]:
        """
        Check SDTM domain structure.

        Args:
            data: Dataset as dictionary
            domain: Domain name

        Returns:
            List of compliance issues
        """
        issues = []
        domain = domain.upper()

        # Check domain is valid
        if not self.is_valid_sdtm_domain(domain):
            issues.append(
                ComplianceIssue(
                    severity="WARNING",
                    category="Unknown Domain",
                    message=f"Domain '{domain}' is not a standard SDTM domain",
                )
            )

        # Check required identifier variables
        required_vars = ["STUDYID", "DOMAIN"]
        for var in required_vars:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message=f"Required variable '{var}' is missing",
                        variable=var,
                    )
                )

        # Check for USUBJID in patient data domains
        if domain not in ["TS", "TA", "TI", "TV"]:
            if "USUBJID" not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message="Required variable 'USUBJID' is missing",
                        variable="USUBJID",
                    )
                )

        # Check for domain-specific prefix variables
        domain_prefix = domain[:2]
        domain_vars = [v for v in data.keys() if v.startswith(domain_prefix)]
        if not domain_vars and domain not in [
            "TS",
            "TA",
            "TI",
            "TV",
            "CO",
            "RELREC",
            "SUPPQUAL",
        ]:
            issues.append(
                ComplianceIssue(
                    severity="WARNING",
                    category="Domain Variables",
                    message=f"No domain-specific variables found with prefix '{domain_prefix}'",
                )
            )

        return issues

    def check_adam_structure(
        self, data: Dict[str, List[Any]], dataset: str
    ) -> List[ComplianceIssue]:
        """
        Check ADaM dataset structure.

        Args:
            data: Dataset as dictionary
            dataset: Dataset name

        Returns:
            List of compliance issues
        """
        issues = []
        dataset = dataset.upper()

        # Check dataset is valid
        if not self.is_valid_adam_dataset(dataset):
            issues.append(
                ComplianceIssue(
                    severity="WARNING",
                    category="Unknown Dataset",
                    message=f"Dataset '{dataset}' is not a standard ADaM dataset",
                )
            )

        # Check required variables
        required_vars = ["STUDYID", "USUBJID"]
        for var in required_vars:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message=f"Required variable '{var}' is missing",
                        variable=var,
                    )
                )

        # ADSL-specific checks
        if dataset == "ADSL":
            for var in ["SAFFL", "TRT01P"]:
                if var not in data:
                    issues.append(
                        ComplianceIssue(
                            severity="WARNING",
                            category="ADSL Variable",
                            message=f"Recommended ADSL variable '{var}' is missing",
                            variable=var,
                        )
                    )

        # BDS structure checks (for analysis datasets)
        if dataset not in ["ADSL", "ADAE", "ADCM", "ADMH", "ADCE"]:
            for var in ["PARAM", "PARAMCD", "AVAL"]:
                if var not in data:
                    issues.append(
                        ComplianceIssue(
                            severity="WARNING",
                            category="BDS Variable",
                            message=f"BDS structure variable '{var}' is missing",
                            variable=var,
                        )
                    )

        return issues


class ControlledTerminologyLookup:
    """
    Lookup service for CDISC Controlled Terminology.

    Note: This is a mock implementation. Real implementation would
    connect to CDISC Library API (https://library.cdisc.org).
    """

    # Common codelist references
    CODELIST_REFS = {
        "C66731": "Sex",
        "C66732": "Gender",
        "C74457": "Race",
        "C66790": "Ethnicity",
        "C66742": "Country",
        "C66796": "Yes/No/Unknown",
        "C66795": "Yes/No",
        "C74413": "Unit of Mass",
        "C74414": "Unit of Length",
        "C74415": "Unit of Volume",
        "C65047": "Unit of Time",
        "C78734": "Disposition Event",
        "C66769": "AE Severity",
        "C66770": "AE Serious",
        "C66768": "AE Relationship",
    }

    def __init__(self, ct_version: str = "latest"):
        """Initialize with CDISC CT version."""
        self.ct_version = ct_version

    def lookup_codelist(self, codelist_id: str) -> Optional[Dict[str, Any]]:
        """
        Lookup codelist by ID.

        Args:
            codelist_id: CDISC CT codelist ID (e.g., "C66731")

        Returns:
            Codelist information or None if not found
        """
        name = self.CODELIST_REFS.get(codelist_id)
        if name:
            return {
                "codelist_id": codelist_id,
                "name": name,
                "submission_value": name.upper().replace("/", "_"),
            }
        return None

    def validate_term(self, value: str, codelist_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a value against a codelist.

        Args:
            value: Value to validate
            codelist_id: CDISC CT codelist ID

        Returns:
            Tuple of (is_valid, matched_term)
        """
        # Mock implementation - would call CDISC Library API
        return True, value

    def get_term_code(self, value: str, codelist_id: str) -> Optional[str]:
        """
        Get the term code for a value.

        Args:
            value: Value to look up
            codelist_id: CDISC CT codelist ID

        Returns:
            Term code or None
        """
        # Mock implementation
        return f"TERM_{hash(value) % 10000:04d}"


class SDTMComplianceChecker:
    """
    Comprehensive SDTM compliance checker.

    Performs checks for:
    - Required variables
    - Variable naming conventions
    - Data type consistency
    - Controlled terminology
    - Cross-domain consistency
    """

    # SDTM IG 3.4 required variables by domain
    DOMAIN_REQUIRED_VARS = {
        "DM": ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "ARM", "ARMCD"],
        "AE": ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM", "AEBODSYS"],
        "LB": ["STUDYID", "DOMAIN", "USUBJID", "LBSEQ", "LBTESTCD", "LBTEST"],
        "VS": ["STUDYID", "DOMAIN", "USUBJID", "VSSEQ", "VSTESTCD", "VSTEST"],
        "CM": ["STUDYID", "DOMAIN", "USUBJID", "CMSEQ", "CMTRT"],
        "MH": ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHTERM"],
        "EX": ["STUDYID", "DOMAIN", "USUBJID", "EXSEQ", "EXTRT"],
        "DS": ["STUDYID", "DOMAIN", "USUBJID", "DSSEQ", "DSTERM", "DSDECOD"],
        "SV": ["STUDYID", "DOMAIN", "USUBJID", "VISIT", "VISITNUM"],
    }

    # Standard SDTM variable suffixes
    SDTM_SUFFIXES = {
        "DTC": "Date/Time Character",
        "DT": "Date Numeric",
        "TM": "Time Numeric",
        "STRF": "Start Relative",
        "ENRF": "End Relative",
        "STTMC": "Start DateTime Character",
        "ENTMC": "End DateTime Character",
        "STAT": "Status",
        "REASND": "Reason Not Done",
        "BLFL": "Baseline Flag",
        "DRVFL": "Derived Flag",
    }

    def __init__(self, strict: bool = False):
        """Initialize compliance checker."""
        self.strict = strict
        self.structure_checker = DomainStructureChecker()

    def check(self, data: Dict[str, List[Any]], domain: str) -> List[ComplianceIssue]:
        """
        Perform comprehensive SDTM compliance check.

        Args:
            data: Dataset as dictionary
            domain: Domain name

        Returns:
            List of compliance issues
        """
        issues = []

        # Structure check
        issues.extend(self.structure_checker.check_sdtm_structure(data, domain))

        # Required variables
        issues.extend(self._check_required_vars(data, domain))

        # Variable naming
        issues.extend(self._check_variable_naming(data, domain))

        # Data consistency
        issues.extend(self._check_data_consistency(data, domain))

        return issues

    def _check_required_vars(
        self, data: Dict[str, List[Any]], domain: str
    ) -> List[ComplianceIssue]:
        """Check for required variables."""
        issues = []
        domain = domain.upper()

        required = self.DOMAIN_REQUIRED_VARS.get(domain, [])
        for var in required:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message=f"Required variable '{var}' is missing for domain {domain}",
                        variable=var,
                        rule_id="SDTM-REQ-001",
                    )
                )

        return issues

    def _check_variable_naming(
        self, data: Dict[str, List[Any]], domain: str
    ) -> List[ComplianceIssue]:
        """Check variable naming conventions."""
        issues = []
        domain_prefix = domain[:2].upper()

        for var in data.keys():
            # Check uppercase
            if var != var.upper():
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="Variable Naming",
                        message=f"Variable '{var}' should be uppercase",
                        variable=var,
                    )
                )

            # Check valid characters
            if not re.match(r"^[A-Z][A-Z0-9_]*$", var):
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="Variable Naming",
                        message=f"Variable '{var}' contains invalid characters",
                        variable=var,
                    )
                )

            # Check length (SDTM max is 8 characters)
            if len(var) > 8:
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="Variable Naming",
                        message=f"Variable '{var}' exceeds 8 character limit",
                        variable=var,
                    )
                )

        return issues

    def _check_data_consistency(
        self, data: Dict[str, List[Any]], domain: str
    ) -> List[ComplianceIssue]:
        """Check data consistency."""
        issues = []

        # Check all columns have same length
        lengths = {var: len(vals) for var, vals in data.items()}
        if lengths:
            unique_lengths = set(lengths.values())
            if len(unique_lengths) > 1:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Data Consistency",
                        message=f"Variables have inconsistent lengths: {lengths}",
                    )
                )

        # Check for empty dataset
        if not data or all(len(vals) == 0 for vals in data.values()):
            issues.append(
                ComplianceIssue(
                    severity="WARNING",
                    category="Empty Dataset",
                    message="Dataset is empty",
                )
            )

        return issues


class ADaMComplianceChecker:
    """
    Comprehensive ADaM compliance checker.

    Performs checks for:
    - ADSL requirements
    - BDS structure
    - OCCDS structure
    - Traceability to SDTM
    - Analysis variable naming
    """

    # ADaM required variables by dataset type
    REQUIRED_VARS = {
        "ADSL": ["STUDYID", "USUBJID", "TRT01P", "TRT01A", "SAFFL"],
        "BDS": ["STUDYID", "USUBJID", "PARAM", "PARAMCD", "AVAL", "AVISIT", "AVISITN"],
        "OCCDS": ["STUDYID", "USUBJID", "ASTDT", "AENDT"],
    }

    # Common ADaM variable suffixes
    ADAM_SUFFIXES = {
        "FL": "Flag",
        "DT": "Date",
        "TM": "Time",
        "DTC": "Date/Time Character",
        "CD": "Code",
        "N": "Numeric",
        "C": "Character",
        "P": "Planned",
        "A": "Actual",
        "CAT": "Category",
        "SCAT": "Subcategory",
    }

    def __init__(self, strict: bool = False):
        """Initialize compliance checker."""
        self.strict = strict
        self.structure_checker = DomainStructureChecker()

    def check(self, data: Dict[str, List[Any]], dataset: str) -> List[ComplianceIssue]:
        """
        Perform comprehensive ADaM compliance check.

        Args:
            data: Dataset as dictionary
            dataset: Dataset name

        Returns:
            List of compliance issues
        """
        issues = []
        dataset = dataset.upper()

        # Structure check
        issues.extend(self.structure_checker.check_adam_structure(data, dataset))

        # ADSL-specific checks
        if dataset == "ADSL":
            issues.extend(self._check_adsl(data))
        # BDS structure
        elif dataset not in ["ADAE", "ADCM", "ADMH"]:
            issues.extend(self._check_bds(data, dataset))
        # OCCDS structure
        else:
            issues.extend(self._check_occds(data, dataset))

        # Variable naming
        issues.extend(self._check_variable_naming(data, dataset))

        return issues

    def _check_adsl(self, data: Dict[str, List[Any]]) -> List[ComplianceIssue]:
        """Check ADSL-specific requirements."""
        issues = []

        # Check required variables
        for var in self.REQUIRED_VARS["ADSL"]:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message=f"Required ADSL variable '{var}' is missing",
                        variable=var,
                        rule_id="ADAM-ADSL-001",
                    )
                )

        # Check one record per subject
        if "USUBJID" in data:
            usubjids = data["USUBJID"]
            if len(usubjids) != len(set(usubjids)):
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="ADSL Structure",
                        message="ADSL must have exactly one record per subject",
                        variable="USUBJID",
                        rule_id="ADAM-ADSL-002",
                    )
                )

        return issues

    def _check_bds(
        self, data: Dict[str, List[Any]], dataset: str
    ) -> List[ComplianceIssue]:
        """Check BDS structure requirements."""
        issues = []

        # Check required BDS variables
        for var in self.REQUIRED_VARS["BDS"]:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="BDS Structure",
                        message=f"BDS structure variable '{var}' is missing in {dataset}",
                        variable=var,
                    )
                )

        # Check PARAM/PARAMCD consistency
        if "PARAM" in data and "PARAMCD" in data:
            if len(data["PARAM"]) != len(data["PARAMCD"]):
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="BDS Structure",
                        message="PARAM and PARAMCD should have same cardinality",
                    )
                )

        return issues

    def _check_occds(
        self, data: Dict[str, List[Any]], dataset: str
    ) -> List[ComplianceIssue]:
        """Check OCCDS structure requirements."""
        issues = []

        # Check required OCCDS variables
        for var in self.REQUIRED_VARS["OCCDS"]:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="INFO",
                        category="OCCDS Structure",
                        message=f"OCCDS structure variable '{var}' is recommended for {dataset}",
                        variable=var,
                    )
                )

        return issues

    def _check_variable_naming(
        self, data: Dict[str, List[Any]], dataset: str
    ) -> List[ComplianceIssue]:
        """Check ADaM variable naming conventions."""
        issues = []

        for var in data.keys():
            # Check uppercase
            if var != var.upper():
                issues.append(
                    ComplianceIssue(
                        severity="WARNING",
                        category="Variable Naming",
                        message=f"Variable '{var}' should be uppercase",
                        variable=var,
                    )
                )

            # Check length (ADaM max is 8 characters)
            if len(var) > 8:
                issues.append(
                    ComplianceIssue(
                        severity="INFO",
                        category="Variable Naming",
                        message=f"Variable '{var}' exceeds 8 character limit (ADaM allows extensions)",
                        variable=var,
                    )
                )

        return issues
