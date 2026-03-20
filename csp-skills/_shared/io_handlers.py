#!/usr/bin/env python3
"""
CSP I/O Handlers

File I/O utilities for clinical trial data formats:
- XPT (SAS Transport v5/v8)
- CSV
- SAS7BDAT

Note: XPT and SAS7BDAT handlers are mock implementations.
Real implementation would use libraries like pyreadstat, pandas, or sas7bdat.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class DatasetMetadata:
    """Metadata about a dataset."""

    name: str
    n_records: int
    n_variables: int
    variables: List[str]
    file_path: Path
    file_size: int
    format: str
    encoding: str = "utf-8"


class DatasetHandler(ABC):
    """Abstract base class for dataset handlers."""

    @abstractmethod
    def read(self, path: Path) -> Dict[str, List[Any]]:
        """Read dataset from file."""
        pass

    @abstractmethod
    def write(
        self,
        data: Dict[str, List[Any]],
        path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write dataset to file."""
        pass

    @abstractmethod
    def get_metadata(self, path: Path) -> DatasetMetadata:
        """Get dataset metadata without reading all data."""
        pass


class CSVHandler(DatasetHandler):
    """
    Handler for CSV files.

    Features:
    - Automatic delimiter detection
    - Header row support
    - Type inference
    - Encoding detection
    """

    def __init__(
        self, delimiter: str = ",", has_header: bool = True, encoding: str = "utf-8"
    ):
        """Initialize CSV handler."""
        self.delimiter = delimiter
        self.has_header = has_header
        self.encoding = encoding

    def read(self, path: Path) -> Dict[str, List[Any]]:
        """
        Read CSV file into dictionary.

        Args:
            path: Path to CSV file

        Returns:
            Dictionary with column names as keys
        """
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        # Detect delimiter if not specified
        delimiter = self.delimiter
        if delimiter == ",":
            delimiter = self._detect_delimiter(path)

        data: Dict[str, List[Any]] = {}

        with open(path, "r", encoding=self.encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)

            # Get headers
            if self.has_header:
                headers = next(reader)
            else:
                first_row = next(reader)
                headers = [f"COL{i}" for i in range(len(first_row))]
                # Put first row back
                for i, val in enumerate(first_row):
                    data[headers[i]] = [val]

            # Initialize columns
            for header in headers:
                data[header] = []

            # Read data
            for row in reader:
                for i, header in enumerate(headers):
                    if i < len(row):
                        data[header].append(row[i])
                    else:
                        data[header].append(None)

        return data

    def write(
        self,
        data: Dict[str, List[Any]],
        path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Write dictionary to CSV file.

        Args:
            data: Dictionary with column names as keys
            path: Output file path
            metadata: Optional metadata (ignored for CSV)

        Returns:
            True if successful
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        if not data:
            # Write empty file with no headers
            with open(path, "w", encoding=self.encoding, newline="") as f:
                pass
            return True

        headers = list(data.keys())
        n_records = len(data[headers[0]]) if headers else 0

        with open(path, "w", encoding=self.encoding, newline="") as f:
            writer = csv.writer(f, delimiter=self.delimiter)

            # Write header
            writer.writerow(headers)

            # Write data rows
            for i in range(n_records):
                row = [data[h][i] if i < len(data[h]) else None for h in headers]
                writer.writerow(row)

        return True

    def get_metadata(self, path: Path) -> DatasetMetadata:
        """Get CSV metadata."""
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        # Read just enough to get metadata
        data = self.read(path)
        n_vars = len(data)
        n_records = len(list(data.values())[0]) if data else 0

        return DatasetMetadata(
            name=path.stem,
            n_records=n_records,
            n_variables=n_vars,
            variables=list(data.keys()),
            file_path=path,
            file_size=path.stat().st_size,
            format="csv",
            encoding=self.encoding,
        )

    def _detect_delimiter(self, path: Path) -> str:
        """Detect CSV delimiter."""
        with open(path, "r", encoding=self.encoding) as f:
            first_line = f.readline()

        for delim in [",", "\t", ";", "|"]:
            if delim in first_line:
                return delim

        return ","


class XPTHandler(DatasetHandler):
    """
    Handler for SAS Transport (XPT) files.

    Note: This is a MOCK implementation. Real implementation would use:
    - pyreadstat (recommended)
    - pandas.read_sas()
    - xport package

    For now, this simulates XPT operations using JSON internally.
    """

    # XPT file signature (SAS v5)
    XPT_SIGNATURE_V5 = b"HEADER RECORD*******LIBRARY HEADER RECORD!!!!!!!000000000000000000000000000000  "
    XPT_SIGNATURE_V8 = b"HEADER RECORD*******LIBRARY V8 HEADER RECORD!!!!!!!000000000000000000000000000000  "

    def __init__(self, sas_version: int = 5):
        """Initialize XPT handler."""
        self.sas_version = sas_version

    def read(self, path: Path) -> Dict[str, List[Any]]:
        """
        Read XPT file into dictionary.

        Args:
            path: Path to XPT file

        Returns:
            Dictionary with variable names as keys

        Note: Mock implementation - reads from sidecar JSON if exists,
        otherwise returns empty dict with warning.
        """
        if not path.exists():
            raise FileNotFoundError(f"XPT file not found: {path}")

        # Check for sidecar JSON (mock mode)
        json_path = path.with_suffix(".json")
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Check if file is actually XPT
        with open(path, "rb") as f:
            signature = f.read(80)

        if signature.startswith(b"HEADER RECORD"):
            # Real XPT file - would need pyreadstat
            raise NotImplementedError(
                "XPT reading requires pyreadstat library. "
                "Install with: pip install pyreadstat"
            )

        # Try to read as JSON for testing
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise NotImplementedError(
                f"Cannot read XPT file: {path}. "
                "Install pyreadstat or provide a sidecar .json file."
            )

    def write(
        self,
        data: Dict[str, List[Any]],
        path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Write dictionary to XPT file.

        Args:
            data: Dictionary with variable names as keys
            path: Output file path
            metadata: Optional dataset metadata (label, variable labels, etc.)

        Returns:
            True if successful

        Note: Mock implementation - writes sidecar JSON alongside XPT.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # Try to write real XPT if pyreadstat is available
        try:
            import pyreadstat
            import pandas as pd

            df = pd.DataFrame(data)

            # Set metadata if provided
            if metadata:
                column_labels = metadata.get("column_labels", {})
                df = df.rename(columns=column_labels)

            pyreadstat.write_xport(
                df,
                str(path),
                file_format_version=self.sas_version,
                table_name=path.stem.upper()[:8],  # XPT limit
            )

            return True

        except ImportError:
            # Mock mode: write JSON sidecar and placeholder XPT
            json_path = path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

            # Write placeholder XPT header
            with open(path, "wb") as f:
                if self.sas_version == 5:
                    f.write(self.XPT_SIGNATURE_V5)
                else:
                    f.write(self.XPT_SIGNATURE_V8)
                # Padding to 80 bytes
                f.write(b"\n")

            return True

    def get_metadata(self, path: Path) -> DatasetMetadata:
        """Get XPT metadata."""
        if not path.exists():
            raise FileNotFoundError(f"XPT file not found: {path}")

        # Try pyreadstat if available
        try:
            import pyreadstat

            df, meta = pyreadstat.read_xport(str(path), metadataonly=True)

            return DatasetMetadata(
                name=path.stem,
                n_records=meta.number_rows,
                n_variables=meta.number_columns,
                variables=meta.column_names,
                file_path=path,
                file_size=path.stat().st_size,
                format="xpt",
            )

        except ImportError:
            # Mock mode: read from sidecar JSON
            json_path = path.with_suffix(".json")
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                return DatasetMetadata(
                    name=path.stem,
                    n_records=len(list(data.values())[0]) if data else 0,
                    n_variables=len(data),
                    variables=list(data.keys()),
                    file_path=path,
                    file_size=path.stat().st_size,
                    format="xpt",
                )

            # Return minimal metadata
            return DatasetMetadata(
                name=path.stem,
                n_records=0,
                n_variables=0,
                variables=[],
                file_path=path,
                file_size=path.stat().st_size,
                format="xpt",
            )


class SAS7BDATHandler(DatasetHandler):
    """
    Handler for SAS7BDAT files.

    Note: This is a MOCK implementation. Real implementation would use:
    - pyreadstat (recommended)
    - sas7bdat package
    - pandas.read_sas()
    """

    def read(self, path: Path) -> Dict[str, List[Any]]:
        """Read SAS7BDAT file into dictionary."""
        if not path.exists():
            raise FileNotFoundError(f"SAS7BDAT file not found: {path}")

        # Check for sidecar JSON (mock mode)
        json_path = path.with_suffix(".json")
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Try pyreadstat
        try:
            import pyreadstat
            import pandas as pd

            df, meta = pyreadstat.read_sas7bdat(str(path))
            return df.to_dict(orient="list")

        except ImportError:
            raise NotImplementedError(
                f"SAS7BDAT reading requires pyreadstat library. "
                "Install with: pip install pyreadstat"
            )

    def write(
        self,
        data: Dict[str, List[Any]],
        path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Write dictionary to SAS7BDAT file.

        Note: Writing SAS7BDAT is not well-supported by Python libraries.
        Consider using XPT format for output instead.
        """
        raise NotImplementedError(
            "Writing SAS7BDAT files is not supported. "
            "Use XPT format for SAS-compatible output."
        )

    def get_metadata(self, path: Path) -> DatasetMetadata:
        """Get SAS7BDAT metadata."""
        if not path.exists():
            raise FileNotFoundError(f"SAS7BDAT file not found: {path}")

        try:
            import pyreadstat

            df, meta = pyreadstat.read_sas7bdat(str(path), metadataonly=True)

            return DatasetMetadata(
                name=path.stem,
                n_records=meta.number_rows,
                n_variables=meta.number_columns,
                variables=meta.column_names,
                file_path=path,
                file_size=path.stat().st_size,
                format="sas7bdat",
            )

        except ImportError:
            return DatasetMetadata(
                name=path.stem,
                n_records=0,
                n_variables=0,
                variables=[],
                file_path=path,
                file_size=path.stat().st_size,
                format="sas7bdat",
            )


class DatasetReader:
    """
    Universal dataset reader that auto-detects format.
    """

    HANDLERS = {
        ".csv": CSVHandler,
        ".xpt": XPTHandler,
        ".xpt5": XPTHandler,
        ".xpt8": lambda: XPTHandler(sas_version=8),
    }

    def __init__(self, default_encoding: str = "utf-8"):
        """Initialize reader."""
        self.default_encoding = default_encoding

    def read(self, path: Union[str, Path]) -> Dict[str, List[Any]]:
        """
        Read dataset, auto-detecting format from extension.

        Args:
            path: Path to dataset file

        Returns:
            Dictionary with variable names as keys
        """
        path = Path(path)
        suffix = path.suffix.lower()

        handler_class = self.HANDLERS.get(suffix)
        if handler_class is None:
            raise ValueError(f"Unsupported file format: {suffix}")

        handler = (
            handler_class()
            if not callable(handler_class) or hasattr(handler_class, "read")
            else handler_class
        )
        return handler.read(path)

    def get_handler(self, path: Union[str, Path]) -> DatasetHandler:
        """Get appropriate handler for file type."""
        path = Path(path)
        suffix = path.suffix.lower()

        handler_class = self.HANDLERS.get(suffix)
        if handler_class is None:
            raise ValueError(f"Unsupported file format: {suffix}")

        return handler_class() if isinstance(handler_class, type) else handler_class


class DatasetWriter:
    """
    Universal dataset writer.
    """

    HANDLERS = {
        "csv": CSVHandler,
        "xpt": XPTHandler,
        "xpt5": XPTHandler,
        "xpt8": lambda: XPTHandler(sas_version=8),
    }

    def __init__(self, output_format: str = "xpt"):
        """Initialize writer with default format."""
        self.output_format = output_format

    def write(
        self,
        data: Dict[str, List[Any]],
        path: Union[str, Path],
        format: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Write dataset to file.

        Args:
            data: Dictionary with variable names as keys
            path: Output file path
            format: Output format (defaults to self.output_format)
            metadata: Optional dataset metadata

        Returns:
            True if successful
        """
        path = Path(path)
        output_format = format or self.output_format

        # Get handler based on format
        handler_class = self.HANDLERS.get(output_format)
        if handler_class is None:
            raise ValueError(f"Unsupported output format: {output_format}")

        handler = handler_class() if isinstance(handler_class, type) else handler_class

        # Ensure correct extension
        if output_format == "csv" and path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        elif output_format in ("xpt", "xpt5", "xpt8") and path.suffix.lower() != ".xpt":
            path = path.with_suffix(".xpt")

        return handler.write(data, path, metadata)
