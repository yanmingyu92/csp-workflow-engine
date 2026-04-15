#!/usr/bin/env python3
"""
CSP Validators

Validation utilities for clinical trial data:
- CDISC Controlled Terminology validation
- ISO 8601 date format validation
- Domain structure validation
- Variable type and constraint validation
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    message: str
    details: List[str] = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


class CDISCTermValidator:
    """
    Validates values against CDISC Controlled Terminology.

    Note: This is a mock implementation. Real implementation would
    connect to CDISC Library API or local CT codelists.
    """

    # Common CDISC CT codelists (subset for demonstration)
    CDISC_CT = {
        # Sex codes
        "sex": {"M", "F", "U", "UNDIFFERENTIATED"},
        # Gender codes
        "gender": {"M", "F", "UNKNOWN", "UNDIFFERENTIATED"},
        # Race codes
        "race": {
            "AMERICAN INDIAN OR ALASKA NATIVE",
            "ASIAN",
            "BLACK OR AFRICAN AMERICAN",
            "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
            "WHITE",
            "MULTIPLE",
            "OTHER",
            "UNKNOWN",
        },
        # Ethnicity codes
        "ethnicity": {
            "HISPANIC OR LATINO",
            "NOT HISPANIC OR LATINO",
            "UNKNOWN",
        },
        # Yes/No/Unknown
        "ynu": {"Y", "N", "U"},
        # Yes/No
        "yn": {"Y", "N"},
        # Country codes (ISO 3166-1 alpha-2 subset)
        "country": {"USA", "CAN", "GBR", "DEU", "FRA", "JPN", "CHN", "AUS"},
        # Disposition status
        "eosstt": {"COMPLETED", "DISCONTINUED", "ONGOING"},
        # Common units
        "unit_mass": {"kg", "g", "mg", "lb"},
        "unit_length": {"cm", "m", "in", "ft"},
        "unit_volume": {"mL", "L"},
        # AE severity
        "aesev": {"MILD", "MODERATE", "SEVERE"},
        # AE seriousness
        "aeser": {"Y", "N"},
        # AE relationship
        "aerel": {"RELATED", "NOT RELATED", "UNKNOWN"},
        # AE outcome
        "aeout": {
            "RECOVERED/RESOLVED",
            "RECOVERING/RESOLVING",
            "NOT RECOVERED/NOT RESOLVED",
            "RECOVERED/RESOLVED WITH SEQUELAE",
            "FATAL",
            "UNKNOWN",
        },
    }

    def __init__(self, ct_version: str = "latest"):
        """Initialize validator with CDISC CT version."""
        self.ct_version = ct_version
        self._custom_codelists: Dict[str, set] = {}

    def register_codelist(self, name: str, values: set):
        """Register a custom codelist."""
        self._custom_codelists[name] = values

    def validate(
        self, value: str, codelist_name: str, case_sensitive: bool = False
    ) -> ValidationResult:
        """
        Validate a value against a CDISC codelist.

        Args:
            value: The value to validate
            codelist_name: Name of the codelist
            case_sensitive: Whether comparison should be case-sensitive

        Returns:
            ValidationResult with validity status and message
        """
        # Check custom codelists first
        codelist = self._custom_codelists.get(codelist_name)
        if codelist is None:
            codelist = self.CDISC_CT.get(codelist_name)

        if codelist is None:
            return ValidationResult(
                is_valid=False,
                message=f"Unknown codelist: {codelist_name}",
            )

        check_value = value if case_sensitive else value.upper()
        check_codelist = codelist if case_sensitive else {v.upper() for v in codelist}

        is_valid = check_value in check_codelist

        if is_valid:
            return ValidationResult(
                is_valid=True,
                message=f"Value '{value}' is valid for codelist '{codelist_name}'",
            )
        else:
            return ValidationResult(
                is_valid=False,
                message=f"Value '{value}' is not in codelist '{codelist_name}'",
                details=[f"Valid values: {', '.join(sorted(codelist))}"],
            )


class ISO8601DateValidator:
    """
    Validates ISO 8601 date/datetime formats.

    Supports:
    - Date: YYYY-MM-DD
    - DateTime: YYYY-MM-DDThh:mm:ss
    - DateTime with TZ: YYYY-MM-DDThh:mm:ss+hh:mm
    - Partial dates: YYYY-MM, YYYY
    - Duration: P[n]Y[n]M[n]DT[n]H[n]M[n]S
    """

    # ISO 8601 patterns
    DATE_PATTERN = re.compile(r"^(\d{4})(-(\d{2})(-(\d{2}))?)?$")
    DATETIME_PATTERN = re.compile(
        r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?"
        r"(Z|([+-])(\d{2}):(\d{2}))?$"
    )
    DURATION_PATTERN = re.compile(
        r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?"
        r"(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
    )
    PARTIAL_DATETIME_PATTERN = re.compile(
        r"^(\d{4})(-(\d{2})(-(\d{2})(T(\d{2})(:(\d{2})(:(\d{2}))?)?)?)?)?$"
    )

    def validate(self, value: str, allow_partial: bool = True) -> ValidationResult:
        """
        Validate an ISO 8601 date/datetime string.

        Args:
            value: The date string to validate
            allow_partial: Whether to allow partial dates (YYYY-MM, YYYY)

        Returns:
            ValidationResult with validity status
        """
        if not value:
            return ValidationResult(
                is_valid=False,
                message="Empty date value",
            )

        # Try full datetime
        if self.DATETIME_PATTERN.match(value):
            return self._validate_datetime_components(value)

        # Try duration
        if value.startswith("P") and self.DURATION_PATTERN.match(value):
            return ValidationResult(
                is_valid=True,
                message=f"Valid ISO 8601 duration: {value}",
            )

        # Try date (including partial)
        if self.DATE_PATTERN.match(value):
            if allow_partial or value.count("-") == 2:
                return self._validate_date_components(value)
            else:
                return ValidationResult(
                    is_valid=False,
                    message="Partial dates not allowed",
                )

        # Try partial datetime
        if allow_partial and self.PARTIAL_DATETIME_PATTERN.match(value):
            return ValidationResult(
                is_valid=True,
                message=f"Valid partial ISO 8601 datetime: {value}",
            )

        return ValidationResult(
            is_valid=False,
            message=f"Invalid ISO 8601 format: {value}",
            details=[
                "Expected formats:",
                "  Date: YYYY-MM-DD",
                "  DateTime: YYYY-MM-DDThh:mm:ss",
                "  Duration: P[n]Y[n]M[n]DT[n]H[n]M[n]S",
            ],
        )

    def _validate_date_components(self, value: str) -> ValidationResult:
        """Validate date components are within valid ranges."""
        parts = value.split("-")

        try:
            year = int(parts[0])
            if len(parts) > 1:
                month = int(parts[1])
                if month < 1 or month > 12:
                    return ValidationResult(
                        is_valid=False,
                        message=f"Invalid month: {month}",
                    )
            if len(parts) > 2:
                day = int(parts[2])
                if day < 1 or day > 31:
                    return ValidationResult(
                        is_valid=False,
                        message=f"Invalid day: {day}",
                    )

            return ValidationResult(
                is_valid=True,
                message=f"Valid ISO 8601 date: {value}",
            )
        except ValueError as e:
            return ValidationResult(
                is_valid=False,
                message=f"Invalid date components: {e}",
            )

    def _validate_datetime_components(self, value: str) -> ValidationResult:
        """Validate datetime components are within valid ranges."""
        # Extract and validate time components
        match = self.DATETIME_PATTERN.match(value)
        if not match:
            return ValidationResult(
                is_valid=False,
                message=f"Invalid datetime format: {value}",
            )

        try:
            hour = int(match.group(4))
            minute = int(match.group(5))
            second = int(match.group(6))

            if hour > 23:
                return ValidationResult(
                    is_valid=False,
                    message=f"Invalid hour: {hour}",
                )
            if minute > 59:
                return ValidationResult(
                    is_valid=False,
                    message=f"Invalid minute: {minute}",
                )
            if second > 59:
                return ValidationResult(
                    is_valid=False,
                    message=f"Invalid second: {second}",
                )

            return ValidationResult(
                is_valid=True,
                message=f"Valid ISO 8601 datetime: {value}",
            )
        except (ValueError, IndexError) as e:
            return ValidationResult(
                is_valid=False,
                message=f"Invalid datetime components: {e}",
            )


class DomainValidator:
    """
    Validates SDTM/ADaM domain structure.

    Checks:
    - Required variables present
    - Variable naming conventions
    - Key variable uniqueness
    """

    # SDTM domain key variables
    SDTM_KEYS = {
        "DM": ["STUDYID", "DOMAIN", "USUBJID"],
        "AE": ["STUDYID", "DOMAIN", "USUBJID", "AESEQ"],
        "LB": ["STUDYID", "DOMAIN", "USUBJID", "LBSEQ"],
        "VS": ["STUDYID", "DOMAIN", "USUBJID", "VSSEQ"],
        "CM": ["STUDYID", "DOMAIN", "USUBJID", "CMSEQ"],
        "MH": ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ"],
        "EX": ["STUDYID", "DOMAIN", "USUBJID", "EXSEQ"],
        "DS": ["STUDYID", "DOMAIN", "USUBJID", "DSSEQ"],
        "SV": ["STUDYID", "DOMAIN", "USUBJID", "VISITNUM"],
        # Trial design
        "TS": ["STUDYID", "TSPARMCD"],
        "TA": ["STUDYID", "ARMCD"],
        "TI": ["STUDYID", "IETESTCD"],
        "TV": ["STUDYID", "VISITNUM"],
    }

    # ADaM domain key variables
    ADAM_KEYS = {
        "ADSL": ["STUDYID", "USUBJID"],
        "ADAE": ["STUDYID", "USUBJID", "ASTDT", "AETERM"],
        "ADLB": ["STUDYID", "USUBJID", "PARAMCD", "AVISITN"],
        "ADTTE": ["STUDYID", "USUBJID", "PARAMCD"],
    }

    def __init__(self, standard: str = "sdtm"):
        """Initialize validator for SDTM or ADaM."""
        self.standard = standard.lower()

    def validate_structure(
        self, data: Dict[str, List[Any]], domain: str
    ) -> ValidationResult:
        """
        Validate domain structure.

        Args:
            data: Dictionary with variable names as keys
            domain: Domain name (DM, AE, ADSL, etc.)

        Returns:
            ValidationResult with validity status
        """
        errors = []
        warnings = []

        # Get required keys for domain
        if self.standard == "sdtm":
            required_keys = self.SDTM_KEYS.get(domain, [])
        else:
            required_keys = self.ADAM_KEYS.get(domain.upper(), [])

        if not required_keys:
            warnings.append(f"Unknown domain '{domain}' - using standard checks")
            required_keys = (
                ["STUDYID", "USUBJID"]
                if self.standard != "sdtm"
                else ["STUDYID", "DOMAIN", "USUBJID"]
            )

        # Check required variables
        for key in required_keys:
            if key not in data:
                errors.append(f"Missing required variable: {key}")
            elif not data[key]:
                errors.append(f"Required variable is empty: {key}")

        # Check for -- prefix variables in SDTM
        if self.standard == "sdtm":
            domain_vars = [v for v in data.keys() if v.startswith(domain.upper()[:2])]
            if not domain_vars and domain.upper() not in [
                "TS",
                "TA",
                "TI",
                "TV",
                "SUPPQUAL",
                "RELREC",
            ]:
                warnings.append(f"No domain-specific variables found for {domain}")

        # Check variable naming
        for var in data.keys():
            if not re.match(r"^[A-Z][A-Z0-9_]*$", var):
                warnings.append(f"Non-standard variable name: {var}")

        if errors:
            return ValidationResult(
                is_valid=False,
                message=f"Domain {domain} validation failed",
                details=errors + warnings,
            )

        if warnings:
            return ValidationResult(
                is_valid=True,
                message=f"Domain {domain} validation passed with warnings",
                details=warnings,
            )

        return ValidationResult(
            is_valid=True,
            message=f"Domain {domain} validation passed",
        )

    def validate_keys_unique(
        self, data: Dict[str, List[Any]], domain: str
    ) -> ValidationResult:
        """
        Validate that key variables form unique combinations.

        Args:
            data: Dictionary with variable names as keys
            domain: Domain name

        Returns:
            ValidationResult indicating if keys are unique
        """
        if not data:
            return ValidationResult(
                is_valid=False,
                message="Empty dataset",
            )

        # Get key variables
        if self.standard == "sdtm":
            key_vars = self.SDTM_KEYS.get(domain, ["USUBJID"])
        else:
            key_vars = self.ADAM_KEYS.get(domain.upper(), ["USUBJID"])

        # Build key combinations
        n_records = len(list(data.values())[0]) if data else 0
        key_combos = set()
        duplicates = []

        for i in range(n_records):
            combo = tuple(data.get(var, [None])[i] for var in key_vars)
            if combo in key_combos:
                duplicates.append(f"Duplicate key at record {i + 1}: {combo}")
            key_combos.add(combo)

        if duplicates:
            return ValidationResult(
                is_valid=False,
                message=f"Duplicate keys found in {domain}",
                details=duplicates[:10],  # Limit to first 10
            )

        return ValidationResult(
            is_valid=True,
            message=f"All keys unique in {domain} ({n_records} records)",
        )


class VariableValidator:
    """
    Validates individual variable values.

    Checks:
    - Data type consistency
    - Length constraints
    - Value ranges
    - Missing value patterns
    """

    def __init__(self, strict: bool = False):
        """Initialize validator."""
        self.strict = strict

    def validate_type(self, values: List[Any], expected_type: str) -> ValidationResult:
        """
        Validate that all values match expected type.

        Args:
            values: List of values to check
            expected_type: Expected type (string, numeric, date, datetime)

        Returns:
            ValidationResult
        """
        errors = []

        for i, val in enumerate(values):
            if val is None or val == "":
                continue  # Skip missing values

            if expected_type == "numeric":
                try:
                    float(val)
                except (ValueError, TypeError):
                    errors.append(f"Record {i + 1}: Non-numeric value '{val}'")

            elif expected_type == "string":
                if not isinstance(val, str):
                    errors.append(f"Record {i + 1}: Non-string value '{val}'")

            elif expected_type == "date":
                date_validator = ISO8601DateValidator()
                result = date_validator.validate(str(val))
                if not result.is_valid:
                    errors.append(f"Record {i + 1}: Invalid date '{val}'")

        if errors:
            return ValidationResult(
                is_valid=False,
                message=f"Type validation failed for {expected_type}",
                details=errors[:20],
            )

        return ValidationResult(
            is_valid=True,
            message=f"All values match type {expected_type}",
        )

    def validate_length(self, values: List[Any], max_length: int) -> ValidationResult:
        """
        Validate that string values don't exceed max length.

        Args:
            values: List of values to check
            max_length: Maximum allowed length

        Returns:
            ValidationResult
        """
        errors = []

        for i, val in enumerate(values):
            if val is None or val == "":
                continue

            str_val = str(val)
            if len(str_val) > max_length:
                errors.append(
                    f"Record {i + 1}: Value exceeds {max_length} chars "
                    f"(actual: {len(str_val)}): '{str_val[:50]}...'"
                )

        if errors:
            return ValidationResult(
                is_valid=False,
                message=f"Length validation failed (max: {max_length})",
                details=errors[:20],
            )

        return ValidationResult(
            is_valid=True,
            message=f"All values within length limit ({max_length})",
        )

    def validate_range(
        self,
        values: List[Any],
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> ValidationResult:
        """
        Validate that numeric values are within range.

        Args:
            values: List of values to check
            min_val: Minimum allowed value (optional)
            max_val: Maximum allowed value (optional)

        Returns:
            ValidationResult
        """
        errors = []

        for i, val in enumerate(values):
            if val is None or val == "":
                continue

            try:
                num_val = float(val)

                if min_val is not None and num_val < min_val:
                    errors.append(
                        f"Record {i + 1}: Value {num_val} below minimum {min_val}"
                    )

                if max_val is not None and num_val > max_val:
                    errors.append(
                        f"Record {i + 1}: Value {num_val} above maximum {max_val}"
                    )

            except (ValueError, TypeError):
                continue  # Type validation handles this

        if errors:
            return ValidationResult(
                is_valid=False,
                message=f"Range validation failed",
                details=errors[:20],
            )

        return ValidationResult(
            is_valid=True,
            message="All values within valid range",
        )

    def check_missing(
        self, values: List[Any], allowed_missing: bool = True
    ) -> ValidationResult:
        """
        Check for missing values.

        Args:
            values: List of values to check
            allowed_missing: Whether missing values are allowed

        Returns:
            ValidationResult with missing value statistics
        """
        missing_count = sum(1 for v in values if v is None or v == "")
        total = len(values)

        if not allowed_missing and missing_count > 0:
            return ValidationResult(
                is_valid=False,
                message=f"Missing values not allowed, found {missing_count}",
                details=[
                    f"Missing: {missing_count}/{total} ({100*missing_count/total:.1f}%)"
                ],
            )

        return ValidationResult(
            is_valid=True,
            message=f"Missing value check passed",
            details=(
                [f"Missing: {missing_count}/{total} ({100*missing_count/total:.1f}%)"]
                if missing_count > 0
                else None
            ),
        )
