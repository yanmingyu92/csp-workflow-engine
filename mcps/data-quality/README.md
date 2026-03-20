# Data Quality MCP

Data Quality MCP server for clinical data integrity checks.

## Overview

This MCP provides tools for comprehensive data quality checks on clinical trial datasets, including referential integrity, date consistency, missing values, and duplicate detection.

## Tools

### check_referential_integrity

Check referential integrity between parent and child datasets.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| parent_dataset | string | Yes | Path to parent dataset |
| child_dataset | string | Yes | Path to child dataset |
| key_variable | string | No | Key variable (default: USUBJID) |

**Returns:**
```json
{
  "status": "PASS",
  "parent_records": 150,
  "child_records": 500,
  "orphan_records": 0,
  "issues": []
}
```

### check_date_consistency

Check date consistency across related records.

### check_missing_values

Analyze missing value patterns in dataset.

**Returns:**
```json
{
  "total_records": 150,
  "variables_checked": 25,
  "issues": [
    {"variable": "AGEU", "missing_count": 5, "missing_percent": 3.3}
  ]
}
```

### check_duplicates

Check for duplicate records.

### check_value_ranges

Check numeric values against expected ranges.

### generate_quality_report

Generate comprehensive data quality report.

## Quality Check Categories

| Check | Description | Severity |
|-------|-------------|----------|
| Referential Integrity | Child records have parent | Error |
| Date Consistency | Logical date sequences | Error/Warning |
| Missing Values | Missing data analysis | Info/Warning |
| Duplicates | Unique key violations | Error |
| Value Ranges | Out-of-range values | Warning |

## Bound Graph Nodes

- `raw-data-validation` - Layer 1
- `data-reconciliation` - Layer 1
- `sdtm-crossdomain-check` - Layer 3
- `adam-traceability-check` - Layer 4

## Configuration

```json
{
  "max_records": 1000000,
  "parallel_checks": true,
  "output_format": "html"
}
```

## Mock Mode

When data quality libraries are not available, the MCP operates in mock mode with simulated check results.
