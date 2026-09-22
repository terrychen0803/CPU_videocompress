#!/usr/bin/env python3
import argparse
import json
import sqlite3
from pathlib import Path


KEYWORDS = (
    "cpu",
    "event",
    "sample",
    "sched",
    "switch",
    "thread",
    "process",
    "metric",
    "pmu",
    "composite",
)


def parse_args():
    p = argparse.ArgumentParser(
        description="Inspect an Nsight Systems SQLite export before writing a schema-specific extractor."
    )
    p.add_argument("sqlite_file")
    p.add_argument(
        "--json-out",
        help="Optional path for a JSON schema inventory.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    db = Path(args.sqlite_file)
    if not db.exists():
        raise SystemExit(f"File not found: {db}")

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()

    tables = [
        row[0]
        for row in cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    ]

    inventory = {}
    for table in tables:
        quoted = table.replace('"', '""')
        cols = [
            {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": row[3],
                "default": row[4],
                "pk": row[5],
            }
            for row in cur.execute(f'PRAGMA table_info("{quoted}")')
        ]
        try:
            count = cur.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
        except sqlite3.DatabaseError:
            count = None

        inventory[table] = {
            "row_count": count,
            "columns": cols,
        }

    con.close()

    print(f"SQLite: {db}")
    print(f"Tables: {len(tables)}")
    print()

    relevant = []
    for table in tables:
        names = " ".join(
            [table] + [c["name"] for c in inventory[table]["columns"]]
        ).lower()
        if any(k in names for k in KEYWORDS):
            relevant.append(table)

    print("Candidate CPU/event/scheduling tables:")
    for table in relevant:
        cols = ", ".join(c["name"] for c in inventory[table]["columns"])
        print(f"- {table} ({inventory[table]['row_count']} rows)")
        print(f"  columns: {cols}")

    if not relevant:
        print("- none matched the generic keywords; inspect the full JSON inventory.")

    if args.json_out:
        out = Path(args.json_out)
    else:
        out = db.with_name(db.stem + "_schema_inventory.json")

    out.write_text(
        json.dumps(
            {
                "sqlite_file": str(db),
                "table_count": len(tables),
                "candidate_tables": relevant,
                "tables": inventory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print(f"Schema inventory written to: {out}")


if __name__ == "__main__":
    main()
