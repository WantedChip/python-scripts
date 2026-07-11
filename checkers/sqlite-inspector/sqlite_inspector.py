"""SQLite Database Inspector.

A utility to audit SQLite databases, summarizing tables, indexes, null patterns,
duplicate rows, and highlighting potential schema/performance issues.
"""

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# pylint: disable=duplicate-code

logger = logging.getLogger("sqlite_inspector")


@dataclass
class ColumnMeta:
    """Metadata representing a single table column."""

    name: str
    data_type: str
    not_null: bool
    is_pk: bool
    null_percentage: float


@dataclass
class TableMeta:
    """Metadata representing a database table summary."""

    # pylint: disable=too-many-instance-attributes

    name: str
    row_count: int
    column_count: int
    columns: List[ColumnMeta]
    primary_keys: List[str]
    index_count: int
    foreign_key_count: int
    duplicate_rows: int
    has_pk: bool


@dataclass
class SchemaIssue:
    """Representation of an identified schema or design issue."""

    table: str
    issue_type: str  # 'NO_PK', 'UNINDEXED_FK', 'REDUNDANT_INDEX', 'FK_TYPE_MISMATCH'
    severity: str  # 'WARNING', 'INFO'
    details: str


@dataclass
class InspectorReport:
    """Complete SQLite database audit summary report."""

    sqlite_version: str
    journal_mode: str
    db_size_bytes: int
    tables: List[TableMeta]
    issues: List[SchemaIssue]


