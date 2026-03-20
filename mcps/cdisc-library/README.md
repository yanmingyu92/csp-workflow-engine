# CDISC Library MCP

CDISC Library MCP server for controlled terminology and standard lookups.

## Overview

This MCP provides tools for accessing CDISC Library API to lookup controlled terminology, domain structures, and standard metadata.

## Tools

### lookup_ct

Lookup CDISC controlled terminology codelist by ID.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| codelist_id | string | Yes | CDISC CT codelist ID (e.g., C66731) |
| ct_version | string | No | CT version (default: latest) |

**Returns:**
```json
{
  "codelist_id": "C66731",
  "name": "Sex",
  "extensible": false,
  "terms": [
    {"code": "C16576", "preferred_term": "M", "synonyms": ["Male"]},
    {"code": "C16577", "preferred_term": "F", "synonyms": ["Female"]}
  ]
}
```

### validate_ct_value

Validate a value against controlled terminology.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| value | string | Yes | Value to validate |
| codelist_id | string | Yes | CDISC CT codelist ID |
| ct_version | string | No | CT version |

### get_domain_structure

Get SDTM/ADaM domain structure.

### search_ct

Search controlled terminology by keyword.

### get_variable_metadata

Get metadata for a specific variable.

## Common Codelist IDs

| ID | Name | Standard |
|----|------|----------|
| C66731 | Sex | SDTM |
| C74457 | Race | SDTM |
| C66790 | Ethnicity | SDTM |
| C66742 | Country | SDTM |
| C66796 | Yes/No/Unknown | SDTM |
| C78734 | Disposition Event | SDTM |
| C66769 | AE Severity | SDTM |

## Configuration

Set the CDISC Library API key:

```bash
export CDISC_LIBRARY_API_KEY=your-api-key
```

## Bound Graph Nodes

- `spec-creation` - Layer 0
- `crf-validation` - Layer 1
- `sdtm-dm-mapping` - Layer 2
- `sdtm-ae-mapping` - Layer 2
- `sdtm-lb-mapping` - Layer 2
- `sdtm-trial-design` - Layer 2

## Mock Mode

When API key is not configured, the MCP operates in mock mode with common codelists pre-populated.
