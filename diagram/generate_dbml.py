"""Generate DBML from PostgreSQL without overwriting the exported diagram."""
import json
import os
from collections import defaultdict
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

import psycopg2


POSITIONS = {
    "roles": (0, 0), "users": (0, 1), "student_profiles": (0, 2), "instructor_profiles": (0, 3),
    "categories": (1, 0), "courses": (1, 1), "course_instructors": (1, 2), "course_prerequisites": (1, 3),
    "modules": (2, 0), "lessons": (2, 1), "materials": (2, 2), "assignments": (2, 3),
    "cohorts": (3, 0), "enrollments": (3, 1), "lesson_progress": (3, 2), "submissions": (3, 3),
    "certificates": (4, 0), "course_reviews": (4, 1), "audit_log": (4, 2),
}
LABELS = ["Користувачі", "Каталог курсів", "Навчальний вміст", "Процес навчання", "Результати та аудит"]
COLORS = ["#246b5c", "#375d9a", "#785336", "#74456f", "#525b65"]


def inspect_database(dsn):
    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                       a.attnotnull, a.attidentity, pg_get_expr(d.adbin, d.adrelid)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
                WHERE n.nspname = 'lms' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum
            """)
            tables = defaultdict(list)
            for table, name, kind, required, identity, default in cursor.fetchall():
                tables[table].append(dict(name=name, type=kind, required=required, identity=bool(identity), default=default))
            cursor.execute("""
                SELECT c.relname, k.contype, k.conname,
                    ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY AS x(num, pos)
                          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = x.num ORDER BY x.pos),
                    target.relname, pg_get_constraintdef(k.oid)
                FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_class target ON target.oid = k.confrelid
                WHERE n.nspname = 'lms' ORDER BY c.relname, k.conname
            """)
            constraints = cursor.fetchall()
            cursor.execute("""
                SELECT c.relname, a.attname, target.relname, ta.attname
                FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_class target ON target.oid = k.confrelid
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.conkey[1]
                JOIN pg_attribute ta ON ta.attrelid = target.oid AND ta.attnum = k.confkey[1]
                WHERE n.nspname = 'lms' AND k.contype = 'f' ORDER BY c.relname, a.attname
            """)
            references = cursor.fetchall()
            cursor.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'lms' ORDER BY tablename, indexname")
            indexes = cursor.fetchall()
    finally:
        connection.close()
    return dict(tables), constraints, references, indexes


def normalize_type(kind):
    return kind.replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz").replace(", ", ",")


def write_dbml(output, tables, constraints, references, indexes):
    primary = {(t, col) for t, kind, _, cols, _, _ in constraints if kind == "p" for col in cols}
    unique = {(t, cols[0]) for t, kind, _, cols, _, _ in constraints if kind == "u" and len(cols) == 1}
    lines = ["// Course management: generated from the installed schema.",
             "Project course_management {", "  database_type: 'PostgreSQL'", "}", ""]
    for table, columns in tables.items():
        lines.append("Table " + table + " {")
        for col in columns:
            flags = []
            if (table, col["name"]) in primary:
                flags.append("pk")
            if col["required"]:
                flags.append("not null")
            if col["identity"]:
                flags.append("increment")
            if (table, col["name"]) in unique:
                flags.append("unique")
            if col["default"] is not None:
                flags.append("default: `" + col["default"] + "`")
            suffix = " [" + ", ".join(flags) + "]" if flags else ""
            lines.append("  " + col["name"] + " " + normalize_type(col["type"]) + suffix)
        composites = [cols for t, kind, _, cols, _, _ in constraints if t == table and kind == "u" and len(cols) > 1]
        if composites:
            lines.append("  indexes {")
            for cols in composites:
                lines.append("    (" + ", ".join(cols) + ") [unique]")
            lines.append("  }")
        checks = [definition for t, kind, _, _, _, definition in constraints if t == table and kind == "c"]
        custom_indexes = [definition for t, name, definition in indexes if t == table and (name.startswith("ix_") or name.startswith("uq_"))]
        notes = checks + custom_indexes
        if notes:
            lines.append("  Note: '''" + "\n".join(notes) + "'''")
        lines.extend(["}", ""])
    for table, column, target, target_column in references:
        relation = "-" if (table, column) in primary or (table, column) in unique else ">"
        lines.append(f"Ref: {table}.{column} {relation} {target}.{target_column}")
    output.write_text("\n".join(lines) + "\n")


def write_svg(output, tables, constraints, references):
    primary = {(t, col) for t, kind, _, cols, _, _ in constraints if kind == "p" for col in cols}
    unique = {(t, cols[0]) for t, kind, _, cols, _, _ in constraints if kind == "u" and len(cols) == 1}
    foreign = {(t, col): target for t, col, target, _ in references}
    width, height, card_width, row_step = 2220, 1910, 370, 420
    svg = Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(width), height=str(height), viewBox=f"0 0 {width} {height}")
    SubElement(svg, "title").text = "Система управління навчальними курсами: 19 сутностей"
    SubElement(svg, "rect", width=str(width), height=str(height), fill="#f6f8fa")
    defs = SubElement(svg, "defs")
    marker = SubElement(defs, "marker", id="arrow", markerWidth="8", markerHeight="8", refX="7", refY="4", orient="auto")
    SubElement(marker, "path", d="M0 0 L8 4 L0 8 Z", fill="#7b8794")

    def text(x, y, value, size=13, fill="#253342", weight="normal", parent=svg):
        node = SubElement(parent, "text", x=str(x), y=str(y), fill=fill,
                          **{"font-family": "Arial, sans-serif", "font-size": str(size), "font-weight": weight})
        node.text = value
        return node

    text(40, 45, "Система управління навчальними курсами", 29, weight="bold")
    text(40, 75, "PostgreSQL  |  19 таблиць  |  PK — первинний ключ; FK — зовнішній; UQ — унікальність", 15)
    text(40, 100, "Стрілка: FK → батьківська таблиця. Зв’язки аудиту з users указані в полях; усі зв’язки є у DBML.", 14)
    for col, label in enumerate(LABELS):
        text(40 + col * 435, 140, label, 18, COLORS[col], "bold")

    def box(table):
        col, row = POSITIONS[table]
        return 40 + col * 435, 170 + row * row_step, card_width, 56 + len(tables[table]) * 23

    # Службові посилання updated_by не дублюємо стрілками: вони підписані біля полів.
    for index, (table, column, target, _) in enumerate(references):
        if column in {"updated_by", "changed_by", "issued_by", "graded_by"} or table == target:
            continue
        x1, y1, w1, h1 = box(table)
        x2, y2, w2, h2 = box(target)
        if x1 == x2:
            start, end = (x1 + w1, y1 + 22), (x2 + w2, y2 + 22)
            lane = x1 + w1 + 15 + (index % 3) * 9
            path = f"M{start[0]} {start[1]} H{lane} V{end[1]} H{end[0]}"
        else:
            sx = x1 if x1 > x2 else x1 + w1
            ex = x2 + w2 if x1 > x2 else x2
            sy, ey = y1 + 27, y2 + 27
            middle = (sx + ex) / 2
            path = f"M{sx} {sy} H{middle} V{ey} H{ex}"
        SubElement(svg, "path", d=path, fill="none", stroke="#98a4b0", **{"stroke-width": "1.3", "marker-end": "url(#arrow)"})

    for table, columns in tables.items():
        x, y, w, h = box(table)
        group = SubElement(svg, "g")
        SubElement(group, "rect", x=str(x), y=str(y), width=str(w), height=str(h), rx="4", fill="white", stroke="#cbd4dc")
        SubElement(group, "rect", x=str(x), y=str(y), width=str(w), height="37", fill=COLORS[POSITIONS[table][0]])
        text(x + 12, y + 25, table, 17, "white", "bold", group)
        for pos, column in enumerate(columns):
            name = column["name"]
            flags = []
            if (table, name) in primary:
                flags.append("PK")
            if (table, name) in foreign:
                flags.append("FK")
            if (table, name) in unique:
                flags.append("UQ")
            label = name + (" [" + ",".join(flags) + "]" if flags else "")
            if name in {"updated_by", "changed_by", "issued_by", "graded_by"}:
                label += " → " + foreign[(table, name)]
            text(x + 12, y + 59 + pos * 23, label, 12, parent=group)
            kind = normalize_type(column["type"])
            if len(kind) > 16:
                kind = kind[:16]
            node = text(x + w - 12, y + 59 + pos * 23, kind + (" *" if column["required"] else ""), 11, "#586979", parent=group)
            node.set("text-anchor", "end")
            SubElement(node, "title").text = normalize_type(column["type"])
    text(40, 1870, "* — NOT NULL. Soft delete: users, categories, courses, assignments. updated_at / updated_by заповнюють тригери.", 14)
    ElementTree(svg).write(output, encoding="unicode", xml_declaration=True)


def main():
    target = Path(__file__).resolve().parent
    tables, constraints, references, indexes = inspect_database(os.environ.get("LMS_DSN", "dbname=course_management host=localhost"))
    if set(tables) != set(POSITIONS):
        raise ValueError("Schema differs from the expected 19 tables")
    write_dbml(target / "schema.dbml", tables, constraints, references, indexes)
    (target / "schema_metadata.json").write_text(json.dumps(dict(tables=tables, constraints=constraints, references=references, indexes=indexes), ensure_ascii=False, indent=2) + "\n")
    print("Generated schema.dbml:", len(tables), "tables,", len(references), "foreign keys")


if __name__ == "__main__":
    main()