def setup_logging(verbose: bool) -> None:
    """Configure logging format and output level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def get_db_info(cursor: sqlite3.Cursor, db_path: Path) -> Tuple[str, str, int]:
    """Gather basic database system metrics."""
    cursor.execute("SELECT sqlite_version()")
    sqlite_version = cursor.fetchone()[0]

    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]

    db_size = db_path.stat().st_size if db_path.exists() else 0
    return sqlite_version, journal_mode, db_size


def get_table_duplicate_rows(cursor: sqlite3.Cursor, table: str, row_count: int) -> int:
    """Determine the count of exact duplicate rows in the table."""
    if row_count == 0:
        return 0

    try:
        # Get count of unique rows
        query = f'SELECT COUNT(*) FROM (SELECT DISTINCT * FROM "{table}")'  # nosec B608
        cursor.execute(query)
        unique_rows = int(cursor.fetchone()[0])
        return max(0, row_count - unique_rows)
    except sqlite3.Error as err:
        logger.warning(
            "Could not calculate duplicate rows for table %s: %s", table, err
        )
        return 0


def get_column_null_pct(
    cursor: sqlite3.Cursor, table: str, column: str, row_count: int
) -> float:
    """Calculate the percentage of null values in a column."""
    if row_count == 0:
        return 0.0

    try:
        query = f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'  # nosec B608
        cursor.execute(query)
        null_count = int(cursor.fetchone()[0])

        return round((null_count / row_count) * 100.0, 2)

    except sqlite3.Error as err:
        logger.warning(
            "Could not calculate NULL statistics for %s.%s: %s", table, column, err
        )
        return 0.0


def check_schema_issues(cursor: sqlite3.Cursor, tables: List[str]) -> List[SchemaIssue]:
    """Scan database schema metadata to identify design flaws and performance risks."""
    # pylint: disable=too-many-locals, too-many-branches
    issues = []

    # Map tables to their columns: {table_name: {col_name: col_type}}
    table_cols: Dict[str, Dict[str, str]] = {}
    table_pks: Dict[str, List[str]] = {}

    for table in tables:
        cursor.execute(f'PRAGMA table_info("{table}")')  # nosec
        cols = cursor.fetchall()
        table_cols[table] = {col[1]: col[2].upper() for col in cols}
        table_pks[table] = [col[1] for col in cols if col[5] > 0]

        # 1. Check for Missing Primary Keys
        if not table_pks[table]:
            issues.append(
                SchemaIssue(
                    table=table,
                    issue_type="NO_PK",
                    severity="WARNING",
                    details=f"Table '{table}' has no defined Primary Key column.",
                )
            )

    for table in tables:
        # Load indexes
        cursor.execute(f'PRAGMA index_list("{table}")')  # nosec
        indexes = cursor.fetchall()
        indexed_cols = set()

        index_details = []
        for idx in indexes:
            idx_name = idx[1]
            cursor.execute(f'PRAGMA index_info("{idx_name}")')  # nosec
            idx_cols = [c[2] for c in cursor.fetchall()]
            index_details.append((idx_name, idx_cols))
            if idx_cols:
                indexed_cols.add(idx_cols[0])  # Track leading index columns

        # 2. Check for Redundant Indexes
        # E.g. composite index [col_A, col_B] renders standalone index
        # [col_A] redundant.
        for idx_name, idx_cols in index_details:
            for other_name, other_cols in index_details:
                if idx_name == other_name:
                    continue
                # If idx_cols is a prefix of other_cols
                if (
                    len(idx_cols) < len(other_cols)
                    and other_cols[: len(idx_cols)] == idx_cols
                ):
                    issues.append(
                        SchemaIssue(
                            table=table,
                            issue_type="REDUNDANT_INDEX",
                            severity="INFO",
                            details=(
                                f"Index '{idx_name}' ({idx_cols}) is redundant "
                                f"because index '{other_name}' ({other_cols}) "
                                f"covers it."
                            ),
                        )
                    )

        # 3. Check Foreign Keys
        cursor.execute(f'PRAGMA foreign_key_list("{table}")')  # nosec
        fk_list = cursor.fetchall()
        for fk in fk_list:
            fk_col = fk[3]
            ref_table = fk[2]
            ref_col = fk[4]

            # A. Check Unindexed Foreign Keys
            if fk_col not in indexed_cols and fk_col not in table_pks[table]:
                issues.append(
                    SchemaIssue(
                        table=table,
                        issue_type="UNINDEXED_FK",
                        severity="WARNING",
                        details=(
                            f"Foreign Key column '{fk_col}' referencing "
                            f"table '{ref_table}' is not indexed. "
                            f"This may cause query slowdowns."
                        ),
                    )
                )

            # B. Check Type Mismatches across Foreign Keys
            if ref_table in table_cols:
                local_type = table_cols[table].get(fk_col, "")
                ref_type = table_cols[ref_table].get(ref_col, "")
                if local_type != ref_type and (local_type and ref_type):
                    issues.append(
                        SchemaIssue(
                            table=table,
                            issue_type="FK_TYPE_MISMATCH",
                            severity="WARNING",
                            details=(
                                f"Foreign key '{fk_col}' ({local_type}) "
                                f"references '{ref_table}.{ref_col}' ({ref_type}). "
                                f"Types should match."
                            ),
                        )
                    )

    return issues


def inspect_db(db_path: Path) -> InspectorReport:
    """Analyze all tables, index metadata, and design constraints in the database."""
    # pylint: disable=too-many-locals

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        sqlite_version, journal_mode, db_size = get_db_info(cursor, db_path)

        # Retrieve tables
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_names = [row[0] for row in cursor.fetchall()]

        table_summaries = []
        for name in table_names:
            # Columns
            cursor.execute(f'PRAGMA table_info("{name}")')  # nosec
            cols = cursor.fetchall()

            # Row count
            cursor.execute(f'SELECT COUNT(*) FROM "{name}"')  # nosec
            row_count = cursor.fetchone()[0]

            col_metas = []
            pks = []
            for col in cols:
                col_name = col[1]
                data_type = col[2]
                not_null = bool(col[3])
                is_pk = bool(col[5] > 0)
                if is_pk:
                    pks.append(col_name)

                null_pct = get_column_null_pct(cursor, name, col_name, row_count)
                col_metas.append(
                    ColumnMeta(
                        name=col_name,
                        data_type=data_type,
                        not_null=not_null,
                        is_pk=is_pk,
                        null_percentage=null_pct,
                    )
                )

            # Indexes count
            cursor.execute(f'PRAGMA index_list("{name}")')  # nosec
            index_count = len(cursor.fetchall())

            # Foreign Keys count
            cursor.execute(f'PRAGMA foreign_key_list("{name}")')  # nosec
            fk_count = len(cursor.fetchall())

            # Duplicate rows count
            dup_rows = get_table_duplicate_rows(cursor, name, row_count)

            table_summaries.append(
                TableMeta(
                    name=name,
                    row_count=row_count,
                    column_count=len(col_metas),
                    columns=col_metas,
                    primary_keys=pks,
                    index_count=index_count,
                    foreign_key_count=fk_count,
                    duplicate_rows=dup_rows,
                    has_pk=len(pks) > 0,
                )
            )

        # Schema audit checks
        issues = check_schema_issues(cursor, table_names)

        return InspectorReport(
            sqlite_version=sqlite_version,
            journal_mode=journal_mode,
            db_size_bytes=db_size,
            tables=table_summaries,
            issues=issues,
        )

    finally:
        conn.close()


def print_terminal_report(report: InspectorReport) -> None:
    """Print the SQLite inspection audit report in human-readable tables."""
    sys.stdout.write("\n=== SQLite Database Inspection Report ===\n")
    sys.stdout.write(f"  SQLite Version: {report.sqlite_version}\n")
    sys.stdout.write(f"  Journal Mode:   {report.journal_mode}\n")
    sys.stdout.write(f"  Database Size:  {report.db_size_bytes:,} bytes\n")
    sys.stdout.write(f"  Total Tables:   {len(report.tables)}\n\n")

    if report.tables:
        _vulture_whitelist(report.tables[0])
    sys.stdout.write("--- Tables Summary ---\n")

    tbl_fmt = (
        "  - {:<20} : {:>8} rows, {:>3} cols, {:>3} indexes, "
        "{:>3} FKs, {:>5} duplicates\n"
    )
    for t in report.tables:
        sys.stdout.write(
            tbl_fmt.format(
                t.name,
                t.row_count,
                t.column_count,
                t.index_count,
                t.foreign_key_count,
                t.duplicate_rows,
            )
        )

    sys.stdout.write("\n--- Null Patterns / Column Stats ---\n")
    col_fmt = "    * {:<15} ({:<10}): Null: {:>6}%\n"
    for t in report.tables:
        if t.row_count > 0:
            sys.stdout.write(f"  {t.name}:\n")
            for c in t.columns:
                sys.stdout.write(
                    col_fmt.format(c.name, c.data_type or "BLOB", c.null_percentage)
                )

    sys.stdout.write("\n--- Schema Issues & Recommendations ---\n")
    if not report.issues:
        sys.stdout.write(
            "  No schema issues identified. Database structure "
            "complies with standard best practices.\n"
        )
    else:
        issue_fmt = "  [{:<7}] Table '{:<15}' : {}\n"
        for issue in report.issues:
            sys.stdout.write(
                issue_fmt.format(
                    issue.severity,
                    issue.table,
                    issue.details,
                )
            )
    sys.stdout.write("\n==========================================\n")


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "SQLite Database Inspector — summarize tables, null patterns, "
            "duplicate data, and schema issues."
        )
    )

    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Path to SQLite database file."
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JSON report file path."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.input.exists():
        logger.error("SQLite database file not found: %s", args.input.as_posix())
        sys.exit(1)

    logger.info("Inspecting SQLite Database: %s", args.input.name)

    try:
        report = inspect_db(args.input)
    except sqlite3.Error as err:
        logger.error("SQLite Database Connection/Execution failed: %s", err)
        sys.exit(1)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(asdict(report), f, indent=2)
            logger.info(
                "Saved SQLite inspection JSON report to: %s", args.output.as_posix()
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to save JSON report: %s", err)
            sys.exit(1)
    else:
        print_terminal_report(report)


def _vulture_whitelist(meta: TableMeta) -> None:
    """Whitelist for Vulture to recognize dataclass attributes."""
    _ = meta.primary_keys
    _ = meta.has_pk


if __name__ == "__main__":
    main()
