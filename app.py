import io
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from rapidfuzz.distance import JaroWinkler

DATABASE = "ehr_demo.db"
PATIENT_FIELDS = [
    "given_name",
    "family_name",
    "dob",
    "sex",
    "phone",
    "email",
    "address",
    "postal_code",
    "national_id",
]
QUALITY_WEIGHTS = {
    "given_name": 15,
    "family_name": 15,
    "dob": 20,
    "sex": 5,
    "phone": 10,
    "email": 10,
    "address": 10,
    "postal_code": 5,
    "national_id": 10,
}
MATCH_WEIGHTS = {
    "given_name": 15,
    "family_name": 15,
    "dob": 20,
    "phone": 10,
    "email": 10,
    "address": 10,
    "postal_code": 5,
    "national_id": 10,
}

st.set_page_config(
    page_title="EHR Data Quality Demo",
    page_icon="🏥",
    layout="wide",
)


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_system TEXT NOT NULL,
                    source_patient_id TEXT NOT NULL,
                    given_name TEXT,
                    family_name TEXT,
                    dob TEXT,
                    sex TEXT,
                    phone TEXT,
                    email TEXT,
                    address TEXT,
                    postal_code TEXT,
                    national_id TEXT,
                    UNIQUE(source_system, source_patient_id)
                )
            """)


def clean_text(value):
    if value is None or (isinstance(value, (float, np.floating)) and np.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def normalize_phone(value):
    return re.sub(r"\D", "", clean_text(value))[-10:]


def normalize_text(value):
    return clean_text(value)


def similarity(left, right):
    left = normalize_text(left)
    right = normalize_text(right)
    if not left or not right:
        return -1.0
    return JaroWinkler.normalized_similarity(left, right)


def exact_match(left, right, normalizer=normalize_text):
    left = normalizer(left)
    right = normalizer(right)
    if not left or not right:
        return -1.0
    return float(left == right)


def assess_quality(record):
    issues = []
    present_weight = 0

    for field, weight in QUALITY_WEIGHTS.items():
        if clean_text(record.get(field)):
            present_weight += weight
        else:
            issues.append({"Field": field, "Problem": "Missing value"})

    invalid_count = 0
    dob = clean_text(record.get("dob"))
    if dob:
        try:
            birth_date = date.fromisoformat(dob[:10])
            age = (date.today() - birth_date).days / 365.2425
            if birth_date > date.today() or age > 120:
                raise ValueError
        except ValueError:
            invalid_count += 1
            issues.append({"Field": "dob", "Problem": "Invalid or unrealistic date"})

    email = clean_text(record.get("email"))
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        invalid_count += 1
        issues.append({"Field": "email", "Problem": "Invalid email format"})

    completeness = 100 * present_weight / sum(QUALITY_WEIGHTS.values())
    validity = max(0, 100 - 25 * invalid_count)
    score = round(0.7 * completeness + 0.3 * validity, 1)
    return score, issues


def address_similarity(left, right):
    return similarity(left, right)


def build_features(left, right):
    return {
        "given_name": similarity(left.get("given_name"), right.get("given_name")),
        "family_name": similarity(left.get("family_name"), right.get("family_name")),
        "dob": exact_match(left.get("dob"), right.get("dob")),
        "phone": exact_match(left.get("phone"), right.get("phone"), normalize_phone),
        "email": exact_match(left.get("email"), right.get("email")),
        "address": address_similarity(left.get("address"), right.get("address")),
        "postal_code": exact_match(left.get("postal_code"), right.get("postal_code")),
        "national_id": exact_match(left.get("national_id"), right.get("national_id")),
    }


def load_patients():
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM patients ORDER BY id"
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def import_csv(uploaded_file):
    frame = pd.read_csv(io.BytesIO(uploaded_file.getvalue()), dtype=str).fillna("")
    available_fields = set(frame.columns)
    patient_columns = available_fields.intersection(PATIENT_FIELDS)
    if not patient_columns:
        raise ValueError(
            "CSV must include at least one patient field, such as given_name or dob."
        )

    default_source = Path(uploaded_file.name).stem or "csv_upload"
    rows = []
    for index, row in frame.iterrows():
        values = {
            "source_system": str(row.get("source_system", "")).strip() or default_source,
            "source_patient_id": str(row.get("source_patient_id", "")).strip()
            or str(index + 1),
        }
        for field in PATIENT_FIELDS:
            value = str(row.get(field, "")).strip()
            values[field] = value or None
        rows.append(values)

    columns = ["source_system", "source_patient_id", *PATIENT_FIELDS]
    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(columns)
    with closing(get_connection()) as connection:
        with connection:
            before = connection.total_changes
            connection.executemany(
                f"INSERT OR IGNORE INTO patients ({column_names}) "
                f"VALUES ({placeholders})",
                [[row[column] for column in columns] for row in rows],
            )
            inserted = connection.total_changes - before
    return inserted, len(rows) - inserted


def find_potential_matches(records, threshold):
    matches = []
    for left_index in range(len(records)):
        left = records.iloc[left_index]
        for right_index in range(left_index + 1, len(records)):
            right = records.iloc[right_index]
            if left["source_system"] == right["source_system"]:
                continue

            features = build_features(left, right)
            comparable = [
                (name, value, MATCH_WEIGHTS[name])
                for name, value in features.items()
                if value >= 0
            ]
            if not comparable:
                continue

            weight_total = sum(weight for _, _, weight in comparable)
            score = 100 * sum(value * weight for _, value, weight in comparable) / weight_total
            if score >= threshold:
                matches.append({
                    "Patient 1": f'{left["given_name"]} {left["family_name"]}'.strip(),
                    "Source 1": left["source_system"],
                    "Patient 2": f'{right["given_name"]} {right["family_name"]}'.strip(),
                    "Source 2": right["source_system"],
                    "Match score": round(score, 1),
                    "Agreeing fields": ", ".join(
                        name for name, value, _ in comparable if value >= 0.85
                    ),
                })
    return pd.DataFrame(matches).sort_values(
        "Match score", ascending=False
    ) if matches else pd.DataFrame(
        columns=["Patient 1", "Source 1", "Patient 2", "Source 2", "Match score", "Agreeing fields"]
    )


initialize_database()
st.title("EHR Data Quality Demo")
st.caption("Import patient records, review data quality, and identify possible cross-system duplicates.")

import_tab, records_tab, quality_tab, matches_tab = st.tabs(
    ["Import CSV", "Patient records", "Data quality", "Potential matches"]
)

with import_tab:
    st.write("Upload a CSV with patient data. Column names should match the fields below.")
    st.code(", ".join(["source_system", "source_patient_id", *PATIENT_FIELDS]))
    st.caption(
        "If source_system or source_patient_id is omitted, the filename and row number are used."
    )
    uploaded_file = st.file_uploader("Choose a patient CSV file", type=["csv"])
    if uploaded_file and st.button("Import records"):
        try:
            inserted, skipped = import_csv(uploaded_file)
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
            st.error(f"Could not import CSV: {error}")
        else:
            st.success(f"Imported {inserted} records. Skipped {skipped} duplicate records.")

records = load_patients()

with records_tab:
    st.subheader("Patient records")
    if records.empty:
        st.info("No records yet. Import a CSV to get started.")
    else:
        st.dataframe(records, use_container_width=True, hide_index=True)

with quality_tab:
    st.subheader("Record quality")
    if records.empty:
        st.info("Import patient records to see quality scores.")
    else:
        scores_and_issues = records.apply(
            lambda record: assess_quality(record), axis=1
        )
        quality = records[["id", "source_system", "source_patient_id"]].copy()
        quality["Quality score"] = [item[0] for item in scores_and_issues]
        quality["Issues"] = [
            "; ".join(f'{issue["Field"]}: {issue["Problem"]}' for issue in item[1])
            for item in scores_and_issues
        ]
        st.metric("Average quality score", f'{quality["Quality score"].mean():.1f}%')
        st.dataframe(quality, use_container_width=True, hide_index=True)

with matches_tab:
    st.subheader("Potential cross-system duplicates")
    threshold = st.slider("Minimum match score", min_value=50, max_value=100, value=80)
    if records.empty or records["source_system"].nunique() < 2:
        st.info("Import records from at least two source systems to compare patients.")
    else:
        matches = find_potential_matches(records, threshold)
        if matches.empty:
            st.info("No potential matches found at this score.")
        else:
            st.dataframe(matches, use_container_width=True, hide_index=True)
