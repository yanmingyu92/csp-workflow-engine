# P21 Validator MCP

Pinnacle 21 validation MCP server for clinical trial data compliance.

## Overview

This MCP provides tools for validating SDTM, ADaM, and Define-XML datasets against FDA conformance rules using Pinnacle 21 Community or Enterprise.

## Tools

### validate_sdtm

Validate SDTM datasets against FDA conformance rules.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| datasets_path | string | Yes | Path to SDTM datasets directory or XPT file |
| config_path | string | No | Path to P21 configuration XML |
| standard_version | string | No | SDTM IG version (default: "3.4") |

**Returns:**
```json
{
  "status": "PASS|FAIL",
  "error_count": 0,
  "warning_count": 5,
  "report_path": "reports/p21-sdtm-report.xlsx"
}
```

### validate_adam

Validate ADaM datasets against FDA conformance rules.

### validate_define

Validate Define-XML file against CDISC specification.

### get_issues

Get categorized list of validation issues.

### generate_report

Generate validation report in XLSX, HTML, or JSON format.

## Configuration

Set environment variables:

```bash
export P21_CLI_PATH=/path/to/p21-cli
export JAVA_PATH=/path/to/java
```

## Bound Graph Nodes

- `p21-sdtm-validation` - Layer 3
- `p21-adam-validation` - Layer 4
- `define-xml-validation` - Layer 6
- `esub-final-validation` - Layer 6

## Mock Mode

When P21 CLI is not available, the MCP operates in mock mode, returning simulated validation results for testing and development.
